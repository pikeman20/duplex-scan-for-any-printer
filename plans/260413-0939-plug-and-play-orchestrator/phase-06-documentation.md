# Phase 6: Documentation Updates

## Context Links
- Current `README.md`: project root
- Current `QUICKSTART.md`: project root
- Phase 1-5: new `run.py` behavior, `start.bat`

## Overview
- **Priority:** Medium (user-facing, but follows implementation)
- **Status:** Pending
- **Description:** Update README and QUICKSTART to reflect the new zero-config `python run.py` experience.

## Key Insights
1. README quick start section needs to become a 3-line thing
2. QUICKSTART should walk through first-time setup
3. Docker instructions unchanged — just mention they still work
4. Old flags (`--ftp`, `--web`, `--docker`) are gone — document new ones

## Requirements

### Functional
- README: Update quick start to `python run.py` (one command)
- README: Document new CLI flags (`--no-ftp`, `--no-web`, `--setup`, `--config`)
- README: Mention `start.bat` for Windows users
- README: Keep Docker section as-is
- QUICKSTART: Step-by-step for first-time users

### Non-functional
- Keep docs concise — users skim, not read
- Show expected output (what they'll see in terminal)

## Implementation Steps

### Step 1: Update README.md Quick Start section

Replace the current quick start with:

```markdown
## Quick Start

### One Command (all platforms)
```bash
pip install -r requirements.txt
python run.py
```

This starts all services automatically:
- **Scan Agent** — watches `./scan_inbox/` for scanned files
- **FTP Server** — receives scans from your Brother printer on port 2121
- **Web UI** — edit and manage scans at http://localhost:8099

### Windows Double-Click
Just double-click `start.bat` — it handles everything.

### CLI Options
```bash
python run.py              # Start everything (default)
python run.py --no-ftp     # Skip FTP server
python run.py --no-web     # Skip web UI
python run.py --setup      # Create config + directories only
python run.py --config X   # Use custom config file
```

### Docker
```bash
docker-compose up -d
```
```

### Step 2: Update QUICKSTART.md

Rewrite to focus on the new zero-config flow:

```markdown
# Quick Start Guide

## Prerequisites
- Python 3.8+
- pip

## Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

## Step 2: Run
```bash
python run.py
```

That's it! On first run, the agent will:
1. Create `config.yaml` with sensible defaults
2. Create `./scan_inbox/` directories for each scan mode
3. Start the FTP server on port 2121
4. Start the Web UI at http://localhost:8099
5. Start watching for scanned files

## Step 3: Configure Your Scanner
Point your Brother scanner's FTP settings to:
- **Server:** your-computer-ip:2121
- **Username:** anonymous
- **Password:** (leave empty)
- **Path:** /scan_duplex (or /scan_document, /card_2in1)

## Optional: Edit Config Before Running
```bash
python run.py --setup    # Creates config.yaml without starting services
# Edit config.yaml (set printer, change ports, etc.)
python run.py            # Now start with your settings
```
```

## Related Code Files

### Files to Modify
- `README.md` — update quick start and CLI usage sections
- `QUICKSTART.md` — rewrite for zero-config flow

## Todo List
- [ ] Update README.md quick start section
- [ ] Update README.md CLI flags documentation
- [ ] Add `start.bat` mention to README.md
- [ ] Rewrite QUICKSTART.md for new flow
- [ ] Verify all documented commands actually work
- [ ] Remove references to old flags (`--ftp`, `--web`, `--docker`)

## Success Criteria
- New user can follow README and have services running in <2 minutes
- No references to deprecated flags
- Docker instructions still present and correct

## Next Steps
- Phase 7: Testing
