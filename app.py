"""Formulário de conferência: o servidor vê a instrução do agente, edita a minuta e registra a decisão.

Nada recusado pela barreira aparece aqui: recusa e falha de execução viram a
mensagem padrão e o pedido volta à análise manual. Um único agente fica em cache;
sessão e usuário vão em cada chamada, então pedidos não se misturam.

Uso: streamlit run app.py   (chama o modelo: precisa da chave no .env)
"""
import json
import sqlite3
from pathlib import Path

import streamlit as st

from diarias import agente as ag
from diarias import barreira, conferencia, guarda, memoria
from diarias.dados import carregar
from diarias.filtro import mascarar

DADOS = Path(__file__).resolve().parent / "exemplos" / "dados"
PEDIDOS = {p["numero"]: p for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))}
COMPLEMENTOS = {c["numero"]: c for c in json.loads((DADOS / "complementacoes.json").read_text(encoding="utf-8"))}
NOMES_NO_CADASTRO = {s["nome"] for s in carregar().servidores.values()}

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


def esquecer(numeros: list[str]) -> None:
    """Tira da tela o que saiu do banco: uma instrução eliminada não pode continuar visível nem conferível."""
    resultados = st.session_state.get("resultados", {})
    for numero in numeros:
        resultados.pop(numero, None)
        st.session_state.pop(f"complemento_{numero}", None)   # o texto da complementação também é do titular
        limpar_conferencia(numero)


def limpar_conferencia(numero: str, turno: str = "") -> None:
    """Uma instrução nova precisa de conferência nova: some o aviso de conferida da anterior."""
    for chave in [k for k in st.session_state if str(k).startswith(f"registrada_{numero}_{turno}")]:
        del st.session_state[chave]


def aplicar_prazo_de_guarda() -> None:
    """Apaga do banco os pedidos sem evento há 30 dias ou mais: conferência, recusa ou uso."""
    _, db, arquivo = recursos()
    try:
        apagados = guarda.expurgar(db, arquivo)
    except (memoria.EliminacaoIncompleta, sqlite3.Error, OSError) as erro:   # banco ocupado: tenta depois
        recursos.clear()
        esquecer(getattr(erro, "sessoes", []))   # o que já saiu do banco sai da tela também
        st.warning(f"O prazo de guarda não pôde ser aplicado agora e será tentado de novo: {erro}")
        return
    if apagados:
        recursos.clear()   # o banco foi fechado para compactar; o próximo uso reabre
        esquecer(apagados)
        st.toast(f"{len(apagados)} pedido(s) saíram do banco do agente (prazo de guarda vencido ou "
                 "eliminação que terminou agora).")
    try:   # a poda vem depois de tirar da tela o que saiu do banco: se ela falhar, nada fica conferível
        guarda.podar_recusas(banco=arquivo)
    except (sqlite3.Error, OSError) as erro:
        st.warning(f"O log de recusas não pôde ser podado agora e será tentado de novo: {erro}")


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
    st.caption(f"Instrução do pedido {i.numero_pedido} para a matrícula {i.matricula}.")
    digitada = PEDIDOS.get(i.numero_pedido, {}).get("matricula")
    if digitada and i.matricula != digitada:   # 0112: a barra lateral mostra a digitada, que é de outro servidor
        st.info(f"A matrícula da instrução ({i.matricula}) é a corrigida na complementação; a digitada no "
                f"pedido ({digitada}) não é a do solicitante.")
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
    registrada = f"registrada_{chave}"
    if registrada in st.session_state:   # já conferida: o formulário some, e um clique duplo não grava de novo
        st.success(st.session_state[registrada])
        return
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
                st.session_state[registrada] = (
                    f"Conferência registrada: {conferencia.ENCAMINHAMENTOS[linha['decidido']]}"
                    + (" (diverge da sugestão do agente)." if linha["divergiu"] else "."))
                st.rerun()


