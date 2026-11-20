"""Filtro de dados pessoais: mascara CPF, conta e agência e nada mais."""
import json
from pathlib import Path

from agno.run.agent import RunInput

from diarias.agente import mensagem_do_pedido
from diarias.filtro import criar_filtro

DADOS = Path(__file__).resolve().parents[1] / "exemplos" / "dados"
PEDIDOS = json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))


def filtrar(texto: str) -> str:
    entrada = RunInput(input_content=texto)
    criar_filtro().check(entrada)
    return entrada.input_content_string()


def test_0104_cpf_conta_e_agencia_nao_passam():
    pedido = next(p for p in PEDIDOS if p["numero"] == "DIA-2026-0104")
    saida = filtrar(mensagem_do_pedido(pedido))
    for dado in ("052.318.947-20", "98765-4", "1234-5"):
        assert dado not in saida
    assert "**************" in saida


def test_nenhuma_matricula_data_ou_numero_de_pedido_e_mascarado():
    for pedido in PEDIDOS:
        saida = filtrar(mensagem_do_pedido(pedido))
        for campo in ("numero", "matricula", "data_pedido", "data_partida", "data_retorno"):
            if pedido[campo]:
                assert pedido[campo] in saida, (pedido["numero"], campo)


def test_so_o_0104_muda():
    alterados = [p["numero"] for p in PEDIDOS if filtrar(mensagem_do_pedido(p)) != mensagem_do_pedido(p)]
    assert alterados == ["DIA-2026-0104"]


def test_complementacoes_passam_intactas():
    for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8")):
        assert filtrar(c["texto"]) == c["texto"]
