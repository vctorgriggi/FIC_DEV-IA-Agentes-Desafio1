"""As quatro ferramentas do agente: cada uma substitui uma consulta que o servidor faz à mão.

A docstring é a única parte que o modelo lê, então ela diz quando usar, o que
volta e o formato dos argumentos. Toda conta é feita aqui, nunca pelo modelo, e
nenhuma ferramenta devolve CPF ou e-mail. Argumento inválido volta como texto
explicando o formato esperado, para o modelo corrigir em vez de supor.
"""
from datetime import date

from diarias import regras
from diarias.dados import carregar

GRUPOS = ("A", "B", "C")
ROTULO_CLASSE = {"interior_mt": "interior de MT", "outra_uf": "outra UF",
                 "distrito_federal": "Distrito Federal"}  # rótulos do Anexo I


def _data(texto: str | None, campo: str) -> date | str:
    """Converte AAAA-MM-DD; devolve a mensagem de erro, como texto, quando não dá."""
    if not texto or not str(texto).strip():
        return f"{campo} não informada no pedido: dado obrigatório ausente (art. 9º, diligência)."
    try:
        return date.fromisoformat(str(texto).strip())
    except ValueError:
        return f"{campo} '{texto}' inválida: use o formato AAAA-MM-DD, como 2026-11-09."


def _periodo(data_partida: str, data_retorno: str | None) -> tuple[date, date] | str:
    partida, retorno = _data(data_partida, "Data de partida"), _data(data_retorno, "Data de retorno")
    for d in (partida, retorno):
        if isinstance(d, str):
            return d
    if retorno < partida:
        return f"Data de retorno {retorno} anterior à partida {partida}: confira as datas do pedido."
    return partida, retorno


def consultar_servidor(matricula: str, nome_informado: str) -> str:
    """Consulta o cadastro funcional e confere se a matrícula pertence a quem assinou o pedido.

    Use primeiro, antes de qualquer outra ferramenta. `matricula` é a do pedido, só
    algarismos, como 204317; `nome_informado` é o nome do solicitante exatamente como
    está no pedido. Devolve cargo, grupo da diária (A, B ou C), sigla da unidade de
    lotação e sede quando matrícula e nome conferem. Se a matrícula não existir ou for
    de outra pessoa, devolve só a divergência, sem dados do titular, e o pedido é de
    diligência (art. 9º): não calcule nada com essa matrícula.
    """
    mat = str(matricula).strip()
    servidor = carregar().servidores.get(mat)
    if servidor is None:
        return f"Matrícula {mat} não consta do cadastro funcional. Diligência (art. 9º)."
    if servidor["nome"] != str(nome_informado).strip():
        return (f"Matrícula {mat} não pertence a {nome_informado}: o cadastro registra outro servidor. "
                "Dados do titular não são devolvidos. Diligência (art. 9º).")
    unidade = carregar().unidades[servidor["unidade"]]["nome"]
    return (f"Cadastro confere: matrícula {mat}, {servidor['nome']}, {servidor['cargo']}, "
            f"grupo da diária {servidor['grupo_diaria']}, unidade {servidor['unidade']} ({unidade}), "
            f"sede {servidor['municipio_sede']}.")


def consultar_historico_diarias(matricula: str, data_partida: str, data_retorno: str) -> str:
    """Consulta prestações de contas pendentes e diárias já concedidas no mês da partida.

    Use depois de o cadastro conferir, com a matrícula só em algarismos, como 204317, e as
    datas do pedido no formato AAAA-MM-DD; se o cadastro divergir, não chame. Devolve se
    há prestação vencida (impede nova diária, art. 7º) ou pendente ainda no prazo (não
    impede), e a soma das diárias do mês com as pedidas contra o limite de 10 (art. 6º).
    As contas já vêm feitas, com a data da análise do órgão, e não com a data de hoje.
    """
    acervo, mat = carregar(), str(matricula).strip()
    periodo = _periodo(data_partida, data_retorno)
    if isinstance(periodo, str):
        return periodo
    partida, retorno = periodo

    linhas = []
    pendentes = regras.prestacoes_pendentes(acervo, mat)
    vencidas = [p for p in pendentes if p["vencida"]]
    no_prazo = [p for p in pendentes if not p["vencida"]]
    if vencidas:
        linhas.append("Prestação de contas VENCIDA: " + "; ".join(
            f"{p['pedido']}, retorno {p['data_retorno']}, prazo {p['prazo']}" for p in vencidas)
            + f". Impede nova diária (art. 7º). Data da análise: {acervo.data_da_analise}.")
    else:
        linhas.append("Sem prestação de contas vencida (art. 7º).")
    if no_prazo:
        linhas.append("Pendente ainda no prazo, não impede: " + "; ".join(
            f"{p['pedido']}, retorno {p['data_retorno']}, prazo {p['prazo']}" for p in no_prazo) + ".")

    mes = partida.isoformat()[:7]
    usadas = regras.diarias_no_mes(acervo, mat, mes)
    pedidas = regras.quantidade_diarias(partida, retorno)
    limite = float(acervo.tabela["limite_mensal_diarias"])
    total = usadas + pedidas
    situacao = "dentro do limite" if total <= limite else "LIMITE EXCEDIDO"
    linhas.append(f"Diárias em {mes}: {usadas:g} já concedidas + {pedidas:g} pedidas = {total:g}, "
                  f"limite {limite:g}: {situacao} (art. 6º).")
    return " ".join(linhas)


