"""Prazo de guarda do banco do agente: 30 dias depois da última conferência do pedido.

Decisão do usuário. O relógio de cada pedido começa na última conferência registrada:
se o pedido é conferido de novo, depois de uma complementação, o prazo recomeça.
Pedido nunca conferido fica até ser conferido ou até a eliminação pelo titular. O
prazo usa a data real, e não a data da análise do acervo, porque é regra de operação
do sistema e não da norma de diárias.

A conferência do expurgo não procura o número do pedido no conteúdo: o 0102 cita o
0101 na justificativa, e isso acusaria resto onde não há. Confere a coluna session_id
de todas as tabelas e os run_id das execuções apagadas nos bytes do arquivo.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from agno.db.sqlite import SqliteDb

from diarias import conferencia, memoria

PRAZO_DIAS = 30


def vencidos(conferencias: list[dict], agora: datetime, prazo_dias: int = PRAZO_DIAS) -> list[str]:
    """Pedidos cuja última conferência tem `prazo_dias` ou mais."""
    ultima: dict[str, datetime] = {}
    for c in conferencias:
        quando = datetime.fromisoformat(c["registrado_em"])
        ultima[c["pedido"]] = max(quando, ultima.get(c["pedido"], quando))
    limite = agora - timedelta(days=prazo_dias)
    return sorted(numero for numero, quando in ultima.items() if quando <= limite)


def _com_session_id(arquivo: Path, ids: list[str]) -> dict[str, int]:
    """Linhas, por tabela, cuja coluna session_id é de um dos pedidos."""
    contagem = {}
    marcas = ",".join("?" * len(ids))
    with sqlite3.connect(arquivo) as con:
        for tabela in memoria.tabelas(arquivo):
            colunas = [c[1] for c in con.execute(f'PRAGMA table_info("{tabela}")')]
            if "session_id" in colunas:
                n = con.execute(f'SELECT count(*) FROM "{tabela}" WHERE session_id IN ({marcas})', ids).fetchone()[0]
                if n:
                    contagem[tabela] = n
    return contagem


def _run_ids(arquivo: Path, ids: list[str]) -> list[str]:
    if "agno_runs" not in memoria.tabelas(arquivo):
        return []
    marcas = ",".join("?" * len(ids))
    with sqlite3.connect(arquivo) as con:
        return [r[0] for r in con.execute(f"SELECT run_id FROM agno_runs WHERE session_id IN ({marcas})", ids)]


def expurgar(db: SqliteDb, arquivo: Path, agora: datetime | None = None, prazo_dias: int = PRAZO_DIAS,
             conferencias: list[dict] | None = None) -> list[str]:
    """Apaga do banco os pedidos com prazo vencido e prova que saíram. Devolve os números apagados.

    Só fecha o banco quando há o que apagar; quem chamou precisa reabrir o agente nesse caso.
    """
    agora = agora or datetime.now()
    candidatos = vencidos(conferencias if conferencias is not None else conferencia.ler(), agora, prazo_dias)
    if not candidatos or not arquivo.exists():
        return []
    ids = [i for i in candidatos if _com_session_id(arquivo, [i])]   # vencidos que ainda estão no banco
    if not ids:
        return []
    execucoes = _run_ids(arquivo, ids)
    db.delete_sessions(ids)                   # leva junto as execuções e os resultados guardados
    db.close()
    memoria.compactar(arquivo)
    restou = _com_session_id(arquivo, ids)
    residuos = memoria.bytes_residuais(arquivo, execucoes)
    if restou or residuos:
        raise memoria.EliminacaoIncompleta(f"expurgo incompleto de {ids}: {restou} {residuos}")
    return ids


def podar_recusas(agora: datetime | None = None, prazo_dias: int = PRAZO_DIAS,
                  arquivo: Path | None = None) -> int:
    """O log de recusas pode citar matrículas: guarda só os registros dentro do prazo."""
    arquivo = arquivo or conferencia.LOG_RECUSAS
    if not arquivo.exists():
        return 0
    limite = (agora or datetime.now()) - timedelta(days=prazo_dias)
    linhas = [json.loads(x) for x in arquivo.read_text(encoding="utf-8").splitlines() if x.strip()]
    ficam = [x for x in linhas if datetime.fromisoformat(x["registrado_em"]) > limite]
    arquivo.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ficam), encoding="utf-8")
    return len(linhas) - len(ficam)
