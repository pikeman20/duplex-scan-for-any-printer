# Plan: Simplified Startup Mechanism

## Problem Statement
Current startup requires multiple steps and configuration knowledge. Users want "python main.py" or simple Docker to get core logic working immediately.

## Requirements

### From User Feedback
1. Simple command: `python run.py` or `python main.py`
2. Simple Docker: `docker-compose up` with minimal config
3. Linux service: Simple systemd setup
4. Core logic works fast with minimal setup
5. Proper design - clean separation between run and configure

### Design Principles (YAGNI/KISS/DRY)
- Keep simple things simple
- Progressive complexity - start basic, add features as needed
- Opinionated defaults - sensible out-of-box experience
- Clear upgrade path from simple to advanced

## Proposed Solution

### 1. Simple CLI Entry Point (`run.py`)
```
python run.py                    # Quick start with defaults
python run.py --mode ftp         # Start with embedded FTP
python run.py --mode watcher     # Watch existing folder (no FTP)
python run.py --docker           # Start with Docker
python run.py --service          # Install as systemd service
python run.py --web              # Start web UI server
```

Features:
- Auto-creates directories if missing
- Uses built-in defaults (local paths, no printer)
- Detects environment (Docker vs local)
- Provides helpful error messages with fix suggestions

### 2. Opinionated Defaults (`config-defaults.yaml`)
- Local development paths (./scan_inbox, ./scan_out)
- No printer configured (graceful skip)
- Conservative resource limits
- Debug logging for troubleshooting
- FTP server disabled by default (use external or enable explicitly)

### 3. Environment Auto-Detection
- Docker: Use /share/scan_inbox, /share/scan_out
- Local: Use ./scan_inbox, ./scan_out
- Raspberry Pi: Warn about memory, suggest reduced workers

### 4. Quickstart Commands
```bash
# Quick start (creates directories, uses defaults)
python run.py quickstart

# Start with Docker
python run.py docker

# Install as service
python run.py install-service
```

### 5. Clear Documentation
- README.md: One-line quick start
- QUICKSTART.md: Detailed getting started
- ADVANCED.md: Full configuration options

## Implementation Phases

### Phase 1: Simplify CLI (run.py)
- Create `run.py` with auto-detection
- Add `--help` with clear options
- Environment variable support (SCAN_MODE, SCAN_INBOX, etc.)

### Phase 2: Opinionated Defaults
- Create `config-defaults.yaml` 
- Merge with user config (user config takes precedence)
- Validate early with helpful messages

### Phase 3: Docker Quick Start
- Simplify docker-compose.yml (single service, clear comments)
- Add `.env` file for simple customization
- Create `docker-compose-quick.yml` for simplest possible start

### Phase 4: Service Installation
- Simplify `deploy/scan-agent.service`
- Create `run.py service-install` command
- Add uninstall command

### Phase 5: Documentation
- Update README with 3-line quick start
- Create QUICKSTART.md with step-by-step
- Keep ADVANCED.md for full config reference

## File Changes

### New Files
- `run.py` - Simple CLI entry point
- `config-defaults.yaml` - Default configuration
- `QUICKSTART.md` - Getting started guide
- `docker-compose-simple.yml` - Minimal Docker config

### Modified Files
- `README.md` - Update quick start section
- `docker-compose.yml` - Simplify and add comments
- `config.yaml` - Keep as reference, not required

### Removed/Deprecated
- `deploy/run-agent.sh` - Replaced by `run.py`
- Complex config options - move to ADVANCED.md

## Acceptance Criteria

1. **Local Quick Start**: `python run.py` works without any config
2. **Docker Quick Start**: `docker-compose up` works with defaults
3. **Service Install**: `python run.py --install-service` works on Linux
4. **Help Available**: `python run.py --help` shows all options
5. **Upgrade Path**: Clear how to move from simple to advanced
6. **Core Works**: With defaults, scanner files are processed correctly

## Notes
- Keep modular architecture intact (src/agent/* unchanged)
- This is a "shell" around existing well-designed core
- Focus on usability, not rewriting core logic