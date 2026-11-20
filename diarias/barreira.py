"""A barreira: o que o agente devolve só passa se cada dado tiver origem conferível.

Fica no código, não no prompt (regra de ouro do AGENTS.md). Confere a execução
contra o pedido que a aplicação tem em mãos e contra o texto que as ferramentas
de fato devolveram. Nada aqui chama o modelo. Os motivos da recusa servem ao log
e à medição; a tela mostra só a mensagem padrão.

O único ponto em que o modelo pode divergir de uma ferramenta é a antecedência:
urgência é julgamento sobre o texto, e o modelo pode considerá-la atendida desde
que marque exige_autorizacao_superior.
"""
import re
from dataclasses import dataclass, field

from agno.agent import RunOutput
from agno.run.base import RunStatus

from diarias.esquema import Instrucao

MENSAGEM_PADRAO = ("Não foi possível instruir este pedido automaticamente. "
                   "Ele foi devolvido para análise manual.")

CRITERIOS = ("cadastro", "dados_completos", "antecedencia", "prestacao_contas",
             "limite_mensal", "saldo_orcamentario")
CAMPOS_DE_DATA = ("data_pedido", "data_partida", "data_retorno")
FERRAMENTAS_CONHECIDAS = {"consultar_servidor", "consultar_historico_diarias",
                          "calcular_diarias", "consultar_saldo_diarias"}

MATRICULA = re.compile(r"\b\d{6}\b")
DATA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
CADASTRO_OK = re.compile(r"Cadastro confere: matrícula (\d+),.*grupo da diária (\w), unidade (\w+) ")
QUANTIDADE = re.compile(r"Quantidade: ([\d.]+) ")
VALOR = re.compile(r"= R\$ ([\d.]+) \(Anexo I\)")


@dataclass
class Veredito:
    aprovada: bool
    motivos: list[str] = field(default_factory=list)


def _permitidos(pedido: dict, complementacao: dict | None) -> tuple[set[str], set[str]]:
    """Matrículas e datas que podem aparecer: as do pedido e as escritas na complementação."""
    matriculas = {str(pedido["matricula"])}
    datas = {str(pedido[c]) for c in CAMPOS_DE_DATA if pedido.get(c)}
    if complementacao:
        texto = str(complementacao.get("texto", ""))
        matriculas |= set(MATRICULA.findall(texto))
        datas |= set(DATA.findall(texto))
    return matriculas, datas


def _ultimo_resultado(resposta: RunOutput, nome: str) -> tuple[dict, str] | None:
    """Argumentos e texto da última chamada bem-sucedida a uma ferramenta."""
    for t in reversed(resposta.tools or []):
        if t.tool_name == nome and not t.tool_call_error:
            return t.tool_args or {}, t.result or ""
    return None


