# Etapa 1 - Desenho do processo e quadro PEAS

Antes de escrever código, descreva o processo como o servidor o executa hoje, em etapas numeradas, e como o agente o executará. Especifique o agente pelo quadro PEAS da Aula 01, sigla de *Performance, Environment, Actuators, Sensors*, que reúne medida de desempenho, ambiente, atuadores e sensores. A medida de desempenho deve ser verificável contra o gabarito, porque é ela que a Etapa 6 mede.

Conte os passos do agente, considerando cada chamada ao modelo como um passo, e aplique a tabela de confiabilidade composta da Aula 01 com 95% e 99% por passo. Para o custo, estime a entrada da primeira chamada, que reúne instrução, esquemas das ferramentas, esquema da saída e pedido, e some o que cada passo acrescenta. Na execução de referência, a primeira chamada consumiu cerca de 2.060 *tokens* e cada passo seguinte acrescentou de 90 a 150, e a estimativa para cinco passos ficou a menos de 3% do medido.

Por fim, posicione o processo na grade de reversibilidade e tempo de detecção da Aula 01, Seção 5. Uma diária paga indevidamente pode ser devolvida, mas o erro costuma ser percebido apenas na auditoria, o que coloca o processo no quadrante em que o agente não age sozinho. Registre em `desenho.md` o processo, o quadro PEAS, as duas contas, o volume mensal adotado e o quadrante.
