"""Registro da conferência humana: o que o agente sugeriu e o que o servidor decidiu.

É o lugar físico da conferência. Cada linha guarda só o necessário para medir com
que frequência o servidor discorda do agente: número do pedido, sugestão, decisão,
motivo e se a minuta foi editada. A minuta em si não é gravada. O motivo é texto livre
do conferente: sai mascarado (CPF, conta, agência, e-mail), e a eliminação tira a linha
que cita o titular. Recusas da barreira não abrem conferência: vão para um log à parte,
com os motivos, que serve à medição e conta para o prazo de guarda, e nunca vai
para a tela.
"""
import json
from datetime import datetime
from pathlib import Path

from diarias.filtro import mascarar
from diarias.memoria import PASTA_BANCOS

ARQUIVO = PASTA_BANCOS / "conferencias.jsonl"
LOG_RECUSAS = PASTA_BANCOS / "recusas.jsonl"

ENCAMINHAMENTOS = {
    "apto_para_autorizacao": "Encaminhar ao ordenador como apto para autorização",
    "nao_recomendado": "Encaminhar ao ordenador com recomendação contrária",
    "diligencia": "Devolver ao solicitante em diligência",
    "analise_manual": "Reter para análise manual",
}


def _gravar(arquivo: Path, linha: dict) -> None:
    arquivo.parent.mkdir(exist_ok=True)
    with open(arquivo, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def registrar(numero: str, sugerido: str, decidido: str, motivo: str = "", minuta_editada: bool = False,
              arquivo: Path | None = None) -> dict:
    """Grava a decisão do conferente. Divergir do agente exige motivo."""
    if decidido not in ENCAMINHAMENTOS:
        raise ValueError(f"encaminhamento desconhecido: {decidido}")
    divergiu = decidido != sugerido
    if divergiu and not motivo.strip():
        raise ValueError("decisão diferente da sugerida pelo agente exige o motivo")
    linha = {"pedido": numero, "sugerido": sugerido, "decidido": decidido, "divergiu": divergiu,
             "motivo": mascarar(motivo.strip()), "minuta_editada": minuta_editada,
             "registrado_em": datetime.now().isoformat(timespec="seconds")}
    _gravar(arquivo or ARQUIVO, linha)
    return linha


def registrar_recusa(numero: str, motivos: list[str], arquivo: Path | None = None) -> None:
    _gravar(arquivo or LOG_RECUSAS, {"pedido": numero, "motivos": motivos,
                      "registrado_em": datetime.now().isoformat(timespec="seconds")})


def ler(arquivo: Path | None = None) -> list[dict]:
    arquivo = arquivo or ARQUIVO
    if not arquivo.exists():
        return []
    linhas = []
    for linha in arquivo.read_text(encoding="utf-8", errors="replace").splitlines():   # byte cortado não derruba
        try:
            linhas.append(json.loads(linha))
        except json.JSONDecodeError:   # linha corrompida (gravação interrompida): pula, não derruba a tela
            continue
    return [x for x in linhas if isinstance(x, dict)]


def taxa_de_divergencia(arquivo: Path | None = None) -> float | None:
    """Fração das conferências em que o servidor decidiu diferente do agente."""
    linhas = ler(arquivo)
    return sum(bool(linha.get("divergiu")) for linha in linhas) / len(linhas) if linhas else None
