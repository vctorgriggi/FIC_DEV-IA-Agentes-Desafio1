# LEIA-ME · Desafio 01, instrução de pedidos de diárias

Um agente Agno que recebe um pedido de diárias como foi protocolado e devolve a instrução pronta
para conferência: as verificações da norma, a quantidade e o valor, a recomendação e a minuta do
despacho. Quem confere é um servidor, num formulário Streamlit; quem decide é o ordenador de
despesa. Dados, servidores e norma são hipotéticos (`exemplos/dados/`).

O enunciado está em `enunciado/README.md`. Os números medidos e o ponto de conferência humana
estão em `relatorio.md`, e o desenho do processo em `desenho.md`.

## Como executar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env          # preencha OPENAI_API_KEY; o .env não é versionado
```

| Comando | O que faz | Chama o modelo? |
|---|---|---|
| `.venv/bin/ruff check . && .venv/bin/python -m pytest -q` | lint e os testes (ferramentas, filtro, barreira, eliminação, prazo de guarda, formulário) | não |
| `.venv/bin/python scripts/estimar_desenho.py` | contas da Etapa 1 | não |
| `.venv/bin/python scripts/testar_ferramentas.py` | as ferramentas nos casos do enunciado | não |
| `.venv/bin/streamlit run app.py` | o formulário de conferência | sim |
| `.venv/bin/python scripts/rodar_casos.py` | o agente em cinco pedidos-chave | sim |
| `.venv/bin/python scripts/medir_memoria.py` | custo da memória nas três configurações | sim |
| `.venv/bin/python scripts/eliminar_titulares.py` | eliminação das duas servidoras nos bancos da medição | não |
| `.venv/bin/python scripts/medir.py` | 3 rodadas contra o gabarito, chamadas paralelas desligadas e ligadas | sim |
| `.venv/bin/python scripts/provocar_falhas.py` | as quatro falhas provocadas | sim |
| `.venv/bin/python scripts/confrontar.py` | Etapa 1 contra o medido | não |

As saídas vão para `resultados/`. Os bancos do agente vão para `bancos/`, fora do git, porque
guardam dados pessoais.

## Como o sistema está dividido

- `diarias/regras.py`: as contas da norma, iguais às de `exemplos/gerar_dados.py`, que gera o gabarito.
- `diarias/ferramentas.py`: as quatro ferramentas que o agente chama. Fazem todas as contas e não
  devolvem CPF nem e-mail.
- `diarias/filtro.py`: mascara CPF, conta e agência antes de o texto chegar ao modelo e ao banco.
- `diarias/agente.py`: o agente, a instrução de sistema e a chamada que passa a resposta pela barreira.
- `diarias/barreira.py`: confere a resposta contra o pedido e contra o que as ferramentas devolveram.
- `diarias/memoria.py`: a memória por pedido e a rotina de eliminação.
- `diarias/conferencia.py` e `app.py`: o registro da conferência e o formulário.

## Decisões técnicas

- **Contas no código, julgamento no modelo.** Antecedência, quantidade, valor, prestação vencida,
  limite mensal e saldo saem prontos das ferramentas. O modelo só julga o que é texto: se a
  justificativa descreve urgência legítima, se há ordem embutida e a redação da minuta.
- **A barreira é código.** Toda matrícula e toda data usadas precisam constar do pedido ou da
  complementação. O grupo e a unidade usados vêm do cadastro, e quantidade e valor são os do
  cálculo. A situação de cada critério numérico precisa bater com o texto da ferramenta, e a
  recomendação e o sinal de autorização superior precisam decorrer das verificações. Recusa e
  erro de execução viram a mesma mensagem padrão.
- **Filtro de dados pessoais.** Os padrões norte-americanos do Agno ficam desligados, porque o de
  telefone casaria com números de pedido e datas. Entram dois padrões próprios: o CPF pela máscara,
  sem conferir dígito, e a conta ou agência pelo formato algarismos-hífen-dígito. Os testes mostram
  que, nos 12 pedidos, só o 0104 muda.
- **Data da análise fixa** (2026-10-09, de `tabela_diarias.json`), nunca a data de hoje, e dias
  úteis sem feriados, como o gabarito.
- **Python 3.15.** É o da máquina, e as dependências instalaram e importaram nele. O enunciado
  pede 3.10 ou superior.

## As perguntas do enunciado

O enunciado anuncia quatro perguntas e lista três. As três estão respondidas abaixo; a quarta
precisa ser confirmada com o professor.

**Que configuração de chamadas paralelas, teto de chamadas e memória você escolheu, e com base em
que número?**

- **Chamadas paralelas desligadas.** Desligadas, deram 84 acertos em 84 casos nas duas medições.
  Ligadas, cortam cerca de 11% do custo (US$ 0,0037 contra 0,0042 por pedido), mas todos os erros
  das duas medições aconteceram com elas: o sinal de autorização do 0107 nas duas e uma
  complementação sem cadastro.
- **Teto de 8 chamadas de ferramenta** (`tool_call_limit=8`). O máximo medido foi 4 consultas por
  turno e 5 chamadas ao modelo. O teto deixa folga para o modelo corrigir um argumento e impede um
  laço sem fim. Com teto 2 (falha provocada 4), a instrução fica incompleta e é recusada.
- **Memória: histórico da sessão com teto de 3 execuções, sem memórias do usuário.** Só com o
  histórico a complementação foi aplicada ao pedido certo (2 de 2; sem memória, 0 de 2). As memórias
  do usuário custaram de 11% a 77% a mais por turno sem acertar mais, e gravaram os dados de uma
  servidora sob a matrícula de outro (0112). Um pedido tem no máximo dois turnos, então 3 é folga.

**Como o sistema impede que uma instrução fundamentada em dado inventado chegue ao conferente?**

Em quatro camadas:

1. As contas não são do modelo: ele não tem número para inventar, porque o número vem pronto.
2. A barreira em código confere cada argumento e cada número contra o pedido e contra o retorno
   real das ferramentas, registrados pelo Agno. São 31 testes em `tests/test_barreira.py`, que montam execuções honestas
   e execuções com um dado inventado.
3. `resposta.status` é conferido antes de usar o conteúdo, e um erro da API vira recusa.
4. O que a barreira recusa não aparece na tela: o servidor vê a mensagem padrão e o pedido volta à
   análise manual.

A medição achou um caso que passava (o sinal de autorização do 0107). A barreira foi corrigida e a
medição refeita; depois dela, nenhum erro entregue em 84 casos (`relatorio.md`, seções 1 e 2).

**Que dados do servidor o agente guarda, por quanto tempo, e como o titular os elimina?**

- **O que fica guardado:**
  - **No banco do agente** (`bancos/agente.db`), por pedido: a sessão, as mensagens com o pedido já
    mascarado (sem CPF, conta e agência), as consultas às ferramentas com os retornos (cadastro sem
    CPF nem e-mail) e a instrução. Não há memórias do usuário, porque ficaram desligadas.
  - **No registro da conferência**: só o número do pedido, a sugestão, a decisão, o motivo e se a
    minuta foi editada.
  - **No log de recusas**: o número do pedido e os motivos internos da recusa.
- **Por quanto tempo:** 30 dias depois da última conferência do pedido. O prazo recomeça se o
  pedido for conferido de novo, depois de uma complementação. Vencido o prazo, o formulário apaga
  sozinho a sessão do pedido e as execuções, compacta o arquivo e confere que nada restou
  (`diarias/guarda.py`). O log de recusas, que pode citar matrículas, segue o mesmo prazo. O
  registro da conferência fica, porque não guarda dados do solicitante e é o que mede a
  discordância com o agente. Pedido nunca conferido fica até ser conferido ou até a eliminação
  pelo titular.
- **Como eliminar:** na aba "Eliminação de dados" do formulário, ou com a função
  `eliminar_titular`. A rotina apaga as sessões do titular (que levam junto as execuções) e as
  memórias, procurando pelo nome e pela matrícula no conteúdo de todas as tabelas, e não só pelo
  `user_id`. É isso que encontra a sessão do 0112, gravada sob a matrícula de outro servidor.
  Depois compacta o arquivo (`VACUUM` e checkpoint do WAL) e confere tabela por tabela e nos bytes.
  Se sobrar qualquer coisa, acusa erro em vez de declarar sucesso.
- **O que a eliminação não alcança:** o processo de diárias em si. Ele é registro de despesa
  pública, sujeito à transparência e à guarda das normas de prestação de contas.
