# Phase 1: Refactor run.py to Subprocess Orchestrator

## Context Links
- Current `run.py`: project root (277 lines, flag-based, single-service)
- `src/main.py`: scan agent entry with `main()` (blocks forever)
- `start_ftp_server.py`: FTP on port 2121 (blocks forever via `serve_forever()`)
- `src/web_ui_server.py`: FastAPI + uvicorn on port 8099 (blocks forever)
- Existing plan (superseded): `plans/260412-2255-simplified-startup/plan.md`

## Overview
- **Priority:** Critical (foundation for all other phases)
- **Status:** Pending
- **Description:** Rewrite `run.py` to spawn 3 child processes via `subprocess.Popen()`, replacing the current flag-based single-service approach.

## Key Insights
1. All 3 services block forever — perfect for child processes
2. `src/main.py` already accepts `--config` flag
3. `start_ftp_server.py` has no CLI args (hardcoded port 2121)
4. `web_ui_server.py` uses `WEB_UI_PORT` env var (default 8099)
5. Current `run.py` already has `create_default_config()` and `create_default_directories()` — reuse these
6. `detect_environment()` already exists — reuse for Docker detection

## Requirements

### Functional
- `python run.py` starts all 3 services (agent + FTP + web UI)
- `python run.py --no-ftp` skips FTP server
- `python run.py --no-web` skips web UI
- `python run.py --setup` creates config + dirs, then exits
- `python run.py --config path/to/config.yaml` uses custom config
- Auto-creates `config.yaml` if missing (existing logic)
- Auto-creates directories if missing (existing logic)
- Print startup banner with service URLs and status

### Non-functional
- Keep `run.py` under 200 lines
- Extract utility functions to `src/orchestrator_utils.py` if needed
- Python 3.8+ compatible

## Architecture

```
run.py main()
  1. Parse args (--no-ftp, --no-web, --setup, --config)
  2. Auto-config: create_default_config() + create_default_directories()
  3. If --setup: print "Ready! Edit config.yaml, then run: python run.py" → exit
  4. Port checks (Phase 2)
  5. Create logs/ dir (Phase 3)
  6. Spawn children:
     a. agent = Popen([sys.executable, "-m", "src.main", "--config", config_path])
     b. ftp = Popen([sys.executable, "start_ftp_server.py"])
     c. web = Popen([sys.executable, "-m", "src.web_ui_server"])
  7. Print startup banner
  8. Monitor loop: poll children every 1s
     - If any child exits → log, terminate others, exit
  9. Signal handler (Phase 4): on interrupt → terminate all children
```

## Related Code Files

### Files to Modify
- `run.py` — complete rewrite of main logic

### Files to Create
- `src/orchestrator_utils.py` — extracted helpers (port check, process spawning, banner)

### Files Unchanged
- `src/main.py` — no changes needed
- `start_ftp_server.py` — no changes needed
- `src/web_ui_server.py` — no changes needed (already supports `__main__` via `if __name__`)

## Implementation Steps

### Step 1: Create `src/orchestrator_utils.py`

Extract shared utilities:

```python
"""Utilities for the run.py orchestrator."""
import subprocess
import sys
import os
from pathlib import Path

def validate_prerequisites():
    """Check that src/ and required modules exist."""
    required = [
        Path("src/main.py"),
        Path("start_ftp_server.py"),
        Path("src/web_ui_server.py"),
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print(f"ERROR: Missing required files: {', '.join(missing)}")
        print("Are you running from the project root directory?")
        sys.exit(1)

def spawn_child(name, cmd, log_file=None, env=None):
    """Spawn a child process with optional log file redirection.
    
    Returns (name, Popen) tuple.
    """
    merged_env = {**os.environ, **(env or {})}
    kwargs = {
        "env": merged_env,
        "cwd": os.getcwd(),
    }
    if log_file:
        kwargs["stdout"] = log_file
        kwargs["stderr"] = subprocess.STDOUT
    
    proc = subprocess.Popen(cmd, **kwargs)
    return (name, proc)

def print_banner(services, config_path):
    """Print startup banner with service info."""
    print()
    print("=" * 60)
    print("  Scan Agent — All Services Running")
    print("=" * 60)
    for name, url in services:
        print(f"  ✓ {name:20s} {url}")
    print(f"  Config: {config_path}")
    print("=" * 60)
    print("  Press Ctrl+C to stop all services")
    print("=" * 60)
    print()
```

