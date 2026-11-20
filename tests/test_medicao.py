"""O critério de acerto da medição: a instrução certa para a pessoa certa."""
import json
from pathlib import Path

from scripts.rodar_casos import acertou, matricula_esperada
from tests.test_barreira import COMPLEMENTOS, PEDIDOS, execucao_honesta

GABARITO = json.loads((Path(__file__).resolve().parents[1] / "exemplos/gabarito.json").read_text(encoding="utf-8"))


def test_matricula_errada_nao_conta_como_acerto():
    instrucao = execucao_honesta(PEDIDOS["DIA-2026-0112"], matricula="207418").content
    esperado = GABARITO["complementacoes"]["DIA-2026-0112"]
    certa = matricula_esperada(PEDIDOS["DIA-2026-0112"], COMPLEMENTOS["DIA-2026-0112"])
    assert certa == "207418"
    assert acertou(instrucao, esperado, certa)
    assert not acertou(alterar_matricula(instrucao, "207481"), esperado, certa)


def test_sem_complementacao_a_matricula_esperada_e_a_do_pedido():
    assert matricula_esperada(PEDIDOS["DIA-2026-0111"], None) == "206689"
    assert matricula_esperada(PEDIDOS["DIA-2026-0111"], COMPLEMENTOS["DIA-2026-0111"]) == "206689"


def alterar_matricula(instrucao, matricula):
    return instrucao.model_copy(update={"matricula": matricula})

