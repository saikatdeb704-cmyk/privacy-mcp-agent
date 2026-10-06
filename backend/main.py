"""
Privacy MCP Agent – Hybrid Orchestrator
───────────────────────────────────────
User → FastAPI → [Cloud LLM | Local Ollama] → tool call → HITL guardrail → MCP server (stdio) → back to LLM

Engine modes (chosen per request by the UI):
  auto    – Internet + cloud key available → cloud (Gemini). Otherwise, or if every
            cloud model fails (503 / 429 / network), fall back to local Ollama.
  online  – cloud only (with multi-model fallback + retries).
  local   – local Ollama only. Nothing leaves the machine.

* Every MCP server is a stdio subprocess driven by the official MCP Python SDK.
* Every tool call is risk-classified. HIGH-risk calls pause the loop for approval.
* Conversation history is stored provider-tagged; when the engine changes mid-
  conversation, foreign tool-call turns are flattened to plain text so that each
  provider only ever sees messages it can validate (Gemini thought signatures etc).
* If ./dist exists (npm run build), the React UI is served from the same port.

Config (env vars or backend/.env):
  GEMINI_API_KEY   enables online mode (or GROQ_API_KEY / OPENAI_API_KEY)
  CLOUD_MODELS     optional comma-separated fallback chain override
  OLLAMA_HOST      default http://127.0.0.1:11434
  AGENT_MODEL      preferred local model, default llama3.2

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
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    DIST_DIR = BASE_DIR / "dist"
    ENV_FILES = [Path(sys.executable).resolve().parent / ".env"]
else:
    BASE_DIR = Path(__file__).resolve().parent
    DIST_DIR = BASE_DIR.parent / "dist"
    ENV_FILES = [BASE_DIR / ".env", BASE_DIR.parent / ".env"]


def _load_env_files() -> None:
    """Tiny .env loader (no extra dependency). Real env vars always win."""
    for path in ENV_FILES:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip().removeprefix("export ").strip(), value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)


_load_env_files()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
PREFERRED_LOCAL_MODEL = os.environ.get("AGENT_MODEL", "llama3.2")
HOSTED = bool(os.environ.get("RENDER") or os.environ.get("AGENT_HOSTED"))
MAX_STEPS = 8
CLOUD_TIMEOUT = 60.0
LOCAL_TIMEOUT = 300.0
STATUS_TTL = 10.0  # seconds to cache connectivity / Ollama checks

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

SYSTEM_PROMPT = """You are Privacy MCP Agent, an assistant connected to the user's sandboxed workspace files and a SQLite database through MCP tools.
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
                await asyncio.wait_for(session.initialize(), timeout=30)
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
                self.errors[name] = str(e) or type(e).__name__
                print(f"[mcp] {name} FAILED: {e!r}")

    async def stop(self) -> None:
        try:
            await self.stack.aclose()
        except Exception:
            pass

    def openai_tools(self) -> list[dict[str, Any]]:
        """OpenAI-format tool specs. Tools with no arguments omit `parameters`
        (Google's OpenAI endpoint rejects empty parameter objects)."""
        result = []
        for tools in self.tools.values():
            for t in tools:
                schema = dict(t.get("inputSchema") or {})
                func: dict[str, Any] = {"name": t["name"], "description": t.get("description", "")}
                if schema.get("properties"):
                    schema.pop("title", None)
                    func["parameters"] = schema
                result.append({"type": "function", "function": func})
        return result

    async def call(self, tool: str, args: dict[str, Any]) -> tuple[str, bool]:
        server = self.tool_owner.get(tool)
        if not server:
            return f"Unknown tool '{tool}'.", True
        async with self.lock:
            result = await self.sessions[server].call_tool(tool, args or {})
        text = "\n".join(getattr(c, "text", str(c)) for c in result.content)
        return text, bool(result.isError)


hub = MCPHub()


# ─────────────────────────────── engines ────────────────────────────────
class Engine:
    def __init__(self, kind: str, label: str, client: AsyncOpenAI | None, models: list[str]) -> None:
        self.kind = kind          # "cloud" | "local"
        self.label = label        # "Gemini" / "Groq" / "OpenAI" / "Ollama"
        self.client = client
        self.models = models      # ordered fallback chain


