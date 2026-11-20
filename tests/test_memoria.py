"""Rotina de eliminação testada sem modelo, num banco montado com a API do Agno."""
import sqlite3

import pytest
from agno.db.schemas.memory import UserMemory
from agno.db.sqlite import SqliteDb
from agno.run.agent import RunInput, RunOutput
from agno.session import AgentSession

from diarias import memoria

BEATRIZ = ("Beatriz Moraes Cunha", ["206689"])
CARLA = ("Carla Regina Souza", ["207418"])    # a corrigida; 207481 é do Rafael e não entra
ANA = ("Ana Paula Figueiredo", ["204317"])


def sessao(db, numero, user_id, texto):
    run = RunOutput(run_id=f"run-{numero}", session_id=numero, user_id=user_id, content=f"Instrução: {texto}",
                    input=RunInput(input_content=f"Pedido {numero}: {texto}"))
    db.upsert_session(AgentSession(session_id=numero, user_id=user_id))
    db.upsert_run(run=run, session_id=numero, user_id=user_id, run_index=0)   # como o agente grava


@pytest.fixture
def banco(tmp_path):
    arquivo = tmp_path / "agente.db"
    db = SqliteDb(db_file=str(arquivo))
    sessao(db, "DIA-2026-0111", "206689", "Beatriz Moraes Cunha, matrícula 206689, retorno em 2026-11-20")
    # 0112: a sessão da Carla fica sob a matrícula digitada, que é do Rafael.
    sessao(db, "DIA-2026-0112", "207481", "Carla Regina Souza; complementação: matrícula correta 207418")
    sessao(db, "DIA-2026-0101", "204317", "Ana Paula Figueiredo, matrícula 204317")
    db.upsert_user_memory(UserMemory(memory="Beatriz Moraes Cunha atua em Colniza", user_id="206689"))
    db.upsert_user_memory(UserMemory(memory="Carla Regina Souza é técnica ambiental", user_id="207481"))
    db.upsert_user_memory(UserMemory(memory="Ana Paula Figueiredo fiscaliza manejo", user_id="204317"))
    return db, arquivo


def test_beatriz_sai_do_banco_e_ana_fica(banco):
    db, arquivo = banco
    rel = memoria.eliminar_titular(db, arquivo, *BEATRIZ)
    assert rel.sessoes_apagadas == ["DIA-2026-0111"] and rel.memorias_apagadas == 1
    assert rel.antes and not rel.depois and not rel.bytes_residuais
    assert memoria.ocorrencias(arquivo, [ANA[0]]) == {"agno_memories": 1, "agno_runs": 1}


def test_carla_e_encontrada_mesmo_sob_o_user_id_de_outro(banco):
    db, arquivo = banco
    assert SqliteDb(db_file=str(arquivo)).get_sessions(user_id="207418") == []   # busca pelo user_id falha
    rel = memoria.eliminar_titular(db, arquivo, *CARLA)
    assert rel.sessoes_apagadas == ["DIA-2026-0112"] and rel.memorias_apagadas == 1
    assert not memoria.ocorrencias(arquivo, ["Carla Regina Souza", "207418"])


def test_sem_compactar_o_texto_apagado_fica_no_arquivo(banco):
    db, arquivo = banco
    db.delete_sessions(["DIA-2026-0111"])
    db.delete_user_memories([m.memory_id for m in db.get_user_memories(user_id="206689")])
    assert not memoria.ocorrencias(arquivo, ["Beatriz Moraes Cunha"])      # as tabelas dizem que saiu
    assert memoria.bytes_residuais(arquivo, ["Beatriz Moraes Cunha"])      # os bytes dizem que não
    db.close()
    memoria.compactar(arquivo)
    assert not memoria.bytes_residuais(arquivo, ["Beatriz Moraes Cunha"])


def test_sobra_em_tabela_que_a_rotina_nao_alcanca_e_acusada(banco):
    db, arquivo = banco
    with sqlite3.connect(arquivo) as con:
        con.execute("CREATE TABLE anotacoes (texto TEXT)")
        con.execute("INSERT INTO anotacoes VALUES ('conversa com Beatriz Moraes Cunha')")
    with pytest.raises(memoria.EliminacaoIncompleta, match="anotacoes"):
        memoria.eliminar_titular(db, arquivo, *BEATRIZ)


def test_grafia_do_json_com_acento_escapado_tambem_e_procurada():
    assert "Ant\\u00f4nio" in memoria._grafias(["Antônio"])
