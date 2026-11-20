"""Prazo de guarda de 30 dias após a conferência, testado sem modelo."""
import json
from datetime import datetime, timedelta

import pytest
from agno.db.sqlite import SqliteDb

from diarias import guarda, memoria
from tests.test_memoria import sessao

AGORA = datetime(2026, 12, 20, 12, 0, 0)


def conferido(numero: str, dias_atras: float) -> dict:
    return {"pedido": numero, "registrado_em": (AGORA - timedelta(days=dias_atras)).isoformat(timespec="seconds")}


def banco(tmp_path):
    arquivo = tmp_path / "agente.db"
    db = SqliteDb(db_file=str(arquivo))
    sessao(db, "DIA-2026-0101", "204317", "Ana Paula Figueiredo, matrícula 204317")
    # o 0102 cita o 0101 na justificativa: não pode ser apagado nem acusado como resto do 0101
    sessao(db, "DIA-2026-0102", "205882", "Marcos Antônio Rezende; motorista da vistoria do pedido DIA-2026-0101")
    sessao(db, "DIA-2026-0103", "203156", "Juliana Campos Arruda, matrícula 203156")
    return db, arquivo


def test_vencidos_conta_a_partir_da_ultima_conferencia():
    conferencias = [conferido("A", 40), conferido("A", 10), conferido("B", 30), conferido("C", 29.9)]
    assert guarda.vencidos(conferencias, AGORA) == ["B"]   # A foi conferido de novo há 10 dias


def test_expurga_so_o_vencido_e_prova_que_saiu(tmp_path):
    db, arquivo = banco(tmp_path)
    apagados = guarda.expurgar(db, arquivo, AGORA, conferencias=[conferido("DIA-2026-0101", 31),
                                                                 conferido("DIA-2026-0102", 5)],
                               ultimo_uso=lambda *_: None)
    assert apagados == ["DIA-2026-0101"]
    assert not memoria.ocorrencias(arquivo, ["Ana Paula Figueiredo", "204317"])
    assert not memoria.bytes_residuais(arquivo, ["Ana Paula Figueiredo"])
    restantes = {s.session_id for s in SqliteDb(db_file=str(arquivo)).get_sessions()}
    assert restantes == {"DIA-2026-0102", "DIA-2026-0103"}   # 0102 no prazo; 0103 nunca conferido


def test_sem_vencidos_nao_toca_no_banco(tmp_path):
    db, arquivo = banco(tmp_path)
    antes = arquivo.read_bytes()
    assert guarda.expurgar(db, arquivo, AGORA, conferencias=[conferido("DIA-2026-0101", 2)],
                           ultimo_uso=lambda *_: None) == []
    assert arquivo.read_bytes() == antes


def test_pedido_vencido_que_ja_saiu_do_banco_e_ignorado(tmp_path):
    db, arquivo = banco(tmp_path)
    assert guarda.expurgar(db, arquivo, AGORA, conferencias=[conferido("DIA-2026-0999", 60)],
                           ultimo_uso=lambda *_: None) == []


def test_log_de_recusas_guarda_so_o_que_esta_no_prazo(tmp_path):
    log = tmp_path / "recusas.jsonl"
    log.write_text("".join(json.dumps({"pedido": n, "motivos": ["matrícula 207481"],
                                       "registrado_em": (AGORA - timedelta(days=d)).isoformat()}) + "\n"
                           for n, d in (("velho", 45), ("novo", 3))), encoding="utf-8")
    assert guarda.podar_recusas(AGORA, arquivo=log) == 1
    assert [json.loads(x)["pedido"] for x in log.read_text(encoding="utf-8").splitlines()] == ["novo"]


# ------------------------------------------------------------- segunda revisão

def test_pedido_usado_depois_da_conferencia_antiga_nao_e_apagado(tmp_path):
    db, arquivo = banco(tmp_path)    # sessões gravadas agora
    apagados = guarda.expurgar(db, arquivo, datetime.now(), conferencias=[
        {"pedido": "DIA-2026-0101", "registrado_em": (datetime.now() - timedelta(days=31)).isoformat()}])
    assert apagados == []


def test_compactacao_que_falhou_e_refeita_na_proxima_vez(tmp_path, monkeypatch):
    db, arquivo = banco(tmp_path)
    conf = [conferido("DIA-2026-0101", 40)]
    real = memoria.compactar

    def ocupado(_arquivo):
        raise memoria.EliminacaoIncompleta("banco em uso")
    monkeypatch.setattr(memoria, "compactar", ocupado)
    with pytest.raises(memoria.EliminacaoIncompleta):
        guarda.expurgar(db, arquivo, AGORA, conferencias=conf, ultimo_uso=lambda *_: None)
    monkeypatch.setattr(memoria, "compactar", real)
    guarda.expurgar(SqliteDb(db_file=str(arquivo)), arquivo, AGORA, conferencias=conf, ultimo_uso=lambda *_: None)
    assert not memoria.bytes_residuais(arquivo, ["Ana Paula Figueiredo"])


def test_recusa_conta_para_o_prazo(tmp_path):
    db, arquivo = banco(tmp_path)
    recusas = [{"pedido": "DIA-2026-0101", "registrado_em": (AGORA - timedelta(days=31)).isoformat()}]
    apagados = guarda.expurgar(db, arquivo, AGORA, conferencias=[], recusas=recusas, ultimo_uso=lambda *_: None)
    assert apagados == ["DIA-2026-0101"]
