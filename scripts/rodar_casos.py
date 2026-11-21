"""Roda o agente de verdade (com a chave) nos 12 pedidos e nas 2 complementações e compara com o gabarito.

É script de medição: só ele e os testes abrem o gabarito, e o agente nunca o vê.
Usa a configuração de produção (histórico da sessão; a complementação vai na mesma
sessão do pedido). Grava em resultados/etapa3_casos.txt, caso a caso, o que a
barreira decidiu, as consultas, as verificações com o fundamento, os alertas, as
pendências e a minuta: é onde se vê como o agente tratou cada pegadinha do acervo.

Uso: python scripts/rodar_casos.py [números dos pedidos...] [--paralelas]
"""
import json
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias import barreira, memoria  # noqa: E402  (depende do sys.path acima)
from diarias.agente import criar_agente, instruir  # noqa: E402

DADOS = RAIZ / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}
GABARITO = json.loads((RAIZ / "exemplos" / "gabarito.json").read_text(encoding="utf-8"))


def matricula_esperada(pedido: dict, complementacao: dict | None) -> str:
    """A matrícula de quem pediu: a corrigida na complementação, se houver, senão a do pedido."""
    corrigida = barreira.MATRICULA.findall(str((complementacao or {}).get("texto", "")))
    return corrigida[0] if corrigida else str(pedido["matricula"])


def acertou(instrucao, esperado: dict, matricula: str | None = None) -> bool:
    """Igual ao gabarito e, quando `matricula` é dada, feita para essa pessoa."""
    if instrucao is None:
        return False
    if matricula is not None and instrucao.matricula != matricula:
        return False
    nao_atende = sorted(v.criterio for v in instrucao.verificacoes if v.situacao == "nao_atende")
    return (instrucao.recomendacao == esperado["recomendacao"]
            and instrucao.quantidade_diarias == esperado["quantidade_diarias"]
            and instrucao.valor_total == esperado["valor_total"]
            and instrucao.exige_autorizacao_superior == esperado["exige_autorizacao_superior"]
            and nao_atende == sorted(esperado["criterios_nao_atendidos"]))


def main() -> None:
    paralelas = "--paralelas" in sys.argv
    numeros = [a for a in sys.argv[1:] if a.startswith("DIA-")] or list(PEDIDOS)
    linhas = [f"ETAPA 3 · OS 12 PEDIDOS E AS 2 COMPLEMENTAÇÕES · memória: histórico da sessão · "
              f"paralelas={'ligadas' if paralelas else 'desligadas'}", ""]
    acertos = 0
    turnos = [(n, None) for n in numeros] + [(n, COMPLEMENTOS[n]) for n in numeros if n in COMPLEMENTOS]
    agentes = {}
    for numero, complementacao in turnos:
        if numero not in agentes:   # um banco por pedido: o turno da complementação reencontra a sessão
            db, _ = memoria.abrir_banco(f"medicao/casos/{numero}")
            agentes[numero] = criar_agente(paralelas=paralelas, db=db, **memoria.CONFIGURACOES["historico"])
        inicio = time.perf_counter()
        r = instruir(agentes[numero], PEDIDOS[numero], complementacao)
        segundos = time.perf_counter() - inicio
        m = r.resposta.metrics if r.resposta else None
        recebido = r.resposta.input.input_content_string() if r.resposta and r.resposta.input else ""
        esperado = GABARITO["complementacoes" if complementacao else "pedidos"][numero]
        certo = acertou(r.instrucao, esperado, matricula_esperada(PEDIDOS[numero], complementacao))
        acertos += certo
        linhas.append(f"## {numero}{' · complementação' if complementacao else ''} · {esperado.get('caso', '')}")
        if complementacao:
            linhas.append(f"texto da complementação: {complementacao['texto']}")
        linhas.append(f"barreira: {'APROVADA' if r.aprovada else 'RECUSADA'} · acerto contra o gabarito: "
                      f"{'sim' if certo else 'NÃO'} · "
                      f"{getattr(m, 'input_tokens', '?')} tokens de entrada, "
                      f"{getattr(m, 'output_tokens', '?')} de saída · {segundos:.1f} s")
        for motivo in r.motivos_da_recusa:
            linhas.append(f"  recusa: {motivo}")
        for t in (r.resposta.tools or []) if r.resposta else []:
            linhas.append(f"  consulta: {t.tool_name}({json.dumps(t.tool_args, ensure_ascii=False)})")
        if "052.318.947-20" in json.dumps(PEDIDOS[numero], ensure_ascii=False):
            vazou = "052.318.947-20" in recebido
            linhas.append(f"  CPF do pedido no que o modelo recebeu: {'SIM' if vazou else 'não'}")
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
    linhas.append(f"Acertos contra o gabarito: {acertos} de {len(turnos)}")
    saida = RAIZ / "resultados" / f"etapa3_casos{'_paralelas' if paralelas else ''}.txt"
    saida.write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
