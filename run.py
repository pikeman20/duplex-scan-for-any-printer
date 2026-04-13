#!/usr/bin/env python3
"""
Plug-and-play orchestrator: starts scan agent + FTP + web UI.

Usage:
    python run.py              # Start everything
    python run.py --no-ftp     # Skip FTP server
    python run.py --no-web     # Skip web UI
    python run.py --setup      # Create config + dirs only
    python run.py --config X   # Use custom config
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from src.orchestrator_utils import (
    check_port_available, create_default_config, install_service,
    log_event, open_log_file, print_banner, setup_log_dir,
    setup_orchestrator_log, setup_signal_handlers, spawn_child,
    terminate_children, validate_prerequisites,
)


def create_default_directories(config_path: str = None):
    """Create default directories based on config.yaml."""
    subdirs = {
        "scan_duplex": "scan_duplex", "copy_duplex": "copy_duplex",
        "scan_document": "scan_document", "card_2in1": "card_2in1",
        "confirm": "confirm", "confirm_print": "confirm_print",
        "reject": "reject", "test_print": "test_print"
    }
    inbox_base = "./scan_inbox"
    output_dir = "./scan_out"

    if config_path and Path(config_path).exists():
        try:
            import yaml
            with open(config_path, 'r') as f:
                cfg = yaml.safe_load(f)
            inbox_base = cfg.get('inbox_base', inbox_base)
            output_dir = cfg.get('output_dir', output_dir)
            subdirs = cfg.get('subdirs', subdirs)
        except Exception as e:
            print(f"Warning: Could not parse config: {e}, using defaults")

    for key in subdirs:
        Path(os.path.join(inbox_base, subdirs[key])).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Scan Agent Orchestrator")
    parser.add_argument('--no-ftp', action='store_true', help='Skip FTP server')
    parser.add_argument('--no-web', action='store_true', help='Skip web UI')
    parser.add_argument('--setup', action='store_true', help='Create config + dirs only')
    parser.add_argument('--config', type=str, default=None, help='Path to config file')
    parser.add_argument('--install-service', action='store_true', help='Install as systemd service')
    args = parser.parse_args()

    # Auto-config
    config_path = args.config or "config.yaml"
    if not Path(config_path).exists():
        config_path = create_default_config()
    create_default_directories(config_path)

    if args.setup:
        print("\nSetup complete! Edit config.yaml, then run: python run.py")
        return

    if args.install_service:
        install_service()
        return

    # Validate prerequisites and ports
    validate_prerequisites()
    if not args.no_ftp:
        check_port_available(2121, "FTP Server")
    if not args.no_web:
        check_port_available(8099, "Web UI")

    # Setup logging
    log_dir = setup_log_dir()
    orch_log = setup_orchestrator_log(log_dir)
    log_files = {}

    # Spawn children
    children = []
    services = []

    # Scan agent (always runs)
    log_files["agent"] = open_log_file(log_dir, "agent")
    agent_cmd = [sys.executable, "-m", "src.main", "--config", config_path]
    children.append(spawn_child("agent", agent_cmd, log_file_handle=log_files["agent"]))
    services.append(("Scan Agent", f"watching {config_path}"))

    # FTP server (optional)
    if not args.no_ftp:
        log_files["ftp"] = open_log_file(log_dir, "ftp")
        ftp_cmd = [sys.executable, "start_ftp_server.py"]
        children.append(spawn_child("ftp", ftp_cmd, log_file_handle=log_files["ftp"]))
        services.append(("FTP Server", "ftp://0.0.0.0:2121"))

    # Web UI (optional)
    if not args.no_web:
        log_files["web"] = open_log_file(log_dir, "web")
        web_cmd = [sys.executable, "-m", "src.web_ui_server"]
        children.append(spawn_child("web", web_cmd, log_file_handle=log_files["web"]))
        services.append(("Web UI", "http://localhost:8099 (browser)"))

    # Banner and signal handlers
    print_banner(services, config_path)
    log_event(orch_log, f"Started {len(children)} services")

    shutdown_event = threading.Event()
    setup_signal_handlers(shutdown_event)

    # Monitor loop
    exit_code = 0
    try:
        while not shutdown_event.is_set():
            for name, proc in children:
                ret = proc.poll()
                if ret is not None:
                    log_event(orch_log, f"ERROR: {name} exited unexpectedly (code {ret})")
                    log_event(orch_log, f"  Check logs/{name}.log for details")
                    exit_code = 1
                    shutdown_event.set()
                    break
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        pass

    # Shutdown
    log_event(orch_log, "Shutting down all services...")
    terminate_children(children, lambda msg: log_event(orch_log, msg))

    for f in log_files.values():
        f.close()
    orch_log.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
