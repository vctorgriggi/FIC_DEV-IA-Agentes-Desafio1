"""Prazo de guarda do banco do agente: 30 dias depois do último evento do pedido.

Decisão do usuário: 30 dias após a conferência. O relógio de cada pedido conta a
partir do último destes: conferência registrada, recusa da barreira (que vai para
análise manual sem conferência) ou uso do pedido no banco. Assim um pedido conferido
de novo, ou reinstruído depois de uma conferência antiga, não some no meio do uso.
Pedido sem conferência nem recusa fica até a eliminação pelo titular. O prazo usa a
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


def vencidos(conferencias: list[dict], agora: datetime, prazo_dias: int = PRAZO_DIAS) -> list[str]:
    """Pedidos cuja última conferência tem `prazo_dias` ou mais."""
    ultima: dict[str, datetime] = {}
    for c in conferencias:
        try:
            quando = datetime.fromisoformat(c["registrado_em"])
        except (KeyError, TypeError, ValueError):   # registro sem data válida não conta para o prazo
            continue
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


def _ultimo_uso_no_banco(arquivo: Path, numero: str) -> datetime | None:
    """Última gravação da sessão do pedido no banco do Agno (updated_at, em segundos)."""
    if "agno_sessions" not in memoria.tabelas(arquivo):
        return None
    with sqlite3.connect(arquivo) as con:
        linha = con.execute("SELECT max(coalesce(updated_at, created_at)) FROM agno_sessions WHERE session_id = ?",
                            (numero,)).fetchone()
    return datetime.fromtimestamp(linha[0]) if linha and linha[0] else None


def _marca_de_pendencia(arquivo: Path) -> Path:
    return arquivo.parent / f"{arquivo.name}.compactacao_pendente"


def _run_ids(arquivo: Path, ids: list[str]) -> list[str]:
    if "agno_runs" not in memoria.tabelas(arquivo):
        return []
    marcas = ",".join("?" * len(ids))
    with sqlite3.connect(arquivo) as con:
        return [r[0] for r in con.execute(f"SELECT run_id FROM agno_runs WHERE session_id IN ({marcas})", ids)]


def expurgar(db: SqliteDb, arquivo: Path, agora: datetime | None = None, prazo_dias: int = PRAZO_DIAS,
             conferencias: list[dict] | None = None, recusas: list[dict] | None = None,
             ultimo_uso: Callable[[Path, str], datetime | None] | None = None) -> list[str]:
    """Apaga do banco os pedidos com prazo vencido e prova que saíram. Devolve os números apagados.

    Só fecha o banco quando há o que apagar ou uma compactação pendente; quem chamou precisa
    reabrir o agente quando a lista volta preenchida.
    """
    agora = agora or datetime.now()
    marca = _marca_de_pendencia(arquivo)
    if marca.exists():                        # a compactação da vez anterior não terminou
        db.close()
        memoria.compactar(arquivo)
        marca.unlink()
    eventos = [*(conferencias if conferencias is not None else conferencia.ler()),
               *(recusas if recusas is not None else conferencia.ler(conferencia.LOG_RECUSAS))]
    candidatos = vencidos(eventos, agora, prazo_dias)
    if not candidatos or not arquivo.exists():
        return []
    uso = ultimo_uso or _ultimo_uso_no_banco
    limite = agora - timedelta(days=prazo_dias)
    ids = [i for i in candidatos if _com_session_id(arquivo, [i])   # ainda no banco
           and ((quando := uso(arquivo, i)) is None or quando <= limite)]   # e sem uso depois do prazo
    if not ids:
        return []
    execucoes = _run_ids(arquivo, ids)
    db.delete_sessions(ids)                   # leva junto as execuções e os resultados guardados
    db.close()
    marca.touch()                             # se compactar falhar, a próxima chamada termina o serviço
    memoria.compactar(arquivo)
    marca.unlink()
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
