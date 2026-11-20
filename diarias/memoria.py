"""Memória do agente no SQLite e a rotina que elimina os dados de um titular.

Cada pedido é uma sessão (session_id = número do pedido) e o usuário é a matrícula
digitada no pedido (user_id). O banco é cópia de trabalho do agente: o processo de
diárias, que é registro de despesa pública, não é tocado por nada aqui.

A eliminação não confia no user_id. No DIA-2026-0112 a sessão da titular fica
gravada sob a matrícula de outro servidor, e a busca pelo user_id dela não a
encontra; por isso a rotina também procura nome e matrícula no conteúdo de todas
as tabelas, e só declara sucesso depois de conferir tabelas e bytes do arquivo.
"""
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from agno.db.sqlite import SqliteDb

PASTA_BANCOS = Path(__file__).resolve().parents[1] / "bancos"
TETO_HISTORICO = 3   # um pedido tem no máximo dois turnos (pedido e complementação); 3 é folga

CONFIGURACOES = {
    "sem_memoria": {},
    "historico": {"add_history_to_context": True, "num_history_runs": TETO_HISTORICO},
    "historico_e_memorias": {"add_history_to_context": True, "num_history_runs": TETO_HISTORICO,
                             "update_memory_on_run": True},
}


class EliminacaoIncompleta(Exception):
    """Sobrou dado do titular no banco depois da rotina."""


@dataclass
class Relatorio:
    titular: str
    sessoes_apagadas: list[str] = field(default_factory=list)
    memorias_apagadas: int = 0
    antes: dict[str, int] = field(default_factory=dict)    # tabela -> linhas com o titular
    depois: dict[str, int] = field(default_factory=dict)
    bytes_residuais: list[str] = field(default_factory=list)


def abrir_banco(nome: str = "agente") -> tuple[SqliteDb, Path]:
    PASTA_BANCOS.mkdir(exist_ok=True)
    arquivo = PASTA_BANCOS / f"{nome}.db"
    return SqliteDb(db_file=str(arquivo)), arquivo


def _grafias(termos: list[str]) -> list[str]:
    """Cada termo como texto e como o JSON o grava (acentos viram \\uXXXX)."""
    saida = set()
    for t in termos:
        saida.add(t)
        saida.add(json.dumps(t)[1:-1])
    return sorted(saida)


def tabelas(arquivo: Path) -> list[str]:
    with sqlite3.connect(arquivo) as con:
        return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def ocorrencias(arquivo: Path, termos: list[str]) -> dict[str, int]:
    """Linhas, por tabela, em que algum termo aparece em qualquer coluna."""
    if not arquivo.exists():
        return {}
    grafias = _grafias(termos)
    contagem = {}
    with sqlite3.connect(arquivo) as con:
        for tabela in tabelas(arquivo):
            n = 0
            for linha in con.execute(f'SELECT * FROM "{tabela}"'):
                texto = " ".join("" if v is None else v.decode("utf-8", "ignore") if isinstance(v, bytes)
                                 else str(v) for v in linha)
                n += any(g in texto for g in grafias)
            if n:
                contagem[tabela] = n
    return contagem


def bytes_residuais(arquivo: Path, termos: list[str]) -> list[str]:
    """Termos ainda presentes nos bytes do banco ou do WAL: o que um DELETE deixa para trás."""
    achados = []
    for parte in (arquivo, Path(f"{arquivo}-wal")):
        if parte.exists():
            conteudo = parte.read_bytes()
            achados += [f"{parte.name}: {g}" for g in _grafias(termos) if g.encode() in conteudo]
    return achados


def compactar(arquivo: Path) -> None:
    """Checkpoint, VACUUM e checkpoint TRUNCATE: só assim o texto apagado sai do arquivo."""
    with sqlite3.connect(arquivo) as con:
        con.execute("PRAGMA wal_checkpoint(FULL)")
        con.execute("VACUUM")
        ocupado, _, _ = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if ocupado:
        raise EliminacaoIncompleta("banco em uso: o checkpoint não terminou; feche o agente e repita")


def _sessoes_e_memorias_do_titular(arquivo: Path, termos: list[str]) -> tuple[set[str], set[str]]:
    """Sessões e memórias cujo conteúdo cita o titular, sob qualquer user_id."""
    sessoes, memorias = set(), set()
    grafias = _grafias(termos)
    with sqlite3.connect(arquivo) as con:
        for tabela in tabelas(arquivo):
            colunas = [c[1] for c in con.execute(f'PRAGMA table_info("{tabela}")')]
            chave = "memory_id" if "memory_id" in colunas else "session_id" if "session_id" in colunas else None
            if chave is None:
                continue
            for linha in con.execute(f'SELECT * FROM "{tabela}"'):
                texto = " ".join("" if v is None else str(v) for v in linha)
                if any(g in texto for g in grafias):
                    valor = linha[colunas.index(chave)]
                    (memorias if chave == "memory_id" else sessoes).add(valor)
    return sessoes, memorias


def eliminar_titular(db: SqliteDb, arquivo: Path, nome: str, matriculas: list[str]) -> Relatorio:
    """Apaga sessões (com as execuções) e memórias do titular e prova, no banco, que nada restou.

    `matriculas` são as do titular, inclusive a corrigida numa complementação. Não inclua a
    matrícula de outra pessoa: ela não é dado do titular.
    """
    termos = [nome, *matriculas]
    relatorio = Relatorio(titular=nome, antes=ocorrencias(arquivo, termos))

    # 1. Sessões do titular: pelo user_id e pelo conteúdo, que pega a sessão do 0112.
    por_usuario = {s.session_id for m in matriculas for s in db.get_sessions(user_id=m)}
    por_conteudo, memorias_por_conteudo = _sessoes_e_memorias_do_titular(arquivo, termos)
    sessoes = sorted(por_usuario | por_conteudo)
    if sessoes:
        db.delete_sessions(sessoes)           # leva junto as execuções e os resultados guardados
    relatorio.sessoes_apagadas = sessoes

    # 2. Memórias: listadas pelo user_id e pelo conteúdo, apagadas com delete_user_memories.
    por_usuario_mem = {m.memory_id for mat in matriculas for m in db.get_user_memories(user_id=mat)}
    ids = sorted(por_usuario_mem | memorias_por_conteudo)
    if ids:
        db.delete_user_memories(ids)
    relatorio.memorias_apagadas = len(ids)

    # 3. Compactação e conferência: tabela por tabela e nos bytes do arquivo.
    db.close()
    compactar(arquivo)
    relatorio.depois = ocorrencias(arquivo, termos)
    relatorio.bytes_residuais = bytes_residuais(arquivo, termos)
    if relatorio.depois or relatorio.bytes_residuais:
        raise EliminacaoIncompleta(f"restou dado de {nome}: {relatorio.depois} {relatorio.bytes_residuais}")
    return relatorio
