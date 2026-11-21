# Desafio 01 · Instrução de pedidos de diárias

**Victor Griggi Moreira Regis da Silva** · FIC DEV IA, Agentes Autônomos

Um agente Agno instrui pedidos de diárias da SEMA-MT (dados e norma hipotéticos): consulta o
cadastro, o histórico, a tabela de valores e o saldo da unidade por quatro ferramentas, faz todas as
contas em código e devolve a instrução pronta para conferência. Uma barreira em código só deixa
chegar ao servidor instrução com dado de origem conferida; o servidor confere num formulário
Streamlit, e quem decide é o ordenador de despesa.

## Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| [`LEIA-ME.md`](LEIA-ME.md) | como executar, decisões técnicas e as respostas às perguntas do enunciado |
| [`relatorio.md`](relatorio.md) | os números medidos, as pegadinhas do acervo, as falhas provocadas e o ponto de conferência humana |
| [`desenho.md`](desenho.md) | a Etapa 1: o processo, o quadro PEAS, a confiabilidade composta, o custo por passos e o quadrante |
| [`enunciado/`](enunciado/README.md) | o enunciado transcrito do docx original (`Desafio-01-Instrucao-de-Pedidos-de-Diarias.docx`) |
| [`resultados/`](resultados/) | as saídas dos scripts e as telas do formulário em uso (`resultados/etapa5_telas/`) |
| `diarias/`, `app.py` | o agente, as ferramentas, a barreira, a memória e o formulário |
| `scripts/`, `tests/` | as medições, que chamam o modelo, e os testes, que não chamam |

## Para rodar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env          # preencha OPENAI_API_KEY; o .env não é versionado
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
.venv/bin/streamlit run app.py
```

O lock instala a partir do Python 3.12 (para 3.10 e 3.11, veja o LEIA-ME). Os demais comandos, e
quais deles chamam o modelo, estão no [`LEIA-ME.md`](LEIA-ME.md).
