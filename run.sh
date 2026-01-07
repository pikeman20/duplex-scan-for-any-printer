#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Scan Agent
# Runs FTP server and scan agent service
# ==============================================================================

bashio::log.info "Starting Scan Agent..."

# Parse configuration
CONFIG_PATH=/data/options.json
LOG_LEVEL=$(bashio::config 'log_level')
RETENTION_DAYS=$(bashio::config 'retention_days')
PRINTER_NAME=$(bashio::config 'printer.name')
PRINTER_ENABLED=$(bashio::config 'printer.enabled')
FTP_PORT=$(bashio::addon.port 2121)
FTP_USERNAME=$(bashio::config 'ftp.username')
FTP_PASSWORD=$(bashio::config 'ftp.password')

# Set log level
export LOG_LEVEL="${LOG_LEVEL^^}"
bashio::log.info "Log level set to: ${LOG_LEVEL}"

# Create directories
bashio::log.info "Setting up directories..."
mkdir -p /share/scan_inbox/{scan_duplex,copy_duplex,scan_document,card_2in1,confirm,confirm_print,reject}
mkdir -p /share/scan_out
mkdir -p /data/checkpoints

# Copy checkpoints if not exist
if [ ! -f "/data/checkpoints/depth_anything_v2_vits_slim.onnx" ]; then
    bashio::log.info "Copying checkpoint models to /data..."
    cp -r /app/checkpoints/* /data/checkpoints/
fi

# Generate config.yaml from options.json
bashio::log.info "Generating configuration..."
cat > /tmp/config.yaml << EOF
# Auto-generated from Home Assistant addon options
scan_inbox_base: /share/scan_inbox
scan_output_dir: /share/scan_out
checkpoint_dir: /data/checkpoints
retention_days: ${RETENTION_DAYS}

scan_modes:
  scan_duplex:
    enabled: $(bashio::config 'scan_modes.scan_duplex.enabled')
    auto_print: $(bashio::config 'scan_modes.scan_duplex.auto_print')
    duplex: $(bashio::config 'scan_modes.scan_duplex.duplex')
    
  scan_document:
    enabled: $(bashio::config 'scan_modes.scan_document.enabled')
    auto_print: $(bashio::config 'scan_modes.scan_document.auto_print')
    
  copy_duplex:
    enabled: $(bashio::config 'scan_modes.copy_duplex.enabled')
    auto_print: $(bashio::config 'scan_modes.copy_duplex.auto_print')
    duplex: $(bashio::config 'scan_modes.copy_duplex.duplex')
    
  card_2in1:
    enabled: $(bashio::config 'scan_modes.card_2in1.enabled')
    auto_print: $(bashio::config 'scan_modes.card_2in1.auto_print')

image_processing:
  enable_background_removal: $(bashio::config 'image_processing.enable_background_removal')
  enable_depth_anything: $(bashio::config 'image_processing.enable_depth_anything')
  max_workers: $(bashio::config 'image_processing.max_workers')

EOF

# Printer configuration
if bashio::config.true 'printer.enabled'; then
    bashio::log.info "Printer enabled: ${PRINTER_NAME}"
    cat >> /tmp/config.yaml << EOF
printer:
  name: ${PRINTER_NAME}
  enabled: true
EOF
else
    bashio::log.info "Printer disabled"
    cat >> /tmp/config.yaml << EOF
printer:
  enabled: false
EOF
fi

# Set environment variables
export SCAN_INBOX_BASE=/share/scan_inbox
export SCAN_OUTPUT_DIR=/share/scan_out
export PYTHONUNBUFFERED=1

# Start FTP server in background
bashio::log.info "Starting built-in FTP server on port ${FTP_PORT}..."

cd /app

# Create FTP startup script  
cat > /tmp/start_ftp.py << 'FTPEOF'
from src.agent.ftp_server import start_ftp_server
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s | FTP | %(message)s')

username = os.environ.get('FTP_USERNAME')
password = os.environ.get('FTP_PASSWORD')
port = int(os.environ.get('FTP_PORT', '2121'))

start_ftp_server(
    host='0.0.0.0',
    port=port,
    directory='/share/scan_inbox',
    username=username if username else None,
    password=password if password else None
)
FTPEOF

# Export env vars for Python script
export FTP_USERNAME="${FTP_USERNAME}"
export FTP_PASSWORD="${FTP_PASSWORD}"
export FTP_PORT="${FTP_PORT}"

# Start FTP server in background
python /tmp/start_ftp.py &
FTP_PID=$!
bashio::log.info "FTP server started (PID: ${FTP_PID})"

# Wait for FTP to start
sleep 2

# Display configuration info
bashio::log.info "Configuration:"
bashio::log.info "  Scan inbox: /share/scan_inbox"
bashio::log.info "  Scan output: /share/scan_out"
bashio::log.info "  Checkpoints: /data/checkpoints"
bashio::log.info "  Retention: ${RETENTION_DAYS} days"
bashio::log.info "  FTP Port: ${FTP_PORT}"
if [ -n "$FTP_USERNAME" ]; then
    bashio::log.info "  FTP User: ${FTP_USERNAME} (authenticated)"
else
    bashio::log.info "  FTP User: anonymous (no auth required)"
fi

# Check CUPS if printer enabled
if bashio::config.true 'printer.enabled'; then
    if ! command -v lpstat &> /dev/null; then
        bashio::log.warning "CUPS not available. Printing features will be disabled."
    else
        bashio::log.info "CUPS available. Printer: ${PRINTER_NAME}"
    fi
fi

# Cleanup function
cleanup() {
    bashio::log.info "Shutting down..."
    if [ -n "$FTP_PID" ]; then
        kill $FTP_PID 2>/dev/null || true
        bashio::log.info "FTP server stopped"
    fi
    if [ -n "$APP_PID" ]; then
        kill $APP_PID 2>/dev/null || true
        bashio::log.info "Scan agent stopped"
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT

# Start the scan agent application
bashio::log.info "Starting Scan Agent service..."
python -m src.main --config /tmp/config.yaml &
APP_PID=$!

# Wait for app to exit
wait $APP_PID
