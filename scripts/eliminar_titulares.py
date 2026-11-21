"""Etapa 4: elimina, nos três bancos da medição de memória, as duas servidoras que passaram por diligência.

Usa os bancos gravados por scripts/medir_memoria.py, sem chamar o modelo. Para cada
banco mostra o que havia de cada titular, o que foi apagado e o que restou, tabela
por tabela e nos bytes do arquivo. Quem não pediu eliminação precisa continuar lá.

Uso: python scripts/eliminar_titulares.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias import memoria  # noqa: E402  (depende do sys.path acima)

TITULARES = [("Beatriz Moraes Cunha", ["206689"]),     # DIA-2026-0111
             ("Carla Regina Souza", ["207418"])]       # DIA-2026-0112: gravada sob 207481, do Rafael
OUTROS = ["Heitor Vasconcelos Lima"]                  # DIA-2026-0104, que não pediu eliminação


def main() -> None:
    linhas = ["ETAPA 4 · ELIMINAÇÃO DOS DADOS DAS TITULARES", ""]
    for nome_banco in ("medicao_historico_e_memorias", "medicao_historico", "medicao_sem_memoria"):
        db, arquivo = memoria.abrir_banco(nome_banco)
        if not arquivo.exists():
            raise SystemExit(f"{arquivo.name} não existe: rode antes scripts/medir_memoria.py")
        linhas.append(f"## {arquivo.name}")
        busca_carla = [s.session_id for s in db.get_sessions(user_id="207418")]
        linhas.append(f"busca da Carla pelo user_id 207418: {busca_carla or 'nenhuma sessão'}")
        # sob que user_id cada sessão e cada memória ficou gravada: o 0112 fica sob a matrícula digitada
        linhas.append("sessões no banco (session_id: user_id): " + ", ".join(
            f"{s.session_id}: {s.user_id}" for s in db.get_sessions()))
        memorias = db.get_user_memories() or []
        linhas.append("memórias no banco (user_id, cita a Carla?): " + (", ".join(
            f"{m.user_id}, {'sim' if 'Carla' in (m.memory or '') else 'não'}" for m in memorias) or "nenhuma"))
        for nome, matriculas in TITULARES:
            db, arquivo = memoria.abrir_banco(nome_banco)
            rel = memoria.eliminar_titular(db, arquivo, nome, matriculas)
            linhas += [f"{nome} ({', '.join(matriculas)})",
                       f"  antes:  {rel.antes}",
                       f"  sessões apagadas: {rel.sessoes_apagadas} · memórias apagadas: {rel.memorias_apagadas}",
                       f"  depois: {rel.depois or 'nenhuma linha'} · "
                       f"bytes residuais: {rel.bytes_residuais or 'nenhum'}"]
        for nome in OUTROS:
            linhas.append(f"{nome}, que não pediu eliminação: {memoria.ocorrencias(arquivo, [nome]) or 'ausente'}")
        linhas.append("")
    (RAIZ / "resultados" / "etapa4_eliminacao.txt").write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
