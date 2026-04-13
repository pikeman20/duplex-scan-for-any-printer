# Phase 5: Windows start.bat

## Context Links
- Phase 1: `phase-01-subprocess-orchestrator.md` (run.py is the target)
- Phase 4: `phase-04-signal-handling.md` (Ctrl+C works in cmd.exe)

## Overview
- **Priority:** Medium (convenience, not blocking)
- **Status:** Pending
- **Description:** Create `start.bat` so Windows users can double-click to launch. Handles common errors (Python not found, venv activation).

## Key Insights
1. Double-click `.bat` opens cmd.exe, runs commands, then closes on exit
2. `pause` keeps window open so users can read errors
3. Users may have Python as `python` or `py` or `python3`
4. Virtual env at `.venv/` is common — activate if present
5. Keep it minimal — just a wrapper, all logic lives in `run.py`

## Requirements

### Functional
- Double-click `start.bat` → starts all services
- Auto-detect Python executable (`python`, `py`, `python3`)
- Activate `.venv/` if present
- Show error and pause if Python not found
- Window stays open on error (via `pause`)
- Ctrl+C works normally (cmd.exe handles it)

### Non-functional
- Single file, no dependencies
- Works on Windows 10+
- Clear error messages for non-technical users

## Implementation Steps

### Step 1: Create `start.bat`

```batch
@echo off
title Scan Agent
cd /d "%~dp0"

echo ============================================================
echo   Scan Agent - Starting...
echo ============================================================
echo.

REM Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Try to find Python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python
    goto :found_python
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=py
    goto :found_python
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python3
    goto :found_python
)

echo ERROR: Python not found!
echo.
echo Install Python 3.8+ from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo Using: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

REM Run the orchestrator
%PYTHON_CMD% run.py %*

REM If run.py exits (error or Ctrl+C), pause so user can read output
echo.
echo ============================================================
echo   Scan Agent stopped.
echo ============================================================
pause
```

## Related Code Files

### Files to Create
- `start.bat` — Windows launcher (project root)

## Todo List
- [ ] Create `start.bat` in project root
- [ ] Test: double-click launches services
- [ ] Test: Python not on PATH → shows error + pauses
- [ ] Test: `.venv/` present → activates it
- [ ] Test: Ctrl+C → clean shutdown, window stays for reading output

## Success Criteria
- Non-technical user can double-click `start.bat` and services start
- Window stays open on errors so user can read the message
- Virtual environment auto-activated if present

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| User has Python in non-standard location | Low | Low | Error message points to python.org |
| `%*` passes unexpected args | Very Low | None | Harmless — run.py argparse handles it |

## Next Steps
- Phase 6: Documentation updates
