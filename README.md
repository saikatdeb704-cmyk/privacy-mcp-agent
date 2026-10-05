# Privacy MCP Agent

A local AI assistant. A small language model running in **Ollama** uses
**Model Context Protocol (MCP)** servers to work with your files and a SQLite database.
Nothing is sent to the cloud, and destructive actions wait for your approval.

```
React UI ──HTTP──▶ FastAPI orchestrator ──▶ Ollama (llama3.2, local)
                        │
                        ├─stdio/JSON-RPC─▶ filesystem-mcp  (sandboxed workspace)
                        └─stdio/JSON-RPC─▶ sqlite-mcp      (local database)
```

## Quick start (Windows)

```powershell
cd internship-tracker
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The script installs/starts Ollama, pulls `llama3.2`, creates the Python venv, builds the UI,
and opens **http://127.0.0.1:8000**.

| Command | What it does |
|---|---|
| `.\start.ps1` | Production: one server on port 8000 |
| `.\start.ps1 -Dev` | Dev: backend :8000 + hot-reload UI :5173 |
| `.\start.ps1 -Model qwen2.5` | Use another tool-capable model |

## Using your own data

| Env var | Default | Purpose |
|---|---|---|
| `AGENT_WORKSPACE` | `backend/workspace` | Folder the agent can read/write (sandboxed) |
| `AGENT_DB_PATH` | `backend/data/enterprise_records.db` | SQLite database to query |
| `AGENT_MODEL` | `llama3.2` | Default Ollama model |

```powershell
$env:AGENT_WORKSPACE = "D:\MyDocs"; $env:AGENT_DB_PATH = "D:\finance.db"; .\start.ps1
```

## Guardrails (Human-in-the-Loop)

| Risk | Tools | Behaviour |
|---|---|---|
| LOW | list_directory, read_file, search_files, get_file_info, list_tables, describe_database_schema | Auto-run |
| MEDIUM | execute_read_query (read-only connection) | Auto-run + notice |
| HIGH | write_file, delete_file, execute_mutation_query | **Paused until you approve** |

Unknown tools default to HIGH. File paths can't escape the workspace folder.

## Adding an MCP server

1. Create `backend/servers/my_server.py` with FastMCP `@mcp.tool()` functions.
2. Register it in `MCP_SERVERS` in `backend/main.py` and add risk levels to `RISK_POLICY`.
3. Restart. The tools are discovered automatically.
