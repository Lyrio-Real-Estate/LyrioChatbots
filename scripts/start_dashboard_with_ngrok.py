#!/usr/bin/env python3
"""
Start Streamlit dashboard with an ngrok tunnel for GHL OAuth v2 local dev.

Usage:
  python scripts/start_dashboard_with_ngrok.py

What it does:
1. Reuses an existing ngrok tunnel for the Streamlit port or starts one.
2. Resolves HTTPS public URL from ngrok.
3. Writes GHL_OAUTH_REDIRECT_URI in .env (optional).
4. Starts Streamlit with env vars set for OAuth redirect resolution.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Streamlit dashboard behind ngrok for OAuth dev.")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port (default: 8501)")
    parser.add_argument(
        "--streamlit-file",
        default="command_center/dashboard_v3.py",
        help="Streamlit entrypoint path",
    )
    parser.add_argument(
        "--ngrok-api-url",
        default="http://127.0.0.1:4040/api/tunnels",
        help="ngrok local API endpoint",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file to update",
    )
    parser.add_argument(
        "--no-write-env",
        action="store_true",
        help="Do not persist redirect URI into .env",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for ngrok tunnel to appear",
    )
    return parser.parse_args()


def _load_tunnels(ngrok_api_url: str) -> list[dict[str, Any]]:
    with urlopen(ngrok_api_url, timeout=2.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tunnels = payload.get("tunnels", []) if isinstance(payload, dict) else []
    return tunnels if isinstance(tunnels, list) else []


def _extract_addr_port(addr: str) -> Optional[int]:
    text = str(addr or "").strip()
    if not text:
        return None
    if ":" in text:
        candidate = text.rsplit(":", 1)[-1]
        if candidate.isdigit():
            return int(candidate)
    if text.isdigit():
        return int(text)
    return None


def find_ngrok_https_url(ngrok_api_url: str, expected_port: int) -> Optional[str]:
    try:
        tunnels = _load_tunnels(ngrok_api_url)
    except Exception:
        return None

    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = str(tunnel.get("public_url") or "").strip()
        if not public_url.startswith("https://"):
            continue
        config = tunnel.get("config", {}) if isinstance(tunnel.get("config"), dict) else {}
        addr_port = _extract_addr_port(str(config.get("addr") or ""))
        if addr_port == expected_port:
            return public_url.rstrip("/")
    return None


def start_ngrok(port: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["ngrok", "http", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def run() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    started_ngrok: Optional[subprocess.Popen[bytes]] = None
    public_url = find_ngrok_https_url(args.ngrok_api_url, args.port)
    if not public_url:
        started_ngrok = start_ngrok(args.port)
        deadline = time.time() + max(args.startup_timeout, 3.0)
        while time.time() < deadline:
            public_url = find_ngrok_https_url(args.ngrok_api_url, args.port)
            if public_url:
                break
            time.sleep(0.4)

    if not public_url:
        if started_ngrok:
            started_ngrok.terminate()
        print("Failed to get ngrok HTTPS URL. Ensure ngrok is installed and authenticated.", file=sys.stderr)
        return 1

    env_file = (repo_root / args.env_file).resolve() if not Path(args.env_file).is_absolute() else Path(args.env_file)
    if not args.no_write_env:
        upsert_env_var(env_file, "GHL_OAUTH_REDIRECT_URI", public_url)
        upsert_env_var(env_file, "GHL_OAUTH_USE_NGROK", "true")
        upsert_env_var(env_file, "GHL_OAUTH_NGROK_API_URL", args.ngrok_api_url)

    print(f"ngrok public URL: {public_url}")
    print(f"OAuth redirect URI: {public_url}")
    print("Ensure this exact URI is added to your GHL OAuth app redirect URIs.")

    child_env = os.environ.copy()
    child_env["GHL_OAUTH_REDIRECT_URI"] = public_url
    child_env["GHL_OAUTH_USE_NGROK"] = "true"
    child_env["GHL_OAUTH_NGROK_API_URL"] = args.ngrok_api_url

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        args.streamlit_file,
        "--server.port",
        str(args.port),
    ]

    streamlit_proc = subprocess.Popen(cmd, cwd=str(repo_root), env=child_env)
    try:
        return streamlit_proc.wait()
    finally:
        if started_ngrok and started_ngrok.poll() is None:
            started_ngrok.terminate()
            try:
                started_ngrok.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                started_ngrok.kill()


if __name__ == "__main__":
    raise SystemExit(run())
