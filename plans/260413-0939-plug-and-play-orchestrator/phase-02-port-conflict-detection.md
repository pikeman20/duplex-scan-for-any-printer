# Phase 2: Port Conflict Detection

## Context Links
- Phase 1: `phase-01-subprocess-orchestrator.md`
- FTP server port: `start_ftp_server.py` line 25 → port 2121
- Web UI port: `src/web_ui_server.py` line 62 → `WEB_UI_PORT` env var, default 8099

## Overview
- **Priority:** High (must run before spawning children)
- **Status:** Pending
- **Description:** Check if ports 2121 and 8099 are available before spawning FTP and web UI. Print clear error with the conflicting process if possible.

## Key Insights
1. `socket.bind()` is the most reliable cross-platform port check
2. On Windows, `netstat` can identify the conflicting process but is slow
3. On Linux, `ss` or `lsof` can identify conflicting process
4. Keep it simple: just check if port is available, don't try to identify the process (YAGNI)
5. Only check ports for services that will actually be started (respect `--no-ftp`, `--no-web`)

## Requirements

### Functional
- Before spawning FTP: check port 2121 is free
- Before spawning web UI: check port 8099 is free
- If port in use: print clear error message with port number and exit
- Skip check for disabled services

### Non-functional
- Cross-platform (Windows + Linux)
- Fast (<100ms total)
- No external dependencies

## Implementation Steps

### Step 1: Add `check_port_available()` to `src/orchestrator_utils.py`

```python
import socket

def check_port_available(port, service_name):
    """Check if a port is available. Exit with error if not.
    
    Args:
        port: Port number to check
        service_name: Human-readable name for error messages
    
    Returns:
        True if available
    
    Raises:
        SystemExit if port is in use
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
        sock.close()
        return True
    except OSError:
        print(f"ERROR: Port {port} is already in use (needed for {service_name})")
        print(f"  → Stop the other process using port {port}, or")
        print(f"  → Use --no-{'ftp' if port == 2121 else 'web'} to skip this service")
        sys.exit(1)
```

### Step 2: Call from `run.py` before spawning

```python
# In main(), after setup, before spawning:
if not args.no_ftp:
    check_port_available(2121, "FTP Server")
if not args.no_web:
    check_port_available(8099, "Web UI")
```

## Related Code Files

### Files to Modify
- `src/orchestrator_utils.py` — add `check_port_available()`
- `run.py` — call port checks before spawn

## Todo List
- [ ] Implement `check_port_available()` in `src/orchestrator_utils.py`
- [ ] Call port checks in `run.py` before spawning children
- [ ] Test with port occupied (e.g., start a dummy listener first)
- [ ] Test with port free (normal case)
- [ ] Test skip when `--no-ftp` / `--no-web` is passed

## Success Criteria
- Port conflict detected before any child is spawned
- Clear error message tells user which port and which service
- Suggests `--no-ftp` or `--no-web` as workaround
- No false positives (ephemeral port reuse edge case handled by SO_REUSEADDR not needed — we bind and immediately release)

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TOCTOU: port free at check, taken by spawn time | Very Low | Low | Acceptable — child will fail and orchestrator catches it |
| `socket.bind()` needs admin on Windows for low ports | N/A | N/A | 2121 and 8099 are high ports, no admin needed |

## Next Steps
- Phase 3: Logging infrastructure
