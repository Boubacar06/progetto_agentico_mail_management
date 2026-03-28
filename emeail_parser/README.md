# Email Multi-Agent Classification & Routing (LangChain + LangGraph)

This project implements a multi-agent pipeline for processing incoming emails:

1. Spam Classification
2. Semantic Analysis (intent, tone, urgency)
3. Routing (HR, IT, Sales, etc.)

Agents share a central `SharedState` object updated at each step.

## Features

- Modular LangChain prompt templates
- LangChain Tools for parsing, CRM (stub), logging
- LangGraph-based flow with branching (spam shortcut)
- Extensible agent design with clear input/output contract
- Unit tests (agents + end-to-end)

## Quick Start

Install dependencies and run tests:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
```

Supported Python versions: 3.11 and 3.12.

Python 3.13 is not currently supported by this dependency set on Windows because `langchain==0.2.14` pulls `numpy<2`, which resolves to `numpy 1.26.4`. For Python 3.13 on Windows, pip does not get a prebuilt wheel for that NumPy version and falls back to a source build, which then requires a local C compiler toolchain.

Copy `.env.example` to `.env` and configure your preferred provider.

For local Ollama usage, set for example:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_FALLBACK_MODELS=mistral,deepseek-r1:14b
```

If the configured Ollama model is not installed, the runtime will automatically try the fallback models and then other locally available Ollama models before failing.

## Architecture

```text
src/email_agents/
  shared_state.py      # Pydantic model
  prompts.py           # PromptTemplate definitions
  tools/               # Tool implementations
  agents/              # Agent node logic
  graph.py             # LangGraph construction
  executor.py          # Orchestration wrapper
run.py                 # CLI entrypoint
```

## Extending

Add new department routing by updating `RouterAgent` mapping and tests.

## LLM Provider (Gemini)

This project defaults to Gemini via `langchain-google-genai`. Provide a `GOOGLE_API_KEY` to enable the real model (`gemini-1.5-flash`). If no key is present, a lightweight heuristic `DummyLLM` is used for local development.

## License

Internal / TBD.
