"""Etapa 6: a aritmética da Etapa 1 confrontada com o medido.

Lê resultados/etapa1_estimativa.txt (feita antes do agente) e
resultados/etapa6_medicao.json, e grava resultados/etapa6_confronto.txt.

Uso: python scripts/confrontar.py   (sem chamar o modelo)
"""
import json
import pathlib
import re
import statistics
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias.agente import INSTRUCAO  # noqa: E402
from diarias.dados import PASTA_DADOS  # noqa: E402
from scripts.estimar_desenho import (  # noqa: E402
    ENC,
    ORDEM_E_PROIBICOES,
    PRECO_ENTRADA,
    PRECO_SAIDA,
    VOLUME_MENSAL,
)

RES = RAIZ / "resultados"
GABARITO = json.loads((RAIZ / "exemplos" / "gabarito.json").read_text(encoding="utf-8"))


def estimativa() -> dict:
    texto = (RES / "etapa1_estimativa.txt").read_text(encoding="utf-8")
    total = int(re.search(r"TOTAL estimado\s+(\d+)", texto).group(1))
    faixas = {}
    for nome, chave in (("sequencial", "sequencial"), ("paralelo", "paralelo"), ("diligencia", "diligencia")):
        m = re.search(rf"{chave}.*?entrada (\d+)–(\d+) · saída (\d+) · US\$ ([\d.]+)–([\d.]+)", texto, re.S)
        faixas[nome] = {"entrada": (int(m.group(1)), int(m.group(2))), "saida": int(m.group(3)),
                        "custo": (float(m.group(4)), float(m.group(5)))}
    return {"primeira_chamada": total, "faixas": faixas}


def tipo(numero: str) -> str:
    """Pela resposta certa do caso: diligência para no cadastro; o resto faz a cadeia toda."""
    if "complementado" in numero:
        return "completa"
    return "diligencia" if GABARITO["pedidos"][numero]["recomendacao"] == "diligencia" else "completa"


def main() -> None:
    est = estimativa()
    medicao = json.loads((RES / "etapa6_medicao.json").read_text(encoding="utf-8"))
    linhas = ["ETAPA 6 · ETAPA 1 CONFRONTADA COM O MEDIDO", ""]
    for modo, faixa_chave in (("sequencial", "sequencial"), ("paralelas", "paralelo")):
        casos = [c | {"numero": n} for k, m in medicao.items() if k.startswith(modo)
                 for n, c in m["casos"].items() if c["passos"]]
        completos = [c for c in casos if tipo(c["numero"]) == "completa" and "complementado" not in c["numero"]]
        diligencias = [c for c in casos if tipo(c["numero"]) == "diligencia"]
        primeira = statistics.mean(c["entrada_por_chamada"][0] for c in completos)
        deltas = [b - a for c in completos for a, b in zip(c["entrada_por_chamada"], c["entrada_por_chamada"][1:],
                                                           strict=False)]
        passos = statistics.mean(c["passos"] for c in completos)
        entrada = statistics.mean(c["entrada"] for c in completos)
        saida = statistics.mean(c["saida"] for c in completos)
        custo = statistics.mean(c["custo"] for c in completos)
        f = est["faixas"][faixa_chave]
        lo, hi = f["entrada"]
        linhas += [f"## {modo} · {len(completos)} instruções completas em 3 rodadas",
                   f"  primeira chamada: estimada {est['primeira_chamada']} · medida {primeira:.0f} "
                   f"({100 * (primeira - est['primeira_chamada']) / est['primeira_chamada']:+.0f}%)",
                   f"  acréscimo por passo: estimado 90–150 · medido {min(deltas)}–{max(deltas)} "
                   f"(média {statistics.mean(deltas):.0f})",
                   f"  passos: estimados {5 if modo == 'sequencial' else 4} · medidos {passos:.2f}",
                   f"  entrada total: estimada {lo}–{hi} · medida {entrada:.0f} "
                   f"({100 * (entrada - hi) / hi:+.0f}% sobre o teto da estimativa)",
                   f"  saída: estimada {f['saida']} · medida {saida:.0f}",
                   f"  custo por instrução: estimado US$ {f['custo'][0]:.5f}–{f['custo'][1]:.5f} · "
                   f"medido US$ {custo:.5f}"]
        if diligencias:
            d = est["faixas"]["diligencia"]
            linhas.append(f"  diligência: entrada estimada {d['entrada'][0]}–{d['entrada'][1]} · medida "
                          f"{statistics.mean(c['entrada'] for c in diligencias):.0f} · passos medidos "
                          f"{statistics.mean(c['passos'] for c in diligencias):.2f} (estimados 2)")
        todos = [c for k, m in medicao.items() if k.startswith(modo) for c in m["casos"].values()]
        acertos = sum(c["acerto"] for c in todos)
        linhas += [f"  acerto por caso: {acertos}/{len(todos)} ({acertos / len(todos):.1%}); "
                   f"erros entregues ao conferente: {sum(c['erro_entregue'] for c in todos)}; "
                   f"recusas visíveis: {sum(not c['aprovada'] for c in todos)}", ""]
    seq = [c for k, m in medicao.items() if k.startswith("sequencial") for c in m["casos"].values()]
    custo_pedido = sum(c["custo"] for c in seq) / (12 * 3)
    linhas.append(f"Mês com {VOLUME_MENSAL} pedidos, sequencial: estimado US$ 1,00–1,04 · medido "
                  f"US$ {custo_pedido * VOLUME_MENSAL:.2f} (preços US$ {PRECO_ENTRADA * 1e6:.2f} e "
                  f"{PRECO_SAIDA * 1e6:.2f} por milhão)")
    # De onde vem a diferença da primeira chamada: a premissa da instrução contra o texto escrito.
    norma = len(ENC.encode((PASTA_DADOS / "normas.md").read_text(encoding="utf-8")))
    regras = len(ENC.encode(INSTRUCAO)) - norma
    linhas += ["", f"Instrução de sistema além da norma: premissa {ORDEM_E_PROIBICOES} tokens · escrita {regras} "
               f"(+{regras - ORDEM_E_PROIBICOES}), com o mesmo tokenizador da estimativa"]
    (RES / "etapa6_confronto.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
