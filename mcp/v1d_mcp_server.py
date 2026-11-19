    def _session_activate(self) -> str:
        if SESSION_FLAG.exists():
            return "already active"
        SESSION_FLAG.write_text("v1d MCP server is active.\nSSE endpoint: http://127.0.0.1:19876\nTools available:\n  v1d_doctor, v1d_workspace_paths, v1d_constraints, v1d_catalog,\n  v1d_lookup_symbol, v1d_sources, v1d_run_job, v1d_run_job_json,\n  v1d_job_status, v1d_cancel_job, cuda_probe, repo_build,\n  headless_import, run_tests, check_licenses, kit_selftest,\n  v1d_tail_kit_log, v1d_shutdown_kit\n\nAI guide: v1d://guide/ai\n", encoding="utf-8")
        return "activated"

    def _doctor(self) -> str:
        issues = []
        if not REL.exists():
            issues.append("missing: _build/linux-x86_64/release")
        if not EXT_BUILT.exists():
            issues.append("missing: _build/linux-x86_64/release/exts/v1d.cor")
        if not KIT_PY.exists():
            issues.append("missing: _build/linux-x86_64/release/kit/python/bin/python3")
        if not KIT_BIN.exists():
            issues.append("missing: _build/linux-x86_64/release/kit/kit")
        if not FATBIN.exists():
            issues.append("missing: _build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin")
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

    def _workspace_paths(self) -> str:
        return json.dumps({"workspace": str(WORKSPACE)})

    def _constraints(self) -> str:
        guide = _load_guide()
        constraints = [
            "Edit the engine file in-place (source/extensions/v1d.cor).",
            "v1d_engine: source/extensions/v1d.cor",
            "v1d_cli: tools/v1d",
        ]
        if guide:
            constraints.append(f"Read v1d://guide/ai for the AI guide.")
        return json.dumps(constraints)

    def _lookup_symbol(self, task: str) -> dict:
        result = _find_symbol(task)
        return result

    def _match_sources(self, task: str) -> dict:
        return _match_sources(task)

    def _catalog(self) -> str:
        if CATALOG_PATH.is_file():
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            return json.dumps(catalog)
        return json.dumps({"error": "catalog.json not found"})

    def _read_resource(self, uri: str) -> tuple:
        if uri == "v1d://guide/ai":
            guide = _load_guide()
            return ("ok", guide)
        elif uri == "v1d://operations":
            return ("ok", json.dumps(json.loads(OPERATIONS_PATH.read_text(encoding="utf-8")) if OPERATIONS_PATH.is_file() else {}))
        elif uri == "v1d://catalog":
            return ("ok", json.dumps(json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.is_file() else {}))
        elif uri == "v1d://sources":
            return ("ok", json.dumps(json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.is_file() else {}))
        return ("error", json.dumps({"error": f"resource not found: {uri}"}).encode("utf-8"))

    def _run_job(self, operation: str, args: dict) -> dict:
        if _job_running():
            return {"ok": False, "summary": "another job is already running"}
        with _job_lock:
            _job_op = operation
        if operation == "run_tests":
            cmd = _build_run_tests_args_with_wait(args.get("task", ""))
        elif operation == "check_licenses":
            cmd = _build_check_licenses_args(args.get("task", ""))
        elif operation == "kit_selftest":
            cmd = _build_kit_selftest_args_with_wait(args.get("task", ""))
        elif operation == "repo_build":
            cmd = _build_repo_build_args(args.get("task", ""))
        elif operation == "headless_import":
            cmd = _build_headless_import_args(args.get("task", ""))
        else:
            return {"ok": False, "summary": f"unknown operation: {operation}"}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, err = proc.communicate(timeout=120)
            if proc.returncode != 0:
                return {"ok": False, "summary": f"stderr: {err}"}
            return {"ok": True, "summary": out}
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            with _job_lock:
                _job_proc = None
            return {"ok": False, "summary": "job timed out"}
        except Exception as e:
            return {"ok": False, "summary": str(e)}
        finally:
            with _job_lock:
                _job_proc = None

    def _run_job_json(self, job: dict, wait_seconds: int = 120) -> dict:
        if _job_running():
            return {"ok": False, "summary": "another job is already running"}
        with _job_lock:
            _job_op = job.get("operation")
            if not _job_op:
                return {"ok": False, "summary": "missing operation field"}
            args = job.get("args", {})
        if _job_op == "run_tests":
            cmd = _build_run_tests_args_with_wait(args.get("task", ""))
        elif _job_op == "check_licenses":
            cmd = _build_check_licenses_args(args.get("task", ""))
        elif _job_op == "kit_selftest":
            cmd = _build_kit_selftest_args_with_wait(args.get("task", ""))
        elif _job_op == "repo_build":
            cmd = _build_repo_build_args(args.get("task", ""))
        elif _job_op == "headless_import":
            cmd = _build_headless_import_args(args.get("task", ""))
        else:
            return {"ok": False, "summary": f"unknown job: {_job_op}"}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, err = proc.communicate(timeout=wait_seconds)
            if proc.returncode != 0:
                return {"ok": False, "summary": f"stderr: {err}"}
            try:
                result = json.loads(out)
                return {"ok": True, "summary": result}
            except json.JSONDecodeError:
                out_text = out[:500] if out else ""
                return {"ok": False, "summary": f"invalid JSON: {out_text}"}
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            with _job_lock:
                _job_proc = None
            return {"ok": False, "summary": f"job {_job_op} timed out after {wait_seconds}s"}
        except Exception as e:
            return {"ok": False, "summary": str(e)}
        finally:
            with _job_lock:
                _job_proc = None

    def _job_status(self) -> dict:
        with _job_lock:
            if _job_proc is None:
                return {"job": None, "status": None}
            return {"job": _job_op, "status": "running", "pid": _job_proc.pid}

    def _cancel_job(self) -> dict:
        with _job_lock:
            if _job_proc is None:
                return {"ok": False, "summary": "no job running"}
            _job_proc.kill()
            _job_proc = None
            _job_op = None
        return {"ok": True, "summary": "cancelled"}

    def _cuda_probe(self) -> str:
        try:
            out, _ = subprocess.Popen(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).communicate(timeout=30)
            if out:
                return {"ok": True, "summary": out.strip()}
        except Exception:
            pass
        return {"ok": False, "summary": "nvidia-smi not available or failed"}

    def _build_repo_build(self, task: str) -> list:
        return _build_repo_build_args(task)

    def _build_headless_import(self, task: str) -> list:
        return _build_headless_import_args(task)

    def _run_tests(self, task: str) -> dict:
        cmd = _build_run_tests_args_with_wait(task)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=300)
        return {"ok": proc.returncode == 0, "summary": out if out else err}

    def _check_licenses(self, task: str) -> dict:
        cmd = _build_check_licenses_args(task)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=300)
        return {"ok": proc.returncode == 0, "summary": out if out else err}

    def _kit_selftest(self, task: str) -> dict:
        cmd = _build_kit_selftest_args_with_wait(task)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=300)
        return {"ok": proc.returncode == 0, "summary": out if out else err}

    def _tail_kit_log(self) -> dict:
        if not KIT_SELFTEST_LOG.exists():
            return {"ok": False, "summary": {"error": "log not found"}}
        content = KIT_SELFTEST_LOG.read_text(encoding="utf-8")
        lines = content.splitlines()[-20:]
        return {"ok": True, "summary": {"lines": lines}}

    def _shutdown_kit(self) -> dict:
        KIT_SELFTEST_LOG.write_text("", encoding="utf-8")
        return {"ok": True, "summary": "shutdown complete"}

    def _send_event(self, event: str, data: Any = None):
        if data is None:
            data = {}
        event_data = json.dumps({"event": event, "data": data})
        self.request.sendall((event_data + "\n\n").encode("utf-8"))


