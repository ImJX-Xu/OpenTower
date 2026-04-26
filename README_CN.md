# OpenTower Linux Ops

OpenTower 是一个面向 Linux 运维场景的 CLI-first 助手。当前仓库刻意保持收敛，只保留一组固定、可审计的工作流：支持少量检查类和用户管理类任务，对语义接近但未命中本地规则的请求做模型归一化补救，并对越界或高风险请求给出结构化拒绝结果。

## 对外命令面

当前正式暴露的命令只有 5 个：

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

顶层 CLI 默认优先把自然语言当作执行目标处理：

```bash
python -m opentower_cli "查看磁盘使用情况"
python -m opentower_cli "找到所有 nginx 配置文件"
python -m opentower_cli "检查 sshd 服务状态"
python -m opentower_cli "show cpu usage"
```

显式命令模式仍然支持：

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

## 三层路由

当前自然语言路由链路为：

1. `local_rule`：本地确定性规则解析。
2. `llm_normalizer`：把同义改写重新映射回已实现操作。
3. `fallback_research`：只处理低风险只读补救场景。

所有 dispatch 结果都会带上：

- `resolution_status`
- `resolution_source`
- `resolution_reason`

这样即使请求不支持，也不会再直接掉到生硬的 parser error。

## 当前能力范围

- `disk-inspection`
  - `disk_usage`
  - `disk_usage_with_logs`
- `file-search`
  - `filename_search`
  - `content_search`
  - `inspect_permissions`
  - `tail_log`（只读 fallback）
  - `recent_error_scan`（只读 fallback）
  - `delete_path`、`chmod_recursive` 仍然受安全门控
- `process-port-inspection`
  - `port_lookup`
  - `top_memory`
  - `service_status`
  - `top_cpu`（只读 fallback）
  - `load_average`（只读 fallback）
  - `uptime_summary`（只读 fallback）
- `user-management`
  - `list_users`
  - `inspect_user`
  - `create_user`
  - `add_user_to_group`
  - `delete_user`
  - `batch_delete_users`

## 安全策略

- 高风险写操作要么直接阻断，要么进入二次确认。
- fallback research 只允许低风险只读动作，不负责写操作兜底。
- `restart nginx service`、`install nginx`、`reboot the machine`、防火墙/包管理/部署类请求仍然不在当前范围内。
- 类似“看日志”这类请求不再误路由到权限修改或删除操作。

## Provider 配置

安装开发依赖：

```bash
python -m pip install -e .[dev]
```

复制本地认证模板：

```bash
cp auth.example.json auth.json
```

如果在 PowerShell 下：

```powershell
Copy-Item auth.example.json auth.json
```

然后编辑仓库根目录的 `auth.json`，填入实际使用的 provider、model、API 地址和密钥。

常用检查命令：

```bash
python -m opentower_cli auth
python -m opentower_cli provider-status
```

说明：

- `auth.example.json` 是要提交到仓库的模板。
- `auth.json` 是本地生效文件，已经加入 `.gitignore`。
- 对 `openai-compatible` 端点，如果未显式填写 `model` 且提供了 `/models`，运行时会自动挑一个可用的 chat 模型。这一条对 DeepSeek 兼容接口尤其有用。

## 使用示例

自然语言直达：

```bash
python -m opentower_cli "查看磁盘使用情况"
python -m opentower_cli "搜索 /etc 下包含 database 的文件"
python -m opentower_cli "检查 sshd 服务状态"
python -m opentower_cli "show cpu usage"
python -m opentower_cli "show load average"
python -m opentower_cli "tail the latest syslog log"
```

显式 dispatch：

```bash
python -m opentower_cli dispatch --objective "show cpu usage" --execute
python -m opentower_cli dispatch --objective "check sshd service status" --execute
python -m opentower_cli dispatch --objective "restart nginx service" --execute
```

最后一个例子预期会返回 `resolution_status: unsupported`。

## 当前验证状态

针对 `2026-04-26` 快照，当前已验证：

- `python -m pytest -q` -> `81 passed`
- `python scripts/run_nl_eval.py` -> `509/509 passed`
- WSL 只读 smoke 已验证：
  - `show cpu usage`
  - `show load average`
  - `tail the latest syslog log`
  - `check sshd service status`
  - 安全拒绝：`restart nginx service`

## 提交说明

- 提交代码时保留 `auth.example.json`，不要提交 `auth.json`。
- `production/` 下的运行日志、转录、确认记录默认都按本地产物处理。
- 英文说明见 [README.md](README.md)。
