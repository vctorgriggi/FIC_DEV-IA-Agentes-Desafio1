# Etapa 5 - Formulário de conferência

Entregue o agente em uma aplicação Streamlit no padrão de formulário descrito na aula 06.

A tela mostra a recomendação, as verificações com o fundamento de cada uma, os alertas, as pendências e as consultas com os argumentos. A minuta do despacho fica em campo editável, e o servidor registra o encaminhamento que decidiu ao lado do que o agente sugeriu, com o motivo quando divergirem. Esse registro é o lugar físico da conferência humana e permitirá medir, com o uso, com que frequência o servidor discorda do agente.

Na diligência, a tela oferece um campo para a complementação, enviada na mesma sessão do pedido, e, em área separada, aciona a rotina de eliminação e mostra o que restou no banco. Se a execução falhar ou a verificação de argumentos recusar a instrução, a tela exibe uma mensagem padrão e devolve o pedido à análise manual. Nada do conteúdo recusado aparece ao servidor.
