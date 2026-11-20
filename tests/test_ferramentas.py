"""Ferramentas testadas sem agente e sem chave (Etapa 2).

Os casos citados pelo enunciado vêm primeiro. Depois, as quatro ferramentas são
encadeadas como o agente faria e o resultado é comparado ao gabarito nos 14
casos: se as contas divergirem do gabarito, o erro aparece aqui, e não depois
como resposta estranha do agente.
"""
import csv
import json
import re
from pathlib import Path

import pytest

from diarias.ferramentas import (
    calcular_diarias,
    consultar_historico_diarias,
    consultar_saldo_diarias,
    consultar_servidor,
)

EXEMPLOS = Path(__file__).resolve().parents[1] / "exemplos"
PEDIDOS = {p["numero"]: p for p in json.loads((EXEMPLOS / "dados/pedidos.json").read_text(encoding="utf-8"))}
GABARITO = json.loads((EXEMPLOS / "gabarito.json").read_text(encoding="utf-8"))

# Urgência é julgamento sobre o texto da justificativa, que cabe ao modelo e nenhuma ferramenta
# calcula. Aqui ela é fixada pelo enunciado: o 0106 descreve incêndio em curso; o 0107 não.
URGENTES = {"DIA-2026-0106"}

# Complementações, como o servidor as escreveu em complementacoes.json, aplicadas ao pedido.
CORRECOES = {"DIA-2026-0111": {"data_retorno": "2026-11-20"}, "DIA-2026-0112": {"matricula": "207418"}}


# ------------------------------------------------------------- casos do enunciado

def test_0112_matricula_trocada_vai_a_diligencia_sem_expor_o_outro_servidor():
    saida = consultar_servidor("207481", "Carla Regina Souza")
    assert "Diligência" in saida
    assert "Rafael" not in saida and "CFA" not in saida   # titular real da 207481 não vaza


def test_0112_matricula_corrigida_confere():
    saida = consultar_servidor("207418", "Carla Regina Souza")
    assert "Cadastro confere" in saida and "grupo da diária C" in saida and "unidade CUC" in saida


def test_0108_prestacao_vencida_impede():
    p = PEDIDOS["DIA-2026-0108"]
    saida = consultar_historico_diarias(p["matricula"], p["data_partida"], p["data_retorno"])
    assert "VENCIDA" in saida and "DIA-2026-0023" in saida and "prazo 2026-09-25" in saida


def test_0102_pendente_no_prazo_nao_impede():
    p = PEDIDOS["DIA-2026-0102"]
    saida = consultar_historico_diarias(p["matricula"], p["data_partida"], p["data_retorno"])
    assert "Sem prestação de contas vencida" in saida and "prazo 2026-10-13" in saida


def test_0103_meia_diaria_sem_pernoite():
    p = PEDIDOS["DIA-2026-0103"]
    saida = calcular_diarias("B", "MT", p["data_pedido"], p["data_partida"], p["data_retorno"])
    assert "Quantidade: 0.5" in saida and "= R$ 140.00" in saida


def test_0110_saldo_insuficiente():
    assert "INSUFICIENTE" in consultar_saldo_diarias("CRH", 1800.0)
    assert "R$ 640.00" in consultar_saldo_diarias("crh ", 1800)


def test_0109_limite_mensal_excedido():
    p = PEDIDOS["DIA-2026-0109"]
    saida = consultar_historico_diarias(p["matricula"], p["data_partida"], p["data_retorno"])
    assert "8 já concedidas + 3.5 pedidas = 11.5" in saida and "LIMITE EXCEDIDO" in saida


# ------------------------------------------------------------- minimização e entradas ruins

def test_nenhuma_ferramenta_devolve_cpf_ou_email_de_ninguem():
    with open(EXEMPLOS / "dados/servidores.csv", encoding="utf-8") as f:
        for s in csv.DictReader(f):
            saida = consultar_servidor(s["matricula"], s["nome"])
            assert s["cpf"] not in saida and s["email"] not in saida and "@" not in saida


