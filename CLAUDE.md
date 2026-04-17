# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProofDive Backend — an AI-powered behavioral interview platform using Streamlit, LangGraph, and OpenAI. A virtual interviewer (Alex) conducts structured behavioral interviews using the CAR framework (Context, Action, Result), evaluates candidates across four competency drivers (Thinking, Action, People, Mastery), and generates detailed evaluation reports.

The architecture is a **supervisor-style LangGraph** where an LLM orchestrator runs at the top of every turn and picks the next agent. There are no Python helper tools — each node mutates state inline. The state itself is tiny (`config`, `phase`, `history`, `next_action`, `final_report`) and everything else (probe count, CAR progress) is derived from `history` on the fly.

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: Poetry (installed into conda env `pdive`)
- **UI Framework**: Streamlit
- **Agent framework**: LangGraph (supervisor pattern)
- **LLM**: OpenAI API (gpt-5.4-mini)
- **Testing**: pytest

## Commands

```bash
# Run the app
poetry run streamlit run app/main.py

# Run all tests
poetry run pytest tests/ -v
```

## Architecture

```
app/
├── main.py                     # Streamlit entry point
├── config.py                   # Environment variable loading
├── graph/
│   ├── state.py                # Slim InterviewState TypedDict + new_state()
│   ├── graph.py                # Supervisor graph: orchestrator is entry; car_agent loops back
│   └── nodes/
│       ├── orchestrator.py     # LLM picks next_action; no validator, no fallback
│       ├── phase_agents.py     # 6 phase agents — same one handles opener + probe
│       ├── car_agent.py        # CAR verdict → appended as history entry
│       └── report_agent.py     # Final report in one LLM call (reuses evaluator prompt)
├── services/
│   ├── llm.py                  # OpenAI client + token tracking
│   ├── evaluator.py            # _format_transcript helper (reused by report_agent)
│   └── candidate.py            # Demo mode: simulated candidate answers
├── ui/
│   ├── components.py           # Badges, CAR indicators
│   └── screens.py              # login, intake, chat, report
└── prompts/
    ├── phases/                 # Per-phase prompts (01_intro…06_close)
    ├── orchestrator/           # Orchestrator system prompt + action vocabulary
    ├── candidate/              # Candidate persona prompts (normal, strong)
    └── evaluator/              # Rubric consumed by report_agent
tests/
    └── test_graph.py           # Smoke tests with mocked LLM
```

## Key Concepts

- **Single decision point**: the orchestrator runs at the start of every turn and picks exactly one action: `intro | thinking | action | people | mastery | close | car_agent | report | end`.
- **car_agent loops back to orchestrator**: after judging, the orchestrator re-evaluates and decides probe-vs-advance. Every other node ends the turn.
- **History is the source of truth**: CAR verdicts, probe counts, and phase progression are all derived from the mixed stream of `assistant`, `user`, and `car_judge` entries in `history`.
- **Trust the LLM**: no deterministic fallback or output validator. If the orchestrator returns malformed JSON, the graph defaults to `"end"`. Iteration happens on the prompt, not on Python guardrails.

## Environment Variables

Requires a `.env` file with:
- `OPENAI_API_KEY` — OpenAI API key
- `APP_USERNAME` — Login username
- `APP_PASSWORD` — Login password
