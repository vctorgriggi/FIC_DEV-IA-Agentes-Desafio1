# Problema

A Coordenadoria de Diárias e Passagens da Secretaria de Estado de Meio Ambiente de Mato Grosso (SEMA-MT) recebe, todo mês, centenas de pedidos de diárias de fiscais, analistas e motoristas que se deslocam ao interior. Cada pedido é instruído por um servidor que consulta o cadastro funcional, o histórico de diárias e de prestações de contas, a tabela de valores e o saldo da dotação da unidade. Só depois dessa conferência o processo segue ao ordenador de despesa, que defere ou indefere.

Os erros desse trabalho raramente aparecem no dia em que são cometidos. Uma diária concedida a quem tem prestação de contas vencida ou um pedido urgente aceito sem a autorização escrita exigida pela norma costumam ser descobertos meses depois, na auditoria. Além disso, muitos pedidos chegam incompletos, voltam ao solicitante em diligência e retornam com a complementação, quando o servidor precisa reconstituir o caso desde o começo.

A pergunta que este desafio responde é se um único agente construído com o Agno, o framework das Aulas 06 e 07, consegue instruir esses pedidos de ponta a ponta, deixando a decisão a quem assina. A resposta exige reunir o que as sete primeiras aulas ensinaram: a aritmética dos passos, ferramentas, saída estruturada, barreiras de verificação, memória com eliminação verificável e um formulário de conferência. O processo foi escolhido porque é regido por regras escritas, repete-se em grande volume e depende de várias fontes, condições em que um agente ajuda sem decidir no lugar de ninguém.

## Objetivos

- Integrar em um único agente Agno as ferramentas, a saída estruturada, os limites de execução, o filtro de dados pessoais e a memória persistente estudados nas Aulas 01 a 07
- Especificar o processo pelo quadro PEAS (medida de desempenho, ambiente, atuadores e sensores) e estimar, antes de qualquer código, sua confiabilidade composta e do número de passos
- Escrever ferramentas sobre os dados do órgão com docstring que funcione como especificação, testando-as sem modelo
- Implementar e verificar a rotina de eliminação dos dados do servidor guardados pelo agente
- Medir o agente contra um gabarito, em acertos, *tokens* (as unidades de texto que o provedor cobra), tempo e custo, e provocar seus modos de falha
- Entregar o agente ao servidor em um formulário, com o ponto de conferência humana justificado por medição
