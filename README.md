# Privacy MCP Agent

A highly capable **Hybrid AI Assistant** built for extreme privacy and flexibility. 
It seamlessly routes between **Google Gemini (Cloud)** for complex online reasoning and **Ollama (Local)** for completely disconnected, private, offline execution.

Both engines connect to **Model Context Protocol (MCP)** servers to securely interact with your local files and SQLite databases. Destructive actions trigger a "Human-in-the-Loop" guardrail modal that halts execution until you explicitly approve it.

```text
React UI ──HTTP──▶ FastAPI Orchestrator ──┬─[Online]─▶ Gemini API (3.8-flash, 3.5-flash fallback)
                                          └─[Offline]─▶ Ollama (llama3.2:latest, local)
                                               │
                                               ├─stdio/JSON-RPC─▶ filesystem-mcp  (sandboxed workspace)
                                               └─stdio/JSON-RPC─▶ sqlite-mcp      (local database)
```

## Features

- **Hybrid Orchestration:** The engine intelligently switches between Cloud (Gemini) and Local (Ollama). If the cloud rate limits trigger, it seamlessly falls back to a lighter cloud model. If the internet goes out, flip the toggle to "Local" and keep working seamlessly.
- **Human-in-the-Loop (HITL) Guardrails:** Built-in security intercepts potentially destructive MCP actions (e.g., executing mutations, deleting files) and prompts the user for approval.
- **Cross-Platform Delivery:** Can be run from source, compiled into a standalone Windows Desktop Application (.exe), or hosted on Render.com as a web application!

## Running Locally (Source)

### Option 1: One-Click Startup Script (Windows)

```powershell
cd internship-tracker
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The script automates everything: it installs/starts Ollama, pulls `llama3.2`, creates the Python venv, builds the UI, and opens **http://127.0.0.1:8000**.

| Command | What it does |
|---|---|
| `.\start.ps1` | Production: builds UI and serves backend on port 8000 |
| `.\start.ps1 -Dev` | Dev: backend on :8000 + hot-reload React UI on :5173 |

### Option 2: Run Desktop Application (.exe)

You can build the app into a standalone desktop application via PyInstaller and Electron:
```powershell
npm install
npm run electron:build
```
This will compile the Python backend and React frontend into a native desktop installer located at `release/Privacy MCP Agent Setup 1.0.0.exe`.

## Hosting on the Web (Render)

This repository is configured out-of-the-box for **Render.com**. Simply link your GitHub repo to a Render Web Service. The provided `Dockerfile` will automatically build the Node.js frontend and the Python FastAPI backend.
*(Note: When hosted on a cloud platform like Render, the "Local" Ollama toggle will automatically disable itself, strictly using the Gemini models).*

## Guardrails (Human-in-the-Loop)

| Risk | Tools | Behaviour |
|---|---|---|
| LOW | `list_directory`, `read_file`, `search_files`, `get_file_info`, `list_tables`, `describe_database_schema` | Auto-run |
| MEDIUM | `execute_read_query` | Auto-run + notice |
| HIGH | `write_file`, `delete_file`, `execute_mutation_query` | **Paused until you approve** |

## Environment Variables

| Env var | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(Required for Cloud Mode)* | Google Gemini API Key |
| `AGENT_WORKSPACE` | `backend/workspace` | Folder the agent can read/write (sandboxed) |
| `AGENT_DB_PATH` | `backend/data/enterprise_records.db` | SQLite database to query |
| `AGENT_HOST` | `127.0.0.1` | Set to `0.0.0.0` to expose to local network (e.g., for phone access) |
