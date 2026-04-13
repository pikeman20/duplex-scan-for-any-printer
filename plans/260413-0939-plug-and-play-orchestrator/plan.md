# Plan: Plug-and-Play Orchestrator

## Problem
`run.py` requires flags (`--ftp`, `--web`) and can only run one service at a time. Users must launch 3 separate terminals. Goal: single `python run.py` starts everything with zero config.

## Architecture

```
run.py (orchestrator process)
  |-- subprocess: python -m src.main --config config.yaml   (scan agent)
  |-- subprocess: python start_ftp_server.py                (FTP server :2121)
  |-- subprocess: python -m src.web_ui_server               (web UI :8099)
  |
  |-- monitors all 3 children
  |-- captures stdout/stderr -> logs/
  |-- graceful shutdown on Ctrl+C / SIGTERM
```

## Phases

| # | Phase | File(s) | Status |
|---|-------|---------|--------|
| 1 | [Refactor run.py to subprocess orchestrator](phase-01-subprocess-orchestrator.md) | `run.py`, `src/orchestrator_utils.py` | ✅ Complete |
| 2 | [Port conflict detection](phase-02-port-conflict-detection.md) | `run.py`, `src/orchestrator_utils.py` | ✅ Complete |
| 3 | [Logging infrastructure](phase-03-logging-infrastructure.md) | `run.py`, `src/orchestrator_utils.py`, `logs/` | ✅ Complete |
| 4 | [Signal handling & graceful shutdown](phase-04-signal-handling.md) | `run.py`, `src/orchestrator_utils.py` | ✅ Complete |
| 5 | [Windows start.bat](phase-05-windows-start-bat.md) | `start.bat` | ✅ Complete |
| 6 | [Documentation updates](phase-06-documentation.md) | `README.md`, `QUICKSTART.md` | ✅ Complete |
| 7 | [Testing](phase-07-testing.md) | manual + integration | ✅ Complete |

## Key Decisions
- `subprocess.Popen()` not threads (process isolation, independent failure)
- Child death = log error + shutdown all (fail-fast, no zombie services)
- Default = all 3 services; `--no-ftp` / `--no-web` to disable
- `--setup` flag for config-only initialization
- `--config` still works for advanced users
- Docker compose files unchanged (backward compatible)

## Constraints
- Python 3.8+ compat (no walrus operators in critical paths)
- Windows + Linux support
- Keep `run.py` under 200 lines (extract helpers to `src/orchestrator_utils.py` if needed)
- Existing `src/main.py`, `start_ftp_server.py`, `src/web_ui_server.py` untouched

## Supersedes
- `plans/260412-2255-simplified-startup/` (less concrete, flag-based approach)