def _build_cloud() -> Engine | None:
    override = [m.strip() for m in os.environ.get("CLOUD_MODELS", "").split(",") if m.strip()]
    if key := os.environ.get("GEMINI_API_KEY", "").strip():
        client = AsyncOpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                             max_retries=0, timeout=CLOUD_TIMEOUT)
        chain = override or ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash",
                             "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
        return Engine("cloud", "Gemini", client, chain)
    if key := os.environ.get("GROQ_API_KEY", "").strip():
        client = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", max_retries=0, timeout=CLOUD_TIMEOUT)
        return Engine("cloud", "Groq", client, override or ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"])
    if key := os.environ.get("OPENAI_API_KEY", "").strip():
        client = AsyncOpenAI(api_key=key, max_retries=0, timeout=CLOUD_TIMEOUT)
        return Engine("cloud", "OpenAI", client, override or ["gpt-4o-mini"])
    return None


CLOUD = _build_cloud()
LOCAL = Engine("local", "Ollama", AsyncOpenAI(base_url=f"{OLLAMA_HOST}/v1", api_key="ollama",
                                              max_retries=0, timeout=LOCAL_TIMEOUT), [])


class Status:
    """Cached probes for internet connectivity and the local Ollama runtime."""

    def __init__(self) -> None:
        self._net: tuple[float, bool] = (0.0, False)
        self._local: tuple[float, list[dict[str, Any]], str | None] = (0.0, [], None)
        self.cloud_models_checked = False

    async def internet(self, force: bool = False) -> bool:
        ts, ok = self._net
        if not force and time.monotonic() - ts < STATUS_TTL:
            return ok
        host = urlparse(str(CLOUD.client.base_url)).hostname if CLOUD else "www.google.com"
        ok = False
        for target in (host, "1.1.1.1"):
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(target, 443), timeout=2.5)
                writer.close()
                ok = True
                break
            except Exception:
                continue
        self._net = (time.monotonic(), ok)
        return ok

    def mark_offline(self) -> None:
        self._net = (time.monotonic(), False)

    async def local(self, force: bool = False) -> tuple[list[dict[str, Any]], str | None]:
        ts, models, err = self._local
        if not force and time.monotonic() - ts < STATUS_TTL:
            return models, err
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{OLLAMA_HOST}/api/tags")
                r.raise_for_status()
                models = [{"name": m["name"], "size": m.get("size", 0)}
                          for m in r.json().get("models", []) if "embed" not in m["name"]]
                err = None if models else "No local model installed. Run: ollama pull llama3.2"
        except Exception:
            models, err = [], "Ollama is not running on this machine."
        self._local = (time.monotonic(), models, err)
        return models, err

    async def refine_cloud_models(self) -> None:
        """Drop chain entries the provider doesn't list (avoids wasted 404 round-trips)."""
        if self.cloud_models_checked or not CLOUD or not await self.internet():
            return
        try:
            listed = await asyncio.wait_for(CLOUD.client.models.list(), timeout=8)
            available = {m.id.removeprefix("models/") for m in listed.data}
            kept = [m for m in CLOUD.models if m in available]
            if kept:
                CLOUD.models = kept
            self.cloud_models_checked = True
            print(f"[cloud] {CLOUD.label} fallback chain: {CLOUD.models}")
        except Exception as e:
            print(f"[cloud] could not list models: {e}")


status = Status()


def pick_local_model(models: list[dict[str, Any]], requested: str | None) -> str | None:
    names = [m["name"] for m in models]
    if not names:
        return None
    for want in (requested, PREFERRED_LOCAL_MODEL):
        if want:
            for n in names:
                if n == want or n.split(":")[0] == want.split(":")[0]:
                    return n
    return names[0]


async def plan_route(mode: str, local_model: str | None) -> list[tuple[Engine, str]]:
    """Ordered list of (engine, model) to try for this mode."""
    route: list[tuple[Engine, str]] = []
    if mode in ("auto", "online") and CLOUD and await status.internet():
        await status.refine_cloud_models()
        route += [(CLOUD, m) for m in CLOUD.models]
    if mode in ("auto", "local"):
        models, _ = await status.local()
        if name := pick_local_model(models, local_model):
            route.append((LOCAL, name))
    return route


async def explain_no_route(mode: str) -> str:
    net = await status.internet(force=True)
    _, local_err = await status.local(force=True)
    if mode == "online":
        if not CLOUD:
            return "Online mode is not configured. Add GEMINI_API_KEY to backend/.env (or the server's environment)."
        return "No internet connection. Switch to Local mode to keep working offline."
    if mode == "local":
        if HOSTED:
            return "Local mode is only available when the agent runs on your PC. Use Online or Auto here."
        return f"Local engine unavailable: {local_err} Start Ollama (ollama serve) and try again."
    # auto
    parts = []
    parts.append("cloud: " + ("no API key configured" if not CLOUD else "no internet" if not net else "unavailable"))
    parts.append("local: " + ("not available on hosted server" if HOSTED else (local_err or "unavailable")))
    return "No AI engine is available (" + "; ".join(parts) + ")."


