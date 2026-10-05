"""
Privacy MCP Agent – Local Host Orchestrator
───────────────────────────────────────────
User → FastAPI → Ollama (local SLM) → tool call → HITL guardrail → MCP server (stdio) → back to SLM

* Spawns every MCP server as a stdio subprocess and talks to it with the
  official MCP Python SDK (proper initialize handshake, tools/list, tools/call).
* Tools are discovered dynamically – add a server to MCP_SERVERS and its tools
  appear automatically.
* Every tool call is risk-classified. HIGH-risk calls pause the agent loop and
  are returned to the UI for explicit approval; nothing executes until approved.
* If ./dist exists (npm run build), the React UI is served from the same port.

Run:  python main.py      (do NOT use --reload on Windows – it breaks subprocess pipes)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
    DIST_DIR = BASE_DIR / "dist"
else:
    BASE_DIR = Path(__file__).resolve().parent
    DIST_DIR = BASE_DIR.parent / "dist"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "llama3.2")
MAX_STEPS = 8

MCP_SERVERS: dict[str, Path] = {
    "filesystem-mcp": BASE_DIR / "servers" / "filesystem_server.py",
    "sqlite-mcp": BASE_DIR / "servers" / "sqlite_server.py",
}

# Guardrail policy. Unknown tools default to HIGH (fail safe).
RISK_POLICY: dict[str, str] = {
    "list_directory": "LOW",
    "read_file": "LOW",
    "search_files": "LOW",
    "get_file_info": "LOW",
    "list_tables": "LOW",
    "describe_database_schema": "LOW",
    "execute_read_query": "MEDIUM",
    "write_file": "HIGH",
    "delete_file": "HIGH",
    "execute_mutation_query": "HIGH",
}

SYSTEM_PROMPT = """You are Privacy MCP Agent, an assistant that runs 100% locally on the user's computer.
You can use tools to work with the user's sandboxed workspace files and a local SQLite database.
Rules:
- Use tools whenever the question is about the user's files or data. Never invent file contents or query results.
- Before writing SQL, call describe_database_schema if you do not already know the table columns.
- Use execute_read_query for SELECT queries. Use execute_mutation_query only when the user clearly asks to change data.
- File paths are relative to the workspace root (e.g. "notes/meeting_notes.md").
- After getting tool results, answer concisely in plain language and cite the numbers you found.
- If the user just chats, answer directly without tools."""


# ─────────────────────────── MCP connection manager ───────────────────────────
class MCPHub:
    def __init__(self) -> None:
        self.stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self.tool_owner: dict[str, str] = {}
        self.tools: dict[str, list[dict[str, Any]]] = {}
        self.errors: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        for name, script in MCP_SERVERS.items():
            try:
                params = StdioServerParameters(command=sys.executable, args=[str(script)], env={**os.environ})
                read, write = await self.stack.enter_async_context(stdio_client(params))
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
                self.sessions[name] = session
                self.tools[name] = [
                    {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema}
                    for t in listed.tools
                ]
                for t in listed.tools:
                    self.tool_owner[t.name] = name
                print(f"[mcp] {name}: {len(listed.tools)} tools")
            except Exception as e:  # keep running with whatever servers did start
                self.errors[name] = str(e)
                print(f"[mcp] {name} FAILED: {e}")

    async def stop(self) -> None:
        await self.stack.aclose()

    def ollama_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["inputSchema"] or {"type": "object", "properties": {}}}}
            for tools in self.tools.values() for t in tools
        ]

    async def call(self, tool: str, args: dict[str, Any]) -> tuple[str, bool]:
        server = self.tool_owner.get(tool)
        if not server:
            return f"Unknown tool '{tool}'.", True
        async with self.lock:
            result = await self.sessions[server].call_tool(tool, args or {})
        text = "\n".join(getattr(c, "text", str(c)) for c in result.content)
        return text, bool(result.isError)


hub = MCPHub()

if os.environ.get("GEMINI_API_KEY"):
    llm = AsyncOpenAI(api_key=os.environ.get("GEMINI_API_KEY"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
elif os.environ.get("GROQ_API_KEY"):
    llm = AsyncOpenAI(api_key=os.environ.get("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
elif os.environ.get("OPENAI_API_KEY"):
    llm = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
else:
    # Use Local Ollama via its OpenAI-compatible endpoint
    llm = AsyncOpenAI(base_url=f"{OLLAMA_HOST}/v1", api_key="ollama")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await hub.start()
    yield
    await hub.stop()


app = FastAPI(title="Privacy MCP Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────── state ────────────────────────────────
class Conversation:
    def __init__(self, model: str) -> None:
        self.model = model
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.pending: dict[str, Any] | None = None  # {"id", "calls": [...], "events": [...]}


CONVERSATIONS: dict[str, Conversation] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None


class ApproveRequest(BaseModel):
    session_id: str
    approval_id: str
    approved: bool


def risk_of(tool: str) -> str:
    return RISK_POLICY.get(tool, "HIGH")


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return dict(raw or {})


async def _execute(conv: Conversation, call: dict[str, Any], approved_by_user: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        output, is_error = await hub.call(call["name"], call["arguments"])
    except Exception as e:
        output, is_error = f"Tool execution failed: {e}", True
    latency = int((time.perf_counter() - t0) * 1000)
    conv.messages.append({"role": "tool", "content": output[:12000], "tool_name": call["name"]})
    return {
        "tool": call["name"], "server": hub.tool_owner.get(call["name"], "unknown"),
        "arguments": call["arguments"], "risk": call["risk"], "output": output,
        "latency_ms": latency, "error": is_error,
        "status": "approved" if approved_by_user else "auto",
    }


async def run_agent(conv: Conversation, events: list[dict[str, Any]], queued: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Agent loop. `queued` = tool calls from the last LLM turn still waiting to run."""
    queued = list(queued or [])
    for _ in range(MAX_STEPS):
        # 1. drain queued tool calls, pausing on the first HIGH-risk one
        while queued:
            call = queued[0]
            if call["risk"] == "HIGH":
                approval_id = uuid.uuid4().hex
                conv.pending = {"id": approval_id, "calls": queued, "events": events}
                return {
                    "status": "approval_required", "reply": "", "events": events,
                    "approval": {"id": approval_id, "tool": call["name"],
                                 "server": hub.tool_owner.get(call["name"], "unknown"),
                                 "arguments": call["arguments"], "risk": "HIGH"},
                }
            queued.pop(0)
            events.append(await _execute(conv, call, approved_by_user=False))

        # 2. ask the model what to do next
        try:
            resp = await llm.chat.completions.create(model=conv.model, messages=conv.messages, tools=hub.ollama_tools() or None)
        except Exception as e:
            raise HTTPException(502, f"LLM error: {e}")

        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        conv.messages.append({
            "role": "assistant", "content": msg.content or "",
            **({"tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                for tc in tool_calls]} if tool_calls else {}),
        })
        if not tool_calls:
            return {"status": "complete", "reply": msg.content or "(no response)", "events": events}

        queued = [{"name": tc.function.name, "arguments": _parse_args(tc.function.arguments),
                   "risk": risk_of(tc.function.name)} for tc in tool_calls]

    return {"status": "complete", "reply": "I stopped after reaching the maximum number of tool steps.", "events": events}


# ─────────────────────────────── routes ────────────────────────────────
@app.get("/api/health")
async def health():
    models, ollama_ok, ollama_error = [], False, None
    try:
        listed = await asyncio.wait_for(llm.models.list(), timeout=3)
        models = [{"name": m.id, "size": getattr(m, "size", 0)} for m in listed.data]
        ollama_ok = True
    except Exception as e:
        ollama_error = str(e)
    return {
        "ok": True,
        "ollama": {"online": ollama_ok, "host": OLLAMA_HOST, "error": ollama_error,
                   "models": models, "default_model": DEFAULT_MODEL},
        "servers": [
            {"name": n, "online": n in hub.sessions, "error": hub.errors.get(n),
             "tools": [{"name": t["name"], "risk": risk_of(t["name"])} for t in hub.tools.get(n, [])]}
            for n in MCP_SERVERS
        ],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    model = req.model or DEFAULT_MODEL
    conv = CONVERSATIONS.get(req.session_id)
    if conv is None:
        conv = CONVERSATIONS[req.session_id] = Conversation(model)
    conv.model = model
    if conv.pending:
        raise HTTPException(409, "An action is waiting for your approval. Approve or reject it first.")
    conv.messages.append({"role": "user", "content": req.message})
    return await run_agent(conv, [])


@app.post("/api/approve")
async def approve(req: ApproveRequest):
    conv = CONVERSATIONS.get(req.session_id)
    if not conv or not conv.pending or conv.pending["id"] != req.approval_id:
        raise HTTPException(404, "No matching pending approval.")
    pending, conv.pending = conv.pending, None
    calls, events = pending["calls"], pending["events"]
    call = calls.pop(0)
    if req.approved:
        events.append(await _execute(conv, call, approved_by_user=True))
    else:
        conv.messages.append({"role": "tool", "tool_name": call["name"],
                              "content": "The user REJECTED this action. It was not executed. Do not retry it."})
        events.append({"tool": call["name"], "server": hub.tool_owner.get(call["name"], "unknown"),
                       "arguments": call["arguments"], "risk": "HIGH", "output": "Rejected by user – not executed.",
                       "latency_ms": 0, "error": False, "status": "denied"})
    return await run_agent(conv, events, calls)


@app.post("/api/reset/{session_id}")
async def reset(session_id: str):
    CONVERSATIONS.pop(session_id, None)
    return {"ok": True}


# ─────────────── serve built React UI (production / published mode) ───────────────
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = DIST_DIR / path
        return FileResponse(f if path and f.is_file() else DIST_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("AGENT_HOST", "127.0.0.1"), port=int(os.environ.get("AGENT_PORT", 8000)))
