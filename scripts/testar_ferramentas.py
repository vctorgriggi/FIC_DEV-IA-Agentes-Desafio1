"""Etapa 2: chama cada ferramenta sem agente e sem chave, com os casos dos próprios pedidos.

Mostra o texto exato que o modelo vai receber. A saída fica em
resultados/etapa2_ferramentas.txt como evidência de que as contas estão certas
antes de o modelo entrar; a prova contra o gabarito está em tests/.

Uso: python scripts/testar_ferramentas.py
"""
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias.ferramentas import (  # noqa: E402  (depende do sys.path acima)
    calcular_diarias,
    consultar_historico_diarias,
    consultar_saldo_diarias,
    consultar_servidor,
)

PEDIDOS = {p["numero"]: p for p in json.loads((RAIZ / "exemplos/dados/pedidos.json").read_text(encoding="utf-8"))}
SAIDA = RAIZ / "resultados" / "etapa2_ferramentas.txt"


def casos() -> list[tuple[str, str, str]]:
    p = PEDIDOS
    return [
        ("DIA-2026-0112 · matrícula trocada", 'consultar_servidor("207481", "Carla Regina Souza")',
         consultar_servidor("207481", "Carla Regina Souza")),
        ("DIA-2026-0112 · matrícula da complementação", 'consultar_servidor("207418", "Carla Regina Souza")',
         consultar_servidor("207418", "Carla Regina Souza")),
        ("DIA-2026-0108 · prestação vencida",
         'consultar_historico_diarias("203648", "2026-11-03", "2026-11-06")',
         consultar_historico_diarias("203648", p["DIA-2026-0108"]["data_partida"], p["DIA-2026-0108"]["data_retorno"])),
        ("DIA-2026-0102 · pendente no prazo",
         'consultar_historico_diarias("205882", "2026-11-09", "2026-11-12")',
         consultar_historico_diarias("205882", p["DIA-2026-0102"]["data_partida"], p["DIA-2026-0102"]["data_retorno"])),
        ("DIA-2026-0103 · meia diária",
         'calcular_diarias("B", "MT", "2026-10-07", "2026-11-05", "2026-11-05")',
         calcular_diarias("B", "MT", "2026-10-07", "2026-11-05", "2026-11-05")),
        ("DIA-2026-0110 · saldo da unidade",
         'calcular_diarias("B", "RO", "2026-10-02", "2026-11-10", "2026-11-14")',
         calcular_diarias("B", "RO", "2026-10-02", "2026-11-10", "2026-11-14")),
        ("DIA-2026-0110 · saldo da unidade", 'consultar_saldo_diarias("CRH", 1800.0)',
         consultar_saldo_diarias("CRH", 1800.0)),
        ("DIA-2026-0109 · limite mensal",
         'consultar_historico_diarias("208114", "2026-11-23", "2026-11-26")',
         consultar_historico_diarias("208114", "2026-11-23", "2026-11-26")),
        ("DIA-2026-0111 · retorno ausente",
         'consultar_historico_diarias("206689", "2026-11-17", None)',
         consultar_historico_diarias("206689", "2026-11-17", None)),
    ]


def main() -> None:
    linhas = ["ETAPA 2 · FERRAMENTAS SEM AGENTE E SEM CHAVE", ""]
    for titulo, chamada, saida in casos():
        linhas += [f"## {titulo}", f">>> {chamada}", saida, ""]
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
