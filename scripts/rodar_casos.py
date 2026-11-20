"""Roda o agente de verdade (com a chave) em alguns pedidos e compara com o gabarito.

É script de medição: só ele e os testes abrem o gabarito, e o agente nunca o vê.
Sem memória (cada pedido isolado). Grava em resultados/etapa3_casos.txt o que a
barreira decidiu, as consultas feitas, tokens, tempo e o confronto com o gabarito.

Uso: python scripts/rodar_casos.py [números dos pedidos...] [--paralelas]
"""
import json
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias.agente import criar_agente, instruir  # noqa: E402  (depende do sys.path acima)

DADOS = RAIZ / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
GABARITO = json.loads((RAIZ / "exemplos" / "gabarito.json").read_text(encoding="utf-8"))["pedidos"]
PADRAO = ["DIA-2026-0101", "DIA-2026-0104", "DIA-2026-0106", "DIA-2026-0107", "DIA-2026-0112"]


def acertou(instrucao, esperado: dict) -> bool:
    if instrucao is None:
        return False
    nao_atende = sorted(v.criterio for v in instrucao.verificacoes if v.situacao == "nao_atende")
    return (instrucao.recomendacao == esperado["recomendacao"]
            and instrucao.quantidade_diarias == esperado["quantidade_diarias"]
            and instrucao.valor_total == esperado["valor_total"]
            and instrucao.exige_autorizacao_superior == esperado["exige_autorizacao_superior"]
            and nao_atende == sorted(esperado["criterios_nao_atendidos"]))


def main() -> None:
    paralelas = "--paralelas" in sys.argv
    numeros = [a for a in sys.argv[1:] if a.startswith("DIA-")] or PADRAO
    agente = criar_agente(paralelas=paralelas)
    linhas = [f"ETAPA 3 · AGENTE SEM MEMÓRIA · paralelas={'ligadas' if paralelas else 'desligadas'}", ""]
    for numero in numeros:
        inicio = time.perf_counter()
        r = instruir(agente, PEDIDOS[numero])
        segundos = time.perf_counter() - inicio
        m = r.resposta.metrics if r.resposta else None
        recebido = r.resposta.input.input_content_string() if r.resposta and r.resposta.input else ""
        esperado = GABARITO[numero]
        linhas.append(f"## {numero} · {esperado['caso']}")
        linhas.append(f"barreira: {'APROVADA' if r.aprovada else 'RECUSADA'} · acerto contra o gabarito: "
                      f"{'sim' if acertou(r.instrucao, esperado) else 'NÃO'} · "
                      f"{getattr(m, 'input_tokens', '?')} tokens de entrada, "
                      f"{getattr(m, 'output_tokens', '?')} de saída · {segundos:.1f} s")
        for motivo in r.motivos_da_recusa:
            linhas.append(f"  recusa: {motivo}")
        for t in (r.resposta.tools or []) if r.resposta else []:
            linhas.append(f"  consulta: {t.tool_name}({json.dumps(t.tool_args, ensure_ascii=False)})")
        if "052.318.947-20" in json.dumps(PEDIDOS[numero], ensure_ascii=False):
            linhas.append(f"  CPF do pedido no que o modelo recebeu: {'SIM' if '052.318.947-20' in recebido else 'não'}")
        if r.instrucao:
            i = r.instrucao
            linhas.append(f"  recomendação {i.recomendacao} · quantidade {i.quantidade_diarias} · valor {i.valor_total}"
                          f" · autorização superior {i.exige_autorizacao_superior}")
            linhas += [f"  {v.criterio}: {v.situacao} · {v.detalhe}" for v in i.verificacoes]
            linhas += [f"  alerta: {a}" for a in i.alertas] + [f"  pendência: {p}" for p in i.pendencias]
            linhas.append(f"  minuta: {i.minuta_despacho}")
        linhas.append(f"  gabarito: {esperado['recomendacao']} · {esperado['quantidade_diarias']} · "
                      f"{esperado['valor_total']} · não atende {esperado['criterios_nao_atendidos']}")
        linhas.append("")
    saida = RAIZ / "resultados" / f"etapa3_casos{'_paralelas' if paralelas else ''}.txt"
    saida.write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
