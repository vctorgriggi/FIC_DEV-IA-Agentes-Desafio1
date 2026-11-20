"""Regras numéricas da IN SEMA nº 07/2026, sem modelo e sem formatação de texto.

Cada função reproduz a conta de `instruir_por_regra` em exemplos/gerar_dados.py,
que gera o gabarito. Divergir daqui é divergir do que a medição cobra.
"""
from datetime import date, timedelta

from diarias.dados import Acervo


def classe_destino(uf: str) -> str:
    """Classe do Anexo I: interior de MT, Distrito Federal ou outra UF."""
    uf = uf.strip().upper()
    if uf == "MT":
        return "interior_mt"
    if uf == "DF":
        return "distrito_federal"
    return "outra_uf"


def quantidade_diarias(partida: date, retorno: date) -> float:
    """Art. 4º: uma diária por pernoite e meia no retorno; sem pernoite, meia diária."""
    pernoites = (retorno - partida).days
    return 0.5 if pernoites == 0 else pernoites + 0.5


def somar_dias_uteis(inicio: date, dias: int) -> date:
    """Dias úteis de segunda a sexta, sem feriados: é como o gabarito conta (art. 7º)."""
    atual = inicio
    while dias:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            dias -= 1
    return atual


def antecedencia_dias(data_pedido: date, partida: date) -> int:
    """Art. 5º: dias corridos entre o protocolo e a partida."""
    return (partida - data_pedido).days


def valor_total(acervo: Acervo, grupo: str, uf: str, quantidade: float) -> tuple[float, float]:
    """Art. 3º e Anexo I: devolve (valor da diária inteira, total do pedido)."""
    unitario = acervo.tabela["valores"][grupo][classe_destino(uf)]
    return unitario, round(quantidade * unitario, 2)


def prestacoes_pendentes(acervo: Acervo, matricula: str) -> list[dict]:
    """Art. 7º: cada prestação pendente da matrícula, com o prazo e se já venceu na data da análise."""
    prazo_uteis = acervo.tabela["prazo_prestacao_dias_uteis"]
    saida = []
    for h in acervo.historico:
        if h["matricula"] == matricula and h["prestacao_contas"] == "pendente":
            prazo = somar_dias_uteis(date.fromisoformat(h["data_retorno"]), prazo_uteis)
            saida.append({"pedido": h["pedido"], "data_retorno": h["data_retorno"],
                          "prazo": prazo, "vencida": prazo < acervo.data_da_analise})
    return saida


def diarias_no_mes(acervo: Acervo, matricula: str, mes: str) -> float:
    """Art. 6º: diárias do histórico com partida no mês civil `mes` (AAAA-MM), qualquer situação."""
    return sum(float(h["quantidade"]) for h in acervo.historico
               if h["matricula"] == matricula and h["data_partida"][:7] == mes)