def _friendly(e: Exception) -> str:
    if isinstance(e, APIStatusError):
        try:
            msg = e.body.get("message") if isinstance(e.body, dict) else None
            if not msg and isinstance(e.body, list):
                msg = e.body[0].get("error", {}).get("message")
        except Exception:
            msg = None
        return f"HTTP {e.status_code}: {msg or e.message}"[:200]
    if isinstance(e, (APIConnectionError, httpx.ConnectError)):
        return "connection failed"
    if isinstance(e, (APITimeoutError, asyncio.TimeoutError)):
        return "timed out"
    return (str(e) or type(e).__name__)[:200]


# ─────────────────────────────── state ────────────────────────────────
class Conversation:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.pending: dict[str, Any] | None = None
        self.mode = "auto"
        self.local_model: str | None = None


CONVERSATIONS: dict[str, Conversation] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str
    mode: str = "auto"
    local_model: str | None = None
    model: str | None = None  # legacy field, ignored


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
            parsed = json.loads(raw or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def build_messages(conv: Conversation, tag: str) -> list[dict[str, Any]]:
    """Render history for a specific engine+model `tag`.
    Messages produced by a different engine/model are converted to plain text so
    provider-specific metadata (e.g. Gemini thought signatures) never leaks across."""
    out: list[dict[str, Any]] = []
    for m in conv.messages:
        src = m.get("_src")
        clean = {k: v for k, v in m.items() if not k.startswith("_")}
        if src is None or src == tag:
            out.append(clean)
            continue
        if m["role"] == "assistant":
            text = m.get("content") or ""
            calls = m.get("tool_calls") or []
            if calls:
                used = ", ".join(f"{c['function']['name']}({c['function'].get('arguments') or ''})" for c in calls)
                text = (text + "\n" if text else "") + f"(Earlier I called the tool(s): {used})"
            out.append({"role": "assistant", "content": text or "(no response)"})
        elif m["role"] == "tool":
            out.append({"role": "user", "content": f"[Result of tool {m.get('_name', 'tool')}]\n{m.get('content', '')}"})
        else:
            out.append(clean)
    return out


async def call_llm(conv: Conversation, route: list[tuple[Engine, str]]) -> tuple[Engine, str, Any, list[str]]:
    tools = hub.openai_tools() or None
    failures: list[str] = []
    cloud_down = False
    for engine, model in route:
        if engine.kind == "cloud" and cloud_down:
            continue
        attempts = 2 if engine.kind == "cloud" else 1
        for attempt in range(attempts):
            try:
                resp = await engine.client.chat.completions.create(
                    model=model, messages=build_messages(conv, f"{engine.kind}:{model}"), tools=tools)
                if not resp.choices:
                    raise RuntimeError("empty response")
                return engine, model, resp, failures
            except Exception as e:
                code = getattr(e, "status_code", None)
                failures.append(f"{model}: {_friendly(e)}")
                print(f"[llm] {engine.label}/{model} attempt {attempt + 1} failed: {_friendly(e)}")
                if isinstance(e, APIConnectionError) and engine.kind == "cloud":
                    status.mark_offline()
                    cloud_down = True
                    break
                if code in (500, 502, 503, 504) or isinstance(e, APITimeoutError):
                    if attempt + 1 < attempts:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                if code in (401, 403) and engine.kind == "cloud":
                    cloud_down = True  # bad key – no point trying other cloud models
                break  # next model in chain
    summary = "; ".join(failures[-4:]) or "no engine attempted"
    raise HTTPException(503, f"All AI engines failed. {summary}")


async def _execute(conv: Conversation, call: dict[str, Any], approved_by_user: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        output, is_error = await hub.call(call["name"], call["arguments"])
    except Exception as e:
        output, is_error = f"Tool execution failed: {e}", True
    latency = int((time.perf_counter() - t0) * 1000)
    conv.messages.append({"role": "tool", "content": output[:12000], "tool_call_id": call["id"],
                          "_src": call["src"], "_name": call["name"]})
    return {
        "tool": call["name"], "server": hub.tool_owner.get(call["name"], "unknown"),
        "arguments": call["arguments"], "risk": call["risk"], "output": output,
        "latency_ms": latency, "error": is_error,
        "status": "approved" if approved_by_user else "auto",
    }


async def run_agent(conv: Conversation, events: list[dict[str, Any]],
                    queued: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Agent loop. `queued` = tool calls from the last LLM turn still waiting to run."""
    queued = list(queued or [])
    engine_info: dict[str, Any] | None = None
    for _ in range(MAX_STEPS):
        # 1. drain queued tool calls, pausing on the first HIGH-risk one
        while queued:
            call = queued[0]
            if call["risk"] == "HIGH":
                approval_id = uuid.uuid4().hex
                conv.pending = {"id": approval_id, "calls": queued, "events": events}
                return {
                    "status": "approval_required", "reply": "", "events": events, "engine": engine_info,
                    "approval": {"id": approval_id, "tool": call["name"],
                                 "server": hub.tool_owner.get(call["name"], "unknown"),
                                 "arguments": call["arguments"], "risk": "HIGH"},
                }
            queued.pop(0)
            events.append(await _execute(conv, call, approved_by_user=False))

        # 2. ask the model what to do next
        route = await plan_route(conv.mode, conv.local_model)
        if not route:
            raise HTTPException(503, await explain_no_route(conv.mode))
        engine, model, resp, failures = await call_llm(conv, route)
        tag = f"{engine.kind}:{model}"
        preferred = route[0][0]
        notice = None
        if engine is LOCAL and preferred is CLOUD:
            notice = f"{CLOUD.label} unavailable – answered locally with {model}."
        elif failures and engine is CLOUD:
            notice = f"Primary model busy – answered with {model}."
        engine_info = {"kind": engine.kind, "provider": engine.label, "model": model, "notice": notice}

        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        # model_dump keeps provider metadata (e.g. Gemini thought_signature) required on the next turn
        stored = msg.model_dump(exclude_none=True)
        stored["_src"] = tag
        conv.messages.append(stored)

        if not tool_calls:
            return {"status": "complete", "reply": msg.content or "(no response)", "events": events,
                    "engine": engine_info}

        queued = [{"id": tc.id, "name": tc.function.name, "arguments": _parse_args(tc.function.arguments),
                   "risk": risk_of(tc.function.name), "src": tag} for tc in tool_calls]

    return {"status": "complete", "reply": "I stopped after reaching the maximum number of tool steps.",
            "events": events, "engine": engine_info}


# ─────────────────────────────── app ────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    await hub.start()
    print(f"[engine] cloud: {CLOUD.label + ' ' + str(CLOUD.models) if CLOUD else 'not configured'}")
    print(f"[engine] local: Ollama at {OLLAMA_HOST} (preferred {PREFERRED_LOCAL_MODEL}) hosted={HOSTED}")
    yield
    await hub.stop()


app = FastAPI(title="Privacy MCP Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    net, (local_models, local_err) = await asyncio.gather(status.internet(), status.local())
    if HOSTED:
        local_models, local_err = [], "Local engine runs only on your PC."
    cloud_ready = bool(CLOUD and net)
    local_ready = bool(local_models)
    return {
        "ok": True,
        "hosted": HOSTED,
        "internet": net,
        "cloud": {
            "configured": bool(CLOUD), "ready": cloud_ready,
            "provider": CLOUD.label if CLOUD else None,
            "models": CLOUD.models if CLOUD else [],
            "model": CLOUD.models[0] if CLOUD and CLOUD.models else None,
        },
        "local": {
            "ready": local_ready, "host": OLLAMA_HOST, "error": local_err,
            "models": local_models, "default_model": pick_local_model(local_models, None),
        },
        "auto_engine": "cloud" if cloud_ready else "local" if local_ready else None,
        "servers": [
            {"name": n, "online": n in hub.sessions, "error": hub.errors.get(n),
             "tools": [{"name": t["name"], "risk": risk_of(t["name"])} for t in hub.tools.get(n, [])]}
            for n in MCP_SERVERS
        ],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    conv = CONVERSATIONS.get(req.session_id)
    if conv is None:
        conv = CONVERSATIONS[req.session_id] = Conversation()
    if conv.pending:
        raise HTTPException(409, "An action is waiting for your approval. Approve or reject it first.")
    conv.mode = req.mode if req.mode in ("auto", "online", "local") else "auto"
    conv.local_model = req.local_model
    snapshot = len(conv.messages)
    conv.messages.append({"role": "user", "content": req.message})
    try:
        return await run_agent(conv, [])
    except Exception:
        del conv.messages[snapshot:]  # roll back the failed turn so history stays valid
        conv.pending = None
        raise


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
        conv.messages.append({"role": "tool", "tool_call_id": call["id"], "_src": call["src"], "_name": call["name"],
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
    if (DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = DIST_DIR / path
        return FileResponse(f if path and f.is_file() else DIST_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("AGENT_HOST", "127.0.0.1"), port=int(os.environ.get("AGENT_PORT") or os.environ.get("PORT") or 8000))
