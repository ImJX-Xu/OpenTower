# OpenTower Linux Ops

OpenTower is a CLI-first Linux operations assistant that routes natural-language requests into a fixed, auditable workflow. This repository intentionally keeps the product surface narrow: a small set of Linux inspection and user-management tasks, model-assisted recovery for in-scope paraphrases, and explicit structured rejection for unsupported or risky requests.

## Command Surface

The shipped user-facing commands are:

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

Natural-language input is the default entrypoint:

```bash
python -m opentower_cli "show disk usage"
python -m opentower_cli "find nginx config files"
python -m opentower_cli "check sshd service status"
python -m opentower_cli "show cpu usage"
```

Slash-prefixed commands remain available:

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

## Routing Model

Requests move through a three-stage routing chain:

1. `local_rule`: deterministic parser for the shipped Linux ops workflows.
2. `llm_normalizer`: remaps in-scope paraphrases onto already-implemented operations.
3. `fallback_research`: low-risk, read-only recovery for a small set of runtime inspection tasks.

Every dispatch result now exposes:

- `resolution_status`
- `resolution_source`
- `resolution_reason`

This keeps unsupported behavior explicit instead of failing with a raw parser error.

## Supported Workflows

- `disk-inspection`
  - `disk_usage`
  - `disk_usage_with_logs`
- `file-search`
  - `filename_search`
  - `content_search`
  - `inspect_permissions`
  - `tail_log` (read-only fallback)
  - `recent_error_scan` (read-only fallback)
  - `delete_path` and `chmod_recursive` remain guarded by the security layer
- `process-port-inspection`
  - `port_lookup`
  - `top_memory`
  - `service_status`
  - `top_cpu` (read-only fallback)
  - `load_average` (read-only fallback)
  - `uptime_summary` (read-only fallback)
- `user-management`
  - `list_users`
  - `inspect_user`
  - `create_user` (confirmation required)
  - `add_user_to_group` (confirmation required)
  - `delete_user`
  - `batch_delete_users`

## Safety Policy

- High-risk writes are blocked or forced through explicit confirmation.
- User creation and group-membership changes now also route through confirmation instead of executing immediately.
- The fallback research path is read-only by design.
- Requests such as `restart nginx service`, `install nginx`, `reboot the machine`, and firewall/package-management actions remain unsupported.
- Log-tail requests no longer misroute into destructive permission-changing operations.
- Operation metadata and confirmation replay now share a centralized catalog and persisted execution context, which reduces drift across normalizer, fallback, and confirmation resolution.

## Provider Setup

Install the package in editable mode:

```bash
python -m pip install -e .[dev]
```

Create a local provider profile:

```bash
cp auth.example.json auth.json
```

On PowerShell:

```powershell
Copy-Item auth.example.json auth.json
```

Then edit `auth.json` and fill in the provider, model, API base URL, and API key you actually want to use.

Useful checks:

```bash
python -m opentower_cli auth
python -m opentower_cli provider-status
python scripts/run_nl_eval.py --fixture-profile core
python scripts/run_nl_eval.py --fixture-profile model --with-model --limit 20
python scripts/run_wsl_smoke.py
```

Notes:

- `auth.example.json` is the committed template.
- `auth.json` is local-only and already ignored by Git.
- For `openai-compatible` endpoints, OpenTower can auto-select a chat-capable model when `model` is omitted and the provider exposes `/models`. This helps with DeepSeek-compatible deployments.

## Example Requests

Direct natural-language entry:

```bash
python -m opentower_cli "show disk usage"
python -m opentower_cli "search for database in /etc"
python -m opentower_cli "check sshd service status"
python -m opentower_cli "show cpu usage"
python -m opentower_cli "show load average"
python -m opentower_cli "tail the latest syslog log"
```

Explicit dispatch:

```bash
python -m opentower_cli dispatch --objective "show cpu usage" --execute
python -m opentower_cli dispatch --objective "check sshd service status" --execute
python -m opentower_cli dispatch --objective "restart nginx service" --execute
```

The last example is expected to return `resolution_status: unsupported`.

## Verification

Current local verification for the `2026-04-26` snapshot:

- `python -m pytest -q` -> `95 passed`
- `python scripts/run_nl_eval.py --fixture-profile extended` -> `2009/2009 passed`
- `python scripts/run_nl_eval.py --fixture-profile core` -> `416/416 passed`
- `python scripts/run_nl_eval.py --fixture-profile model` -> `228/228 passed`
- `python scripts/run_nl_eval.py --fixture-profile model --with-model --limit 20` -> `20/20 passed`
- `python scripts/run_wsl_smoke.py` -> `10/10 passed`
- WSL real-execution rounded report derived from a completed 543-case run -> `499/500 passed`

## Repo Notes

- Commit `auth.example.json`, not `auth.json`.
- Runtime outputs under `production/` are local artifacts unless you intentionally want to version them.
- The NL eval corpus now ships as layered `extended / core / model` JSONL fixtures; expanding them is PR-able as evaluation coverage, while new runtime support should still be promoted through reviewed changes in the parser, normalizer, or fallback agent.
- Chinese project notes live in [README_CN.md](README_CN.md).
- The judge-facing design overview lives in [比赛版设计说明文档.md](比赛版设计说明文档.md).
