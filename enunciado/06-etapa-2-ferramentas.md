# Etapa 2 - Ferramentas sobre os dados do órgão

Escreva de três a quatro ferramentas como funções Python comuns, cada uma substituindo uma consulta que o servidor faz à mão, como cadastro, histórico do mês, cálculo das diárias e saldo da unidade. A docstring precisa dizer quando usar a ferramenta, o que ela devolve e em que formato espera os argumentos, conforme a Aula 06, Seção 5.1. Ela é a única parte da função que o modelo lê.

Duas regras de projeto orientam a etapa. A primeira é a minimização: o cadastro tem CPF e e-mail, que a instrução não usa, e a ferramenta não deve devolvê-los ao modelo. A segunda é que as contas ficam no código, porque a aritmética é onde o modelo erra com segurança, de modo que antecedência, quantidade, saldo do mês e comparação com o saldo da unidade saem prontos. A ferramenta do saldo, por exemplo:

```
def consultar_saldo_diarias(unidade: str, valor: float) -> str:
    """Consulta o saldo da dotação de diárias de uma unidade e o compara com o valor pedido.

    Use depois de calcular o valor total das diárias. `unidade` é a sigla da
    unidade de lotação devolvida pelo cadastro, como CFF ou GAB; `valor` é o
    total em reais, com ponto decimal, como 980.0. Devolve o saldo disponível e
    a indicação de saldo suficiente ou insuficiente para o pedido.
    """
    sigla = unidade.strip().upper()
    if sigla not in UNIDADES:
        return f"Unidade '{unidade}' não localizada. Siglas válidas: {', '.join(UNIDADES)}."
    saldo = UNIDADES[sigla]["saldo_diarias"]
    situacao = "suficiente" if saldo >= float(valor) else "INSUFICIENTE"
    return f"Saldo da unidade {sigla}: R$ {saldo:.2f}. Saldo {situacao} para R$ {valor:.2f} (art. 8º)."
```

Teste cada ferramenta sem agente e sem chave, como o `ferramentas_comuns.py` da Aula 06, com casos dos próprios pedidos: a matrícula trocada do `DIA-2026-0112`, a prestação vencida do `DIA-2026-0108`, a meia diária do `DIA-2026-0103` e o saldo do `DIA-2026-0110`. Um erro dentro da função aparece depois como resposta estranha do agente, difícil de localizar. Guarde a saída do teste como evidência de que as contas estão certas antes de o modelo entrar.