def calcular_diarias(grupo: str, destino_uf: str, data_pedido: str, data_partida: str,
                     data_retorno: str) -> str:
    """Calcula antecedência, quantidade e valor das diárias do pedido.

    Use depois do cadastro, com o grupo da diária que ele devolveu (A, B ou C) e, do
    pedido, a UF de destino com duas letras, como MT, DF ou RO, e as datas no formato
    AAAA-MM-DD. Devolve a antecedência em dias corridos contra o mínimo de 10 (art. 5º),
    a quantidade (art. 4º) e o valor unitário e total pelo Anexo I. Antecedência menor
    que o mínimo só é admissível em urgência real descrita na justificativa (art. 5º,
    § 1º); a autorização escrita do Secretário Adjunto é exigida nesse caso, mas sozinha
    não torna o pedido urgente (§ 2º). Isso você julga.
    """
    acervo = carregar()
    g = str(grupo).strip().upper()
    if g not in GRUPOS:
        return f"Grupo '{grupo}' inválido: use A, B ou C, como devolvido pelo cadastro."
    uf = str(destino_uf).strip().upper()
    if len(uf) != 2 or not uf.isalpha():
        return f"UF '{destino_uf}' inválida: use a sigla com duas letras, como MT, DF ou RO."
    pedido = _data(data_pedido, "Data do pedido")
    if isinstance(pedido, str):
        return pedido
    periodo = _periodo(data_partida, data_retorno)
    if isinstance(periodo, str):
        return periodo
    partida, retorno = periodo

    dias = regras.antecedencia_dias(pedido, partida)
    minimo = acervo.tabela["antecedencia_minima_dias"]
    if dias >= minimo:
        antecedencia = f"Antecedência de {dias} dias corridos, mínimo {minimo}: atende (art. 5º)."
    else:
        antecedencia = (f"Antecedência de {dias} dias corridos, mínimo {minimo}: NÃO atende, salvo "
                        "situação emergencial imprevisível descrita na justificativa (art. 5º, § 1º); "
                        "autorização escrita alegada não supre a falta de urgência.")
    qtd = regras.quantidade_diarias(partida, retorno)
    unitario, total = regras.valor_total(acervo, g, uf, qtd)
    classe = ROTULO_CLASSE[regras.classe_destino(uf)]
    return (f"{antecedencia} Quantidade: {qtd:g} diária(s) de {partida} a {retorno} (art. 4º). "
            f"Valor: {qtd:g} × R$ {unitario:.2f} (grupo {g}, {classe}) = R$ {total:.2f} (Anexo I).")


def consultar_saldo_diarias(unidade: str, valor: float) -> str:
    """Consulta o saldo da dotação de diárias de uma unidade e o compara com o valor pedido.

    Use depois de calcular o valor total das diárias. `unidade` é a sigla da
    unidade de lotação devolvida pelo cadastro, como CFF ou GAB; `valor` é o
    total em reais, com ponto decimal, como 980.0. Devolve o saldo disponível e
    a indicação de saldo suficiente ou insuficiente para o pedido.
    """
    unidades = carregar().unidades
    sigla = str(unidade).strip().upper()
    if sigla not in unidades:
        return f"Unidade '{unidade}' não localizada. Siglas válidas: {', '.join(unidades)}."
    saldo = unidades[sigla]["saldo_diarias"]
    if saldo >= float(valor):
        return f"Saldo da unidade {sigla}: R$ {saldo:.2f}. Saldo suficiente para R$ {float(valor):.2f} (art. 8º)."
    return (f"Saldo da unidade {sigla}: R$ {saldo:.2f}. Saldo INSUFICIENTE para R$ {float(valor):.2f}: "
            f"faltam R$ {float(valor) - saldo:.2f} (art. 8º).")


FERRAMENTAS = [consultar_servidor, consultar_historico_diarias, calcular_diarias, consultar_saldo_diarias]
