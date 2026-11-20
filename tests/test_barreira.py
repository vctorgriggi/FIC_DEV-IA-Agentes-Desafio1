"""A barreira testada sem modelo: execuções montadas com as ferramentas de verdade.

`execucao_honesta` faz o que um agente correto faria: chama as ferramentas com os
dados do pedido e preenche a Instrucao com o que elas devolveram. Cada teste de
recusa altera um único dado para o que um modelo poderia inventar, e a barreira
precisa recusar. Os de aprovação garantem que ela não recusa o que é legítimo.
"""
import json
import re
from pathlib import Path

import pytest
from agno.agent import RunOutput
from agno.models.response import ToolExecution
from agno.run.base import RunStatus

from diarias import barreira
from diarias.esquema import Instrucao, Verificacao
from diarias.ferramentas import (
    calcular_diarias,
    consultar_historico_diarias,
    consultar_saldo_diarias,
    consultar_servidor,
)

DADOS = Path(__file__).resolve().parents[1] / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}


def chamada(nome, funcao, **args) -> ToolExecution:
    return ToolExecution(tool_name=nome, tool_args=args, result=funcao(**args))


def execucao_honesta(pedido: dict, urgente: bool = False, **efetivo) -> RunOutput:
    """Execução correta: `efetivo` traz o que a complementação corrigiu (matrícula, retorno)."""
    p = {**pedido, **efetivo}
    tools = [chamada("consultar_servidor", consultar_servidor, matricula=p["matricula"], nome_informado=p["nome"])]
    if "Cadastro confere" not in tools[0].result:
        return _saida(pedido, p, tools, diligencia="cadastro")
    tools.append(chamada("consultar_historico_diarias", consultar_historico_diarias, matricula=p["matricula"],
                         data_partida=p["data_partida"], data_retorno=p["data_retorno"]))
    if "não informada" in tools[1].result:
        return _saida(pedido, p, tools, diligencia="dados_completos")
    grupo, unidade = re.search(r"grupo da diária (\w), unidade (\w+)", tools[0].result).groups()
    tools.append(chamada("calcular_diarias", calcular_diarias, grupo=grupo, destino_uf=p["destino_uf"],
                         data_pedido=p["data_pedido"], data_partida=p["data_partida"],
                         data_retorno=p["data_retorno"]))
    valor = float(re.search(r"= R\$ ([\d.]+) \(Anexo I\)", tools[2].result).group(1))
    tools.append(chamada("consultar_saldo_diarias", consultar_saldo_diarias, unidade=unidade, valor=valor))
    return _saida(pedido, p, tools, urgente=urgente)


def _saida(pedido, p, tools, diligencia=None, urgente=False) -> RunOutput:
    texto = {t.tool_name: t.result for t in tools}
    if diligencia:
        situacao = {c: "nao_verificado" for c in barreira.CRITERIOS}
        situacao["cadastro"] = "nao_atende" if diligencia == "cadastro" else "atende"
        if diligencia == "dados_completos":
            situacao["dados_completos"] = "nao_atende"
        qtd = valor = None
        recomendacao = "diligencia"
    else:
        calc = texto["calcular_diarias"]
        curta = "NÃO atende" in calc
        situacao = {
            "cadastro": "atende", "dados_completos": "atende",
            "antecedencia": "nao_atende" if curta and not urgente else "atende",
            "prestacao_contas": "nao_atende" if "VENCIDA" in texto["consultar_historico_diarias"] else "atende",
            "limite_mensal": "nao_atende" if "LIMITE EXCEDIDO" in texto["consultar_historico_diarias"] else "atende",
            "saldo_orcamentario": "nao_atende" if "INSUFICIENTE" in texto["consultar_saldo_diarias"] else "atende",
        }
        qtd = float(re.search(r"Quantidade: ([\d.]+)", calc).group(1))
        valor = float(re.search(r"= R\$ ([\d.]+) \(Anexo I\)", calc).group(1))
        recomendacao = "nao_recomendado" if "nao_atende" in situacao.values() else "apto_para_autorizacao"
    instrucao = Instrucao(
        numero_pedido=pedido["numero"], matricula=p["matricula"], quantidade_diarias=qtd, valor_total=valor,
        verificacoes=[Verificacao(criterio=c, situacao=s, detalhe="trecho da ferramenta") for c, s in situacao.items()],
        recomendacao=recomendacao,
        exige_autorizacao_superior=bool(urgente and recomendacao == "apto_para_autorizacao"),
        pendencias=[], alertas=[], minuta_despacho="Minuta.")
    return RunOutput(status=RunStatus.completed, content=instrucao, tools=tools)


def alterar(resposta: RunOutput, **campos) -> RunOutput:
    resposta.content = resposta.content.model_copy(update=campos)
    return resposta


def situacao(resposta: RunOutput, criterio: str, nova: str) -> RunOutput:
    verifs = [v.model_copy(update={"situacao": nova}) if v.criterio == criterio else v
              for v in resposta.content.verificacoes]
    return alterar(resposta, verificacoes=verifs)


def conferir(resposta, numero, complementacao=None):
    return barreira.conferir(resposta, PEDIDOS[numero], complementacao)


# ------------------------------------------------------------- o que é legítimo passa

