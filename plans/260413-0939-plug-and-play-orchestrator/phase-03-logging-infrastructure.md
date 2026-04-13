# Phase 3: Logging Infrastructure

## Context Links
- Phase 1: `phase-01-subprocess-orchestrator.md` (spawn_child needs log files)
- Existing agent logger: `src/agent/logger.py` (separate, internal to agent)
- Existing test logs dir: `logs_test/` (scan_agent.log, debug.log, errors.log)

## Overview
- **Priority:** High (needed for debugging production issues)
- **Status:** Pending
- **Description:** Route each child process's stdout/stderr to dedicated log files. Orchestrator itself also logs to a file.

## Key Insights
1. `subprocess.Popen(stdout=file, stderr=STDOUT)` is the simplest approach
2. Agent already has its own internal logger writing to `logs_test/` — that's separate and stays
3. Orchestrator logs capture the *console output* of each child (print statements, startup messages, errors)
4. On Windows, users expect to see output in the console too — use a tee approach or just log to files (KISS: files only, user reads logs)
5. Log rotation is YAGNI for now — files reset on each restart

## Requirements

### Functional
- Create `./logs/` directory on startup
- `logs/agent.log` — stdout/stderr of scan agent child process
- `logs/ftp.log` — stdout/stderr of FTP server child process
- `logs/web.log` — stdout/stderr of web UI child process
- `logs/orchestrator.log` — orchestrator's own messages (startup, shutdown, child events)
- Console output: orchestrator prints key events (startup banner, shutdown, errors)

### Non-functional
- Log files truncated on each start (simple, no rotation)
- UTF-8 encoding for all log files
- Flush frequently (no buffered surprises)

## Architecture

```
run.py orchestrator
  |-- print() → console + logs/orchestrator.log (via tee_print helper)
  |
  |-- agent child → stdout/stderr piped to logs/agent.log (file handle)
  |-- ftp child   → stdout/stderr piped to logs/ftp.log (file handle)
  |-- web child   → stdout/stderr piped to logs/web.log (file handle)
```

## Implementation Steps

### Step 1: Add logging setup to `src/orchestrator_utils.py`

```python
import os
import sys
from pathlib import Path
from datetime import datetime

def setup_log_dir():
    """Create logs/ directory, return path."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir

def open_log_file(log_dir, name):
    """Open a log file for writing (truncate on start).
    
    Returns file handle. Caller must close.
    """
    path = log_dir / f"{name}.log"
    f = open(path, "w", encoding="utf-8", buffering=1)  # line-buffered
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"=== {name} started at {timestamp} ===\n")
    f.flush()
    return f

def setup_orchestrator_log(log_dir):
    """Set up orchestrator logging to both console and file.
    
    Returns the log file handle for cleanup.
    """
    log_path = log_dir / "orchestrator.log"
    log_file = open(log_path, "w", encoding="utf-8", buffering=1)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file.write(f"=== orchestrator started at {timestamp} ===\n")
    log_file.flush()
    return log_file

def log_event(log_file, msg):
    """Write a timestamped message to orchestrator log and console."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()
```

### Step 2: Update `spawn_child()` to accept log file handle

```python
def spawn_child(name, cmd, log_file_handle=None, env=None):
    """Spawn a child process with log file redirection."""
    merged_env = {**os.environ, **(env or {})}
    # Force unbuffered Python output in children
    merged_env["PYTHONUNBUFFERED"] = "1"
    
    kwargs = {
        "env": merged_env,
        "cwd": os.getcwd(),
    }
    if log_file_handle:
        kwargs["stdout"] = log_file_handle
        kwargs["stderr"] = subprocess.STDOUT
    
    proc = subprocess.Popen(cmd, **kwargs)
    return (name, proc)
```

### Step 3: Wire up in `run.py`

```python
# In main():
log_dir = setup_log_dir()
orch_log = setup_orchestrator_log(log_dir)
log_files = {}  # track for cleanup

# For each child:
log_files["agent"] = open_log_file(log_dir, "agent")
children.append(spawn_child("agent", [...], log_file_handle=log_files["agent"]))

# On shutdown:
for f in log_files.values():
    f.close()
orch_log.close()
```

## Related Code Files

### Files to Modify
- `src/orchestrator_utils.py` — add logging helpers
- `run.py` — wire up log files during spawn and cleanup

### Directories to Create
- `./logs/` — created at runtime

## Todo List
- [ ] Add `setup_log_dir()`, `open_log_file()`, `setup_orchestrator_log()`, `log_event()` to orchestrator_utils
- [ ] Update `spawn_child()` to set `PYTHONUNBUFFERED=1` in child env
- [ ] Wire log file handles in `run.py` spawn calls
- [ ] Close all log file handles on shutdown
- [ ] Add `logs/` to `.gitignore`
- [ ] Test: verify log files created and populated after startup

## Success Criteria
- `./logs/` directory created automatically on first run
- Each service writes output to its own log file
- Orchestrator events (start, stop, child death) logged with timestamps
- Log files are human-readable UTF-8 text

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Log files grow unbounded | Low (restart truncates) | Low | YAGNI — add rotation later if needed |
| File handle leak on crash | Low | Low | OS cleans up on process exit |
| Buffered output lost on crash | Medium | Medium | `PYTHONUNBUFFERED=1` + `buffering=1` |

## Next Steps
- Phase 4: Signal handling (uses log_event for shutdown messages)
