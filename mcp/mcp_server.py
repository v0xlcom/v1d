#!/usr/bin/env python3
import subprocess
"""
v1d MCP Server — stdio transport.

Usage:
  python mcp_server.py --stdio
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

MCP_DIR = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("V1D_WORKSPACE_ROOT", ".")).resolve()
GUIDE_PATH = MCP_DIR / "AI_GUIDE.md"
CATALOG_PATH = MCP_DIR / "catalog.json"
SOURCES_PATH = MCP_DIR / "sources.json"
INBOX = WORKSPACE / "workspace" / "inbox"
SESSION_FLAG = WORKSPACE / "workspace" / ".v1d_mcp_active"
STATUS_SOCKET = os.environ.get("V1D_SERVER_STATUS_SOCKET", "/tmp/v1d_mcp_server_status")
REL = WORKSPACE / "_build/linux-x86_64/release"
EXT_BUILT = REL / "exts/v1d.cor"
KIT_PY = REL / "kit/python/bin/python3"
KIT_BIN = REL / "kit/kit"
KIT_SELFTEST_LOG = WORKSPACE / "_build/kit_selftest.log"
V1D_CLI = WORKSPACE / "tools/v1d"
REPO_SH = WORKSPACE / "repo.sh"
ENGINE_SRC = WORKSPACE / "source/extensions/v1d.cor"
PV_SRC = WORKSPACE / "source/extensions/v1d.pv"
TL_SRC = WORKSPACE / "source/extensions/v1d.tl"
APP_KIT = WORKSPACE / "source/apps/v1d.app.kit"

_job_lock = None
_job_proc = None
_job_op = None


def _load_guide() -> str:
    if GUIDE_PATH.is_file():
        return GUIDE_PATH.read_text(encoding="utf-8")
    return "(AI_GUIDE.md missing)"


mcp = FastMCP("v1d-mcp", instructions="v1d MCP server — grounding, jobs, and headless v1d engine")


@mcp.tool(name="v1d_session_activate")
def v1d_session_activate() -> str:
    if SESSION_FLAG.exists():
        return "already active"
    SESSION_FLAG.write_text("v1d MCP server is active.\nSSE endpoint: http://127.0.0.1:19876\n", encoding="utf-8")
    return "activated"


@mcp.tool(name="v1d_doctor")
def v1d_doctor() -> str:
    issues = []
    if not REL.exists():
        issues.append("missing: _build/linux-x86_64/release")
    if not EXT_BUILT.exists():
        issues.append("missing: _build/linux-x86_64/release/exts/v1d.cor")
    if not KIT_PY.exists():
        issues.append("missing: _build/linux-x86_64/release/kit/python/bin/python3")
    if not KIT_BIN.exists():
        issues.append("missing: _build/linux-x86_64/release/kit/kit")
    if KIT_SELFTEST_LOG.exists():
        content = KIT_SELFTEST_LOG.read_text(encoding="utf-8")
        if "FAILED" in content:
            issues.append(f"kit selftest failed: {KIT_SELFTEST_LOG.read_text(encoding='utf-8')[:200]}")
        elif "SUCCESS" in content:
            issues.append("kit selftest passed")
    if not KIT_BIN.exists():
        issues.append("kit binary missing, try: ./repo.sh build -r")
    status = "healthy" if not issues else "issues"
    return f"v1d doctor: {status}. Issues: {issues}"


@mcp.tool(name="v1d_workspace_paths")
def v1d_workspace_paths() -> str:
    return json.dumps({"workspace": str(WORKSPACE)})


@mcp.tool(name="v1d_constraints")
def v1d_constraints() -> str:
    guide = _load_guide()
    constraints = [
        "Edit the engine file in-place (source/extensions/v1d.cor).",
        "v1d_engine: source/extensions/v1d.cor",
        "v1d_cli: tools/v1d",
    ]
    if guide:
        constraints.append(f"Read v1d://guide/ai for the AI guide.")
    return json.dumps(constraints)


@mcp.tool(name="v1d_lookup_symbol")
def v1d_lookup_symbol(task: str) -> dict:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.is_file() else {}
    for row in sources:
        if row.get("local_exists"):
            local = row.get("local")
            if local and task.lower() in local.lower():
                return {"symbol": local, "found": True}
    return {"symbol": None, "found": False, "message": "No matching symbol found in sources."}


@mcp.tool(name="v1d_sources")
def v1d_sources(task: str) -> dict:
    sources = {}
    if SOURCES_PATH.is_file():
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return {"matched": [], "source_count": 0, "sources": sources}


@mcp.tool(name="v1d_run_job")
def v1d_run_job(operation: str, args: dict) -> dict:
    if _job_proc is not None:
        return {"ok": False, "summary": "another job is already running"}
    global _job_proc, _job_op
    _job_op = operation
    if operation == "run_tests":
        cmd = [str(WORKSPACE / "tools/run_tests.sh"), "-v"]
    elif operation == "check_licenses":
        cmd = [str(WORKSPACE / "tools/check_licenses.sh")]
    elif operation == "kit_selftest":
        cmd = [str(WORKSPACE / "tools/run_kit_selftest.sh")]
    elif operation == "repo_build":
        cmd = ["./repo.sh", "build"]
        for arg in args.get("args", []):
            cmd.append(arg)
    elif operation == "headless_import":
        cmd = [str(V1D_CLI), "-p"] + args.get("parts", [])
    else:
        return {"ok": False, "summary": f"unknown operation: {operation}"}
    _job_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return {"ok": True, "summary": f"job '{operation}' started"}


@mcp.tool(name="v1d_run_job_json")
def v1d_run_job_json(job: dict, wait_seconds: int = 120) -> dict:
    operation = job.get("operation")
    if _job_proc is not None:
        return {"ok": False, "summary": "another job is already running"}
    global _job_proc, _job_op
    _job_op = operation
    if operation == "run_tests":
        cmd = [str(WORKSPACE / "tools/run_tests.sh"), "-v"] + job.get("args", [])
    elif operation == "check_licenses":
        cmd = [str(WORKSPACE / "tools/check_licenses.sh")] + job.get("args", [])
    elif operation == "kit_selftest":
        cmd = [str(WORKSPACE / "tools/run_kit_selftest.sh")] + job.get("args", [])
    elif operation == "repo_build":
        cmd = ["./repo.sh", "build"] + job.get("args", [])
    elif operation == "headless_import":
        cmd = [str(V1D_CLI), "-p"] + job.get("parts", [])
    else:
        return {"ok": False, "summary": f"unknown job: {operation}"}
    _job_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = _job_proc.communicate(timeout=wait_seconds)
        if _job_proc.returncode != 0:
            return {"ok": False, "summary": f"stderr: {err}"}
        return {"ok": True, "summary": json.loads(out) if out else {}}
    except subprocess.TimeoutExpired:
        _job_proc.kill()
        _job_proc.wait()
        return {"ok": False, "summary": f"job {operation} timed out"}
    except Exception as e:
        return {"ok": False, "summary": str(e)}
    finally:
        _job_proc = None


@mcp.tool(name="v1d_job_status")
def v1d_job_status() -> dict:
    if _job_proc is None:
        return {"job": None, "status": None}
    return {"job": _job_op, "status": "running", "pid": _job_proc.pid}


@mcp.tool(name="v1d_cancel_job")
def v1d_cancel_job() -> dict:
    global _job_proc, _job_op
    if _job_proc is None:
        return {"ok": False, "summary": "no job running"}
    _job_proc.kill()
    _job_proc = None
    _job_op = None
    return {"ok": True, "summary": "cancelled"}


@mcp.tool(name="cuda_probe")
def cuda_probe() -> dict:
    try:
        out, _ = subprocess.Popen(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).communicate(timeout=30)
        if out:
            return {"ok": True, "summary": out.strip()}
    except Exception:
        pass
    return {"ok": False, "summary": "nvidia-smi not available or failed"}


@mcp.tool(name="repo_build")
def repo_build(task: str) -> dict:
    parts = task.split()
    cmd = ["./repo.sh", "build"]
    for arg in parts[1:]:
        cmd.append(arg)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=300)
    return {"ok": proc.returncode == 0, "summary": out if out else err}


@mcp.tool(name="headless_import")
def headless_import(task: str) -> dict:
    parts = task.split()
    cmd = [str(V1D_CLI), "-p"] + parts[1:]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=300)
    return {"ok": proc.returncode == 0, "summary": out if out else err}


@mcp.tool(name="run_tests")
def run_tests(task: str) -> dict:
    cmd = [str(WORKSPACE / "tools/run_tests.sh"), "-v"] + task.split()[1:] if task else [str(WORKSPACE / "tools/run_tests.sh"), "-v"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=300)
    return {"ok": proc.returncode == 0, "summary": out if out else err}


@mcp.tool(name="check_licenses")
def check_licenses(task: str) -> dict:
    parts = task.split()
    cmd = [str(WORKSPACE / "tools/check_licenses.sh")] + parts[1:] if len(parts) >= 2 else [str(WORKSPACE / "tools/check_licenses.sh")]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=300)
    return {"ok": proc.returncode == 0, "summary": out if out else err}


@mcp.tool(name="kit_selftest")
def kit_selftest(task: str) -> dict:
    parts = task.split()
    cmd = [str(WORKSPACE / "tools/run_kit_selftest.sh")] + parts[1:] if len(parts) >= 2 else [str(WORKSPACE / "tools/run_kit_selftest.sh")]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=300)
    return {"ok": proc.returncode == 0, "summary": out if out else err}


@mcp.tool(name="v1d_tail_kit_log")
def v1d_tail_kit_log() -> dict:
    if not KIT_SELFTEST_LOG.exists():
        return {"ok": False, "summary": {"error": "log not found"}}
    content = KIT_SELFTEST_LOG.read_text(encoding="utf-8")
    lines = content.splitlines()[-20:]
    return {"ok": True, "summary": {"lines": lines}}


@mcp.tool(name="v1d_shutdown_kit")
def v1d_shutdown_kit() -> dict:
    KIT_SELFTEST_LOG.write_text("", encoding="utf-8")
    return {"ok": True, "summary": "shutdown complete"}


@mcp.tool(name="v1d_get_ai_guide")
def v1d_get_ai_guide() -> str:
    return _load_guide()


@mcp.tool(name="v1d_catalog")
def v1d_catalog() -> str:
    if CATALOG_PATH.is_file():
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return json.dumps(catalog)
    return json.dumps({"error": "catalog.json not found"})


@mcp.resource("v1d://guide/ai")
def get_guide() -> str:
    return _load_guide()


@mcp.resource("v1d://operations")
def get_operations() -> str:
    if OPERATIONS_PATH.is_file():
        return json.loads(OPERATIONS_PATH.read_text(encoding="utf-8"))
    return {}


@mcp.resource("v1d://catalog")
def get_catalog() -> str:
    if CATALOG_PATH.is_file():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {}


@mcp.resource("v1d://sources")
def get_sources() -> str:
    if SOURCES_PATH.is_file():
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return {}


def run_stdio_server():
    """Run the MCP server via stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="v1d MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run as stdio server")
    args = parser.parse_args()
    if args.stdio:
        run_stdio_server()
    else:
        run_stdio_server()
