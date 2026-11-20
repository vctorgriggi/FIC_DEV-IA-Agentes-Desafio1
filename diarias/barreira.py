"""A barreira: o que o agente devolve só passa se cada dado tiver origem conferível.

Fica no código, não no prompt (regra de ouro do AGENTS.md). Confere a execução
contra o pedido que a aplicação tem em mãos e contra o texto que as ferramentas
de fato devolveram. Nada aqui chama o modelo. Os motivos da recusa servem ao log
e à medição; a tela mostra só a mensagem padrão.

Cada dado é conferido no lugar em que foi usado, e não só pela presença no pedido:
a data de partida tem de ser a partida do pedido, a matrícula das consultas tem de
ser a que o cadastro conferiu, e uma diligência precisa de causa comprovada. Uma
complementação pode corrigir a matrícula e a data de retorno, como as do acervo;
outra correção não é reconhecida e o pedido cai na análise manual.

O único julgamento que o modelo faz sem ferramenta que o confirme é a urgência:
ele pode considerar atendida a antecedência curta, desde que marque
exige_autorizacao_superior, e só quando nada mais impede o pedido.
"""
import re
from dataclasses import dataclass, field

from agno.agent import RunOutput
from agno.run.base import RunStatus

from diarias.dados import carregar
from diarias.esquema import Instrucao

MENSAGEM_PADRAO = ("Não foi possível instruir este pedido automaticamente. "
                   "Ele foi devolvido para análise manual.")

CRITERIOS = ("cadastro", "dados_completos", "antecedencia", "prestacao_contas",
             "limite_mensal", "saldo_orcamentario")
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


def permitidos(pedido: dict, complementacao: dict | None) -> dict[str, set[str]]:
    """Por argumento de ferramenta, os valores aceitos: o campo do pedido e a correção escrita."""
    texto = str((complementacao or {}).get("texto", ""))
    retorno = {str(pedido["data_retorno"])} if pedido.get("data_retorno") else set()
    # Com mais de uma data (ou matrícula) no texto não há como saber qual é a correção: nenhuma vale.
    datas, matriculas = set(DATA.findall(texto)), set(MATRICULA.findall(texto))
    datas = datas if len(datas) == 1 else set()
    matriculas = matriculas if len(matriculas) == 1 else set()
    return {
        "matricula": {str(pedido["matricula"])} | matriculas,
        "nome_informado": {str(pedido["nome"]).strip()},
        "destino_uf": {str(pedido["destino_uf"]).strip().upper()},
        "data_pedido": {str(pedido["data_pedido"])},
        "data_partida": {str(pedido["data_partida"])},
        "data_retorno": retorno | datas,
    }


def _ultimo_resultado(resposta: RunOutput, nome: str) -> tuple[dict, str] | None:
    """Argumentos e texto da última chamada bem-sucedida a uma ferramenta."""
    for t in reversed(resposta.tools or []):
        if t.tool_name == nome and not t.tool_call_error:
            return t.tool_args or {}, t.result or ""
    return None


def _normal(campo: str, valor) -> str:
    texto = str(valor).strip()
    return texto.upper() if campo == "destino_uf" else texto


def conferir(resposta: RunOutput | None, pedido: dict, complementacao: dict | None = None) -> Veredito:
    """Nunca lança: qualquer imprevisto na conferência vira recusa, e a tela mostra a mensagem padrão."""
    try:
        return _conferir(resposta, pedido, complementacao)
    except Exception as erro:  # saída em formato que a conferência não previu: recusar, não quebrar
        return Veredito(False, [f"conferência não concluída: {type(erro).__name__}"])


