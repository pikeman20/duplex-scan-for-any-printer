# Scan Agent — Brother Scanner Home Assistant Addon

A Home Assistant addon that extends the Brother MFC-7860DW "Scan to FTP" feature into predictable duplex scanning, copying, small-document layout, and 2-in-1 card scanning.

Core philosophy: reflect physical intent; do not guess, beautify, or auto-center.

## Features

- **Scan duplex** — Pair fronts/backs, interleaved PDF with auto-orientation correction
- **Copy duplex** — Render PDF, print via CUPS two-sided
- **Scan small documents** — Strict 2×2 quadrant layout, respects physical placement
- **Card/ID 2-in-1** — Pair images per page (left-right or top-bottom)
- **Session management** — Explicit Confirm/Reject with timeout fallback and mode switching
- **Web dashboard** — Monitor sessions, view scan history, manage settings
- **Telegram notifications** — Get notified when a session is ready to confirm

## Scan Modes

```
/share/scan_inbox/
 ├─ scan_duplex/      # Duplex scanning with auto-orientation
 ├─ copy_duplex/      # Duplex scanning + auto-print
 ├─ scan_document/    # Multi-document layout (2×2 grid)
 ├─ card_2in1/        # ID/card scanning (2 cards per page)
 ├─ test_print/       # Quick printer test (direct print, no processing)
 ├─ confirm/          # Confirm session processing
 └─ reject/           # Cancel session
```

Each FTP profile on the scanner should point to one of these subfolders.

## Installation (Home Assistant)

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the three-dot menu → **Repositories** → add your repository URL
3. Find **Scan Agent** and click **Install**
4. Configure options (FTP credentials, printer, Telegram)
5. Start the addon

The addon exposes:
- **Port 2121** — FTP control (scanner uploads)
- **Ports 30000–30002** — FTP passive data ports
- **Ingress** — Web dashboard (accessible from HA sidebar)

## Scanner Configuration (Brother MFC-7860DW)

Set up an FTP profile on the scanner for each scan mode:

| Profile | Remote Path |
|---------|-------------|
| Scan Duplex | `/scan_duplex` |
| Copy Duplex | `/copy_duplex` |
| Scan Document | `/scan_document` |
| Card 2-in-1 | `/card_2in1` |

- **Server**: Home Assistant IP address
- **Port**: 2121
- **Username/Password**: as configured in addon options (or leave blank for anonymous)

## Local Development

### Requirements
- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

### Run locally
```bash
# Copy and edit the local config
cp config.local.template.yaml config.local.yaml
# Edit config.local.yaml with your local paths

# Start all services (scan agent + FTP server + web UI)
python run.py

# Start selectively
python run.py --no-ftp      # agent + web UI only
python run.py --no-web      # agent + FTP only
python run.py --no-ftp --no-web  # agent only

# Setup directories only (no services)
python run.py --setup
```

### Docker (local testing)
```bash
docker-compose up -d
docker-compose logs -f scan-agent
```

### Run tests
```bash
pytest tests/
```

## Notes

- Duplex scan assumes user scans fronts first, then backs; images are interleaved as `1F, 1B, 2F, 2B, ...`
- Card 2-in-1 pairs two images per page: landscape → left-right, portrait → top-bottom
- Scan Document uses a 2×2 logical grid placed by bounding box center — no auto-centering
- Confirm/Reject is triggered by any file arriving in the `confirm/` or `reject/` folder
- Printing uses CUPS `lp` and only works on Linux (inside the container)
- Background removal requires ONNX models in `checkpoints/` — see `plans/model-dependencies.md`

## License

Internal deployment; no external license headers added.

