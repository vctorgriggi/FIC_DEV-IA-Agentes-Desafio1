# Desenho do processo · Etapa 1

Instrução de pedidos de diárias da SEMA-MT (IN SEMA nº 07/2026, hipotética). Os números deste
documento saem de `scripts/estimar_desenho.py`, gravados em `resultados/etapa1_estimativa.txt`,
e são estimativas feitas antes de existir agente: a Etapa 6 confronta cada um com o medido.

## 1. O processo hoje, como o servidor o executa

1. Recebe o pedido protocolado: matrícula, nome, destino, datas, transporte e justificativa.
2. Confere se o pedido está completo (art. 9º). Faltando dado, devolve em diligência.
3. Consulta o cadastro funcional: a matrícula existe e o nome confere; anota grupo do cargo e
   unidade de lotação. Divergência também é diligência (art. 9º).
4. Calcula a antecedência entre o protocolo e a partida (mínimo de 10 dias corridos, art. 5º). Se
   for menor, lê a justificativa para decidir se há urgência legítima (§ 1º) e se a autorização
   escrita do Secretário Adjunto existe ou precisa ser pedida (§ 2º).
5. Calcula a quantidade de diárias (uma por pernoite e meia no retorno; sem pernoite, meia, art.
   4º) e o valor pela tabela do grupo e do destino (art. 3º e Anexo I).
6. Consulta o histórico: prestação de contas vencida impede (art. 7º); soma as diárias já
   concedidas no mês da partida às pedidas, com teto de 10 (art. 6º).
7. Consulta o saldo da dotação de diárias da unidade e o compara com o valor (art. 8º).
8. Redige a recomendação e a minuta do despacho e encaminha ao ordenador de despesa, que
   defere ou indefere (art. 10).
9. Na diligência, o pedido volta ao solicitante; quando a complementação chega, o servidor
   reconstitui o caso desde o passo 1.

## 2. O processo com o agente

1. A aplicação recebe o pedido e o passa pelo filtro de dados pessoais: CPF, conta, agência e
   e-mail são mascarados antes de chegar ao modelo e ao banco.
2. O agente roda com `session_id` = número do pedido e `user_id` = matrícula informada no pedido
   (no 0112, a digitada é de outro servidor; por isso a eliminação procura também pelo conteúdo).
3. O agente consulta as quatro ferramentas, que fazem todas as contas dos passos 3 a 7: cadastro,
   histórico do mês, cálculo das diárias e saldo da unidade. Ele julga só o que é texto: se a
   justificativa descreve urgência legítima e se há ordem embutida a sinalizar.
4. A saída é um objeto `Instrucao` validado (`diarias/esquema.py`), nunca texto livre.
5. Uma barreira em código confere a saída: a execução terminou sem erro; cada argumento das
   ferramentas é o do seu campo no pedido ou a correção da complementação; a matrícula é a que o
   cadastro conferiu; quantidade, valor e critérios numéricos são os das ferramentas; os valores,
   quantidades e datas do texto têm origem no pedido ou nas ferramentas; e a recomendação decorre
   das verificações.
   Recusada, o pedido volta à análise manual com a mensagem padrão.
6. O formulário mostra recomendação, verificações, alertas, pendências e consultas. O servidor
   confere, edita a minuta e registra a decisão dele ao lado da sugerida pelo agente.
7. O ordenador de despesa decide. O agente não defere, não indefere e não grava no processo.
8. Na diligência, a complementação entra na mesma sessão, e o agente recupera o caso pela memória.

## 3. Quadro PEAS

| | |
|---|---|
| **Medida de desempenho** | Por pedido, acerto é recomendação, quantidade, valor, `exige_autorizacao_superior` e conjunto de critérios "nao_atende" iguais ao `exemplos/gabarito.json`, para a matrícula certa. Mede-se nos 12 pedidos e 2 complementações, em 3 rodadas: taxa de acerto, tokens, tempo e custo por pedido. Restrição que vale mais que o acerto: **nenhuma** instrução chega ao conferente com dado que não veio do pedido, da complementação ou das ferramentas; erro visível (recusa com mensagem padrão) é preferível a erro silencioso. |
| **Ambiente** | Pedidos protocolados e complementações (`exemplos/dados/pedidos.json`, `exemplos/dados/complementacoes.json`); dados do órgão: cadastro, histórico de diárias e prestações, tabela de valores, saldos das unidades e a norma; data da análise fixa em 2026-10-09; o servidor conferente e o ordenador. É parcialmente observável (a urgência só existe no texto da justificativa), determinístico nas regras numéricas, sequencial dentro do pedido (diligência e complementação) e adversarial na entrada: dado pessoal colado na justificativa (0104), ordem dirigida ao sistema (0107) e matrícula de outra pessoa (0112). |
| **Atuadores** | Chamadas às quatro ferramentas, todas de leitura; o objeto `Instrucao` com verificações, recomendação, pendências, alertas e minuta; a gravação da sessão no banco do agente. Nenhum atuador altera o processo de diárias. |
| **Sensores** | O texto do pedido já filtrado, o retorno das ferramentas (sem CPF nem e-mail) e o histórico da sessão na complementação. |

