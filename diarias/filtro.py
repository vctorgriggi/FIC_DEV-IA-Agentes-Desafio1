"""Filtro de dados pessoais aplicado ao pedido antes do modelo e do banco.

Os padrões norte-americanos do Agno ficam desligados: o de telefone casa com
números de pedido e datas, e o de cartão com sequências de algarismos que nada
têm de pessoal. Ficam dois padrões nossos e o de e-mail. O CPF é reconhecido
pela máscara, sem conferir dígito verificador (o acervo usa CPFs inválidos de
propósito). A conta e a agência têm o formato algarismos-hífen-dígito, que não
aparece em matrícula (seis algarismos), data (AAAA-MM-DD) nem número de pedido.
"""
import re

from agno.guardrails import PIIDetectionGuardrail

CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
CONTA_OU_AGENCIA = re.compile(r"\b\d{3,12}-[\dXx]\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def mascarar(texto: str) -> str:
    """Os mesmos padrões fora do agente: na tela e no texto livre que o conferente digita."""
    for padrao in (CPF, CONTA_OU_AGENCIA, EMAIL):
        texto = padrao.sub(lambda m: "*" * len(m.group()), texto)
    return texto


def criar_filtro() -> PIIDetectionGuardrail:
    return PIIDetectionGuardrail(
        mask_pii=True,                  # mascara e segue: o pedido continua sendo instruído
        enable_ssn_check=False,
        enable_credit_card_check=False,
        enable_phone_check=False,
        enable_email_check=True,
        custom_patterns={"CPF": CPF, "Conta ou agência bancária": CONTA_OU_AGENCIA},
    )
