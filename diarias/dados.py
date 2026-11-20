"""Leitura do acervo do órgão em exemplos/dados/, uma vez por processo.

O gabarito não é lido aqui: este módulo alimenta as ferramentas, e o que as
ferramentas leem o agente pode ver.
"""
import csv
import json
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

PASTA_DADOS = Path(__file__).resolve().parents[1] / "exemplos" / "dados"


@dataclass(frozen=True)
class Acervo:
    servidores: dict[str, dict]   # por matrícula; inclui CPF e e-mail, que nenhuma ferramenta devolve
    historico: list[dict]
    tabela: dict
    unidades: dict[str, dict]

    @property
    def data_da_analise(self) -> date:
        """Data fixa da análise; as regras de prazo nunca usam a data de hoje."""
        return date.fromisoformat(self.tabela["data_da_analise"])


def _csv(nome: str) -> list[dict]:
    with open(PASTA_DADOS / nome, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@cache
def carregar() -> Acervo:
    return Acervo(
        servidores={s["matricula"]: s for s in _csv("servidores.csv")},
        historico=_csv("historico_diarias.csv"),
        tabela=json.loads((PASTA_DADOS / "tabela_diarias.json").read_text(encoding="utf-8")),
        unidades=json.loads((PASTA_DADOS / "unidades.json").read_text(encoding="utf-8")),
    )
