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
pip install -r requirements.txt
pytest -q
```

Copy `.env.example` to `.env` and set `GOOGLE_API_KEY` for Gemini (Google Generative AI) if you want real LLM processing.

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