def aba_instrucao(pedido: dict) -> None:
    resultados = st.session_state.setdefault("resultados", {})
    numero = pedido["numero"]
    if st.button("Instruir pedido", type="primary"):
        limpar_conferencia(numero)
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
        limpar_conferencia(numero, "complemento")
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
    resultado_da_eliminacao()
    confirmar = st.checkbox("Confirmo que o titular pediu a eliminação dos seus dados",
                            key=f"confirma_eliminacao_{pedido['numero']}")   # não vale para outro pedido
    if st.button("Eliminar dados do titular", disabled=not confirmar):
        lista = [m.strip() for m in matriculas.split(",") if m.strip()]
        if " ".join(nome.split()) not in NOMES_NO_CADASTRO:
            # a busca é por trecho de texto: nome vazio apagaria tudo, e nome parcial, outras pessoas
            st.error("Informe o nome completo do titular, exatamente como está no cadastro.")
            return
        servidores = carregar().servidores
        de_outro = [m for m in lista if m in servidores and servidores[m]["nome"] != " ".join(nome.split())]
        if de_outro:   # no 0112 a digitada é de outro servidor: apagá-la apagaria os dados dele
            st.error(f"A matrícula {', '.join(de_outro)} é de outro servidor no cadastro e não entra na eliminação.")
            return
        _, db, arquivo = recursos()
        try:
            rel = memoria.eliminar_titular(db, arquivo, nome, lista,
                                           registros=[conferencia.LOG_RECUSAS, conferencia.ARQUIVO])
        except ValueError as erro:
            st.error(str(erro))
            return
        except (memoria.EliminacaoIncompleta, sqlite3.Error, OSError) as erro:
            esquecer(getattr(erro, "sessoes", []))   # o que já saiu do banco não pode seguir conferível
            st.session_state["eliminacao"] = {"erro": f"A eliminação não se completou: {erro}"}
        else:
            esquecer(rel.sessoes_apagadas)
            st.session_state["eliminacao"] = {
                "sucesso": f"Eliminação concluída: {len(rel.sessoes_apagadas)} sessão(ões), "
                           f"{rel.memorias_apagadas} memória(s) e {rel.linhas_de_registro_apagadas} linha(s) "
                           "de registro que citavam o titular apagadas.",
                "tabela": [{"Tabela": t, "Linhas com o titular antes": n, "Depois": rel.depois.get(t, 0)}
                           for t, n in rel.antes.items()]
                          or [{"Tabela": "—", "Linhas com o titular antes": 0, "Depois": 0}],
                "legenda": f"Sessões apagadas: {', '.join(rel.sessoes_apagadas) or 'nenhuma'} · texto do "
                           f"titular nos bytes do arquivo: {', '.join(rel.bytes_residuais) or 'nenhum'}"}
        finally:
            recursos.clear()   # o banco foi fechado para compactar; o próximo uso reabre
        # a aba Instrução já foi desenhada nesta rodada: só uma rodada nova a desenha sem o que saiu do banco
        st.rerun()


def resultado_da_eliminacao() -> None:
    """Mostra, na rodada seguinte ao clique, o que a eliminação fez."""
    feito = st.session_state.pop("eliminacao", None)
    if not feito:
        return
    if "erro" in feito:
        st.error(feito["erro"])
        return
    st.success(feito["sucesso"])
    st.table(feito["tabela"])
    st.caption(feito["legenda"])


def aba_conferencias() -> None:
    linhas = conferencia.ler()
    taxa = conferencia.taxa_de_divergencia()
    st.caption(f"Prazo de guarda: o banco do agente mantém cada pedido por {guarda.PRAZO_DIAS} dias depois "
               "da conferência ou da recusa (uso posterior recomeça a contagem); depois disso ele é apagado "
               "automaticamente. Pedido nunca conferido nem recusado fica até a eliminação pelo titular.")
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
