"""Formulário de conferência: o servidor vê a instrução do agente, edita a minuta e registra a decisão.

Nada recusado pela barreira aparece aqui: recusa e falha de execução viram a
mensagem padrão e o pedido volta à análise manual. Um único agente fica em cache;
sessão e usuário vão em cada chamada, então pedidos não se misturam.

Uso: streamlit run app.py   (chama o modelo: precisa da chave no .env)
"""
import json
from pathlib import Path

import streamlit as st

from diarias import agente as ag
from diarias import barreira, conferencia, guarda, memoria
from diarias.dados import carregar
from diarias.filtro import CONTA_OU_AGENCIA, CPF

DADOS = Path(__file__).resolve().parent / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}

ROTULO_CONSULTA = {
    "consultar_servidor": "Consultando o cadastro funcional",
    "consultar_historico_diarias": "Consultando prestações e diárias do mês",
    "calcular_diarias": "Calculando antecedência, quantidade e valor",
    "consultar_saldo_diarias": "Consultando o saldo da unidade",
}
ROTULO_RECOMENDACAO = {
    "apto_para_autorizacao": "Apto para autorização",
    "nao_recomendado": "Não recomendado",
    "diligencia": "Diligência",
}
ROTULO_CRITERIO = {
    "cadastro": "Cadastro", "dados_completos": "Dados completos", "antecedencia": "Antecedência",
    "prestacao_contas": "Prestação de contas", "limite_mensal": "Limite mensal",
    "saldo_orcamentario": "Saldo orçamentário",
}
SITUACAO = {"atende": "✅ atende", "nao_atende": "❌ não atende", "nao_verificado": "— não verificado"}


@st.cache_resource
def recursos():
    """Um agente e um banco por processo do Streamlit."""
    db, arquivo = memoria.abrir_banco("agente")
    return ag.criar_agente(db=db, **memoria.CONFIGURACOES["historico"]), db, arquivo


def aplicar_prazo_de_guarda() -> None:
    """Apaga do banco os pedidos conferidos há 30 dias ou mais (decisão do órgão)."""
    _, db, arquivo = recursos()
    try:
        apagados = guarda.expurgar(db, arquivo)
        guarda.podar_recusas()
    except memoria.EliminacaoIncompleta as erro:   # banco ocupado: tenta de novo na próxima interação
        recursos.clear()
        st.warning(f"O prazo de guarda não pôde ser aplicado agora e será tentado de novo: {erro}")
        return
    if apagados:
        recursos.clear()   # o banco foi fechado para compactar; o próximo uso reabre
        st.toast(f"Prazo de guarda: {len(apagados)} pedido(s) conferido(s) há {guarda.PRAZO_DIAS} dias ou "
                 "mais saíram do banco do agente.")


def mascarar(texto: str) -> str:
    return CONTA_OU_AGENCIA.sub(lambda m: "*" * len(m.group()), CPF.sub(lambda m: "*" * len(m.group()), texto))


def executar(pedido: dict, complementacao: dict | None = None) -> ag.Resultado:
    agente, _, _ = recursos()
    titulo = "Aplicando a complementação" if complementacao else "Instruindo o pedido"
    with st.status(f"{titulo} {pedido['numero']}…", expanded=True) as status:
        def ouvir(nome: str, _args: dict) -> None:
            status.write(f"{ROTULO_CONSULTA.get(nome, nome)}…")

        resultado = ag.instruir(agente, pedido, complementacao, ao_consultar=ouvir)
        if resultado.aprovada:
            status.update(label="Instrução pronta para conferência", state="complete", expanded=False)
        else:
            status.update(label="Instrução não aprovada", state="error", expanded=False)
            conferencia.registrar_recusa(pedido["numero"], resultado.motivos_da_recusa)
    return resultado


