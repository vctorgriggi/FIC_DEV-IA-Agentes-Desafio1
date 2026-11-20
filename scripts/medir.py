"""Etapa 6: o agente contra o gabarito, em 3 rodadas, com chamadas paralelas desligadas e ligadas.

Cada rodada instrui os 12 pedidos e as 2 complementações (na mesma sessão), com a
memória escolhida (histórico da sessão). Cada pedido tem banco próprio, para que
pedidos instruídos ao mesmo tempo não disputem o arquivo. Para cada caso registra
o que a barreira decidiu, se a instrução bate com o gabarito, tokens por chamada
ao modelo, passos, tempo e custo. O agregado separa o que mais pesa: instrução
ERRADA que a barreira deixou passar até o conferente.

Uso: python scripts/medir.py [--rodadas 3] [--trabalhadores 4]   (chama o modelo)
"""
import argparse
import json
import pathlib
import shutil
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias import memoria  # noqa: E402  (depende do sys.path acima)
from diarias.agente import criar_agente, instruir  # noqa: E402
from scripts.estimar_desenho import PRECO_ENTRADA, PRECO_SAIDA, VOLUME_MENSAL  # noqa: E402
from scripts.rodar_casos import acertou, matricula_esperada  # noqa: E402

DADOS = RAIZ / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}
GABARITO = json.loads((RAIZ / "exemplos" / "gabarito.json").read_text(encoding="utf-8"))
PASTA = memoria.PASTA_BANCOS / "medicao"


def chamadas_ao_modelo(resposta) -> list[dict]:
    """Uma entrada por chamada ao modelo neste turno (sem as mensagens vindas do histórico)."""
    saida = []
    for m in (resposta.messages or []) if resposta else []:
        if m.role == "assistant" and not getattr(m, "from_history", False) and m.metrics:
            saida.append({"entrada": m.metrics.input_tokens or 0, "saida": m.metrics.output_tokens or 0})
    return saida


def caso(resultado, esperado: dict, segundos: float, matricula: str) -> dict:
    r = resultado.resposta
    chamadas = chamadas_ao_modelo(r)
    entrada = getattr(r.metrics, "input_tokens", 0) if r and r.metrics else 0
    saida = getattr(r.metrics, "output_tokens", 0) if r and r.metrics else 0
    certo = acertou(resultado.instrucao, esperado, matricula)
    return {
        "aprovada": resultado.aprovada,
        "acerto": certo,
        # o erro que mais pesa: errado e mesmo assim aprovado, ou seja, entregue ao conferente
        "erro_entregue": resultado.aprovada and not certo,
        "recomendacao": resultado.instrucao.recomendacao if resultado.instrucao else "recusada",
        "motivos_da_recusa": resultado.motivos_da_recusa,
        "consultas": [t.tool_name for t in (r.tools or [])] if r else [],
        "passos": len(chamadas),
        "entrada_por_chamada": [c["entrada"] for c in chamadas],
        "entrada": entrada, "saida": saida,
        "custo": round(entrada * PRECO_ENTRADA + saida * PRECO_SAIDA, 6),
        "segundos": round(segundos, 1),
    }


def instruir_pedido(numero: str, paralelas: bool, pasta: pathlib.Path) -> dict:
    db, _ = memoria.abrir_banco(str((pasta / numero).relative_to(memoria.PASTA_BANCOS)))
    agente = criar_agente(paralelas=paralelas, db=db, **memoria.CONFIGURACOES["historico"])
    saida = {}
    inicio = time.perf_counter()
    r = instruir(agente, PEDIDOS[numero])
    saida[numero] = caso(r, GABARITO["pedidos"][numero], time.perf_counter() - inicio,
                         matricula_esperada(PEDIDOS[numero], None))
    if numero in COMPLEMENTOS:
        inicio = time.perf_counter()
        r = instruir(agente, PEDIDOS[numero], COMPLEMENTOS[numero])
        saida[f"{numero} complementado"] = caso(r, GABARITO["complementacoes"][numero],
                                                time.perf_counter() - inicio,
                                                matricula_esperada(PEDIDOS[numero], COMPLEMENTOS[numero]))
    db.close()
    return saida


