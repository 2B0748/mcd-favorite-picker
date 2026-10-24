# Agent 兼容性

本 Skill 的目标是**不绑定任何一家客户端**。三条路径保证覆盖面：

1. **MCP 直连**——客户端支持远程 MCP 时效果最好（能追问、能换店、能解释）。
2. **命令直跑**——`run_recommend.py` 一条命令出完整报告，不需要客户端懂 MCP。
3. **工具直调**——`mcp_client.py` 精确调用单个工具，供需要自己编排的 Agent 使用。

## 能力矩阵

| 客户端 | Skill 目录 | MCP 配置 | 工具名前缀 | 推荐路径 |
|---|---|---|---|---|
| WorkBuddy | `~/.workbuddy/skills/` | `~/.workbuddy/mcp.json` | `mcp__mcd-mcp__<tool>` | MCP 直连 |
| Claude Code | `~/.claude/skills/` | `claude mcp add` 或 `~/.claude.json` | `mcp__mcd-mcp__<tool>` | MCP 直连 |
| Cursor | 无原生 Skill 目录，放 `AGENTS.md` | `~/.cursor/mcp.json` 或 `.cursor/mcp.json` | 裸名 | MCP 直连 + AGENTS.md |
| Cherry Studio | 无 Skill 目录，读 `AGENTS.md` | 设置 → MCP 服务器 | 裸名 | MCP 直连 |
| Cline / Roo | 无 Skill 目录，读 `AGENTS.md` | 扩展内 MCP 设置 | 裸名 | MCP 直连 |
| Codex CLI | 读 `AGENTS.md` | `~/.codex/config.toml` | 裸名 | MCP 或 CLI |
| Zed | 读 `AGENTS.md` | `settings.json` → `context_servers` | 裸名 | MCP 或 CLI |
| Aider / 任意终端 Agent | 读 `AGENTS.md` | 不支持 | — | **命令直跑** |
| 任何 CI / 定时任务 | — | — | — | **命令直跑** |

> 各客户端的目录与配置键名会随版本变化，上表是常见位置。对不上时以你客户端当前文档为准，但**不需要改本项目的任何代码**——只要有 Python 3.10+，走「命令直跑」一定能用。

## 三条路径的取舍

| | MCP 直连 | 命令直跑 | 工具直调 |
|---|---|---|---|
| 需要客户端支持 MCP | 是 | 否 | 否 |
| 能追问 / 换店 / 解释 | 能 | 不能（一次一跑） | 由 Agent 自己编排 |
| 输出 | 对话里的自然语言 | 完整的 md 报告 | 原始工具文本 |
| 适合 | 日常点餐 | 批量、CI、无 MCP 环境 | 定制流程 |

## 为什么要有 `mcp_client.py`

远程 MCP 不是所有 Agent 都支持。这个脚本用标准库实现了 Streamable HTTP 传输、JSON-RPC 编解码、SSE 响应解析与 `Mcp-Session-Id` 会话保持，所以：

- Agent 不支持 MCP 时，仍能通过 shell 调到同一批官方接口；
- 支持 MCP 但工具名/协议实现有差异的客户端（例如某些版本对数组参数校验严格），可以用它绕开；
- 人可以脱离 AI 直接用命令行核对某个数字。

它不做任何缓存、不落盘 Token、不重试写操作。

## 给 Skill 作者的建议

如果你要把这套逻辑接到别的 Agent，只需要提供三件事：

1. **Token 来源**——环境变量或文件，不要硬编码。
2. **一个能执行的入口**——`run_recommend.py` 就是那个入口。
3. **一份能被读到的说明**——`AGENTS.md` + `SKILL.md`。

前两件决定「能不能跑」，第三件决定「模型会不会按你的约束跑」。
