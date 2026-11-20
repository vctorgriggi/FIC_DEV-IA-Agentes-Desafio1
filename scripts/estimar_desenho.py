"""Etapa 1: as contas do desenho, feitas antes de existir agente.

Conta, com o tokenizador o200k_base, o que entra na primeira chamada ao modelo
(regras da norma, esquemas das ferramentas, esquema da saída e pedido), aplica a
confiabilidade composta aos cenários de passos e estima custo por pedido e por
mês. Grava tudo em resultados/etapa1_estimativa.txt, que a Etapa 6 confronta com
o medido.

Uso: python scripts/estimar_desenho.py   (sem chave de API)
"""
import json
import pathlib
import sys

import tiktoken

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from diarias.esquema import Instrucao, Verificacao  # noqa: E402  (depende do sys.path acima)

DADOS = RAIZ / "exemplos" / "dados"
SAIDA = RAIZ / "resultados" / "etapa1_estimativa.txt"
ENC = tiktoken.get_encoding("o200k_base")  # aproximação: o tokenizador do gpt-5.6 não é público

VOLUME_MENSAL = 300                  # premissa do AGENTS.md: o enunciado diz "centenas"
PRECO_ENTRADA = 0.20 / 1_000_000     # US$ por token, developers.openai.com/api/docs/pricing, nov/2026
PRECO_SAIDA = 1.20 / 1_000_000
REFERENCIA_1A_CHAMADA = 2060         # execução de referência citada no enunciado
DELTA_POR_PASSO = (90, 150)          # idem: o que cada passo seguinte acrescenta
ORDEM_E_PROIBICOES = 250             # premissa: texto da instrução além da norma, ainda não escrito
SAIDA_POR_CHAMADA_DE_FERRAMENTA = 40 # premissa: nome da função e argumentos em JSON

# Docstring do enunciado (Etapa 2), usada como tamanho típico de uma ferramenta.
FERRAMENTA_EXEMPLO = {
    "type": "function",
    "function": {
        "name": "consultar_saldo_diarias",
        "description": (
            "Consulta o saldo da dotação de diárias de uma unidade e o compara com o valor pedido.\n\n"
            "Use depois de calcular o valor total das diárias. `unidade` é a sigla da\n"
            "unidade de lotação devolvida pelo cadastro, como CFF ou GAB; `valor` é o\n"
            "total em reais, com ponto decimal, como 980.0. Devolve o saldo disponível e\n"
            "a indicação de saldo suficiente ou insuficiente para o pedido."),
        "parameters": {"type": "object", "properties": {
            "unidade": {"type": "string"}, "valor": {"type": "number"}},
            "required": ["unidade", "valor"]},
    },
}

# Saída plausível de um pedido apto, só para medir o tamanho da resposta final.
SAIDA_EXEMPLO = Instrucao(
    numero_pedido="DIA-2026-0101", matricula="204317", quantidade_diarias=3.5, valor_total=980.0,
    verificacoes=[Verificacao(criterio=c, situacao="atende", detalhe=d) for c, d in [
        ("cadastro", "Matrícula 204317, Ana Paula Figueiredo, Fiscal Ambiental, grupo B, unidade CFF."),
        ("dados_completos", "Destino, datas de partida e retorno e justificativa informados."),
        ("antecedencia", "Pedido em 2026-10-08, partida em 2026-11-09: 32 dias (mínimo 10, art. 5º)."),
        ("prestacao_contas", "Sem prestação pendente; última entregue em 2026-09-28 (art. 7º)."),
        ("limite_mensal", "0 diárias em 2026-11 + 3,5 pedidas = 3,5, abaixo de 10 (art. 6º)."),
        ("saldo_orcamentario", "Saldo da CFF R$ 18.400,00, suficiente para R$ 980,00 (art. 8º)."),
    ]],
    recomendacao="apto_para_autorizacao", exige_autorizacao_superior=False, pendencias=[], alertas=[],
    minuta_despacho=("Instruído o pedido DIA-2026-0101, de Ana Paula Figueiredo, matrícula 204317, para "
                     "Sinop/MT, de 2026-11-09 a 2026-11-12: 3,5 diárias, R$ 980,00. Atendidos os arts. 5º "
                     "a 8º da IN SEMA nº 07/2026. Encaminhe-se ao ordenador de despesa para deliberação."),
)

# Passos = chamadas ao modelo. Cadeia: cadastro dá o grupo e a unidade; o cálculo dá o valor;
# o saldo precisa do valor; o histórico só precisa da matrícula e do mês, que estão no pedido.
CENARIOS = {
    "sequencial (paralelas desligadas)": ["cadastro", "historico", "calculo", "saldo", "resposta"],
    "paralelo (cadastro + historico juntos)": ["cadastro+historico", "calculo", "saldo", "resposta"],
    "diligencia (para no cadastro)": ["cadastro", "resposta"],
}


