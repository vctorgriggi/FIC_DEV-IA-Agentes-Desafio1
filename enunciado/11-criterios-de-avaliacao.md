# Critérios de Avaliação

A avaliação recai sobre os arquivos gerados e as medições, e não sobre a elegância do código:

| Critério | O que se observa |
|---|---|
| Funcionamento de ponta a ponta | Instrui os doze pedidos e as duas complementações sem intervenção manual e sem quebrar |
| Ferramentas e agente | Docstrings completas, contas no código, contrato Pydantic, limites, filtro configurado e verificação de `status` |
| Memória e eliminação | Identificadores corretos, custo por turno medido e rotina que comprova, no banco, que nada restou |
| Medição e falhas | Três rodadas contra o gabarito, comparação das chamadas paralelas e quatro falhas provocadas com honestidade |
| Formulário de conferência | Progresso visível, despacho editável, decisão do conferente registrada e mensagem padrão no erro |
| Desenho e relatório | Aritmética da Etapa 1 confrontada com o medido e ponto de conferência humana justificado |

**O que mais pesa negativamente:** uma instrução que chega ao conferente fundamentada em dado que não veio do pedido nem das ferramentas. Um agente que acerta onze casos e recusa três com a mensagem padrão vale mais que um que acerta treze e entrega o décimo quarto calculado para o servidor errado, porque o primeiro erra de forma visível.
