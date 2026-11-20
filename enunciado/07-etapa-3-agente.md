# Etapa 3 - Agente com saída estruturada, limites e filtro

Monte o agente com `output_schema`, declarando uma classe Pydantic que a tela e a medição leiam sem interpretar texto. O contrato mínimo tem os campos abaixo, e cada campo acrescentado deve existir porque alguém precisa lê-lo:

```
class Verificacao(BaseModel):
    criterio: Literal["cadastro", "dados_completos", "antecedencia", "prestacao_contas",
                      "limite_mensal", "saldo_orcamentario"]
    situacao: Literal["atende", "nao_atende", "nao_verificado"]
    detalhe: str            # o dado que fundamenta a situação, como veio da ferramenta


class Instrucao(BaseModel):
    numero_pedido: str
    matricula: str
    quantidade_diarias: Optional[float]   # nulo na diligência
    valor_total: Optional[float]          # nulo na diligência
    verificacoes: list[Verificacao]
    recomendacao: Literal["apto_para_autorizacao", "diligencia", "nao_recomendado"]
    exige_autorizacao_superior: bool
    pendencias: list[str]   # o que o solicitante precisa corrigir
    alertas: list[str]      # ordens embutidas, dados mascarados, o que o conferente precisa ver
    minuta_despacho: str
```

A instrução de sistema contém as regras da norma, a ordem das consultas e a proibição de calcular com dados supostos. Configure `tool_call_limit`, `telemetry=False` e `reasoning_effort="none"`, exigido pela família GPT-5.6 quando há ferramentas, e decida se as chamadas paralelas ficam ligadas. A decisão considera a Aula 06, Seção 4.3, porque o cálculo depende do grupo que vem do cadastro e o saldo depende do valor calculado.

Configure o `PIIDetectionGuardrail` com os padrões norte-americanos desligados, um para o CPF(não verifique se o CPF é válido, mas sim máscara válida) e outro para conta e agência bancária. A configuração está certa quando o CPF do `DIA-2026-0104` não chega ao modelo nem ao banco, e nenhuma matrícula, data ou número de pedido é mascarado. Confira também `resposta.status` antes de usar o conteúdo, como na Aula 06, Seção 5.3, para que um erro da API nunca seja tratado como instrução.

> **Atenção:** a barreira pertence ao código, e não ao *prompt*, o texto de instruções enviado ao modelo, conforme a Aula 01. Escreva uma verificação que confira os argumentos das ferramentas contra o pedido que a aplicação tem em mãos: toda matrícula consultada e toda data usada no cálculo precisam constar do pedido ou da complementação. A Etapa 4 mostra quando essa verificação passa a ser a única defesa.
