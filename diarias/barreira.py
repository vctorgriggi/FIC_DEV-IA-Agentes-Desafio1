"""A barreira: o que o agente devolve só passa se cada dado tiver origem conferível.

Fica no código, não no prompt (regra de ouro do AGENTS.md). Confere a execução
contra o pedido que a aplicação tem em mãos e contra o texto que as ferramentas
de fato devolveram. Nada aqui chama o modelo. Os motivos da recusa servem ao log
e à medição; a tela mostra só a mensagem padrão.

Cada dado é conferido no lugar em que foi usado, e não só pela presença no pedido:
a data de partida tem de ser a partida do pedido, a matrícula das consultas tem de
ser a que o cadastro conferiu, e uma diligência precisa de causa comprovada. Uma
complementação pode corrigir a matrícula e a data de retorno, como as do acervo,
e a correção substitui o valor do pedido; a data só vale como retorno quando o
texto fala em retorno. Outra correção não é reconhecida e o pedido cai na análise
manual. Complementação
com mais de uma data ou de uma matrícula não corrige nada, e a correção para um
nome que tem homônimo no cadastro também vai para a análise manual. O texto livre
(minuta, alertas, pendências, detalhes) não pode citar outra matrícula nem outro
servidor do cadastro.

O único julgamento que o modelo faz sem ferramenta que o confirme é a urgência:
ele pode considerar atendida a antecedência curta, desde que marque
exige_autorizacao_superior, e só quando nada mais impede o pedido. Deixar a
antecedência curta sem julgamento ("nao_verificado") é recusado.
"""
import re
from dataclasses import dataclass, field
from datetime import date

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
# a data só corrige o retorno colada ao verbo ("o retorno está previsto para …", "volto no dia 21"):
# até cinco palavras entre eles, sem pontuação e sem palavra que abra outra oração ou outro evento
DATA_DE_RETORNO = re.compile(
    r"(?:retorn|volt|regress)\w*"
    r"(?:\s+(?!(?:quando|que|ap[óo]s|depois|inici\w*|come[çc]\w*|parti\w*|sa[íi]d\w*)\b)[^\s,.;:]+){0,5}?"
    r"\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
MATRICULA_CORRIGIDA = re.compile(r"matr[íi]cula\D{0,40}?\b(\d{6})\b", re.IGNORECASE)
FALA_DE_RETORNO = re.compile(r"\b(?:retorn|volt|regress)\w*", re.IGNORECASE)
FALA_DE_OUTRO_CAMPO = re.compile(r"\b(?:partida|sa[íi]da|embarque|destino|munic[íi]pio|matr[íi]cula)\b", re.IGNORECASE)
MESES = {m: i for i, m in enumerate(("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"), 1)}
_MES = "(" + "|".join(MESES) + ")"
CADASTRO_OK = re.compile(r"Cadastro confere: matrícula (\d+),.*grupo da diária (\w), unidade (\w+) ")
QUANTIDADE = re.compile(r"Quantidade: ([\d.]+) ")
VALOR = re.compile(r"= R\$ ([\d.]+) \(Anexo I\)")
DATA_BR = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PERIODO_BR = re.compile(r"\b(\d{1,2})(?:/(\d{1,2}))? a (\d{1,2})/(\d{1,2})/(\d{4})\b")   # "12 a 14/10/2026"
PERIODO_EXTENSO = re.compile(rf"\b(\d{{1,2}}) a (\d{{1,2}}) de {_MES} de (\d{{4}})\b", re.IGNORECASE)
DATA_EXTENSO = re.compile(rf"\b(\d{{1,2}}) de {_MES}(?: de (\d{{4}}))?\b", re.IGNORECASE)
DIA_E_MES = re.compile(r"\b(\d{1,2})/(\d{1,2})\b(?!/)")
SO_O_DIA = re.compile(r"\bdia (\d{1,2})\b(?![/\d]| de )", re.IGNORECASE)
DINHEIRO = re.compile(r"R\$\s*(\d[\d.]*(?:,\d{1,2})?)")
QTD_DE_DIARIAS = re.compile(r"(\d+(?:[.,]\d+)?)\s+diárias?(\s+e\s+meia)?\b")
NUMERO = re.compile(r"\d[\d.]*(?:,\d+)?")


@dataclass
class Veredito:
    aprovada: bool
    motivos: list[str] = field(default_factory=list)


@dataclass
class Leitura:
    """O que a barreira leu da complementação: as correções e o que ela cita sem conseguir ler."""
    retorno: set[str]
    matricula: set[str]
    nao_lido: list[str]


def ler_complementacao(pedido: dict, complementacao: dict | None) -> Leitura:
    texto = str((complementacao or {}).get("texto", ""))
    try:
        referencia = date.fromisoformat(str(pedido.get("data_partida")))
    except ValueError:
        referencia = None
    normal = _datas_iso(texto, referencia)
    # Com mais de uma data (ou matrícula) no texto não há como saber qual é a correção: nenhuma vale.
    datas = set(DATA.findall(normal))
    retorno = set(DATA_DE_RETORNO.findall(normal)) if len(datas) == 1 else set()
    matriculas = set(MATRICULA_CORRIGIDA.findall(texto))
    matriculas = matriculas if len(matriculas) == 1 else set()
    nao_lido = []
    if FALA_DE_RETORNO.search(texto) and not retorno:
        nao_lido.append("retorno")
    for campo in {m.lower() for m in FALA_DE_OUTRO_CAMPO.findall(texto)}:
        if not (campo.startswith("matr") and matriculas):
            nao_lido.append(campo)
    return Leitura(retorno, matriculas, sorted(nao_lido))


def permitidos(pedido: dict, complementacao: dict | None) -> dict[str, set[str]]:
    """Por argumento de ferramenta, os valores aceitos: o do pedido ou, se houver, a correção escrita.

    A correção substitui o valor do pedido: aceitar os dois deixaria passar a complementação ignorada.
    """
    leitura = ler_complementacao(pedido, complementacao)
    retorno = {str(pedido["data_retorno"])} if pedido.get("data_retorno") else set()
    datas, matriculas = leitura.retorno, leitura.matricula
    return {
        "matricula": matriculas or {str(pedido["matricula"])},
        "nome_informado": {str(pedido["nome"]).strip()},
        "destino_uf": {str(pedido["destino_uf"]).strip().upper()},
        "data_pedido": {str(pedido["data_pedido"])},
        "data_partida": {str(pedido["data_partida"])},
        "data_retorno": datas or retorno,
    }


def _iso(ano, mes, dia) -> str:
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:   # 31/02 e afins: fica como está, e não casa com data nenhuma
        return f"{ano}-{int(mes):02d}-{int(dia):02d}?"


def _datas_iso(texto: str, referencia: date | None = None) -> str:
    """Reescreve as datas em português como AAAA-MM-DD, o formato das ferramentas e do pedido.

    Lê "12/11/2026", "12 de novembro de 2026" e os períodos "9 a 12/11/2026", "09/11 a 12/11/2026"
    e "9 a 12 de novembro de 2026". Com `referencia` (a partida, na complementação) lê também a data
    sem ano ("12/11", "12 de novembro") e o "dia 12", no mês da partida ou no seguinte.
    """
    def periodo(m):
        dia1, mes1, dia2, mes2, ano = m.groups()
        ano1 = int(ano) - 1 if mes1 and int(mes1) > int(mes2) else int(ano)
        return f"{_iso(ano1, mes1 or mes2, dia1)} a {_iso(ano, mes2, dia2)}"
    texto = PERIODO_BR.sub(periodo, texto)
    texto = PERIODO_EXTENSO.sub(lambda m: f"{_iso(m[4], MESES[m[3].lower()], m[1])} a "
                                          f"{_iso(m[4], MESES[m[3].lower()], m[2])}", texto)
    texto = DATA_BR.sub(lambda m: _iso(m[3], m[2], m[1]), texto)
    texto = DATA_EXTENSO.sub(lambda m: _iso(m[3] or (referencia.year if referencia else 0),
                                            MESES[m[2].lower()], m[1]) if m[3] or referencia else m[0], texto)
    if referencia:
        texto = DIA_E_MES.sub(lambda m: _iso(referencia.year, m[2], m[1]), texto)

        def so_o_dia(m):
            dia = int(m[1])
            mes, ano = (referencia.month, referencia.year) if dia >= referencia.day else (
                (referencia.month % 12) + 1, referencia.year + (referencia.month == 12))
            return _iso(ano, mes, dia)
        texto = SO_O_DIA.sub(so_o_dia, texto)
    return texto


def _numero(bruto: str) -> float | None:
    """Número escrito em português (9.250,00) ou como as ferramentas o escrevem (9250.00)."""
    s = bruto.rstrip(".")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):   # 9.250: separador de milhar
        s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _datas_citadas(texto: str) -> set[str]:
    return set(DATA.findall(_datas_iso(texto)))


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
    leitura = ler_complementacao(pedido, complementacao)
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

    # Texto que o conferente lê: não pode citar outro servidor nem matrícula que não esteja no pedido.
    # Citar o que o pedido traz é legítimo: o alerta sobre uma ordem embutida repete a matrícula dela.
    livre = " ".join([instrucao.minuta_despacho, *instrucao.alertas, *instrucao.pendencias,
                      *(v.detalhe for v in instrucao.verificacoes)])
    origem = " ".join([*(str(v) for v in pedido.values()), str((complementacao or {}).get("texto", ""))])
    for numero in set(MATRICULA.findall(livre)) - aceitos["matricula"] - set(MATRICULA.findall(origem)):
        motivos.append(f"texto da instrução cita a matrícula {numero}, que não é do pedido")
    for nome in {s["nome"] for s in carregar().servidores.values()} - aceitos["nome_informado"]:
        if nome in livre and nome not in origem:
            motivos.append(f"texto da instrução cita outro servidor: {nome}")
    # Valores em reais, quantidades de diárias e datas do texto também precisam ter origem: o
    # detalhe é o fundamento que o conferente lê, "como veio da ferramenta".
    # Só a última chamada válida de cada ferramenta conta: uma consulta extra com valor inventado não
    # pode tornar esse valor "conhecido".
    ultimas = [r[1] for nome in sorted(FERRAMENTAS_CONHECIDAS) if (r := _ultimo_resultado(resposta, nome))]
    fontes = " ".join([origem, _datas_iso(origem), *ultimas])
    conhecidos = {n for bruto in NUMERO.findall(fontes) if (n := _numero(bruto)) is not None}
    citados = [bruto for bruto in DINHEIRO.findall(livre)]
    citados += [f"{bruto} e meia" if meia else bruto for bruto, meia in QTD_DE_DIARIAS.findall(livre)]
    for bruto in citados:
        valor = _numero(bruto.removesuffix(" e meia"))
        if valor is not None and bruto.endswith(" e meia"):
            valor += 0.5
        if valor not in conhecidos:
            motivos.append(f"texto da instrução cita {bruto}, que nenhuma ferramenta nem o pedido trazem")
    datas_conhecidas = _datas_citadas(fontes) | {str(carregar().data_da_analise)}
    for data in sorted(_datas_citadas(livre) - datas_conhecidas):
        motivos.append(f"texto da instrução cita a data {data}, que nenhuma ferramenta nem o pedido trazem")

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
    if leitura.nao_lido:
        # a complementação corrige algo que a barreira não sabe ler: se o modelo aplicou ou ignorou a
        # correção, ela não tem como conferir, e o pedido vai para a análise manual
        motivos.append(f"complementação cita {', '.join(leitura.nao_lido)} sem correção que a barreira leia")
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
    if curta and situacao.get("antecedencia") not in ("atende", "nao_atende"):
        # sem julgar a urgência não há como derivar a recomendação nem o sinal de autorização
        motivos.append("antecedência curta sem julgamento da urgência")
    # O sinal decorre das verificações, como no gabarito: só quando a urgência foi aceita e nada
    # mais impede. A regra antiga só cobria a antecedência suficiente e deixou passar, na medição,
    # um 0107 com urgência negada e autorização exigida (resultados/etapa6_medicao_antes_da_correcao).
    exige = curta and situacao.get("antecedencia") == "atende" and not impedido
    if instrucao.exige_autorizacao_superior != exige:
        motivos.append(f"exige_autorizacao_superior {instrucao.exige_autorizacao_superior} não decorre das "
                       f"verificações ({exige})")

    return Veredito(not motivos, motivos)