def _conferir(resposta: RunOutput | None, pedido: dict, complementacao: dict | None) -> Veredito:
    motivos: list[str] = []

    if resposta is None or resposta.status != RunStatus.completed:
        return Veredito(False, [f"execução não concluída: {getattr(resposta, 'status', None)}"])
    instrucao = resposta.content
    if not isinstance(instrucao, Instrucao):
        return Veredito(False, ["saída não é um objeto Instrucao validado"])

    aceitos = permitidos(pedido, complementacao)
    retorno_ausente = not aceitos["data_retorno"]

    # 1. Cada argumento no seu campo: valor do pedido ou da correção escrita na complementação.
    if instrucao.numero_pedido != pedido["numero"]:
        motivos.append(f"número do pedido trocado: {instrucao.numero_pedido}")
    usados: dict[str, set[str]] = {}
    for t in resposta.tools or []:
        if t.tool_name not in FERRAMENTAS_CONHECIDAS:
            motivos.append(f"ferramenta desconhecida: {t.tool_name}")
        for campo, valor in (t.tool_args or {}).items():
            if campo not in aceitos:
                continue
            if valor in (None, "") or not str(valor).strip():
                # vazio só onde o pedido também não tem o dado: um vazio a mais devolve erro em vez de
                # histórico, e esconderia uma prestação vencida ou o limite mensal
                if aceitos[campo]:
                    motivos.append(f"{t.tool_name} usou {campo} vazio, mas o pedido o informa")
                continue
            normal = _normal(campo, valor)
            usados.setdefault(campo, set()).add(normal)
            if normal not in aceitos[campo]:
                motivos.append(f"{t.tool_name} usou {campo}={valor}, que não é o do pedido")
    for campo, valores in usados.items():
        if len(valores) > 1:
            motivos.append(f"chamadas com {campo} diferentes: {sorted(valores)}")

    # 2. Uma pessoa só: a matrícula que o cadastro conferiu vale para todas as consultas e para a instrução.
    cadastro = _ultimo_resultado(resposta, "consultar_servidor")
    conferido = CADASTRO_OK.search(cadastro[1]) if cadastro else None
    if instrucao.matricula not in aceitos["matricula"]:
        motivos.append(f"matrícula da instrução fora do pedido: {instrucao.matricula}")
    if conferido:
        efetiva = conferido.group(1)
        if instrucao.matricula != efetiva:
            motivos.append(f"instrução com matrícula {instrucao.matricula}, cadastro conferiu {efetiva}")
        for t in resposta.tools or []:
            usada = (t.tool_args or {}).get("matricula")
            if usada is not None and str(usada).strip() != efetiva:
                motivos.append(f"{t.tool_name} consultou {usada}, cadastro conferiu {efetiva}")
        nomes = [s["nome"] for s in carregar().servidores.values()]
        if efetiva != str(pedido["matricula"]) and nomes.count(str(pedido["nome"]).strip()) > 1:
            motivos.append("matrícula corrigida para um nome que outro servidor também tem: análise manual")

    # Texto que o conferente lê: não pode citar outro servidor nem matrícula fora do pedido.
    livre = " ".join([instrucao.minuta_despacho, *instrucao.alertas, *instrucao.pendencias,
                      *(v.detalhe for v in instrucao.verificacoes)])
    for numero in set(MATRICULA.findall(livre)) - aceitos["matricula"]:
        motivos.append(f"texto da instrução cita a matrícula {numero}, que não é do pedido")
    for nome in {s["nome"] for s in carregar().servidores.values()} - aceitos["nome_informado"]:
        if nome in livre:
            motivos.append(f"texto da instrução cita outro servidor: {nome}")

    # 3. Cada critério uma vez, e a recomendação e o sinal de autorização como consequência deles.
    situacao = {v.criterio: v.situacao for v in instrucao.verificacoes}
    if sorted(v.criterio for v in instrucao.verificacoes) != sorted(CRITERIOS):
        motivos.append("verificações incompletas ou repetidas")
    diligencia = any(situacao.get(c) == "nao_atende" for c in ("cadastro", "dados_completos"))
    impedido = any(situacao.get(c) == "nao_atende" for c in CRITERIOS[2:])
    esperada = "diligencia" if diligencia else "nao_recomendado" if impedido else "apto_para_autorizacao"
    if instrucao.recomendacao != esperada:
        motivos.append(f"recomendação {instrucao.recomendacao} não decorre das verificações ({esperada})")

    # 4. Diligência: a causa tem de estar no texto da ferramenta ou na falta real do dado.
    if instrucao.recomendacao == "diligencia":
        if instrucao.quantidade_diarias is not None or instrucao.valor_total is not None:
            motivos.append("diligência com quantidade ou valor calculados")
        if instrucao.exige_autorizacao_superior:
            motivos.append("diligência com autorização superior exigida")
        if cadastro is None:
            motivos.append("diligência sem consulta ao cadastro")
        elif situacao.get("cadastro") == ("nao_atende" if conferido else "atende"):
            motivos.append(f"cadastro '{situacao.get('cadastro')}', ferramenta indica "
                           f"'{'atende' if conferido else 'nao_atende'}'")
        if situacao.get("dados_completos") == "nao_atende" and not retorno_ausente:
            motivos.append("dados incompletos alegados com o pedido completo")
        if situacao.get("dados_completos") == "atende" and retorno_ausente:
            motivos.append("dados completos alegados sem data de retorno")
        # na diligência a análise de mérito não acontece (art. 9º): nada além do cadastro e dos dados
        for criterio in CRITERIOS[2:]:
            if situacao.get(criterio) != "nao_verificado":
                motivos.append(f"diligência com {criterio} '{situacao.get(criterio)}'; deveria ser 'nao_verificado'")
        if cadastro is not None and not conferido:
            outras = sorted({t.tool_name for t in resposta.tools or [] if t.tool_name != "consultar_servidor"})
            if outras:
                motivos.append(f"cadastro divergente, mas o agente ainda consultou {outras}")
        return Veredito(not motivos, motivos)

    # 5. Instrução de mérito: toda consulta feita, e os números iguais aos das ferramentas.
    historico = _ultimo_resultado(resposta, "consultar_historico_diarias")
    calculo = _ultimo_resultado(resposta, "calcular_diarias")
    saldo = _ultimo_resultado(resposta, "consultar_saldo_diarias")
    if None in (cadastro, historico, calculo, saldo):
        return Veredito(False, [*motivos, "instrução de mérito sem as quatro consultas"])
    if not conferido:
        return Veredito(False, [*motivos, "instrução de mérito sem cadastro conferido"])
    if retorno_ausente:
        return Veredito(False, [*motivos, "instrução de mérito sem data de retorno no pedido"])
    _, grupo, unidade = conferido.groups()
    if "Diárias em" not in historico[1]:
        return Veredito(False, [*motivos, "histórico sem resultado válido (a ferramenta devolveu erro)"])

    args_calc, texto_calc = calculo
    if str(args_calc.get("grupo", "")).strip().upper() != grupo:
        motivos.append(f"cálculo com grupo {args_calc.get('grupo')}, cadastro diz {grupo}")
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

    # 6. Situação de cada critério numérico igual à da ferramenta.
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
    # O sinal decorre das verificações, como no gabarito: só quando a urgência foi aceita e nada
    # mais impede. A regra antiga só cobria a antecedência suficiente e deixou passar, na medição,
    # um 0107 com urgência negada e autorização exigida (resultados/etapa6_medicao_antes_da_correcao).
    exige = curta and situacao.get("antecedencia") == "atende" and not impedido
    if instrucao.exige_autorizacao_superior != exige:
        motivos.append(f"exige_autorizacao_superior {instrucao.exige_autorizacao_superior} não decorre das "
                       f"verificações ({exige})")

    return Veredito(not motivos, motivos)
