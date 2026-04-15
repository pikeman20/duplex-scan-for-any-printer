#!/usr/bin/with-contenv bashio
# ==============================================================================
# Prepare environment and configuration
# Runs once before services start
# Uses bashio to read Home Assistant addon options
# ==============================================================================

set -e

bashio::log.info "Preparing Scan Agent environment..."

# ── Read options via bashio ──────────────────────────────────────────────────
SESSION_TIMEOUT=$(bashio::config 'session_timeout_seconds' '300')
DELETE_INBOX=$(bashio::config 'delete_inbox_files_after_process' 'true')
TEST_MODE=$(bashio::config 'test_mode' 'false')
PRINTER_ENABLED=$(bashio::config 'printer.enabled' 'false')
PRINTER_NAME=$(bashio::config 'printer.name' '')
PRINTER_IP=$(bashio::config 'printer.ip' '')
FTP_USERNAME=$(bashio::config 'ftp.username' '')
FTP_PASSWORD=$(bashio::config 'ftp.password' '')
TG_ENABLED=$(bashio::config 'telegram.enabled' 'false')
TG_TOKEN=$(bashio::config 'telegram.bot_token' '')
TG_AUTH=$(bashio::config 'telegram.authorized_users' '[]')
TG_NOTIFY=$(bashio::config 'telegram.notify_chat_ids' '[]')
TG_NOTIFY_ON_READY=$(bashio::config 'telegram.notify_on_session_ready' 'true')

bashio::log.info "Log level: $(bashio::config 'log_level' 'info')"

# ── Create directories ───────────────────────────────────────────────────────
bashio::log.info "Setting up directories..."
mkdir -p /share/scan_inbox/{scan_duplex,copy_duplex,scan_document,card_2in1,confirm,confirm_print,reject,test_print}
mkdir -p /share/scan_out
mkdir -p /data/checkpoints

# Copy checkpoint models to persistent storage on first run
if [ ! -f "/data/checkpoints/depth_anything_v2_vits_slim.onnx" ]; then
    bashio::log.info "Copying checkpoint models to /data/checkpoints..."
    cp -r /app/checkpoints/* /data/checkpoints/
fi

# ── Generate /data/config.yaml ───────────────────────────────────────────────
# bashio::config for arrays returns a JSON array (e.g. ["123","456"]) which is
# valid YAML inline sequence syntax — no conversion needed.
bashio::log.info "Generating /data/config.yaml..."
cat > /data/config.yaml << EOF
# Auto-generated from Home Assistant addon options — DO NOT EDIT MANUALLY
inbox_base: /share/scan_inbox
subdirs:
  scan_duplex: scan_duplex
  copy_duplex: copy_duplex
  scan_document: scan_document
  card_2in1: card_2in1
  confirm: confirm
  confirm_print: confirm_print
  reject: reject
  test_print: test_print
output_dir: /share/scan_out
session_timeout_seconds: ${SESSION_TIMEOUT}
a4_page:
  width_pt: 595
  height_pt: 842
margin_pt: 15
delete_inbox_files_after_process: ${DELETE_INBOX}
test_mode: ${TEST_MODE}

printer:
  enabled: ${PRINTER_ENABLED}
  name: "${PRINTER_NAME}"
  ip: "${PRINTER_IP}"

telegram:
  enabled: ${TG_ENABLED}
  bot_token: "${TG_TOKEN}"
  authorized_users: ${TG_AUTH}
  notify_chat_ids: ${TG_NOTIFY}
  notify_on_session_ready: ${TG_NOTIFY_ON_READY}
EOF

bashio::log.info "/data/config.yaml written."

# ── Propagate settings to S6 container environment for service scripts ───────
# Paths — consumed by Config.load() (SCAN_INBOX_BASE / SCAN_OUTPUT_DIR)
# and web_ui_server.py (SCAN_INBOX_DIR / SCAN_OUTPUT_DIR)
printf '%s' "/share/scan_inbox" > /var/run/s6/container_environment/SCAN_INBOX_BASE
printf '%s' "/share/scan_inbox" > /var/run/s6/container_environment/SCAN_INBOX_DIR
printf '%s' "/share/scan_out"   > /var/run/s6/container_environment/SCAN_OUTPUT_DIR
# FTP credentials (read by ftp-server service)
printf '%s' "${FTP_USERNAME}"   > /var/run/s6/container_environment/FTP_USERNAME
printf '%s' "${FTP_PASSWORD}"   > /var/run/s6/container_environment/FTP_PASSWORD
# Telegram bot token override (Config.load() reads SCAN_TELEGRAM_BOT_TOKEN)
printf '%s' "${TG_TOKEN}"       > /var/run/s6/container_environment/SCAN_TELEGRAM_BOT_TOKEN
# Python output unbuffered so logs appear immediately in HA log viewer
printf '%s' "1"                 > /var/run/s6/container_environment/PYTHONUNBUFFERED

# ── Summary ──────────────────────────────────────────────────────────────────
bashio::log.info "Session timeout:  ${SESSION_TIMEOUT}s"
bashio::log.info "Printer enabled:  ${PRINTER_ENABLED}"
bashio::log.info "Telegram enabled: ${TG_ENABLED}"
bashio::log.info "Test mode:        ${TEST_MODE}"
bashio::log.info "Preparation complete. Starting services..."
zxc