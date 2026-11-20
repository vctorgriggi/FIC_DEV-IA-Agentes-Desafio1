"""Etapa 4: custo da memória por turno, com as duas complementações, em três configurações.

Para cada configuração, um banco novo: o primeiro turno instrui o pedido e o
segundo envia só a complementação, na mesma sessão. Registra a entrada de cada
turno e se a complementação foi aplicada ao pedido certo (barreira aprovada e
instrução igual ao gabarito da complementação). No fim, instrui o DIA-2026-0104
num banco e confere se o CPF, a conta ou a agência chegaram aos bytes do arquivo.

Uso: python scripts/medir_memoria.py   (chama o modelo: precisa da chave no .env)
"""
import json
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias import memoria  # noqa: E402  (depende do sys.path acima)
from diarias.agente import criar_agente, instruir  # noqa: E402
from scripts.rodar_casos import acertou, matricula_esperada  # noqa: E402

DADOS = RAIZ / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}
GABARITO = json.loads((RAIZ / "exemplos" / "gabarito.json").read_text(encoding="utf-8"))
DADOS_PESSOAIS_0104 = ["052.318.947-20", "98765-4", "1234-5"]


def entrada(resultado) -> int | str:
    m = resultado.resposta.metrics if resultado.resposta else None
    return getattr(m, "input_tokens", "?")


def limpar(arquivo: pathlib.Path) -> None:
    for sufixo in ("", "-wal", "-shm"):
        pathlib.Path(f"{arquivo}{sufixo}").unlink(missing_ok=True)


def medir() -> dict:
    medicoes = {}
    for nome, config in memoria.CONFIGURACOES.items():
        db, arquivo = memoria.abrir_banco(f"medicao_{nome}")
        db.close()
        limpar(arquivo)
        db, arquivo = memoria.abrir_banco(f"medicao_{nome}")
        agente = criar_agente(db=db, **config)
        for numero in COMPLEMENTOS:
            inicio = time.perf_counter()
            t1 = instruir(agente, PEDIDOS[numero])
            t2 = instruir(agente, PEDIDOS[numero], COMPLEMENTOS[numero])
            certa = matricula_esperada(PEDIDOS[numero], COMPLEMENTOS[numero])
            aplicada = t2.aprovada and acertou(t2.instrucao, GABARITO["complementacoes"][numero], certa)
            medicoes[f"{nome} · {numero}"] = {
                "configuracao": nome, "pedido": numero,
                "entrada_turno_1": entrada(t1), "entrada_complementacao": entrada(t2),
                "turno_1": t1.instrucao.recomendacao if t1.instrucao else "recusada",
                "complementacao": t2.instrucao.recomendacao if t2.instrucao else "recusada",
                "aplicada_ao_pedido_certo": aplicada,
                "motivos_da_recusa": t2.motivos_da_recusa,
                "consultas_na_complementacao": [t.tool_name for t in (t2.resposta.tools or [])] if t2.resposta else [],
                "segundos": round(time.perf_counter() - inicio, 1),
            }
        medicoes[f"{nome} · memórias gravadas"] = len(db.get_user_memories())
        db.close()
    return medicoes


def cpf_no_banco() -> list[str]:
    db, arquivo = memoria.abrir_banco("medicao_historico")
    agente = criar_agente(db=db, **memoria.CONFIGURACOES["historico"])
    instruir(agente, PEDIDOS["DIA-2026-0104"])
    db.close()
    return memoria.bytes_residuais(arquivo, DADOS_PESSOAIS_0104)


def main() -> None:
    medicoes = medir()
    vazou = cpf_no_banco()
    linhas = ["ETAPA 4 · CUSTO DA MEMÓRIA POR TURNO (tokens de entrada)", "",
              f"{'configuração':24}{'pedido':16}{'turno 1':>9}{'complem.':>10}  turno 1 → complementação"]
    for chave, m in medicoes.items():
        if isinstance(m, dict):
            certo = "aplicada ao pedido certo" if m["aplicada_ao_pedido_certo"] else "NÃO aplicada"
            linhas.append(f"{m['configuracao']:24}{m['pedido']:16}{m['entrada_turno_1']:>9}"
                          f"{m['entrada_complementacao']:>10}  {m['turno_1']} → {m['complementacao']} · {certo}")
            linhas += [f"{'':40}recusa: {motivo}" for motivo in m["motivos_da_recusa"]]
            consultas = ", ".join(m["consultas_na_complementacao"]) or "nenhuma"
            linhas.append(f"{'':40}consultas na complementação: {consultas}")
        else:
            linhas.append(f"{chave}: {m}")
    linhas += ["", f"DIA-2026-0104 · CPF, conta ou agência nos bytes do banco: {vazou or 'nenhum'}"]
    (RAIZ / "resultados" / "etapa4_memoria.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (RAIZ / "resultados" / "etapa4_memoria.json").write_text(
        json.dumps({"medicoes": medicoes, "dados_pessoais_no_banco": vazou}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
