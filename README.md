# ProofDive Interview Platform

An AI-powered behavioral interview platform that conducts structured interviews using the CAR framework (Context, Action, Result), evaluates candidates across four competency drivers, and generates detailed evaluation reports.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Streamlit UI (app/main.py)                                   │
│    └── invoke_turn(state) per user interaction                │
└───────────────┬───────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────┐
│  LangGraph Supervisor (app/graph/graph.py)                    │
│                                                               │
│  START → orchestrator ─┬── intro_agent ──────► END            │
│                        ├── thinking_agent ───► END            │
│                        ├── action_agent ─────► END            │
│                        ├── people_agent ─────► END            │
│                        ├── mastery_agent ────► END            │
│                        ├── close_agent ──────► END            │
│                        ├── car_agent ──► orchestrator (loop)  │
│                        ├── report_agent ─────► END            │
│                        └── end ──────────────► END            │
└───────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Model | Role |
|-------|-------|------|
| **Orchestrator** | gpt-5.4 | Routes every turn — decides which agent runs next |
| **Phase Agents** (intro, thinking, action, people, mastery, close) | gpt-5.4-mini | Ask interview questions and probes |
| **CAR Agent** | gpt-5.4 | Judges if candidate's answer has Context, Action, Result |
| **Report Agent** | gpt-5.4 | Three-step pipeline: extract evidence → score → generate report |

### Evaluation Pipeline

```
Transcript
    ↓
Evidence Extractor (gpt-5.4)
    → extracts direct candidate quotes per driver
    ↓
Scorer × 4 (gpt-5.4, temp=0.0)
    → one call per driver, classifies rubric level from quotes
    ↓
Python Score Computation
    → overall = mean(driver scores), labels, pass/fail
    ↓
Report Writer (gpt-5.4)
    → generates narrative: strengths, areas, coaching, verdict
```

### Key Files

```
app/
├── main.py                          # Streamlit entry point
├── config.py                        # Environment variables
├── model_config.py                  # Per-agent model + pricing config
├── graph/
│   ├── state.py                     # InterviewState TypedDict
│   ├── graph.py                     # LangGraph wiring
│   └── nodes/
│       ├── orchestrator.py          # LLM decision maker
│       ├── phase_agents.py          # 6 interview phase agents
│       ├── car_agent.py             # CAR framework evaluator
│       └── report_agent.py          # Evidence → Score → Report pipeline
├── services/
│   ├── llm.py                       # OpenAI Responses API client
│   ├── evaluator.py                 # Transcript formatter
│   └── candidate.py                 # Demo mode candidate simulator
├── ui/
│   ├── components.py                # Streamlit UI components
│   └── screens.py                   # Login, intake, chat, report screens
└── prompts/
    ├── phases/                      # Per-phase interviewer prompts
    ├── orchestrator/                # Orchestrator decision prompt
    ├── car/                         # CAR evaluation prompt
    ├── evaluator/                   # Rubric, scorer, evidence extractor, report writer
    └── candidate/                   # Demo candidate persona prompts
```

## Setup

### Prerequisites

- Python 3.12+
- OpenAI API key

### Option A: Using Poetry

```bash
# Clone the repo
git clone https://github.com/Ateeb-tkxel12/Proofdive_interview_poc.git
cd Proofdive_interview_poc

# Install dependencies
pip install poetry
poetry install

# Create .env file
cp .env.example .env
# Edit .env and add your keys

# Run
poetry run streamlit run app/main.py
```

### Option B: Using Conda + pip

```bash
# Clone the repo
git clone https://github.com/Ateeb-tkxel12/Proofdive_interview_poc.git
cd Proofdive_interview_poc

# Create conda environment
conda create -n pdive python=3.12 -y
conda activate pdive

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your keys

# Run
streamlit run app/main.py
```

## Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-key-here
APP_USERNAME=your_username
APP_PASSWORD=your_password
```

## Demo Mode

The app includes a demo mode with a simulated candidate. On the intake form:

1. Check **Demo Mode**
2. Set competency levels (1-5) for each driver using the sliders
3. The simulated candidate will answer at exactly those levels
4. The evaluation pipeline scores the answers against the rubric

## Model Configuration

Edit `app/model_config.py` to change which models each agent uses:

```python
AGENT_MODELS = {
    "orchestrator": {"model": "gpt-5.4", "temperature": None},
    "agent:thinking": {"model": "gpt-5.4-mini", "temperature": None},
    "report": {"model": "gpt-5.4", "temperature": 0.0},
    # ...
}
```

## Running Tests

```bash
pytest tests/ -v
```
