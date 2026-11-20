# Etapa 4 - Memória, custo por turno e eliminação

Ligue a memória com `SqliteDb`, `add_history_to_context` e um teto em `num_history_runs`, tratando cada pedido como uma sessão. O `session_id` é o número do pedido, e o `user_id` é a matrícula do solicitante, nunca a sigla da unidade. Informe os dois em cada chamada a `run`, e não na construção do agente, o que permite manter um único agente em cache no formulário sem misturar pedidos.

Meça o custo da memória com as duas complementações, em três configurações: sem memória, com o histórico da sessão e com o histórico acrescido das memórias do usuário (`update_memory_on_run`). Registre a entrada do primeiro turno, a do turno da complementação e se ela foi aplicada ao pedido certo.

Implemente a rotina de eliminação e teste-a com as duas servidoras que passaram por diligência. A rotina apaga as sessões do titular, que levam junto as execuções, lista e apaga as memórias com `delete_user_memories` e confere o banco tabela por tabela, procurando matrícula e nome. O pedido `DIA-2026-0112` mostra por que a conferência é obrigatória: a matrícula digitada pertence a outro servidor, a sessão fica gravada sob o identificador dele, e a busca pelo `user_id` da titular não a encontra.

A rotina alcança somente o banco do agente, que é cópia de trabalho. O processo de diárias é o registro de despesa pública, sujeito à transparência e à guarda das normas de prestação de contas, e a Lei Geral de Proteção de Dados Pessoais (LGPD).
