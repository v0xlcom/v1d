#!/usr/bin/env python3
"""
Slash command entry point for /v1d_mcp.

Activates the v1d MCP server by:
  1. Starting the v1d MCP server (SSE/HTTP) in the background if not already running.
  2. Calling v1d_session_activate() to mark the CLI session as v1d-MCP-driven.
  3. Returning a summary of the server state.

The v1d MCP server is started as an SSE (HTTP) server so the opencode
standalone server can connect to it via HTTP.
"""

import os
import sys
import json
import time
import socket
import subprocess
import signal
from pathlib import Path

# v1d MCP server path
V1D_MCP_SERVER_PATH = "./mcp/v1d_mcp_server.py"
# Session flag file
V1D_SESSION_FLAG_PATH = os.environ.get("V1D_SESSION_FLAG_PATH", "./workspace/.v1d_mcp_active")
# Status socket file (used by the v1d MCP server to report status)
V1D_SERVER_STATUS_SOCKET = os.environ.get("V1D_SERVER_STATUS_SOCKET", "/tmp/v1d_mcp_server_status")
# SSE server bind address
V1D_SSE_HOST = os.environ.get("V1D_SSE_HOST", "127.0.0.1")
V1D_SSE_PORT = int(os.environ.get("V1D_SSE_PORT", "19876"))


def check_server_status() -> dict:
    """Check the v1d MCP server status via the status socket file."""
    status_file = Path(V1D_SERVER_STATUS_SOCKET)
    if status_file.exists():
        try:
            return json.loads(status_file.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return {"status": "stopped"}


def start_server() -> int:
    """Start the v1d MCP server (SSE) in the background. Returns the process PID."""
    try:
        # Set environment variable for the server to know it's being started via SSE
        env = dict(os.environ)
        env["V1D_SSE_MODE"] = "true"
        env["V1D_SSE_HOST"] = V1D_SSE_HOST
        env["V1D_SSE_PORT"] = str(V1D_SSE_PORT)
        
        process = subprocess.Popen(
            [sys.executable, V1D_MCP_SERVER_PATH, "--transport", "sse"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        return process.pid
    except Exception as e:
        print(f"Failed to start v1d MCP server: {e}", file=sys.stderr)
        return -1


def activate_session() -> bool:
    """Mark the CLI session as v1d-MCP-driven by writing the flag file."""
    try:
        Path(V1D_SESSION_FLAG_PATH).write_text(
            json.dumps({"active": True, "ts": time.time()}),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        print(f"Failed to create session flag: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point for the /v1d_mcp slash command."""
    # Check if server is already running
    status = check_server_status()
    if status["status"] == "running":
        print(json.dumps({
            "status": "already_running",
            "pid": status.get("pid"),
            "message": "v1d MCP server is already running.",
        }))
        return 0

    # Start the server
    print("Starting v1d MCP server (SSE)...", file=sys.stderr)
    pid = start_server()
    if pid < 0:
        print(json.dumps({
            "status": "failed",
            "message": "Failed to start v1d MCP server.",
        }))
        return 1

    # Give it a moment to initialize
    time.sleep(1.0)

    # Verify it's running by checking the status socket
    status = check_server_status()
    if status["status"] != "running":
        print(json.dumps({
            "status": "failed",
            "message": f"Server failed to start (PID {pid}).",
        }))
        return 1

    # Activate the session
    if not activate_session():
        print(json.dumps({
            "status": "partial",
            "message": "Server started but session activation failed.",
        }))
        return 0

    print(json.dumps({
        "status": "running",
        "pid": pid,
        "host": V1D_SSE_HOST,
        "port": V1D_SSE_PORT,
        "message": "v1d MCP server is running and session is activated.",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
