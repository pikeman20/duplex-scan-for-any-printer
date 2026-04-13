# Quick Start Guide

## Overview
This guide shows you how to get the PrinterDuplexScanForCheapPrint scan agent up and running quickly with minimal setup.

## Option 1: Local Quick Start (Recommended for Testing)

### Step 1: Install Dependencies
```bash
# Clone the repository
git clone <repository-url>
cd PrinterDuplexScanForCheapPrint

# Install Python dependencies
pip install -r requirements.txt
```

### Step 2: Run with Defaults
```bash
# Starts scan agent + FTP server (port 2121) + web UI (port 8099)
python run.py

# Windows: Double-click start.bat
```

This will automatically:
1. Create default directories (`scan_inbox/`, `scan_out/`)
2. Create a default `config.yaml` with safe settings
3. Start all 3 services
4. Log all output to `./logs/` directory

### Step 3: Test with Sample Files
1. Place any image file in `scan_inbox/scan_duplex/`
2. The agent will automatically:
   - Detect the file
   - Process it (orientation, deskew, background removal if models available)
   - Generate duplex PDFs in `scan_out/`
   - Clean up the input file

### Step 4: Stop the Agent
Press `Ctrl+C` to stop the agent when you're done.

## Option 2: With Embedded FTP Server

If your scanner supports FTP, use the built-in server:
```bash
python run.py --no-web  # agent + FTP only
```

Then configure your scanner:
- **Server**: Your computer's IP address
- **Port**: 2121
- **Username**: anonymous
- **Password**: (leave blank)
- **Remote Directory**: `/scan_duplex` (or other mode folders)

## Option 3: Web Interface

Start with the web interface for manual editing:
```bash
python run.py --no-ftp  # agent + web UI only
```

Then open your browser to: http://localhost:8099

## Option 4: Docker (Recommended for Production)

### Step 1: Start the Service
```bash
docker-compose -f docker-compose-simple.yml up -d
```

### Step 2: Verify It's Running
```bash
docker-compose -f docker-compose-simple.yml logs -f scan-agent
```

### Step 3: Access Web Interface
Open: http://localhost:8099

## Option 5: Install as Linux Service

For 24/7 operation on a dedicated machine:
```bash
sudo python run.py --install-service
```

Then manage with:
```bash
# Check status
sudo systemctl status scan-agent

# View logs
sudo journalctl -u scan-agent -f

# Stop service
sudo systemctl stop scan-agent

# Start service
sudo systemctl start scan-agent
```

## Folder Structure
After starting, you'll see:
```
scan_inbox/
├── scan_duplex/      # Place front/back scans here (paired automatically)
├── copy_duplex/      # Scan + auto-print
├── scan_document/    # Multi-document layout (2x2 grid)
├── card_2in1/        # ID cards (2 per page)
├── confirm/          # Files here trigger processing
├── reject/           # Files here cancel processing
└── test_print/       # Direct PDF print (no processing)

scan_out/
├── Generated PDFs go here
└── Metadata JSON files
```

## Next Steps
1. **For better scanning**: Download the required ONNX model files to `./checkpoints/` (see `plans/model-dependencies.md`)
2. **For printing**: Configure a printer in `config.yaml` or enable it via the web UI
3. **For production**: Adjust `image_processing.max_workers` based on your CPU
4. **For troubleshooting**: Check logs - they're detailed and include timing information

## Need Help?
- Check the logs for detailed error messages
- See `DEPLOYMENT.md` for advanced installation options
- Look at `plans/model-dependencies.md` for model requirements