def run_http_server(host: str = "127.0.0.1", port: int = 19876):
    """Run the HTTP/SSE server."""
    import socketserver
    from http.server import HTTPServer, BaseHTTPRequestHandler

    # Determine the path to the stdio MCP server module
    stdio_server_path = MCP_DIR / "mcp_server.py"
    if not stdio_server_path.is_file():
        print(f"Error: stdio server module not found at {stdio_server_path}", file=sys.stderr)
        sys.exit(1)

    # Start the stdio server in a subprocess
    status_socket = STATUS_SOCKET
    socket_dir = Path(status_socket).parent
    socket_dir.mkdir(parents=True, exist_ok=True)

    server_process = subprocess.Popen(
        [str(MCP_SERVER_MODULE_PATH), "--stdio"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def update_status():
        """Update the status socket with the server process info."""
        try:
            time.sleep(0.1)  # Give the subprocess time to start
            while server_process.poll() is None:
                status = {"status": "running", "pid": server_process.pid, "host": host, "port": port}
                STATUS_SOCKET.write_text(json.dumps(status), encoding="utf-8")
                time.sleep(0.1)
        except Exception:
            pass

    status_thread = threading.Thread(target=update_status, daemon=True)
    status_thread.start()

    # Start the HTTP/SSE server
    server_address = (host, port)
    http_server = SSEServer(server_address, SSEConnection)
    http_server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http_server.serve_forever()


def run_stdio_server():
    """Run the stdio MCP server (for direct Python invocation)."""
    # Import the stdio server module
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("mcp_server_stdio", MCP_SERVER_MODULE_PATH)
    if spec is None or spec.loader is None:
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mcp_server_stdio"] = module
    spec.loader.exec_module(module)

    server = module.mcp
    server.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v1d MCP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=19876, help="Port to bind to")
    parser.add_argument("--stdio", action="store_true", help="Run as stdio server")
    args = parser.parse_args()

    if args.stdio:
        run_stdio_server()
    else:
        run_http_server(args.host, args.port)
