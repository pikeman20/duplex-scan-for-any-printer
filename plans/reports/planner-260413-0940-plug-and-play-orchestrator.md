# Planner Report: Plug-and-Play Orchestrator

**Date:** 2026-04-13
**Plan:** `plans/260413-0939-plug-and-play-orchestrator/`

## Summary

Created 7-phase implementation plan to transform `run.py` from a single-service flag-based launcher into a multi-process orchestrator that starts all 3 services (scan agent, FTP server, web UI) with zero configuration.

## Codebase Analysis

### Current State
- `run.py` (277 lines): flag-based (`--ftp`, `--web`), runs one service at a time, uses in-process imports (threads for FTP)
- `src/main.py` (898 lines): scan agent, blocks forever, accepts `--config`
- `start_ftp_server.py` (57 lines): FTP on port 2121, blocks via `serve_forever()`
- `src/web_ui_server.py` (~1550 lines): FastAPI on port 8099, blocks via `uvicorn.run()`
- Docker compose files: two variants, both work independently

### Key Design Decision
**Subprocess over threads.** All 3 services block forever and have no shared state. Subprocesses give: process isolation, independent failure, clean signal handling, and visible PIDs in task manager. Current `--ftp` mode already showed threading limitations (daemon thread, no error propagation).

## File Changes Summary

| Action | File | Lines (est.) |
|--------|------|-------------|
| Rewrite | `run.py` | ~150 (down from 277) |
| Create | `src/orchestrator_utils.py` | ~120 |
| Create | `start.bat` | ~40 |
| Modify | `README.md` | ~30 lines changed |
| Modify | `QUICKSTART.md` | ~40 lines changed |
| Optional | `tests/test_orchestrator.py` | ~60 |
| Unchanged | `src/main.py`, `start_ftp_server.py`, `src/web_ui_server.py` | — |
| Unchanged | `docker-compose.yml`, `docker-compose-simple.yml` | — |

## Phase Breakdown

| # | Phase | Est. Effort | Risk |
|---|-------|------------|------|
| 1 | Subprocess orchestrator (core rewrite) | 1-2 hrs | Medium — foundation, must work first |
| 2 | Port conflict detection | 15 min | Low — simple socket check |
| 3 | Logging infrastructure | 30 min | Low — file handles + PYTHONUNBUFFERED |
| 4 | Signal handling | 30 min | Medium — Windows/Linux differences |
| 5 | Windows start.bat | 15 min | Low — simple batch script |
| 6 | Documentation | 30 min | Low |
| 7 | Testing | 1 hr | Low — mostly manual |

**Total estimate: 4-5 hours**

## Unresolved Questions
1. Should `--install-service` be kept as-is or updated for the new orchestrator model? (Current plan: keep as-is for backward compat, only installs the agent service)
2. Should the orchestrator support `--port-ftp` and `--port-web` overrides? (Current plan: YAGNI — use config.yaml or env vars)
3. Should Docker entrypoint switch to `run.py`? (Current plan: no — Docker has its own `run.sh` / S6 service management. Separate concern.)