def conferir(resposta: RunOutput | None, pedido: dict, complementacao: dict | None = None) -> Veredito:
    motivos: list[str] = []

    if resposta is None or resposta.status != RunStatus.completed:
        return Veredito(False, [f"execução não concluída: {getattr(resposta, 'status', None)}"])
    instrucao = resposta.content
    if not isinstance(instrucao, Instrucao):
        return Veredito(False, ["saída não é um objeto Instrucao validado"])

    matriculas, datas = _permitidos(pedido, complementacao)

    # 1. Origem dos argumentos: nenhuma matrícula ou data fora do pedido ou da complementação.
    if instrucao.numero_pedido != pedido["numero"]:
        motivos.append(f"número do pedido trocado: {instrucao.numero_pedido}")
    if instrucao.matricula not in matriculas:
        motivos.append(f"matrícula da instrução fora do pedido: {instrucao.matricula}")
    for t in resposta.tools or []:
        args = t.tool_args or {}
        if t.tool_name not in FERRAMENTAS_CONHECIDAS:
            motivos.append(f"ferramenta desconhecida: {t.tool_name}")
        if "matricula" in args and str(args["matricula"]).strip() not in matriculas:
            motivos.append(f"{t.tool_name} consultou matrícula fora do pedido: {args['matricula']}")
        for campo in CAMPOS_DE_DATA:
            valor = args.get(campo)
            if valor and str(valor).strip() not in datas:
                motivos.append(f"{t.tool_name} usou {campo} fora do pedido: {valor}")

    # 2. Cada critério uma vez, e a recomendação como consequência das verificações.
    situacao = {v.criterio: v.situacao for v in instrucao.verificacoes}
    if sorted(v.criterio for v in instrucao.verificacoes) != sorted(CRITERIOS):
        motivos.append("verificações incompletas ou repetidas")
    diligencia = any(situacao.get(c) == "nao_atende" for c in ("cadastro", "dados_completos"))
    impedido = any(situacao.get(c) == "nao_atende" for c in CRITERIOS[2:])
    esperada = "diligencia" if diligencia else "nao_recomendado" if impedido else "apto_para_autorizacao"
    if instrucao.recomendacao != esperada:
        motivos.append(f"recomendação {instrucao.recomendacao} não decorre das verificações ({esperada})")

    cadastro = _ultimo_resultado(resposta, "consultar_servidor")
    historico = _ultimo_resultado(resposta, "consultar_historico_diarias")
    calculo = _ultimo_resultado(resposta, "calcular_diarias")
    saldo = _ultimo_resultado(resposta, "consultar_saldo_diarias")

    if instrucao.recomendacao == "diligencia":
        if instrucao.quantidade_diarias is not None or instrucao.valor_total is not None:
            motivos.append("diligência com quantidade ou valor calculados")
        if cadastro is None:
            motivos.append("diligência sem consulta ao cadastro")
        elif situacao.get("cadastro") == "atende" and not CADASTRO_OK.search(cadastro[1]):
            motivos.append("cadastro dado como atendido sem conferência na ferramenta")
        return Veredito(not motivos, motivos)

    # 3. Instrução de mérito: toda consulta feita, e os números iguais aos das ferramentas.
    if None in (cadastro, historico, calculo, saldo):
        return Veredito(False, [*motivos, "instrução de mérito sem as quatro consultas"])
    ok = CADASTRO_OK.search(cadastro[1])
    if not ok:
        return Veredito(False, [*motivos, "instrução de mérito sem cadastro conferido"])
    _, grupo, unidade = ok.groups()

    args_calc, texto_calc = calculo
    if str(args_calc.get("grupo", "")).strip().upper() != grupo:
        motivos.append(f"cálculo com grupo {args_calc.get('grupo')}, cadastro diz {grupo}")
    if str(args_calc.get("destino_uf", "")).strip().upper() != str(pedido["destino_uf"]).upper():
        motivos.append(f"cálculo com UF {args_calc.get('destino_uf')}, pedido diz {pedido['destino_uf']}")
    qtd, valor = QUANTIDADE.search(texto_calc), VALOR.search(texto_calc)
    if not (qtd and valor):
        return Veredito(False, [*motivos, "cálculo sem quantidade e valor legíveis"])
    if instrucao.quantidade_diarias != float(qtd.group(1)):
        motivos.append(f"quantidade {instrucao.quantidade_diarias} difere do cálculo {qtd.group(1)}")
    if instrucao.valor_total != float(valor.group(1)):
        motivos.append(f"valor {instrucao.valor_total} difere do cálculo {valor.group(1)}")

    args_saldo, texto_saldo = saldo
    if str(args_saldo.get("unidade", "")).strip().upper() != unidade:
        motivos.append(f"saldo consultado na unidade {args_saldo.get('unidade')}, cadastro diz {unidade}")
    if float(args_saldo.get("valor", -1)) != float(valor.group(1)):
        motivos.append(f"saldo consultado para {args_saldo.get('valor')}, cálculo diz {valor.group(1)}")

    # 4. Situação de cada critério numérico igual à da ferramenta.
    texto_hist = historico[1]
    pela_ferramenta = {
        "cadastro": "atende",
        "dados_completos": "atende",
        "prestacao_contas": "nao_atende" if "VENCIDA" in texto_hist else "atende",
        "limite_mensal": "nao_atende" if "LIMITE EXCEDIDO" in texto_hist else "atende",
        "saldo_orcamentario": "nao_atende" if "INSUFICIENTE" in texto_saldo else "atende",
    }
    for criterio, esperado in pela_ferramenta.items():
        if situacao.get(criterio) != esperado:
            motivos.append(f"{criterio} '{situacao.get(criterio)}', ferramenta indica '{esperado}'")

    curta = "NÃO atende" in texto_calc
    if not curta and situacao.get("antecedencia") != "atende":
        motivos.append("antecedência suficiente marcada como não atendida")
    aceita_por_urgencia = curta and situacao.get("antecedencia") == "atende"
    if aceita_por_urgencia and not impedido and not instrucao.exige_autorizacao_superior:
        motivos.append("antecedência curta aceita sem exigir autorização superior")
    if instrucao.exige_autorizacao_superior and not curta:
        motivos.append("autorização superior exigida sem antecedência curta")

    return Veredito(not motivos, motivos)