## 4. Passos e confiabilidade composta

Cada chamada ao modelo é um passo. A ordem das ferramentas é forçada pelos dados: o cadastro dá
o grupo e a unidade, o cálculo precisa do grupo, o saldo precisa do valor calculado. O histórico
só precisa da matrícula e do mês, que estão no pedido, e por isso pode correr junto do cadastro.

| Cenário | Passos | p = 95% por passo | p = 99% por passo |
|---|---|---|---|
| Sequencial: cadastro → histórico → cálculo → saldo → resposta | 5 | 77,4% | 95,1% |
| Paralelo: (cadastro + histórico) → cálculo → saldo → resposta | 4 | 81,5% | 96,1% |
| Diligência: cadastro → resposta | 2 | 90,2% | 98,0% |

Na composição do acervo (10 instruções completas, 2 diligências e 2 complementações que refazem
a cadeia a cada 12 pedidos), a média é de 5,33 passos por pedido. Tratando os 300 pedidos do mês como instruções completas de
5 passos, espera-se que **68 instruções** (p = 95%) ou **15** (p = 99%) tenham algum passo errado. É
esse número, e não a média de acerto, que obriga a conferência humana.

## 5. Custo por passos

A entrada da chamada k é a da primeira chamada mais o que os passos anteriores acrescentaram
(Δ de 90 a 150 tokens por passo, faixa da execução de referência do enunciado).

| Primeira chamada, por componente | Tokens |
|---|---|
| Regras da norma (`exemplos/dados/normas.md`) | 642 |
| Ordem das consultas e proibições (premissa, texto ainda não escrito) | 250 |
| Quatro ferramentas, docstring e parâmetros (168 cada, pela docstring do enunciado) | 672 |
| Esquema da saída `Instrucao` | 495 |
| Pedido (média dos 12; de 123 a 179) | 136 |
| **Total estimado** | **2.195** |
| Referência do enunciado | 2.060 (+7%) |

A resposta final, um `Instrucao` de pedido apto, tem cerca de 446 tokens de saída; cada passo que chama
ferramenta acrescenta à saída cerca de 40 tokens (premissa): 606 no sequencial (4 passos com
ferramenta), 566 no paralelo (3) e 486 na diligência (1). Com os
preços do gpt-5.6-luna (US$ 0,20 por milhão de entrada e US$ 1,20 de saída, fonte: docs oficiais
OpenAI, developers.openai.com/api/docs/pricing, nov/2026):

| Cenário | Entrada | Saída | US$ por pedido |
|---|---|---|---|
| Sequencial (5 passos) | 11.875 a 12.475 | 606 | 0,00310 a 0,00322 |
| Paralelo (4 passos) | 9.320 a 9.680 | 566 | 0,00254 a 0,00262 |
| Diligência (2 passos) | 4.480 a 4.540 | 486 | 0,00148 a 0,00149 |

**Volume mensal adotado: 300 pedidos** (o enunciado diz "centenas"; premissa, não dado do
órgão). Sequencial, o mês custa de **US$ 1,00 a 1,04**, pela composição do acervo: a cada 12
pedidos, 10 instruções completas, 2 diligências e 2 complementações que refazem a cadeia (só 300
instruções completas dariam US$ 0,93 a 0,97). O custo não decide o desenho; a
confiabilidade e o ponto de conferência decidem.

Limites da estimativa: o tokenizador usado (o200k_base) é aproximação, porque o do gpt-5.6 não é
público; o texto que o Agno acrescenta ao prompt e a instrução de sistema ainda não existem; a
memória da sessão aumenta a entrada do turno da complementação e é medida na Etapa 4.

## 6. Quadrante de autonomia

Grade de reversibilidade e tempo de detecção (Aula 01, Seção 5, citada pelo enunciado; o texto da
Aula 01 não está neste repositório).

```
                    detecção imediata          detecção tardia
                 ┌─────────────────────────┬─────────────────────────┐
  reversível     │                         │   ● INSTRUÇÃO DE        │
                 │                         │     DIÁRIAS             │
                 ├─────────────────────────┼─────────────────────────┤
  irreversível   │                         │                         │
                 └─────────────────────────┴─────────────────────────┘
```

Uma diária paga indevidamente pode ser devolvida, então o erro é reversível. Mas ele costuma ser
percebido só na auditoria, meses depois. Esse é o quadrante em que o agente não age sozinho: ele
instrui, a barreira em código recusa o que não se sustenta, o servidor confere e registra a
decisão, e o ordenador decide.