def rodada(paralelas: bool, n: int, trabalhadores: int) -> dict:
    pasta = PASTA / f"{'paralelas' if paralelas else 'sequencial'}_r{n}"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    with ThreadPoolExecutor(trabalhadores) as pool:
        partes = pool.map(lambda numero: instruir_pedido(numero, paralelas, pasta), PEDIDOS)
    casos = {}
    for parte in partes:
        casos.update(parte)
    return casos


def resumo(casos: dict) -> dict:
    valores = list(casos.values())
    completos = [c for nome, c in casos.items() if c["passos"] and "complementado" not in nome
                 and GABARITO["pedidos"][nome[:13]]["recomendacao"] != "diligencia"]
    return {
        "casos": len(valores),
        "acertos": sum(c["acerto"] for c in valores),
        "recusadas": sum(not c["aprovada"] for c in valores),
        "erros_entregues": sum(c["erro_entregue"] for c in valores),
        "entrada_media": round(statistics.mean(c["entrada"] for c in valores)),
        "primeira_chamada_media": round(statistics.mean(c["entrada_por_chamada"][0] for c in completos))
        if completos else None,
        "passos_medios_instrucao_completa": round(statistics.mean(c["passos"] for c in completos), 2)
        if completos else None,
        "segundos_medios": round(statistics.mean(c["segundos"] for c in valores), 1),
        "custo_total": round(sum(c["custo"] for c in valores), 4),
        "custo_por_pedido": round(sum(c["custo"] for c in valores) / 12, 5),
    }


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--rodadas", type=int, default=3)
    args.add_argument("--trabalhadores", type=int, default=4)
    a = args.parse_args()

    medicao = {}
    for paralelas in (False, True):
        modo = "paralelas" if paralelas else "sequencial"
        for n in range(1, a.rodadas + 1):
            inicio = time.perf_counter()
            casos = rodada(paralelas, n, a.trabalhadores)
            medicao[f"{modo} r{n}"] = {"casos": casos, "resumo": resumo(casos),
                                       "duracao_da_rodada": round(time.perf_counter() - inicio, 1)}
            print(f"{modo} r{n}: {medicao[f'{modo} r{n}']['resumo']}", flush=True)

    linhas = ["ETAPA 6 · MEDIÇÃO CONTRA O GABARITO (12 pedidos + 2 complementações por rodada)", ""]
    cab = (f"{'rodada':15}{'acertos':>8}{'recusas':>8}{'erros ent.':>11}{'entrada méd.':>13}"
           f"{'1ª chamada':>11}{'passos':>7}{'s/caso':>7}{'US$/pedido':>11}")
    linhas.append(cab)
    for nome, m in medicao.items():
        s = m["resumo"]
        linhas.append(f"{nome:15}{s['acertos']:>5}/14{s['recusadas']:>8}{s['erros_entregues']:>11}"
                      f"{s['entrada_media']:>13}{s['primeira_chamada_media'] or '-':>11}"
                      f"{s['passos_medios_instrucao_completa'] or '-':>7}{s['segundos_medios']:>7}"
                      f"{s['custo_por_pedido']:>11.5f}")
    linhas += ["", "Casos que não acertaram em alguma rodada:"]
    for nome, m in medicao.items():
        for numero, c in m["casos"].items():
            if not c["acerto"]:
                motivo = "; ".join(c["motivos_da_recusa"]) or "aprovada pela barreira, mas diferente do gabarito"
                linhas.append(f"  {nome} · {numero}: {c['recomendacao']} · {motivo}")
    custo_seq = statistics.mean(m["resumo"]["custo_por_pedido"] for k, m in medicao.items() if k.startswith("seq"))
    linhas += ["", f"Custo mensal medido, sequencial, {VOLUME_MENSAL} pedidos: US$ {custo_seq * VOLUME_MENSAL:.2f}"]

    pasta = RAIZ / "resultados"
    (pasta / "etapa6_medicao.json").write_text(json.dumps(medicao, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / "etapa6_medicao.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
