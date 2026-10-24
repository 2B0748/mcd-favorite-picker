#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
零依赖的麦当劳 MCP 客户端（只用标准库）。

存在的理由：不是每个 Agent 都支持远程 MCP。有了它，任何能执行命令的
Agent（Claude Code、Codex、Cursor、Cline、Aider…）甚至人肉终端，都能调
官方接口，不必依赖特定客户端的 MCP 集成。

Token 来源优先级：
    1. 命令行 --token
    2. 环境变量 MCD_MCP_TOKEN
    3. 文件 ~/.mcd_mcp_token（或 --token-file 指定）

用法:
    python mcp_client.py tools
    python mcp_client.py call order-list
    python mcp_client.py call query-meals --args '{"storeCode":"123","orderType":1,"beType":1}'
    python mcp_client.py call query-meals --args-file args.json --out result.txt
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://mcp.mcd.cn"
DEFAULT_TOKEN_FILE = Path.home() / ".mcd_mcp_token"


class McpError(RuntimeError):
    pass


def load_token(token=None, token_file=None):
    if token:
        return token.strip()
    env = os.environ.get("MCD_MCP_TOKEN")
    if env:
        return env.strip()
    p = Path(token_file) if token_file else DEFAULT_TOKEN_FILE
    if p.exists():
        return p.read_text(encoding="utf-8-sig").strip()
    raise McpError(
        "找不到 MCP Token。请设置环境变量 MCD_MCP_TOKEN，"
        f"或把 Token 写入 {DEFAULT_TOKEN_FILE}"
    )


class McpClient:
    def __init__(self, url=None, token=None, token_file=None, timeout=45):
        self.url = (url or os.environ.get("MCD_MCP_URL") or DEFAULT_URL).rstrip("/")
        self.token = load_token(token, token_file)
        self.timeout = timeout
        self._id = 0
        self._session = None
        self._ready = False

    # ---------- 传输层 ----------

    def _post(self, method, params=None):
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params if params is not None else {}}
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("User-Agent", "mcd-favorite-picker/1.2")
        if self._session:
            req.add_header("Mcp-Session-Id", self._session)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session = sid
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            hint = {401: "Token 无效，或缺 Bearer 前缀",
                    405: "URL 应为主机根路径（https://mcp.mcd.cn），不是 open.mcd.cn/mcp",
                    429: "超过 600 次/分钟限流"}.get(e.code, "")
            raise McpError(f"{method} HTTP {e.code} {hint} {body}".strip()) from None
        except urllib.error.URLError as e:
            raise McpError(f"网络不可达: {e.reason}") from None

        if not raw.strip():
            return None
        return self._parse(raw, ctype)

    @staticmethod
    def _parse(raw, ctype):
        """兼容 JSON 与 SSE（text/event-stream）两种响应。"""
        if "event-stream" in ctype or raw.lstrip().startswith(("event:", "data:", "id:")):
            best = None
            for line in raw.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    obj = json.loads(chunk)
                except Exception:
                    continue
                if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                    best = obj
            if best is not None:
                return best
            raise McpError("SSE 响应里没有可解析的 JSON-RPC 结果")
        try:
            return json.loads(raw)
        except Exception:
            raise McpError("响应不是合法 JSON：\n" + raw[:400]) from None

    # ---------- MCP 层 ----------

    def initialize(self):
        if self._ready:
            return
        self._post("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcd-favorite-picker", "version": "1.2"},
        })
        self._ready = True

    def list_tools(self):
        self.initialize()
        resp = self._post("tools/list")
        if resp and resp.get("error"):
            raise McpError("tools/list 失败: " + json.dumps(resp["error"], ensure_ascii=False))
        return ((resp or {}).get("result") or {}).get("tools") or []

    def call(self, name, arguments=None):
        """调用工具，返回 content[0].text 原文（MCP 的 markdown+JSON 混合文本）。"""
        self.initialize()
        resp = self._post("tools/call", {"name": name, "arguments": arguments or {}})
        if resp and resp.get("error"):
            raise McpError(f"{name} 返回错误: " + json.dumps(resp["error"], ensure_ascii=False))
        result = (resp or {}).get("result") or {}
        if result.get("isError"):
            raise McpError(f"{name} 执行失败: " + json.dumps(result, ensure_ascii=False)[:400])
        content = result.get("content") or []
        for item in content:
            if item.get("type") == "text":
                return item.get("text", "")
        return json.dumps(result, ensure_ascii=False)


def main():
    # 全局参数用 SUPPRESS，避免子命令的默认值把子命令前面给的值覆盖掉
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS,
                        help="MCP 地址，默认 https://mcp.mcd.cn")
    common.add_argument("--token-file", default=argparse.SUPPRESS,
                        help="Token 文件，默认 ~/.mcd_mcp_token")

    ap = argparse.ArgumentParser(description="麦当劳 MCP 命令行客户端（零依赖）",
                                 parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tools", help="列出全部工具名", parents=[common])

    c = sub.add_parser("call", help="调用一个工具", parents=[common])
    c.add_argument("name")
    c.add_argument("--args", default="{}", help="JSON 字符串")
    c.add_argument("--args-file", help="从文件读取 JSON 参数")
    c.add_argument("--out", help="结果写入文件")

    a = ap.parse_args()
    url = getattr(a, "url", None)
    token_file = getattr(a, "token_file", None)

    try:
        cli = McpClient(url=url, token_file=token_file)
        if a.cmd == "tools":
            tools = cli.list_tools()
            lines = [f"{len(tools)} tools", ""]
            for t in tools:
                lines.append(f"{t.get('name')}\t{(t.get('description') or '').splitlines()[0][:80]}")
            out = "\n".join(lines)
        else:
            args = (json.loads(Path(a.args_file).read_text(encoding="utf-8-sig"))
                    if a.args_file else json.loads(a.args))
            out = cli.call(a.name, args)
    except McpError as e:
        print(f"[MCP 错误] {e}", file=sys.stderr)
        return 2

    if getattr(a, "out", None):
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"written -> {a.out}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