### Step 2: Rewrite `run.py`

New structure (skeleton):

```python
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
import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

# Keep existing functions: create_default_config(), create_default_directories(), detect_environment()
# Import new helpers from orchestrator_utils

def main():
    parser = argparse.ArgumentParser(description="Scan Agent Orchestrator")
    parser.add_argument('--no-ftp', action='store_true', help='Skip FTP server')
    parser.add_argument('--no-web', action='store_true', help='Skip web UI')
    parser.add_argument('--setup', action='store_true', help='Create config + dirs only')
    parser.add_argument('--config', type=str, default=None, help='Path to config file')
    # Keep --install-service for backward compat
    parser.add_argument('--install-service', action='store_true', help='Install as systemd service')
    args = parser.parse_args()

    # Auto-config
    config_path = args.config or "config.yaml"
    if not Path(config_path).exists():
        config_path = create_default_config()
    create_default_directories(config_path)

    if args.setup:
        print("Setup complete! Edit config.yaml, then run: python run.py")
        return

    if args.install_service:
        install_service()
        return

    # Validate prerequisites
    validate_prerequisites()

    # Port conflict detection (Phase 2)
    # Logging setup (Phase 3)

    # Spawn children
    children = []
    children.append(spawn_child("agent", [sys.executable, "-m", "src.main", "--config", config_path]))
    if not args.no_ftp:
        children.append(spawn_child("ftp", [sys.executable, "start_ftp_server.py"]))
    if not args.no_web:
        children.append(spawn_child("web", [sys.executable, "-m", "src.web_ui_server"]))

    print_banner(...)

    # Monitor loop
    try:
        while True:
            for name, proc in children:
                ret = proc.poll()
                if ret is not None:
                    print(f"ERROR: {name} exited with code {ret}")
                    # Terminate others and exit
                    ...
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        for name, proc in children:
            proc.terminate()
        # Wait for children to exit
        for name, proc in children:
            proc.wait(timeout=5)
```

### Step 3: Remove Dead Code

Remove from `run.py`:
- `run_agent()` — replaced by subprocess spawn
- `start_ftp_server()` — replaced by subprocess spawn
- `start_web_ui()` — replaced by subprocess spawn
- `--ftp`, `--web`, `--docker` flags — replaced by new flags

Keep:
- `create_default_config()` — still needed
- `create_default_directories()` — still needed
- `detect_environment()` — still needed
- `install_service()` — still needed (Linux only)

## Todo List
- [ ] Create `src/orchestrator_utils.py` with `validate_prerequisites()`, `spawn_child()`, `print_banner()`
- [ ] Rewrite `run.py` argument parser (new flags)
- [ ] Implement subprocess spawning for all 3 services
- [ ] Implement monitor loop (poll children every 1s)
- [ ] Remove dead in-process functions (`run_agent`, `start_ftp_server`, `start_web_ui`)
- [ ] Keep backward-compat: `--install-service`, `--config`
- [ ] Test: `python run.py` starts all 3
- [ ] Test: `python run.py --no-ftp --no-web` starts only agent
- [ ] Test: `python run.py --setup` creates config and exits

## Success Criteria
- `python run.py` spawns 3 child processes visible in task manager
- All 3 services respond (agent watches folders, FTP accepts connections on 2121, web UI loads on 8099)
- Ctrl+C terminates all children cleanly
- `run.py` is under 200 lines

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `src.main` can't run as `-m` module | Low | High | Test early; fallback to `python src/main.py` |
| Child process env missing PYTHONPATH | Medium | Medium | Pass `PYTHONPATH=.` in env |
| Windows subprocess behavior differs | Medium | Medium | Test on Windows specifically |

## Next Steps
- Phase 2: Port conflict detection (before spawning children)
- Phase 3: Log file redirection (during spawn)
