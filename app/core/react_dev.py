"""Spawn Vite (React) dev server alongside FastAPI and open the UI in a browser."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIR = _REPO_ROOT / "frontend"


def frontend_dir() -> Path:
    return _FRONTEND_DIR


def start_react_dev_server(
    logger: logging.Logger,
    *,
    url: str = "http://127.0.0.1:5173",
) -> subprocess.Popen[bytes] | None:
    if not (_FRONTEND_DIR / "package.json").exists():
        logger.info("No frontend/ package.json — skipping React dev server")
        return None

    npm = shutil.which("npm")
    if not npm:
        logger.warning("npm not on PATH — cannot start React dev server")
        return None

    host = "127.0.0.1"
    port = "5173"
    cmd = [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        host,
        "--port",
        port,
        "--strictPort",
    ]

    try:
        kwargs: dict = {"cwd": str(_FRONTEND_DIR)}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception:
        logger.exception("Failed to start React dev server (npm run dev)")
        return None

    logger.info(
        "React dev server starting (Vite) at %s — if it fails, try: cd frontend && npm install",
        url,
    )
    return proc


def stop_react_dev_server(
    proc: subprocess.Popen[bytes] | None,
    logger: logging.Logger,
) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        logger.warning("React dev server did not exit cleanly; killing")
        proc.kill()
    except ProcessLookupError:
        pass
    except Exception:
        logger.exception("Error while stopping React dev server")


def schedule_open_browser(url: str, logger: logging.Logger, delay_sec: float = 2.0) -> None:
    def _open() -> None:
        try:
            webbrowser.open(url)
            logger.info("Opened browser: %s", url)
        except Exception:
            logger.exception("Could not open browser for React UI")

    threading.Timer(delay_sec, _open).start()