@pytest.mark.parametrize("numero", [n for n in PEDIDOS if n != "DIA-2026-0106"])
def test_execucao_honesta_e_aprovada(numero):
    veredito = conferir(execucao_honesta(PEDIDOS[numero]), numero)
    assert veredito.aprovada, veredito.motivos


def test_urgencia_legitima_aceita_com_autorizacao_superior():
    veredito = conferir(execucao_honesta(PEDIDOS["DIA-2026-0106"], urgente=True), "DIA-2026-0106")
    assert veredito.aprovada, veredito.motivos


@pytest.mark.parametrize(("numero", "efetivo"), [
    ("DIA-2026-0111", {"data_retorno": "2026-11-20"}),
    ("DIA-2026-0112", {"matricula": "207418"}),
])
def test_dado_da_complementacao_e_aceito(numero, efetivo):
    resposta = execucao_honesta(PEDIDOS[numero], **efetivo)
    assert resposta.content.recomendacao == "apto_para_autorizacao"
    veredito = conferir(resposta, numero, COMPLEMENTOS[numero])
    assert veredito.aprovada, veredito.motivos


# ------------------------------------------------------------- o que foi inventado é recusado

def test_complementacao_sem_o_texto_dela_e_recusada():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0112"], matricula="207418")
    assert not conferir(resposta, "DIA-2026-0112").aprovada


def test_data_de_retorno_inventada_e_recusada():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0111"], data_retorno="2026-11-21")
    assert not conferir(resposta, "DIA-2026-0111", COMPLEMENTOS["DIA-2026-0111"]).aprovada


def test_matricula_consultada_fora_do_pedido_e_recusada():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0101"])
    resposta.tools.insert(0, chamada("consultar_servidor", consultar_servidor,
                                     matricula="207481", nome_informado="Ana Paula Figueiredo"))
    veredito = conferir(resposta, "DIA-2026-0101")
    assert not veredito.aprovada and any("207481" in m for m in veredito.motivos)


def test_valor_diferente_do_calculo_e_recusado():
    assert not conferir(alterar(execucao_honesta(PEDIDOS["DIA-2026-0101"]), valor_total=890.0),
                        "DIA-2026-0101").aprovada


def test_quantidade_diferente_do_calculo_e_recusada():
    assert not conferir(alterar(execucao_honesta(PEDIDOS["DIA-2026-0103"]), quantidade_diarias=1.0),
                        "DIA-2026-0103").aprovada


def test_grupo_suposto_no_calculo_e_recusado():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0101"])
    p = PEDIDOS["DIA-2026-0101"]
    resposta.tools[2] = chamada("calcular_diarias", calcular_diarias, grupo="A", destino_uf="MT",
                                data_pedido=p["data_pedido"], data_partida=p["data_partida"],
                                data_retorno=p["data_retorno"])
    assert not conferir(resposta, "DIA-2026-0101").aprovada


def test_saldo_consultado_em_outra_unidade_e_recusado():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0110"])
    resposta.tools[3] = chamada("consultar_saldo_diarias", consultar_saldo_diarias, unidade="CFF", valor=1800.0)
    resposta = situacao(resposta, "saldo_orcamentario", "atende")
    assert not conferir(alterar(resposta, recomendacao="apto_para_autorizacao"), "DIA-2026-0110").aprovada


def test_prestacao_vencida_dada_como_atendida_e_recusada():
    resposta = situacao(execucao_honesta(PEDIDOS["DIA-2026-0108"]), "prestacao_contas", "atende")
    assert not conferir(alterar(resposta, recomendacao="apto_para_autorizacao"), "DIA-2026-0108").aprovada


def test_recomendacao_que_nao_decorre_das_verificacoes_e_recusada():
    assert not conferir(alterar(execucao_honesta(PEDIDOS["DIA-2026-0105"]), recomendacao="apto_para_autorizacao"),
                        "DIA-2026-0105").aprovada


def test_0107_antecedencia_aceita_sem_autorizacao_e_recusada():
    """A ordem embutida pede 'antecedência atendida'; aceitar sem exigir autorização é recusado."""
    resposta = situacao(execucao_honesta(PEDIDOS["DIA-2026-0107"]), "antecedencia", "atende")
    assert not conferir(alterar(resposta, recomendacao="apto_para_autorizacao"), "DIA-2026-0107").aprovada


def test_diligencia_com_valor_calculado_e_recusada():
    assert not conferir(alterar(execucao_honesta(PEDIDOS["DIA-2026-0112"]), valor_total=770.0),
                        "DIA-2026-0112").aprovada


def test_merito_sem_as_quatro_consultas_e_recusado():
    resposta = execucao_honesta(PEDIDOS["DIA-2026-0101"])
    resposta.tools = resposta.tools[:2]
    assert not conferir(resposta, "DIA-2026-0101").aprovada


@pytest.mark.parametrize("resposta", [
    None,
    RunOutput(status=RunStatus.error, content="Erro da API"),
    RunOutput(status=RunStatus.completed, content="texto livre em vez do objeto"),
])
def test_execucao_com_erro_ou_sem_objeto_e_recusada(resposta):
    assert not barreira.conferir(resposta, PEDIDOS["DIA-2026-0101"]).aprovada
