#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-learn}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

find_conda_sh() {
  if [[ -n "${CONDA_EXE:-}" ]]; then
    local conda_base
    conda_base="$("$CONDA_EXE" info --base 2>/dev/null || true)"
    if [[ -n "$conda_base" && -f "$conda_base/etc/profile.d/conda.sh" ]]; then
      printf '%s\n' "$conda_base/etc/profile.d/conda.sh"
      return 0
    fi
  fi

  local candidates=(
    "$HOME/miniconda3/etc/profile.d/conda.sh"
    "$HOME/anaconda3/etc/profile.d/conda.sh"
    "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    "/usr/local/Caskroom/miniconda/base/etc/profile.d/conda.sh"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

CONDA_SH="$(find_conda_sh || true)"
if [[ -z "$CONDA_SH" ]]; then
  echo "未找到 conda.sh，请确认 Conda 已安装。" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate "$CONDA_ENV_NAME"

if ! command -v python >/dev/null 2>&1; then
  echo "激活环境后未找到 python，请检查 conda 环境: $CONDA_ENV_NAME" >&2
  exit 1
fi

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

echo "使用 conda 环境: $CONDA_ENV_NAME"
echo "项目目录: $ROOT_DIR"
echo "后端地址: http://$BACKEND_HOST:$BACKEND_PORT"
echo "前端地址: http://$FRONTEND_HOST:$FRONTEND_PORT"

python -m uvicorn app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

PROJECT_ROOT="$ROOT_DIR" BACKEND_HOST="$BACKEND_HOST" BACKEND_PORT="$BACKEND_PORT" FRONTEND_HOST="$FRONTEND_HOST" FRONTEND_PORT="$FRONTEND_PORT" python - <<'PY' &
from __future__ import annotations

import http.client
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

frontend_dir = Path(os.environ["PROJECT_ROOT"]) / "frontend"
backend_host = os.environ.get("BACKEND_HOST", "127.0.0.1")
backend_port = int(os.environ.get("BACKEND_PORT", "8000"))
frontend_host = os.environ.get("FRONTEND_HOST", "127.0.0.1")
frontend_port = int(os.environ.get("FRONTEND_PORT", "3000"))


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(frontend_dir), **kwargs)

    def _should_proxy(self):
        return self.path.startswith("/api/") or self.path == "/api/projects" or self.path.startswith("/static/")

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            return super().do_GET()

        if self._should_proxy():
            return self._proxy_request()

        return super().do_GET()

    def do_POST(self):
        if self._should_proxy():
            return self._proxy_request()
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self._should_proxy():
            return self._proxy_request()
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        if self._should_proxy():
            return self._proxy_request()
        self.send_response(204)
        self.end_headers()

    def _proxy_request(self):
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        parsed = urlsplit(self.path)
        target = parsed.path
        if parsed.query:
            target = f"{target}?{parsed.query}"

        connection = http.client.HTTPConnection(backend_host, backend_port, timeout=300)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }

        try:
            connection.request(self.command, target, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in {"transfer-encoding", "connection", "server", "date"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    def log_message(self, format, *args):
        print(f"[frontend] {self.address_string()} - {format % args}")


handler = partial(FrontendHandler)
server = ThreadingHTTPServer((frontend_host, frontend_port), handler)
print(f"Frontend server running at http://{frontend_host}:{frontend_port}")
server.serve_forever()
PY
FRONTEND_PID=$!

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

exit 1