def mostrar_pedido(pedido: dict) -> None:
    st.sidebar.subheader("Pedido protocolado")
    st.sidebar.markdown(
        f"**{pedido['numero']}** · protocolo em {pedido['data_pedido']}  \n"
        f"{pedido['nome']} · matrícula {pedido['matricula']}  \n"
        f"{pedido['destino_municipio']}/{pedido['destino_uf']} · {pedido['data_partida']} a "
        f"{pedido['data_retorno'] or '(retorno não informado)'}  \n"
        f"Transporte: {pedido['transporte']}")
    st.sidebar.caption(mascarar(pedido["justificativa"]))


def mostrar_instrucao(resultado: ag.Resultado, chave: str) -> None:
    if not resultado.aprovada:
        st.error(barreira.MENSAGEM_PADRAO)
        return
    i = resultado.instrucao
    c1, c2, c3 = st.columns(3)
    c1.caption("Recomendação do agente")    # st.metric corta rótulos longos
    c1.markdown(f"### {ROTULO_RECOMENDACAO[i.recomendacao]}")
    c2.metric("Diárias", "—" if i.quantidade_diarias is None else f"{i.quantidade_diarias:g}".replace(".", ","))
    c3.metric("Valor total", "—" if i.valor_total is None else
              f"R$ {i.valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if i.exige_autorizacao_superior:
        st.warning("Exige autorização expressa e escrita do Secretário Adjunto (art. 5º, § 2º).")

    st.subheader("Verificações")
    st.table([{"Critério": ROTULO_CRITERIO[v.criterio], "Situação": SITUACAO[v.situacao], "Fundamento": v.detalhe}
              for v in i.verificacoes])
    for alerta in i.alertas:
        st.warning(alerta)
    for pendencia in i.pendencias:
        st.info(f"Pendência para o solicitante: {pendencia}")

    with st.expander("Consultas feitas pelo agente, com os argumentos e o retorno exato"):
        for t in resultado.resposta.tools or []:
            st.markdown(f"**{ROTULO_CONSULTA.get(t.tool_name, t.tool_name)}** · `{t.tool_name}`")
            st.code(json.dumps(t.tool_args, ensure_ascii=False), language="json")
            st.caption(t.result)

    st.subheader("Conferência")
    with st.form(f"conferencia_{chave}"):
        minuta = st.text_area("Minuta do despacho (editável)", value=i.minuta_despacho, height=180)
        opcoes = list(conferencia.ENCAMINHAMENTOS)
        decidido = st.radio("Encaminhamento decidido pelo servidor", opcoes,
                            index=opcoes.index(i.recomendacao), format_func=conferencia.ENCAMINHAMENTOS.get)
        motivo = st.text_input("Motivo (obrigatório quando a decisão diverge da sugestão do agente)")
        if st.form_submit_button("Registrar conferência"):
            try:
                linha = conferencia.registrar(i.numero_pedido, i.recomendacao, decidido, motivo,
                                              minuta_editada=minuta.strip() != i.minuta_despacho.strip())
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.success(f"Conferência registrada: {conferencia.ENCAMINHAMENTOS[linha['decidido']]}"
                           + (" (diverge da sugestão do agente)." if linha["divergiu"] else "."))


def aba_instrucao(pedido: dict) -> None:
    resultados = st.session_state.setdefault("resultados", {})
    numero = pedido["numero"]
    if st.button("Instruir pedido", type="primary"):
        resultados[numero] = {"pedido": executar(pedido)}
    atual = resultados.get(numero, {})
    if "pedido" not in atual:
        st.caption("Escolha um pedido na barra lateral e clique em Instruir pedido.")
        return

    mostrar_instrucao(atual["pedido"], f"{numero}_pedido")
    instrucao = atual["pedido"].instrucao
    if instrucao is None or instrucao.recomendacao != "diligencia":
        return

    st.divider()
    st.subheader("Complementação da diligência")
    st.caption("Enviada na mesma sessão do pedido: o agente recupera o caso pela memória.")
    campo = f"complemento_{numero}"
    if numero in COMPLEMENTOS and st.button("Preencher com a complementação recebida"):
        st.session_state[campo] = COMPLEMENTOS[numero]["texto"]
    texto = st.text_area("Texto da complementação", key=campo)
    if st.button("Enviar complementação") and texto.strip():
        complemento = {"numero": numero, "data": str(carregar().data_da_analise), "texto": texto.strip()}
        atual["complementacao"] = executar(pedido, complemento)
    if "complementacao" in atual:
        mostrar_instrucao(atual["complementacao"], f"{numero}_complemento")


def aba_eliminacao(pedido: dict) -> None:
    st.caption("Apaga do banco do agente, que é cópia de trabalho, as sessões, execuções e memórias do "
               "titular, e confere tabela por tabela e nos bytes do arquivo. O processo de diárias, "
               "registro de despesa pública, não é alcançado por esta rotina.")
    nome = st.text_input("Nome do titular", value=pedido["nome"])
    corrigida = COMPLEMENTOS.get(pedido["numero"], {}).get("texto", "")
    sugestao = barreira.MATRICULA.findall(corrigida) or [pedido["matricula"]]   # a corrigida, se houver
    matriculas = st.text_input("Matrículas do titular, separadas por vírgula", value=", ".join(sugestao))
    st.caption("Informe só matrículas do titular. No DIA-2026-0112 a digitada (207481) é de outro servidor.")
    confirmar = st.checkbox("Confirmo que o titular pediu a eliminação dos seus dados")
    if st.button("Eliminar dados do titular", disabled=not confirmar):
        _, db, arquivo = recursos()
        lista = [m.strip() for m in matriculas.split(",") if m.strip()]
        try:
            rel = memoria.eliminar_titular(db, arquivo, nome.strip(), lista,
                                           registros=[conferencia.LOG_RECUSAS, conferencia.ARQUIVO])
        except memoria.EliminacaoIncompleta as erro:
            st.error(f"A eliminação não se completou: {erro}")
        else:
            st.success(f"Eliminação concluída: {len(rel.sessoes_apagadas)} sessão(ões), "
                       f"{rel.memorias_apagadas} memória(s) e {rel.linhas_de_registro_apagadas} linha(s) "
                       "de registro que citavam o titular apagadas.")
            st.table([{"Tabela": t, "Linhas com o titular antes": n,
                       "Depois": rel.depois.get(t, 0)} for t, n in rel.antes.items()] or
                     [{"Tabela": "—", "Linhas com o titular antes": 0, "Depois": 0}])
            st.caption(f"Sessões apagadas: {', '.join(rel.sessoes_apagadas) or 'nenhuma'} · "
                       f"texto do titular nos bytes do arquivo: {', '.join(rel.bytes_residuais) or 'nenhum'}")
        finally:
            recursos.clear()   # o banco foi fechado para compactar; o próximo uso reabre


def aba_conferencias() -> None:
    linhas = conferencia.ler()
    taxa = conferencia.taxa_de_divergencia()
    st.caption(f"Prazo de guarda: o banco do agente mantém cada pedido por {guarda.PRAZO_DIAS} dias depois "
               "da última conferência; depois disso ele é apagado automaticamente.")
    st.metric("Conferências registradas", len(linhas),
              help="Cada linha é uma decisão do servidor ao lado da sugestão do agente.")
    if taxa is not None:
        st.metric("Decisões que divergiram do agente", f"{taxa:.0%}")
    if linhas:
        st.table(linhas)


def main() -> None:
    st.set_page_config(page_title="Instrução de diárias · SEMA-MT", layout="wide")
    st.title("Instrução de pedidos de diárias")
    st.caption("O agente instrui; o servidor confere; o ordenador de despesa decide (art. 10). Dados hipotéticos.")
    aplicar_prazo_de_guarda()
    numero = st.sidebar.selectbox("Pedido", list(PEDIDOS))
    pedido = PEDIDOS[numero]
    mostrar_pedido(pedido)
    instrucao, eliminacao, registros = st.tabs(["Instrução", "Eliminação de dados", "Conferências"])
    with instrucao:
        aba_instrucao(pedido)
    with eliminacao:
        aba_eliminacao(pedido)
    with registros:
        aba_conferencias()


main()
