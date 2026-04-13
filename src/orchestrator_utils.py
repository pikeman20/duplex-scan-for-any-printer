"""Utilities for run.py subprocess orchestrator."""
from __future__ import annotations

import os
import platform
import signal
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def validate_prerequisites():
    """Check required service files exist."""
    required = [Path("src/main.py"), Path("start_ftp_server.py"), Path("src/web_ui_server.py")]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print(f"ERROR: Missing required files: {', '.join(missing)}")
        print("Are you running from the project root directory?")
        sys.exit(1)


def check_port_available(port: int, service_name: str) -> bool:
    """Check if a TCP port is free. Exits with error if in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
        sock.close()
        return True
    except OSError:
        flag = "ftp" if port == 2121 else "web"
        print(f"ERROR: Port {port} is already in use (needed for {service_name})")
        print(f"  -> Stop the other process using port {port}, or")
        print(f"  -> Use --no-{flag} to skip this service")
        sys.exit(1)


def setup_log_dir() -> Path:
    """Create ./logs/ directory."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def open_log_file(log_dir: Path, name: str):
    """Open a truncated log file (line-buffered, UTF-8). Caller closes."""
    path = log_dir / f"{name}.log"
    f = open(path, "w", encoding="utf-8", buffering=1)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"=== {name} started at {timestamp} ===\n")
    f.flush()
    return f


def setup_orchestrator_log(log_dir: Path):
    """Open orchestrator.log."""
    return open_log_file(log_dir, "orchestrator")


def log_event(log_file, msg: str) -> None:
    """Write timestamped message to console and log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()


def spawn_child(name: str, cmd: list, log_file_handle=None, env: dict | None = None):
    """Spawn child process with optional log redirection.

    Sets PYTHONUNBUFFERED=1 so children flush output immediately.
    Adds project root and src/ to PYTHONPATH for module imports.
    """
    merged_env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", **(env or {})}

    # Add project root and src/ to PYTHONPATH
    project_root = os.getcwd()
    src_dir = os.path.join(project_root, "src")
    extra_paths = os.pathsep.join([project_root, src_dir])
    existing = merged_env.get('PYTHONPATH', '')
    merged_env['PYTHONPATH'] = f"{extra_paths}{os.pathsep}{existing}" if existing else extra_paths

    kwargs: dict = {"env": merged_env, "cwd": os.getcwd()}
    if log_file_handle is not None:
        kwargs["stdout"] = log_file_handle
        kwargs["stderr"] = subprocess.STDOUT

    proc = subprocess.Popen(cmd, **kwargs)
    return (name, proc)


def print_banner(services: list, config_path: str) -> None:
    """Print startup banner with service info."""
    print()
    print("=" * 60)
    print("  Scan Agent - All Services Running")
    print("=" * 60)
    for display_name, info in services:
        print(f"  [+] {display_name:<20s} {info}")
    print(f"  Config: {config_path}")
    print("=" * 60)
    print("  Press Ctrl+C to stop all services")
    print("=" * 60)
    print()


def terminate_children(children: list, log_fn, timeout: int = 3) -> None:
    """Terminate all children, force-kill stragglers after timeout."""
    for name, proc in children:
        if proc.poll() is None:
            log_fn(f"Stopping {name}...")
            try:
                proc.terminate()
            except OSError:
                pass

    for name, proc in children:
        try:
            proc.wait(timeout=timeout)
            log_fn(f"  {name} stopped (exit code {proc.returncode})")
        except subprocess.TimeoutExpired:
            log_fn(f"  {name} didn't stop in {timeout}s, force killing...")
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            log_fn(f"  {name} killed")


def setup_signal_handlers(shutdown_event) -> None:
    """Register SIGINT/SIGTERM to set threading.Event."""
    def _handler(signum, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


def detect_environment() -> str:
    """Detect if running in Docker, Windows, Linux."""
    if os.path.exists("/.dockerenv"):
        return "docker"
    elif platform.system().lower() == "windows":
        return "windows"
    else:
        return "linux"


def create_default_config() -> str:
    """Create minimal default config if none exists."""
    config_path = Path("config.yaml")
    if config_path.exists():
        return str(config_path)

    print("Creating default configuration...")
    default_config = (
        "# Default configuration for quick start\n"
        "inbox_base: ./scan_inbox\n"
        "subdirs:\n"
        "  scan_duplex: scan_duplex\n"
        "  copy_duplex: copy_duplex\n"
        "  scan_document: scan_document\n"
        "  card_2in1: card_2in1\n"
        "  confirm: confirm\n"
        "  confirm_print: confirm_print\n"
        "  reject: reject\n"
        "  test_print: test_print\n"
        "\n"
        "output_dir: ./scan_out\n"
        "session_timeout_seconds: 120\n"
        "delete_inbox_files_after_process: true\n"
        "test_mode: true\n"
        "\n"
        "a4_page:\n"
        "  width_pt: 595\n"
        "  height_pt: 842\n"
        "\n"
        "margin_pt: 15\n"
        "gutter_pt: 18\n"
        "\n"
        "# Printer settings (disabled by default for quick start)\n"
        "printer:\n"
        "  enabled: false\n"
        "  name: \"\"\n"
        "  ip: \"\"\n"
        "\n"
        "# Image processing settings\n"
        "image_processing:\n"
        "  max_workers: 2\n"
        "  enable_background_removal: true\n"
        "  enable_depth_anything: false\n"
        "\n"
        "# FTP server settings (embedded server)\n"
        "ftp:\n"
        "  enabled: false\n"
        "  port: 2121\n"
        "  username: anonymous\n"
        "  password: \"\"\n"
    )
    with open(config_path, 'w') as f:
        f.write(default_config)
    print("Default config.yaml created")
    return str(config_path)


def install_service() -> None:
    """Install as systemd service (Linux only)."""
    if detect_environment() != "linux":
        print("Service installation only supported on Linux")
        return

    print("Installing as systemd service...")
    service_content = """[Unit]
Description=Scan Agent
After=network.target

[Service]
Type=simple
User=scanagent
Group=scanagent
WorkingDirectory=/opt/scan-agent
ExecStart=/opt/scan-agent/.venv/bin/python /opt/scan-agent/run.py
Restart=always
RestartSec=10

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

MemoryMax=1G
TasksMax=100

[Install]
WantedBy=multi-user.target
"""
    with open("/tmp/scan-agent.service", "w") as f:
        f.write(service_content)

    subprocess.run(["sudo", "mv", "/tmp/scan-agent.service", "/etc/systemd/system/"])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", "scan-agent"])
    subprocess.run(["sudo", "systemctl", "start", "scan-agent"])

    print("Service installed and started")