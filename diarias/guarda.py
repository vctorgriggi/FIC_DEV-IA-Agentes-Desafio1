"""Prazo de guarda do banco do agente: 30 dias depois do último evento do pedido.

Decisão do usuário: 30 dias após a conferência. O relógio de cada pedido conta a
partir do último destes: conferência registrada, recusa da barreira (que vai para
análise manual sem conferência) ou uso do pedido no banco. Assim um pedido conferido
de novo, ou reinstruído depois de uma conferência antiga, não some no meio do uso.
Pedido sem conferência nem recusa fica até a eliminação pelo titular. A recusa só sai do
log depois que o pedido sai do banco: ela é o relógio dele. O prazo usa a
data real, e não a data da análise do acervo, porque é regra de operação do sistema
e não da norma de diárias.

A conferência do expurgo não procura o número do pedido no conteúdo: o 0102 cita o
0101 na justificativa, e isso acusaria resto onde não há. Confere a coluna session_id
de todas as tabelas e os run_id das execuções apagadas nos bytes do arquivo.
"""
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from agno.db.sqlite import SqliteDb

from diarias import conferencia, memoria

PRAZO_DIAS = 30


def _quando(registro) -> datetime | None:
    """Data do registro em hora local sem fuso; None se o registro não tiver data válida."""
    try:
        quando = datetime.fromisoformat(registro["registrado_em"])
    except (KeyError, TypeError, ValueError):
        return None
    return quando.astimezone().replace(tzinfo=None) if quando.tzinfo else quando


def vencidos(conferencias: list[dict], agora: datetime, prazo_dias: int = PRAZO_DIAS) -> list[str]:
    """Pedidos cujo último evento tem `prazo_dias` ou mais."""
    ultima: dict[str, datetime] = {}
    for c in conferencias:
        quando, numero = _quando(c), c.get("pedido") if isinstance(c, dict) else None
        if quando is None or not isinstance(numero, str) or not numero:   # sem data ou sem pedido: não conta
            continue
        ultima[numero] = max(quando, ultima.get(numero, quando))
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


def _ultimo_uso_no_banco(arquivo: Path, numero: str) -> datetime | None:
    """Última gravação da sessão do pedido no banco do Agno (updated_at, em segundos)."""
    if "agno_sessions" not in memoria.tabelas(arquivo):
        return None
    with sqlite3.connect(arquivo) as con:
        linha = con.execute("SELECT max(coalesce(updated_at, created_at)) FROM agno_sessions WHERE session_id = ?",
                            (numero,)).fetchone()
    return datetime.fromtimestamp(linha[0]) if linha and linha[0] else None


def expurgar(db: SqliteDb, arquivo: Path, agora: datetime | None = None, prazo_dias: int = PRAZO_DIAS,
             conferencias: list[dict] | None = None, recusas: list[dict] | None = None,
             ultimo_uso: Callable[[Path, str], datetime | None] | None = None) -> list[str]:
    """Apaga do banco os pedidos com prazo vencido e prova que saíram. Devolve os números apagados.

    Só fecha o banco quando há o que apagar ou uma compactação pendente; quem chamou precisa
    reabrir o agente quando a lista volta preenchida.
    """
    agora = agora or datetime.now()
    pendentes = []
    if memoria.marca_de_pendencia(arquivo).exists():   # a compactação da vez anterior não terminou
        db.close()
        sessoes, execucoes = memoria.concluir_pendencia(arquivo)
        # confere pelas execuções apagadas: o pedido pode ter sido instruído de novo nesse meio-tempo, e
        # a sessão nova, com outras execuções, não é resto; também não sai da tela
        if memoria.bytes_residuais(arquivo, execucoes):
            raise memoria.EliminacaoIncompleta(f"compactação pendente incompleta: {execucoes}", sessoes)
        pendentes = [s for s in sessoes if not _com_session_id(arquivo, [s])]
    eventos = [*(conferencias if conferencias is not None else conferencia.ler()),
               *(recusas if recusas is not None else conferencia.ler(conferencia.LOG_RECUSAS))]
    candidatos = vencidos(eventos, agora, prazo_dias)
    if not candidatos or not arquivo.exists():
        return pendentes
    uso = ultimo_uso or _ultimo_uso_no_banco
    limite = agora - timedelta(days=prazo_dias)
    ids = [i for i in candidatos if _com_session_id(arquivo, [i])   # ainda no banco
           and ((quando := uso(arquivo, i)) is None or quando <= limite)]   # e sem uso depois do prazo
    if not ids:
        return pendentes
    execucoes = memoria.run_ids(arquivo, ids)
    memoria.marcar_pendencia(arquivo, ids, execucoes)   # antes de apagar
    db.delete_sessions(ids)                   # leva junto as execuções e os resultados guardados
    db.close()
    memoria.compactar_com_marca(arquivo, ids, execucoes)   # se falhar, a próxima chamada termina
    restou = _com_session_id(arquivo, ids)
    residuos = memoria.bytes_residuais(arquivo, execucoes)
    if restou or residuos:
        raise memoria.EliminacaoIncompleta(f"expurgo incompleto de {ids}: {restou} {residuos}", ids)
    return [*pendentes, *ids]


def podar_recusas(agora: datetime | None = None, prazo_dias: int = PRAZO_DIAS,
                  arquivo: Path | None = None, banco: Path | None = None) -> int:
    """O log de recusas pode citar matrículas: guarda só os registros dentro do prazo.

    A recusa de um pedido que ainda está no `banco` fica, mesmo vencida: é o único relógio dele, e
    sem ela o pedido nunca venceria. Linha ilegível sai, porque não conta para prazo nenhum.
    """
    arquivo = arquivo or conferencia.LOG_RECUSAS
    if not arquivo.exists():
        return 0
    limite = (agora or datetime.now()) - timedelta(days=prazo_dias)
    brutas = [x for x in arquivo.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
    linhas = conferencia.ler(arquivo)
    no_banco = _sessoes_no_banco(banco) if banco else set()
    ficam = [x for x in linhas if isinstance(x, dict) and (quando := _quando(x)) is not None
             and (quando > limite or x.get("pedido") in no_banco)]
    arquivo.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ficam), encoding="utf-8")
    return len(brutas) - len(ficam)


def _sessoes_no_banco(arquivo: Path) -> set[str]:
    if not arquivo.exists() or "agno_sessions" not in memoria.tabelas(arquivo):
        return set()
    with sqlite3.connect(arquivo) as con:
        return {r[0] for r in con.execute("SELECT session_id FROM agno_sessions")}
