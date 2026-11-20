"""Contrato da saída do agente: o objeto que a tela e a medição leem sem interpretar texto.

Os campos são o contrato mínimo da Etapa 3 do enunciado. Campo novo só entra
quando alguém precisa lê-lo.
"""
from typing import Literal

from pydantic import BaseModel

Criterio = Literal["cadastro", "dados_completos", "antecedencia", "prestacao_contas",
                   "limite_mensal", "saldo_orcamentario"]
Recomendacao = Literal["apto_para_autorizacao", "diligencia", "nao_recomendado"]


class Verificacao(BaseModel):
    criterio: Criterio
    situacao: Literal["atende", "nao_atende", "nao_verificado"]
    detalhe: str            # o dado que fundamenta a situação, como veio da ferramenta


class Instrucao(BaseModel):
    numero_pedido: str
    matricula: str
    quantidade_diarias: float | None   # nulo na diligência
    valor_total: float | None          # nulo na diligência
    verificacoes: list[Verificacao]
    recomendacao: Recomendacao
    exige_autorizacao_superior: bool
    pendencias: list[str]   # o que o solicitante precisa corrigir
    alertas: list[str]      # ordens embutidas, dados mascarados, o que o conferente precisa ver
    minuta_despacho: str
