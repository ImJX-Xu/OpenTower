# 🏢 OpenTower V1.0

**5-Layer Multi-Agent Architecture for Zero-Intervention Closed-Loop Rate (ZICR)**

> From natural language intent to physical execution — an autonomous agent pipeline
> modeled as the "Empire State Building" of AI orchestration.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: DEFINITION                                        │
│  company.yaml → CEO / Worker / QA roles, prompts, budgets   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: ROUTING                                           │
│  EMPBus (asyncio) — millisecond intent_type dispatch        │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: PROTOCOL                                          │
│  EMPPacket JSON — trace_id, action, payload, token_budget   │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: AGENTS                                            │
│  CEO (decompose) → Worker (execute) → QA (verify)           │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: ACTIONS                                           │
│  shell_execute · github_create_issue · (extensible)         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
cd OpenTower
pip install -e ".[dev]"

# Configure LLM (default: LM Studio at localhost:1234)
export OPENAI_BASE_URL=http://localhost:1234/v1
export OPENAI_API_KEY=no-key

# Run
python -m opentower.main
```

## Message Flow

```
User Input
    │
    ▼
  [CEO] ──LLM──> decompose into tasks
    │
    ▼ (task_assign × N)
  [Worker] ──Action Registry──> execute
    │
    ▼ (task_result)
  [QA] ──static + LLM──> APPROVE / REJECT
    │                         │
    ▼                    (retry ≤ 2×)
  Output
```

## Project Structure

```
company.yaml          # Organization definition (3 agent nodes)
opentower/
├── schema/           # Layer 1 & 3: YAML parser + EMP protocol
├── bus/              # Layer 2: asyncio event bus
├── agents/           # Layer 4: CEO / Worker / QA
├── actions/          # Layer 5: shell, GitHub (extensible)
├── memory/           # SQLite state wall (full trace log)
├── llm/              # OpenAI-compatible client
└── main.py           # REPL entry point
```

## Requirements

- Python ≥ 3.11
- An OpenAI-compatible LLM endpoint (LM Studio, Ollama, or cloud)

## License

MIT
