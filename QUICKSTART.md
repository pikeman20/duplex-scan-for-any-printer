# Quick Start Guide

## Option 1: Home Assistant Addon (Recommended)

1. Add the repository to HA Add-on Store
2. Install **Scan Agent**
3. Configure FTP credentials and optional printer/Telegram in the addon options
4. Start the addon — the web dashboard is available in the HA sidebar

Scanner FTP profiles: point each profile to a subfolder on the addon's FTP server (port 2121).

## Option 2: Local Development

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Create local config
```bash
cp config.local.template.yaml config.local.yaml
# Edit config.local.yaml with your local paths
```

### Step 3: Run
```bash
# Start all services (scan agent + FTP server port 2121 + web UI port 8099)
python run.py

# Windows: Double-click start.bat
```

The orchestrator automatically:
1. Creates default directories (`scan_inbox/`, `scan_out/`) if missing
2. Starts scan agent, FTP server, and web UI
3. Logs all output to `./logs/`
4. Handles graceful shutdown on Ctrl+C

### Selective Services
```bash
python run.py --no-ftp       # agent + web UI only
python run.py --no-web       # agent + FTP only
python run.py --no-ftp --no-web  # agent only
python run.py --setup        # create config + dirs, don't start
```

## Option 3: Docker (local testing)

```bash
docker-compose up -d
docker-compose logs -f scan-agent
# Web UI: http://localhost:8099
```

## Folder Structure

```
scan_inbox/
├── scan_duplex/      # Place front/back scans here (auto-paired)
├── copy_duplex/      # Scan + auto-print
├── scan_document/    # Multi-document layout (2×2 grid)
├── card_2in1/        # ID cards (2 per page)
├── test_print/       # Direct PDF print (no processing)
├── confirm/          # Files here trigger session processing
└── reject/           # Files here cancel session

scan_out/
└── Generated PDFs and metadata JSON files
```

## Next Steps

- **Models**: Download ONNX model files to `./checkpoints/` — see `plans/model-dependencies.md`
- **Printer**: Configure printer IP in addon options or `config.local.yaml`
- **Telegram**: Set bot token and chat IDs in addon options for scan notifications
- **Troubleshooting**: Check `./logs/` for detailed output
