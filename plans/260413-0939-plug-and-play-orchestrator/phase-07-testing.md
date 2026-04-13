# Phase 7: Testing

## Context Links
- Phases 1-6: all implementation phases
- Existing tests: `tests/` directory, `integration_tests.py`
- Test FTP simulation: `test_ftp_user_simulation.py`

## Overview
- **Priority:** High (validates everything works)
- **Status:** Pending
- **Description:** Manual and automated testing of the orchestrator on Windows and Linux.

## Key Insights
1. Orchestrator is a process manager — hard to unit test, easier to integration test
2. Core services already have their own tests — orchestrator testing focuses on spawn/shutdown/logging
3. Windows is the development environment — test there first
4. Linux testing can happen via Docker or WSL

## Test Plan

### Test 1: Happy Path — All Services Start
```
Command: python run.py
Expected:
  - config.yaml created if missing
  - scan_inbox/ directories created
  - logs/ directory created with agent.log, ftp.log, web.log, orchestrator.log
  - Banner shows all 3 services running
  - FTP: telnet localhost 2121 responds
  - Web UI: browser at http://localhost:8099 loads
  - Agent: logs/agent.log shows "Watching:" messages
Verify: All 3 processes visible in Task Manager / ps
```

### Test 2: Ctrl+C Shutdown
```
Command: python run.py, then Ctrl+C after 5 seconds
Expected:
  - "Shutting down..." message printed
  - All 3 child processes terminated within 5s
  - Log files contain shutdown events
  - No zombie processes (check Task Manager / ps)
Verify: Re-run python run.py immediately (ports should be free)
```

### Test 3: Child Death Recovery
```
Command: python run.py, then kill the FTP child process manually
Expected:
  - Orchestrator detects FTP death within 2s
  - Logs: "ERROR: ftp exited unexpectedly (code X)"
  - Remaining children (agent, web) terminated
  - Orchestrator exits with code 1
```

### Test 4: Port Conflict
```
Setup: Start a dummy listener on port 2121 (python -c "import socket; s=socket.socket(); s.bind(('',2121)); s.listen(); input()")
Command: python run.py
Expected:
  - "ERROR: Port 2121 is already in use (needed for FTP Server)"
  - Suggests --no-ftp
  - Exits immediately, no children spawned
```

### Test 5: --no-ftp and --no-web
```
Command: python run.py --no-ftp --no-web
Expected:
  - Only scan agent started
  - No FTP log file written
  - No web log file written  
  - Banner shows only agent running
```

### Test 6: --setup Mode
```
Command: python run.py --setup (with no existing config.yaml)
Expected:
  - config.yaml created
  - scan_inbox/ directories created
  - Prints "Setup complete!" message
  - Exits immediately (no services started)
  - No logs/ directory created
```

### Test 7: --config Custom Path
```
Command: python run.py --config /tmp/my-config.yaml
Expected:
  - Uses specified config file
  - Agent spawned with --config /tmp/my-config.yaml argument
```

### Test 8: start.bat (Windows Only)
```
Action: Double-click start.bat
Expected:
  - Window opens with title "Scan Agent"
  - .venv activated if present
  - Services start
  - Ctrl+C stops services
  - Window stays open with "Scan Agent stopped." and pause
```

### Test 9: Log File Content
```
Command: python run.py, wait 10s, Ctrl+C
Expected:
  - logs/orchestrator.log: startup banner, shutdown events, timestamps
  - logs/agent.log: agent startup messages
  - logs/ftp.log: FTP server started message
  - logs/web.log: uvicorn startup message
  - All files are UTF-8 readable
```

### Test 10: Existing Config Preserved
```
Setup: Existing config.yaml with custom settings
Command: python run.py
Expected:
  - "Using existing config.yaml" message
  - Custom settings NOT overwritten
```

## Automated Test Script (Optional)

If time permits, create `tests/test_orchestrator.py`:

```python
"""Integration tests for orchestrator spawn/shutdown."""
import subprocess
import sys
import time
import socket
import os
import signal

def test_orchestrator_starts_and_stops():
    """Spawn orchestrator, verify children, send SIGINT, verify cleanup."""
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # Wait for startup
    time.sleep(5)
    
    # Verify services are running
    assert _port_in_use(2121), "FTP should be listening"
    assert _port_in_use(8099), "Web UI should be listening"
    
    # Send Ctrl+C
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    
    # Verify cleanup
    time.sleep(1)
    assert not _port_in_use(2121), "FTP port should be free"
    assert not _port_in_use(8099), "Web UI port should be free"

def test_port_conflict_detection():
    """Occupy a port, verify orchestrator refuses to start."""
    # Occupy port 2121
    blocker = socket.socket()
    blocker.bind(("", 2121))
    blocker.listen(1)
    
    try:
        proc = subprocess.Popen(
            [sys.executable, "run.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        ret = proc.wait(timeout=5)
        assert ret != 0, "Should exit with error"
        output = proc.stdout.read().decode()
        assert "Port 2121" in output
    finally:
        blocker.close()

def _port_in_use(port):
    sock = socket.socket()
    try:
        sock.connect(("127.0.0.1", port))
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False
```

## Todo List
- [ ] Test 1: Happy path — all services start
- [ ] Test 2: Ctrl+C shutdown
- [ ] Test 3: Child death recovery
- [ ] Test 4: Port conflict detection
- [ ] Test 5: --no-ftp and --no-web flags
- [ ] Test 6: --setup mode
- [ ] Test 7: --config custom path
- [ ] Test 8: start.bat on Windows
- [ ] Test 9: Log file content verification
- [ ] Test 10: Existing config preserved
- [ ] (Optional) Create `tests/test_orchestrator.py` automated tests

## Success Criteria
- All 10 manual tests pass on Windows
- Tests 1-7, 9-10 pass on Linux (via WSL or Docker)
- No zombie processes after any test
- Clean re-start after shutdown (ports freed)

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tests pass locally, fail in CI | Medium | Low | Manual testing acceptable for orchestrator |
| Timing-dependent tests flaky | Medium | Low | Use generous timeouts (5-10s) |
