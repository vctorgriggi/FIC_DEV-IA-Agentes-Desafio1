# Requisitos

Este desafio integra o conteúdo das sete primeiras aulas do módulo. Vale rever, antes de começar:

| Assunto | Onde foi estudado |
|---|---|
| Quadro PEAS, confiabilidade composta, custo por passos e níveis de autonomia | Aula 01 |
| Saída estruturada com esquema declarado | Aula 02 |
| Ferramentas, critério de acerto, custo da cauda e modos de falha | Aula 03 |
| Erro que atravessa a cadeia e ancoragem numérica | Aula 04 |
| Conferência humana como etapa do fluxo | Aula 05 |
| Agente no Agno, docstring, chamadas paralelas, filtro de dados pessoais, erro devolvido pela interface de programação (API, *Application Programming Interface*) e formulário | Aula 06 |
| Histórico da sessão, identificadores, custo da memória e eliminação de dados | Aula 07 |

Ambiente sugerido: Python 3.10 ou superior, com Agno 3.0.9, `openai`, `python-dotenv`, `pydantic`, `streamlit` e `sqlalchemy[asyncio]`. A chave `OPENAI_API_KEY` fica no `.env` da raiz do repositório, lido com `load_dotenv`, e nunca aparece no código, no relatório nem na tela. O modelo de referência é o `gpt-5.6-luna`, o nível de menor custo da família GPT-5.6.

```
pip install agno openai python-dotenv pydantic streamlit "sqlalchemy[asyncio]"
```

> **Atenção:** a série 2.1 do `sqlalchemy` não instala o pacote `greenlet`, de que o `SqliteDb` do Agno depende, e a importação falha com "The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed". O alvo `sqlalchemy[asyncio]` traz a dependência.
