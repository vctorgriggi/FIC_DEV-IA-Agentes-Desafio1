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
import re
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
    """Sobrou dado do titular no banco depois da rotina, ou a compactação não terminou.

    `sessoes` são as que já saíram do banco: quem chamou precisa tirá-las da tela mesmo assim.
    """

    def __init__(self, mensagem: str, sessoes: list[str] | None = None):
        super().__init__(mensagem)
        self.sessoes = list(sessoes or [])


@dataclass
class Relatorio:
    titular: str
    sessoes_apagadas: list[str] = field(default_factory=list)
    memorias_apagadas: int = 0
    antes: dict[str, int] = field(default_factory=dict)    # tabela -> linhas com o titular
    depois: dict[str, int] = field(default_factory=dict)
    bytes_residuais: list[str] = field(default_factory=list)
    linhas_de_registro_apagadas: int = 0


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


def marca_de_pendencia(arquivo: Path) -> Path:
    """Arquivo que lembra uma compactação interrompida e as sessões que ela apagou."""
    return arquivo.parent / f"{arquivo.name}.compactacao_pendente"


def compactar_com_marca(arquivo: Path, sessoes: list[str]) -> None:
    """Compacta deixando a marca até terminar: se falhar, a próxima abertura termina o serviço."""
    marca = marca_de_pendencia(arquivo)
    marca.write_text(json.dumps(sessoes), encoding="utf-8")
    try:
        compactar(arquivo)
    except (EliminacaoIncompleta, sqlite3.Error) as erro:
        raise EliminacaoIncompleta(f"{erro}; a compactação será refeita na próxima abertura", sessoes) from erro
    marca.unlink()


def concluir_pendencia(arquivo: Path) -> list[str]:
    """Termina a compactação interrompida, se houver, e devolve as sessões que ela tinha apagado."""
    marca = marca_de_pendencia(arquivo)
    if not marca.exists():
        return []
    try:
        sessoes = [str(s) for s in json.loads(marca.read_text(encoding="utf-8") or "[]")]
    except (json.JSONDecodeError, TypeError):   # marca antiga ou truncada: compacta mesmo assim
        sessoes = []
    compactar(arquivo)
    marca.unlink()
    return sessoes


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


def apagar_dos_registros(arquivos: list[Path], termos: list[str]) -> int:
    """Tira, dos registros em JSON Lines, as linhas que citam o titular. Devolve quantas saíram."""
    grafias = _grafias(termos)
    apagadas = 0
    for arquivo in arquivos:
        if not arquivo.exists():
            continue
        linhas = arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
        ficam = [linha for linha in linhas if not any(g in linha for g in grafias)]
        apagadas += len(linhas) - len(ficam)
        arquivo.write_text("".join(ficam), encoding="utf-8")
    return apagadas


def eliminar_titular(db: SqliteDb, arquivo: Path, nome: str, matriculas: list[str],
                     registros: list[Path] = ()) -> Relatorio:
    """Apaga sessões (com as execuções) e memórias do titular e prova, no banco, que nada restou.

    `matriculas` são as do titular, inclusive a corrigida numa complementação. Não inclua a
    matrícula de outra pessoa: ela não é dado do titular. `registros` são os arquivos em JSON
    Lines fora do banco (log de recusas, registro da conferência) que também podem citá-lo.
    """
    nome, matriculas = _titular_valido(nome, matriculas)
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

    # 3. Registros fora do banco antes da compactação: uma compactação que falhe não os deixa para trás.
    relatorio.linhas_de_registro_apagadas = apagar_dos_registros(list(registros), termos)

    # 4. Compactação e conferência: tabela por tabela e nos bytes do arquivo.
    db.close()
    compactar_com_marca(arquivo, sessoes)
    relatorio.depois = ocorrencias(arquivo, termos)
    relatorio.bytes_residuais = bytes_residuais(arquivo, termos)
    relatorio.bytes_residuais += [f"{r.name}: {g}" for r in registros if r.exists()
                                  for g in _grafias(termos) if g in r.read_text(encoding="utf-8")]
    if relatorio.depois or relatorio.bytes_residuais:
        raise EliminacaoIncompleta(f"restou dado de {nome}: {relatorio.depois} {relatorio.bytes_residuais}",
                                   sessoes)
    return relatorio


def _titular_valido(nome: str, matriculas: list[str]) -> tuple[str, list[str]]:
    """A busca é por trecho de texto: nome vazio casaria com tudo, e nome parcial com outras pessoas."""
    nome = " ".join(str(nome).split())
    if len(nome.split()) < 2:
        raise ValueError("informe o nome completo do titular, como está no cadastro")
    matriculas = [str(m).strip() for m in matriculas if str(m).strip()]
    invalidas = [m for m in matriculas if not re.fullmatch(r"\d{6}", m)]
    if invalidas:
        raise ValueError(f"matrícula com formato inválido: {invalidas}; use os 6 algarismos")
    return nome, matriculas
