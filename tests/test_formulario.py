"""Formulário e registro da conferência, sem modelo: o agente é trocado por um resultado pronto."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from diarias import agente as ag
from diarias import barreira, conferencia, memoria
from tests.test_barreira import PEDIDOS, execucao_honesta

APP = str(Path(__file__).resolve().parents[1] / "app.py")
SEGREDO = "MOTIVO-INTERNO-207481"


@pytest.fixture(autouse=True)
def pasta_temporaria(tmp_path, monkeypatch):
    """Banco, registro e log de recusas numa pasta descartável; nenhuma chamada ao modelo."""
    monkeypatch.setattr(memoria, "PASTA_BANCOS", tmp_path)
    monkeypatch.setattr(conferencia, "ARQUIVO", tmp_path / "conferencias.jsonl")
    monkeypatch.setattr(conferencia, "LOG_RECUSAS", tmp_path / "recusas.jsonl")
    st.cache_resource.clear()
    yield tmp_path
    st.cache_resource.clear()


def trocar_agente(monkeypatch, resultado: ag.Resultado) -> None:
    def falso(agente, pedido, complementacao=None, ao_consultar=None):
        for t in (resultado.resposta.tools or []) if resultado.resposta else []:
            if ao_consultar:
                ao_consultar(t.tool_name, t.tool_args)
        return resultado
    monkeypatch.setattr(ag, "instruir", falso)


def aprovado(numero: str) -> ag.Resultado:
    resposta = execucao_honesta(PEDIDOS[numero])
    assert barreira.conferir(resposta, PEDIDOS[numero]).aprovada
    return ag.Resultado(numero=numero, aprovada=True, instrucao=resposta.content, resposta=resposta)


def texto_da_tela(at: AppTest) -> str:
    partes = [e.value for grupo in (at.markdown, at.caption, at.error, at.warning, at.info, at.success)
              for e in grupo]
    partes += [str(t.value) for t in at.table] + [m.value for m in at.metric] + [c.value for c in at.code]
    return "\n".join(map(str, partes))


def abrir(numero: str = "DIA-2026-0101") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.selectbox[0].set_value(numero).run()
    return at


def test_abre_sem_chamar_o_modelo():
    at = abrir()
    assert not at.exception
    assert at.title[0].value == "Instrução de pedidos de diárias"


def test_recusa_mostra_so_a_mensagem_padrao(monkeypatch, pasta_temporaria):
    trocar_agente(monkeypatch, ag.Resultado(numero="DIA-2026-0101", aprovada=False, instrucao=None,
                                            motivos_da_recusa=[SEGREDO]))
    at = abrir()
    at.button[0].click().run()
    assert barreira.MENSAGEM_PADRAO in [e.value for e in at.error]
    assert SEGREDO not in texto_da_tela(at)
    assert SEGREDO in (pasta_temporaria / "recusas.jsonl").read_text(encoding="utf-8")   # vai para o log


def test_instrucao_aprovada_mostra_verificacoes_consultas_e_minuta(monkeypatch):
    trocar_agente(monkeypatch, aprovado("DIA-2026-0101"))
    at = abrir()
    at.button[0].click().run()
    tela = texto_da_tela(at)
    assert "Apto para autorização" in tela and "R$ 980,00" in tela
    assert "Cadastro confere: matrícula 204317" in tela           # retorno exato da consulta
    assert at.text_area[0].value == "Minuta."                     # minuta editável


def test_divergir_sem_motivo_nao_registra(monkeypatch):
    trocar_agente(monkeypatch, aprovado("DIA-2026-0101"))
    at = abrir()
    at.button[0].click().run()
    at.radio[0].set_value("analise_manual")
    at.button[1].click().run()                                   # Registrar conferência
    assert any("exige o motivo" in e.value for e in at.error)
    assert conferencia.ler() == []


def test_divergir_com_motivo_registra_ao_lado_da_sugestao(monkeypatch):
    trocar_agente(monkeypatch, aprovado("DIA-2026-0105"))
    at = abrir("DIA-2026-0105")
    at.button[0].click().run()
    at.radio[0].set_value("apto_para_autorizacao")
    at.text_input[0].set_value("Urgência comprovada por ofício anexado depois")
    at.text_area[0].set_value("Minuta reescrita pelo servidor.")
    at.button[1].click().run()
    [linha] = conferencia.ler()
    assert linha["sugerido"] == "nao_recomendado" and linha["decidido"] == "apto_para_autorizacao"
    assert linha["divergiu"] and linha["minuta_editada"] and linha["motivo"]


def test_registro_exige_encaminhamento_conhecido(tmp_path):
    with pytest.raises(ValueError):
        conferencia.registrar("DIA-2026-0101", "apto_para_autorizacao", "deferido", arquivo=tmp_path / "r.jsonl")


def test_taxa_de_divergencia(tmp_path):
    arquivo = tmp_path / "r.jsonl"
    conferencia.registrar("A", "apto_para_autorizacao", "apto_para_autorizacao", arquivo=arquivo)
    conferencia.registrar("B", "apto_para_autorizacao", "nao_recomendado", "falta documento", arquivo=arquivo)
    assert conferencia.taxa_de_divergencia(arquivo) == 0.5


def test_falha_no_expurgo_avisa_e_nao_derruba_o_formulario(monkeypatch):
    from diarias import guarda

    def ocupado(*_args, **_kwargs):
        raise memoria.EliminacaoIncompleta("banco em uso: o checkpoint não terminou")
    monkeypatch.setattr(guarda, "expurgar", ocupado)
    at = abrir()
    assert not at.exception
    assert any("prazo de guarda" in w.value.lower() for w in at.warning)


# ------------------------------------------------------------- segunda revisão

def botao(at, rotulo):
    return next(b for b in at.button if b.label == rotulo)


def agente_que_grava(monkeypatch, aprovada=True):
    """Troca o agente por um que grava a sessão no banco temporário, como o real faria."""
    from tests.test_memoria import sessao

    def falso(agente, pedido, complementacao=None, ao_consultar=None):
        sessao(agente.db, pedido["numero"], pedido["matricula"], f"{pedido['nome']}, matrícula {pedido['matricula']}")
        r = execucao_honesta(PEDIDOS[pedido["numero"]])
        if not aprovada:
            return ag.Resultado(numero=pedido["numero"], aprovada=False, instrucao=None,
                                motivos_da_recusa=["recusa"], resposta=r)
        return ag.Resultado(numero=pedido["numero"], aprovada=True, instrucao=r.content, resposta=r)
    monkeypatch.setattr(ag, "instruir", falso)


def test_eliminacao_tira_a_instrucao_da_tela(monkeypatch):
    agente_que_grava(monkeypatch)
    at = abrir()
    botao(at, "Instruir pedido").click().run()
    at.checkbox[0].check().run()
    botao(at, "Eliminar dados do titular").click().run()
    assert any("Eliminação concluída" in s.value for s in at.success)
    at.run()
    assert "Cadastro confere: matrícula 204317" not in texto_da_tela(at)
    assert not any(b.label == "Registrar conferência" for b in at.button)


def test_clique_duplo_na_conferencia_grava_uma_linha(monkeypatch):
    agente_que_grava(monkeypatch)
    at = abrir()
    botao(at, "Instruir pedido").click().run()
    botao(at, "Registrar conferência").click().run()
    if any(b.label == "Registrar conferência" for b in at.button):
        botao(at, "Registrar conferência").click().run()
    assert len(conferencia.ler()) == 1


def test_confirmacao_da_eliminacao_nao_atravessa_a_troca_de_pedido():
    at = abrir()
    at.checkbox[0].check().run()
    at.sidebar.selectbox[0].set_value("DIA-2026-0103").run()
    assert not at.checkbox[0].value
    assert botao(at, "Eliminar dados do titular").disabled


def test_banco_travado_no_expurgo_avisa_e_nao_derruba(monkeypatch):
    import sqlite3

    from diarias import guarda

    def travado(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(guarda, "expurgar", travado)
    at = abrir()
    assert not at.exception
    assert any("prazo de guarda" in w.value.lower() for w in at.warning)


def test_linha_corrompida_no_registro_nao_derruba(pasta_temporaria):
    (pasta_temporaria / "conferencias.jsonl").write_text('{"pedido": "A", "divergiu": false}\n{quebrado\n',
                                                         encoding="utf-8")
    assert [x["pedido"] for x in conferencia.ler()] == ["A"]
    at = abrir()
    assert not at.exception


# ------------------------------------------------------------- terceira revisão

def test_nome_vazio_na_eliminacao_nao_apaga_nada(monkeypatch, pasta_temporaria):
    from agno.db.sqlite import SqliteDb
    agente_que_grava(monkeypatch)
    at = abrir("DIA-2026-0103")
    botao(at, "Instruir pedido").click().run()
    next(t for t in at.text_input if t.label == "Nome do titular").set_value("   ").run()
    at.checkbox[0].check().run()
    botao(at, "Eliminar dados do titular").click().run()
    assert any("nome completo" in e.value for e in at.error)
    assert {s.session_id for s in SqliteDb(db_file=str(pasta_temporaria / "agente.db")).get_sessions()} == {
        "DIA-2026-0103"}


def test_eliminacao_que_falha_depois_de_apagar_tira_a_instrucao_da_tela(monkeypatch):
    agente_que_grava(monkeypatch)
    at = abrir()
    botao(at, "Instruir pedido").click().run()

    def ocupado(_arquivo):
        raise memoria.EliminacaoIncompleta("banco em uso")
    monkeypatch.setattr(memoria, "compactar", ocupado)
    at.checkbox[0].check().run()
    botao(at, "Eliminar dados do titular").click().run()
    assert any("não se completou" in e.value for e in at.error)
    at.run()
    assert "Cadastro confere: matrícula 204317" not in texto_da_tela(at)
    assert not any(b.label == "Registrar conferência" for b in at.button)


def test_reinstruir_depois_de_conferir_pede_conferencia_nova(monkeypatch):
    agente_que_grava(monkeypatch)
    at = abrir("DIA-2026-0105")
    botao(at, "Instruir pedido").click().run()
    botao(at, "Registrar conferência").click().run()
    assert len(conferencia.ler()) == 1
    botao(at, "Instruir pedido").click().run()
    assert any(b.label == "Registrar conferência" for b in at.button)


def test_eliminacao_tira_o_texto_da_complementacao(monkeypatch):
    agente_que_grava(monkeypatch)
    at = abrir("DIA-2026-0112")
    at.session_state["complemento_DIA-2026-0112"] = "minha matrícula correta é 207418"
    botao(at, "Instruir pedido").click().run()
    next(t for t in at.text_input if t.label.startswith("Matrículas")).set_value("207418").run()
    at.checkbox[0].check().run()
    botao(at, "Eliminar dados do titular").click().run()
    assert any("Eliminação concluída" in s.value for s in at.success), [e.value for e in at.error]
    assert "complemento_DIA-2026-0112" not in at.session_state


def test_motivo_da_conferencia_sai_mascarado(tmp_path):
    arquivo = tmp_path / "conferencias.jsonl"
    conferencia.registrar("DIA-2026-0101", "apto_para_autorizacao", "analise_manual",
                          "servidora ligou, CPF 052.318.947-20, e-mail ana@sema.mt.gov.br", arquivo=arquivo)
    gravado = arquivo.read_text(encoding="utf-8")
    assert "052.318.947-20" not in gravado and "ana@sema.mt.gov.br" not in gravado
    assert "servidora ligou" in gravado
