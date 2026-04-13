# Phase 4: Signal Handling & Graceful Shutdown

## Context Links
- Phase 1: `phase-01-subprocess-orchestrator.md` (monitor loop, children list)
- Phase 3: `phase-03-logging-infrastructure.md` (log_event for shutdown messages)
- Current signal handling in `src/main.py` lines 879-880: `signal.SIGINT` + `signal.SIGTERM`
- Current `run.py` line 143: catches `KeyboardInterrupt` in `run_agent()`

## Overview
- **Priority:** High (required for clean shutdown)
- **Status:** Pending
- **Description:** Handle Ctrl+C (SIGINT), SIGTERM, and child death gracefully on both Windows and Linux.

## Key Insights
1. **Windows**: No `SIGTERM`. Only `SIGINT` (Ctrl+C) works. `signal.signal(signal.SIGTERM, ...)` silently ignored.
2. **Windows**: `proc.terminate()` sends `TerminateProcess` (hard kill). No graceful signal.
3. **Linux**: Both `SIGINT` and `SIGTERM` work. `proc.terminate()` sends `SIGTERM`.
4. **Child cascade**: When orchestrator gets SIGINT, Python also sends SIGINT to children in same process group on both OS. But explicit cleanup is safer.
5. **Child death detection**: Monitor loop polls `proc.poll()` — if not None, child exited.
6. Strategy: on any shutdown trigger → terminate all children → wait with timeout → force kill stragglers.

## Requirements

### Functional
- Ctrl+C in terminal → all children terminated within 5 seconds
- SIGTERM on Linux → same behavior as Ctrl+C
- Any child exits unexpectedly → log which one, terminate others, exit with code 1
- Graceful wait: give children 3s to exit after terminate, then force kill
- Print "Shutting down..." message on shutdown
- Close all log file handles

### Non-functional
- No zombie processes left behind
- Works on Windows 10+ and Linux (Ubuntu 20.04+)
- No external dependencies

## Architecture

```
Shutdown Flow:
  Trigger (Ctrl+C / SIGTERM / child death)
    → Set shutdown_event flag
    → Monitor loop detects flag
    → For each child: proc.terminate()
    → Wait up to 3s for each child
    → If still alive: proc.kill() (SIGKILL / TerminateProcess)
    → Close log files
    → Exit
```

## Implementation Steps

### Step 1: Add shutdown logic to `src/orchestrator_utils.py`

```python
import signal
import threading

def terminate_children(children, log_fn, timeout=3):
    """Terminate all child processes gracefully, force-kill if needed.
    
    Args:
        children: list of (name, Popen) tuples
        log_fn: callable for logging messages
        timeout: seconds to wait before force-killing
    """
    # Send terminate signal
    for name, proc in children:
        if proc.poll() is None:  # still running
            log_fn(f"Stopping {name}...")
            try:
                proc.terminate()
            except OSError:
                pass  # already dead
    
    # Wait for graceful exit
    for name, proc in children:
        try:
            proc.wait(timeout=timeout)
            log_fn(f"  {name} stopped (exit code {proc.returncode})")
        except subprocess.TimeoutExpired:
            log_fn(f"  {name} didn't stop in {timeout}s, force killing...")
            proc.kill()
            proc.wait(timeout=2)
            log_fn(f"  {name} killed")

def setup_signal_handlers(shutdown_event):
    """Register signal handlers for graceful shutdown.
    
    Args:
        shutdown_event: threading.Event to set on signal
    """
    def _handler(signum, frame):
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, _handler)
    # SIGTERM only on POSIX
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _handler)
```

### Step 2: Update monitor loop in `run.py`

```python
import threading

def main():
    # ... setup, spawn children ...
    
    shutdown_event = threading.Event()
    setup_signal_handlers(shutdown_event)
    
    # Monitor loop
    exit_code = 0
    while not shutdown_event.is_set():
        for name, proc in children:
            ret = proc.poll()
            if ret is not None:
                log_event(orch_log, f"ERROR: {name} exited unexpectedly (code {ret})")
                log_event(orch_log, f"  Check logs/{name}.log for details")
                exit_code = 1
                shutdown_event.set()
                break
        
        # Sleep in small increments so we respond to signals quickly
        shutdown_event.wait(timeout=1.0)
    
    # Shutdown
    log_event(orch_log, "Shutting down all services...")
    terminate_children(children, lambda msg: log_event(orch_log, msg))
    
    # Cleanup log files
    for f in log_files.values():
        f.close()
    orch_log.close()
    
    sys.exit(exit_code)
```

### Step 3: Windows-specific considerations

```python
# Windows: Ctrl+C in cmd.exe sends SIGINT to entire process group.
# Children (Python processes) will also receive it and may exit on their own.
# Our terminate_children() handles both cases:
#   - If child already exited from SIGINT → proc.poll() != None → skip
#   - If child still running → proc.terminate() → wait → kill

# No special Windows code needed beyond what's already handled.
# Key: SIGTERM handler registration silently succeeds but never fires on Windows.
# That's fine — Windows users use Ctrl+C (SIGINT) exclusively.
```

## Related Code Files

### Files to Modify
- `src/orchestrator_utils.py` — add `terminate_children()`, `setup_signal_handlers()`
- `run.py` — use `threading.Event` for shutdown coordination

## Todo List
- [ ] Implement `terminate_children()` with graceful timeout + force kill
- [ ] Implement `setup_signal_handlers()` with POSIX/Windows awareness
- [ ] Update monitor loop to use `shutdown_event.wait(timeout=1.0)` instead of `time.sleep(1)`
- [ ] Handle child death → set shutdown_event → terminate siblings
- [ ] Close log file handles on shutdown
- [ ] Test: Ctrl+C on Windows → all children die within 5s
- [ ] Test: `kill <pid>` on Linux → all children die within 5s
- [ ] Test: kill one child manually → orchestrator shuts down others

## Success Criteria
- No zombie processes after Ctrl+C
- Child death triggers clean shutdown of remaining services
- Shutdown completes within 5 seconds
- Log files contain shutdown events with timestamps

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Children ignore SIGTERM | Low | Medium | Force kill after 3s timeout |
| Signal handler race with monitor loop | Low | Low | `threading.Event` is thread-safe |
| Windows `terminate()` is hard kill (no cleanup) | Expected | Low | Acceptable — children are stateless servers |

## Next Steps
- Phase 5: Windows `start.bat` wrapper
