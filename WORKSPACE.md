# OpenTower Linux Ops

## Source of truth

- Runtime config: `org/system.yaml`
- Workflow catalog: `org/skills.yaml`
- Agent definitions: `.opentower/agents/*.md`
- Workflow definitions: `.opentower/skills/*/SKILL.md`
- CLI entrypoint: `python -m opentower_cli ...`

## Product surface

Only these user-facing commands are shipped:

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

Natural-language input is the default entrypoint. If the first token is not a known subcommand, the CLI routes it through `dispatch --execute`.

## Operating model

The repository is scoped to a fixed Linux operations workflow:

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

Routing is intentionally narrow:

- `local_rule`: deterministic parser for the shipped workflows
- `llm_normalizer`: remaps in-scope paraphrases onto existing operations only
- `fallback_research`: low-risk read-only recovery for `top_cpu`, `load_average`, `uptime_summary`, `tail_log`, `recent_error_scan`, and `service_status`

Out-of-scope examples remain unsupported:

- service restart/start/stop
- package management, deployment, and firewall changes
- arbitrary shell generation outside the fixed planner

Keep the repo aligned with that narrow surface. Do not reintroduce extra entrypoints or legacy governance/runtime layers.
