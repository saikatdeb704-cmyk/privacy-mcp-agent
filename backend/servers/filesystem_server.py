"""
FileSystem MCP Server (sandboxed)
─────────────────────────────────
All paths are resolved relative to a single workspace root. Anything that
escapes the root (../, absolute paths, symlinks) is rejected.

Tools:
  list_directory   LOW
  read_file        LOW
  search_files     LOW   – filename + content keyword search
  get_file_info    LOW
  write_file       HIGH  – needs approval
  delete_file      HIGH  – needs approval

Set AGENT_WORKSPACE to point the agent at a folder of your choice.
"""
import datetime as dt
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("AGENT_WORKSPACE", BASE_DIR / "workspace")).resolve()
MAX_READ_BYTES = 64_000
TEXT_EXT = {".md", ".txt", ".csv", ".json", ".py", ".js", ".ts", ".jsx", ".html", ".css", ".yaml", ".yml", ".log", ".ini", ".toml", ".sql"}

mcp = FastMCP("filesystem-mcp")


def _seed_workspace() -> None:
    (ROOT / "notes").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports").mkdir(parents=True, exist_ok=True)
    (ROOT / "README.md").write_text(
        "# Agent Workspace\n\nThis folder is the sandbox the Privacy MCP Agent can see.\n"
        "Drop your own documents here (or set AGENT_WORKSPACE) and ask the agent about them.\n",
        encoding="utf-8")
    (ROOT / "notes" / "meeting_notes.md").write_text(
        "# Weekly Sync – 2024-09-12\n\n- Budget reallocation: +8% to Engineering for Q4.\n"
        "- Europe pipeline slowed; Contoso renewal at risk.\n- Action: Priya to draft edge-gateway roadmap.\n",
        encoding="utf-8")
    (ROOT / "reports" / "Q3_summary.md").write_text(
        "# Q3 2024 Summary\n\nTotal revenue grew 12% YoY. North America remains the largest region.\n"
        "Q3 budget allocation across departments increased 12%, driven by Engineering hiring.\n",
        encoding="utf-8")


if not ROOT.exists():
    _seed_workspace()


def _safe(path: str) -> Path:
    p = (ROOT / (path or ".")).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"Access denied: '{path}' is outside the workspace sandbox.")
    return p


def _rel(p: Path) -> str:
    return "." if p == ROOT else p.relative_to(ROOT).as_posix()


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List files and folders inside a workspace directory (default: workspace root)."""
    try:
        d = _safe(path)
        if not d.is_dir():
            return f"Not a directory: {path}"
        entries = sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = [f"[dir]  {e.name}/" if e.is_dir() else f"[file] {e.name} ({e.stat().st_size:,} bytes)" for e in entries]
        return f"Workspace path: {_rel(d)}\n" + ("\n".join(lines) or "(empty)")
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def read_file(path: str) -> str:
    """Read the text content of a file in the workspace."""
    try:
        f = _safe(path)
        if not f.is_file():
            return f"File not found: {path}"
        data = f.read_bytes()[:MAX_READ_BYTES]
        text = data.decode("utf-8", errors="replace")
        suffix = "\n… (truncated)" if f.stat().st_size > MAX_READ_BYTES else ""
        return f"--- {_rel(f)} ---\n{text}{suffix}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def search_files(query: str, max_results: int = 20) -> str:
    """Search workspace files whose name or text content contains the query (case-insensitive)."""
    q = query.lower()
    hits: list[str] = []
    for f in ROOT.rglob("*"):
        if len(hits) >= max_results:
            break
        if not f.is_file():
            continue
        if q in f.name.lower():
            hits.append(f"{_rel(f)}  (filename match)")
            continue
        if f.suffix.lower() in TEXT_EXT and f.stat().st_size < 2_000_000:
            try:
                for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if q in line.lower():
                        hits.append(f"{_rel(f)}:{n}  {line.strip()[:160]}")
                        break
            except OSError:
                pass
    return "\n".join(hits) if hits else f"No matches for '{query}'."


@mcp.tool()
def get_file_info(path: str) -> str:
    """Get size and modification time for a file or folder in the workspace."""
    try:
        p = _safe(path)
        if not p.exists():
            return f"Not found: {path}"
        st = p.stat()
        kind = "directory" if p.is_dir() else "file"
        mtime = dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        return f"{_rel(p)}\ntype: {kind}\nsize: {st.st_size:,} bytes\nmodified: {mtime}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file in the workspace. HIGH RISK – requires human approval."""
    try:
        f = _safe(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"Wrote {len(content.encode('utf-8')):,} bytes to {_rel(f)}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def delete_file(path: str) -> str:
    """Delete a single file from the workspace. HIGH RISK – requires human approval."""
    try:
        f = _safe(path)
        if not f.is_file():
            return f"File not found: {path}"
        f.unlink()
        return f"Deleted {_rel(f)}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