def tokens(texto: str) -> int:
    return len(ENC.encode(texto))


def main() -> None:
    norma = tokens((DADOS / "normas.md").read_text(encoding="utf-8"))
    ferramenta = tokens(json.dumps(FERRAMENTA_EXEMPLO, ensure_ascii=False))
    esquema = tokens(json.dumps(Instrucao.model_json_schema(), ensure_ascii=False))
    pedidos = [tokens(json.dumps(p, ensure_ascii=False))
               for p in json.loads((DADOS / "pedidos.json").read_text(encoding="utf-8"))]
    pedido_medio = round(sum(pedidos) / len(pedidos))
    resposta_final = tokens(SAIDA_EXEMPLO.model_dump_json())

    instrucao = norma + ORDEM_E_PROIBICOES
    base = instrucao + 4 * ferramenta + esquema + pedido_medio
    linhas = ["ETAPA 1 · ESTIMATIVA ANTES DO CÓDIGO (tokenizador o200k_base)", "",
              "Primeira chamada, por componente:",
              *(f"  {rotulo:<40}{valor:>6}{nota}" for rotulo, valor, nota in [
                  ("regras da norma (normas.md)", norma, ""),
                  ("ordem das consultas e proibições", ORDEM_E_PROIBICOES, "  (premissa)"),
                  (f"4 ferramentas ({ferramenta} cada)", 4 * ferramenta, ""),
                  ("esquema da saída (Instrucao)", esquema, ""),
                  (f"pedido (média de 12; {min(pedidos)} a {max(pedidos)})", pedido_medio, ""),
                  ("TOTAL estimado", base, ""),
                  ("referência do enunciado", REFERENCIA_1A_CHAMADA,
                   f"  (diferença {100 * (base - REFERENCIA_1A_CHAMADA) / REFERENCIA_1A_CHAMADA:+.0f}%)"),
              ]),
              f"Resposta final (Instrucao de um pedido apto): {resposta_final} tokens de saída", ""]

    linhas += ["Confiabilidade composta (p^n): probabilidade de os n passos darem certo",
               "  n   p=95%   p=99%"]
    linhas += [f"  {n}   {0.95 ** n:6.1%}  {0.99 ** n:6.1%}" for n in range(1, 9)]
    linhas.append("")

    linhas.append("Cenários (entrada da chamada k = base + (k-1)·Δ; Δ de 90 a 150 tokens):")
    custo_por_cenario = {}
    for nome, passos in CENARIOS.items():
        n = len(passos)
        faixa = []
        for delta in DELTA_POR_PASSO:
            entrada = n * base + delta * n * (n - 1) // 2
            saida = (n - 1) * SAIDA_POR_CHAMADA_DE_FERRAMENTA + resposta_final
            faixa.append((entrada, saida, entrada * PRECO_ENTRADA + saida * PRECO_SAIDA))
        custo_por_cenario[nome] = faixa
        (e0, s0, c0), (e1, _, c1) = faixa
        linhas.append(f"  {nome}: {n} passos · {' → '.join(passos)}")
        linhas.append(f"    confiabilidade {0.95 ** n:.1%} (95%) a {0.99 ** n:.1%} (99%) · entrada "
                      f"{e0}–{e1} · saída {s0} · US$ {c0:.5f}–{c1:.5f} por pedido")
    linhas.append("")

    # Mês pela composição do próprio acervo: 10 instruções completas, 2 diligências e
    # 2 complementações que refazem a cadeia, a cada 12 pedidos.
    seq = custo_por_cenario["sequencial (paralelas desligadas)"]
    dil = custo_por_cenario["diligencia (para no cadastro)"]
    for i, rotulo in enumerate(("Δ=90", "Δ=150")):
        por_12 = 10 * seq[i][2] + 2 * dil[i][2] + 2 * seq[i][2]
        linhas.append(f"Mês com {VOLUME_MENSAL} pedidos, sequencial, {rotulo}: "
                      f"US$ {por_12 / 12 * VOLUME_MENSAL:.2f}")
    passos_medios = (10 * 5 + 2 * 2 + 2 * 5) / 12
    for p in (0.95, 0.99):
        falhas = VOLUME_MENSAL * (1 - p ** 5)
        linhas.append(f"Instruções completas com algum passo errado por mês (p={p:.0%}, 5 passos): "
                      f"{falhas:.0f} de {VOLUME_MENSAL}")
    linhas.append(f"Passos por pedido na composição do acervo: {passos_medios:.2f}")

    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