@pytest.mark.parametrize(("chamada", "trecho"), [
    (lambda: consultar_servidor("999999", "Ninguém"), "não consta do cadastro"),
    (lambda: consultar_historico_diarias("206689", "2026-11-17", None), "Data de retorno não informada"),
    (lambda: calcular_diarias("B", "MT", "2026-10-09", "2026-11-17", ""), "Data de retorno não informada"),
    (lambda: calcular_diarias("Z", "MT", "2026-10-09", "2026-11-17", "2026-11-20"), "use A, B ou C"),
    (lambda: calcular_diarias("B", "Mato Grosso", "2026-10-09", "2026-11-17", "2026-11-20"), "duas letras"),
    (lambda: calcular_diarias("B", "MT", "09/10/2026", "2026-11-17", "2026-11-20"), "AAAA-MM-DD"),
    (lambda: calcular_diarias("B", "MT", "2026-10-09", "2026-11-20", "2026-11-17"), "anterior à partida"),
    (lambda: consultar_saldo_diarias("XYZ", 100.0), "não localizada"),
])
def test_argumento_invalido_volta_como_texto_explicando_o_formato(chamada, trecho):
    assert trecho in chamada()


# ------------------------------------------------------------- encadeamento contra o gabarito

def instruir_com_ferramentas(pedido: dict) -> dict:
    """Encadeia as ferramentas como o agente faria e lê só o texto que elas devolvem."""
    nao_atendidos = []
    cadastro = consultar_servidor(pedido["matricula"], pedido["nome"])
    if "Cadastro confere" not in cadastro:
        nao_atendidos.append("cadastro")
    historico = consultar_historico_diarias(pedido["matricula"], pedido["data_partida"], pedido["data_retorno"])
    if "não informada" in historico:
        nao_atendidos.append("dados_completos")
    if nao_atendidos:
        return {"recomendacao": "diligencia", "quantidade_diarias": None, "valor_total": None,
                "exige_autorizacao_superior": False, "criterios_nao_atendidos": nao_atendidos}

    grupo = re.search(r"grupo da diária (\w)", cadastro).group(1)
    unidade = re.search(r"unidade (\w+) \(", cadastro).group(1)
    calculo = calcular_diarias(grupo, pedido["destino_uf"], pedido["data_pedido"],
                               pedido["data_partida"], pedido["data_retorno"])
    qtd = float(re.search(r"Quantidade: ([\d.]+)", calculo).group(1))
    valor = float(re.search(r"= R\$ ([\d.]+) \(Anexo I\)", calculo).group(1))
    saldo = consultar_saldo_diarias(unidade, valor)

    urgente = "NÃO atende" in calculo and pedido["numero"] in URGENTES
    if "NÃO atende" in calculo and not urgente:
        nao_atendidos.append("antecedencia")
    if "VENCIDA" in historico:
        nao_atendidos.append("prestacao_contas")
    if "LIMITE EXCEDIDO" in historico:
        nao_atendidos.append("limite_mensal")
    if "INSUFICIENTE" in saldo:
        nao_atendidos.append("saldo_orcamentario")
    return {"recomendacao": "nao_recomendado" if nao_atendidos else "apto_para_autorizacao",
            "quantidade_diarias": qtd, "valor_total": valor,
            "exige_autorizacao_superior": urgente and not nao_atendidos,
            "criterios_nao_atendidos": nao_atendidos}


CASOS = [(n, PEDIDOS[n], GABARITO["pedidos"][n]) for n in PEDIDOS] + [
    (f"{n} complementado", {**PEDIDOS[n], **c}, GABARITO["complementacoes"][n]) for n, c in CORRECOES.items()]


@pytest.mark.parametrize(("nome", "pedido", "esperado"), CASOS, ids=[c[0] for c in CASOS])
def test_ferramentas_encadeadas_chegam_ao_gabarito(nome, pedido, esperado):
    obtido = instruir_com_ferramentas(pedido)
    assert obtido == {k: v for k, v in esperado.items() if k != "caso"}
