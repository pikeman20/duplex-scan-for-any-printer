#!/usr/bin/with-contenv bash
# ==============================================================================
# Prepare environment and configuration
# Runs once before services start
# ==============================================================================

set -e

echo "[INFO] Preparing Scan Agent environment..."

# Check if running in HAOS (Supervisor available) or standalone
if [ -f "/data/options.json" ]; then
    CONFIG_FILE="/data/options.json"
    echo "[INFO] Using configuration from: ${CONFIG_FILE}"
else
    echo "[ERROR] Configuration file not found!"
    exit 1
fi

# Parse configuration using jq
LOG_LEVEL=$(jq -r '.log_level // "INFO"' ${CONFIG_FILE})
RETENTION_DAYS=$(jq -r '.retention_days // "7"' ${CONFIG_FILE})
PRINTER_NAME=$(jq -r '.printer.name // ""' ${CONFIG_FILE})
PRINTER_IP=$(jq -r '.printer.ip // ""' ${CONFIG_FILE})
PRINTER_ENABLED=$(jq -r '.printer.enabled // "false"' ${CONFIG_FILE})
FTP_PORT=$(jq -r '.ftp.port // "2121"' ${CONFIG_FILE})
FTP_USERNAME=$(jq -r '.ftp.username // "anonymous"' ${CONFIG_FILE})
FTP_PASSWORD=$(jq -r '.ftp.password // ""' ${CONFIG_FILE})

# Set log level
export LOG_LEVEL="${LOG_LEVEL^^}"
echo "[INFO] Log level set to: ${LOG_LEVEL}"

# Create directories
echo "[INFO] Setting up directories..."
mkdir -p /share/scan_inbox/{scan_duplex,copy_duplex,scan_document,card_2in1,confirm,confirm_print,reject,test_print}
mkdir -p /share/scan_out
mkdir -p /data/checkpoints

# Copy checkpoints if not exist
if [ ! -f "/data/checkpoints/depth_anything_v2_vits_slim.onnx" ]; then
    echo "[INFO] Copying checkpoint models to /data..."
    cp -r /app/checkpoints/* /data/checkpoints/
fi

# Generate config.yaml from options.json
echo "[INFO] Generating configuration..."
cat > /data/config.yaml << EOF
# Auto-generated from Home Assistant addon options
scan_inbox_base: /share/scan_inbox
scan_output_dir: /share/scan_out
checkpoint_dir: /data/checkpoints
retention_days: ${RETENTION_DAYS}

scan_modes:
  scan_duplex:
    enabled: $(jq -r '.scan_modes.scan_duplex.enabled // "true"' ${CONFIG_FILE})
    auto_print: $(jq -r '.scan_modes.scan_duplex.auto_print // "false"' ${CONFIG_FILE})
    duplex: $(jq -r '.scan_modes.scan_duplex.duplex // "true"' ${CONFIG_FILE})
    
  scan_document:
    enabled: $(jq -r '.scan_modes.scan_document.enabled // "true"' ${CONFIG_FILE})
    auto_print: $(jq -r '.scan_modes.scan_document.auto_print // "false"' ${CONFIG_FILE})
    
  copy_duplex:
    enabled: $(jq -r '.scan_modes.copy_duplex.enabled // "true"' ${CONFIG_FILE})
    auto_print: $(jq -r '.scan_modes.copy_duplex.auto_print // "false"' ${CONFIG_FILE})
    duplex: $(jq -r '.scan_modes.copy_duplex.duplex // "true"' ${CONFIG_FILE})
    
  card_2in1:
    enabled: $(jq -r '.scan_modes.card_2in1.enabled // "true"' ${CONFIG_FILE})
    auto_print: $(jq -r '.scan_modes.card_2in1.auto_print // "false"' ${CONFIG_FILE})

image_processing:
  enable_background_removal: $(jq -r '.image_processing.enable_background_removal // "true"' ${CONFIG_FILE})
  enable_depth_anything: $(jq -r '.image_processing.enable_depth_anything // "true"' ${CONFIG_FILE})
  max_workers: $(jq -r '.image_processing.max_workers // "4"' ${CONFIG_FILE})

EOF

# Printer configuration
if [ "${PRINTER_ENABLED}" = "true" ]; then
    if [ -n "${PRINTER_IP}" ]; then
        echo "[INFO] Printer enabled (network): ${PRINTER_IP}"
    elif [ -n "${PRINTER_NAME}" ]; then
        echo "[INFO] Printer enabled: ${PRINTER_NAME}"
    else
        echo "[INFO] Printer enabled: default"
    fi
    cat >> /data/config.yaml << EOF
printer:
  name: ${PRINTER_NAME}
  ip: ${PRINTER_IP}
  enabled: true
EOF
else
    echo "[INFO] Printer disabled"
    cat >> /data/config.yaml << EOF
printer:
  enabled: false
EOF
fi

# Create FTP environment file for service
cat > /var/run/s6/container_environment/FTP_PORT << EOF
${FTP_PORT}
EOF

cat > /var/run/s6/container_environment/FTP_USERNAME << EOF
${FTP_USERNAME}
EOF

cat > /var/run/s6/container_environment/FTP_PASSWORD << EOF
${FTP_PASSWORD}
EOF

# Set environment variables
echo "/share/scan_inbox" > /var/run/s6/container_environment/SCAN_INBOX_BASE
echo "/share/scan_out" > /var/run/s6/container_environment/SCAN_OUTPUT_DIR
echo "1" > /var/run/s6/container_environment/PYTHONUNBUFFERED

# Display configuration info
echo "[INFO] Configuration:"
echo "[INFO]   Scan inbox: /share/scan_inbox"
echo "[INFO]   Scan output: /share/scan_out"
echo "[INFO]   Checkpoints: /data/checkpoints"
echo "[INFO]   Retention: ${RETENTION_DAYS} days"
echo "[INFO]   FTP Port: ${FTP_PORT}"
if [ -n "$FTP_USERNAME" ] && [ "$FTP_USERNAME" != "anonymous" ]; then
    echo "[INFO]   FTP User: ${FTP_USERNAME} (authenticated)"
else
    echo "[INFO]   FTP User: anonymous (no auth required)"
fi

# Check CUPS if printer enabled
if [ "${PRINTER_ENABLED}" = "true" ]; then
    if ! command -v lpstat &> /dev/null; then
        echo "[WARN] CUPS not available. Printing features will be disabled."
    else
        if [ -n "${PRINTER_IP}" ]; then
            echo "[INFO] CUPS available. Network printer: ${PRINTER_IP}"
        elif [ -n "${PRINTER_NAME}" ]; then
            echo "[INFO] CUPS available. Printer: ${PRINTER_NAME}"
        else
            echo "[INFO] CUPS available. Using default printer"
        fi
    fi
fi

echo "[INFO] Preparation complete. Starting services..."
