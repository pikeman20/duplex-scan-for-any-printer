# Deployment Guide

## Overview

This guide covers deploying the Scan Agent on various platforms:
- **Docker** (recommended for Home Assistant OS)
- **Bare Metal** (systemd service for Raspberry Pi/Linux)
- **Development** (local testing)

---

## Prerequisites

### Hardware Requirements
- **CPU**: 2+ cores (ARM64 or x86_64)
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 5GB for application + models, plus space for scans/PDFs
- **Network**: Stable connection for FTP and CUPS printing

### Software Requirements
- Linux (Ubuntu 20.04+, Debian 11+, Raspberry Pi OS)
- Python 3.10+ (for bare metal)
- Docker + Docker Compose (for Docker deployment)
- CUPS (for printing features)

---

## Option 1: Docker Deployment (Recommended)

### Quick Start

```bash
# Clone or download the project
cd /path/to/PrinterDuplexScanForCheapPrint

# Run installation script
sudo ./deploy/install.sh
# Select option 1 (Docker)

# Check status
docker-compose ps
docker-compose logs -f scan-agent
```

### Manual Docker Setup

1. **Install Docker** (if not already installed):
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

2. **Build and run**:
```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# View logs
docker-compose logs -f scan-agent
```

### Docker Configuration

Edit `docker-compose.yml` to customize:
- **Ports**: Change `2121:2121` if FTP port conflicts
- **Volumes**: Adjust paths for `scan_inbox`, `scan_out`, `checkpoints`
- **Resources**: Modify CPU/memory limits based on hardware
- **Environment**: Set `LOG_LEVEL=DEBUG` for troubleshooting

### Home Assistant OS Integration

1. **SSH into Home Assistant OS**:
```bash
ssh root@homeassistant.local
```

2. **Navigate to addon_configs or share directory**:
```bash
cd /share
git clone https://github.com/yourusername/PrinterDuplexScanForCheapPrint
cd PrinterDuplexScanForCheapPrint
```

3. **Start with Docker Compose**:
```bash
docker-compose up -d
```

4. **Add automation** (optional):
Create automation in Home Assistant to monitor `/scan_out` for new PDFs

---

## Option 2: Bare Metal Deployment (Systemd)

### Quick Start

```bash
# Run installation script
sudo ./deploy/install.sh
# Select option 2 (Bare metal)

# Check service status
sudo systemctl status scan-agent
sudo journalctl -u scan-agent -f
```

### Manual Setup

1. **Install system dependencies**:
```bash
# Ubuntu/Debian/Raspberry Pi OS
sudo apt-get update
sudo apt-get install -y \
    python3.10 python3.10-venv python3-pip \
    cups cups-client \
    libopencv-dev python3-opencv \
    build-essential gcc g++
```

2. **Create user and directories**:
```bash
sudo useradd -m -s /bin/bash scanagent
sudo mkdir -p /opt/scan-agent
sudo mkdir -p /scan_inbox/{scan_duplex,copy_duplex,scan_document,card_2in1,confirm,confirm_print,reject}
sudo mkdir -p /scan_out
sudo chown -R scanagent:scanagent /opt/scan-agent /scan_inbox /scan_out
```

3. **Install application**:
```bash
# Copy files
sudo cp -r src /opt/scan-agent/
sudo cp config.yaml /opt/scan-agent/
sudo cp -r checkpoints /opt/scan-agent/
sudo cp requirements.txt /opt/scan-agent/

# Create virtual environment
sudo -u scanagent python3.10 -m venv /opt/scan-agent/.venv
sudo -u scanagent /opt/scan-agent/.venv/bin/pip install -r /opt/scan-agent/requirements.txt
```

4. **Install systemd service**:
```bash
sudo cp deploy/scan-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable scan-agent
sudo systemctl start scan-agent
```

5. **Verify**:
```bash
sudo systemctl status scan-agent
sudo journalctl -u scan-agent -f
```

---

## CUPS Printer Setup

### Quick Setup

```bash
sudo ./deploy/setup-cups.sh
```

Interactive menu will guide you through:
1. Auto-detect printers
2. Manually add printer
3. Configure duplex/monochrome
4. Set default printer
5. Test print

### Manual CUPS Configuration

1. **Add network printer**:
```bash
# Brother example (socket protocol)
sudo lpadmin -p Brother_HL_L2350DW \
    -v socket://192.168.1.100 \
    -m drv:///sample.drv/generic-pcl6.ppd \
    -E

# Enable printer
sudo cupsenable Brother_HL_L2350DW
sudo cupsaccept Brother_HL_L2350DW

# Set as default
sudo lpadmin -d Brother_HL_L2350DW
```

2. **Configure duplex printing**:
```bash
lpoptions -p Brother_HL_L2350DW -o sides=two-sided-long-edge
```

3. **Test print**:
```bash
echo "Test print" | lp -d Brother_HL_L2350DW
```

---

## Scanner Configuration

### Brother Scanner FTP Settings

1. **Access scanner web interface**:
   - URL: `http://<scanner-ip>`
   - Or use scanner control panel

2. **Configure FTP settings**:
   - **Server**: IP of machine running Scan Agent
   - **Port**: `2121` (Docker) or `21` (external FTP server)
   - **Username**: `anonymous` or configured user
   - **Password**: (leave blank for anonymous)
   - **Remote Directory**: 
     - `/scan_duplex` for duplex scans
     - `/scan_document` for single-page scans
     - `/copy_duplex` for duplex copy mode
     - `/card_2in1` for ID card scanning

3. **Test scan**:
   - Place document in scanner
   - Press scan button
   - Check `/scan_out` for generated PDF

### FTP Server Options

**Option 1: Built-in FTP (Simple)**
- Scan Agent includes minimal FTP server
- Port 2121 by default
- Anonymous authentication

**Option 2: External FTP (Advanced)**
- Use `pure-ftpd` or `vsftpd`
- Uncomment `ftp-server` in `docker-compose.yml`
- Configure users and permissions

---

## Troubleshooting

### Docker Issues

**Container won't start**:
```bash
# Check logs
docker-compose logs scan-agent

# Check system resources
docker stats

# Rebuild image
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

**Permission errors**:
```bash
# Fix permissions
sudo chmod 777 scan_inbox scan_out
sudo chmod 777 scan_inbox/*
```

### Systemd Issues

**Service fails to start**:
```bash
# Check status
sudo systemctl status scan-agent

# View logs
sudo journalctl -u scan-agent -n 100

# Check permissions
ls -la /scan_inbox /scan_out
```

**Python module not found**:
```bash
# Reinstall dependencies
sudo -u scanagent /opt/scan-agent/.venv/bin/pip install -r /opt/scan-agent/requirements.txt
```

### CUPS Issues

**Printer not detected**:
```bash
# Check CUPS status
sudo systemctl status cups

# List available printers
lpstat -p -d
lpinfo -v

# Restart CUPS
sudo systemctl restart cups
```

**Print job fails**:
```bash
# Check print queue
lpstat -o

# Check printer status
lpstat -p -d

# View CUPS logs
sudo tail -f /var/log/cups/error_log
```

### Scanner Issues

**Scanner can't connect via FTP**:
- Verify IP address and port
- Check firewall: `sudo ufw allow 2121/tcp`
- Test FTP manually: `ftp <server-ip> 2121`

**Files uploaded but not processed**:
- Check `/scan_inbox` directory permissions
- View agent logs for processing errors
- Verify checkpoint models are present: `ls -lh checkpoints/`

---

## Performance Tuning

### Docker Resource Limits

Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'      # Increase for faster processing
      memory: 4G       # Increase for large scans
    reservations:
      cpus: '1.0'
      memory: 1G
```

### Systemd Resource Limits

Edit `/etc/systemd/system/scan-agent.service`:
```ini
[Service]
MemoryLimit=4G
CPUQuota=400%
```

### Processing Configuration

Edit `config.yaml`:
```yaml
image_processing:
  max_workers: 4           # Parallel processing threads
  enable_background_removal: true
  enable_depth_anything: true
  
scan_modes:
  scan_duplex:
    resolution: 300        # Lower for speed, higher for quality
```

---

## Monitoring

### Docker

```bash
# View real-time logs
docker-compose logs -f scan-agent

# Check resource usage
docker stats scan-agent

# Inspect container
docker inspect scan-agent
```

### Systemd

```bash
# Service status
sudo systemctl status scan-agent

# Real-time logs
sudo journalctl -u scan-agent -f

# Last 100 log lines
sudo journalctl -u scan-agent -n 100

# Logs since boot
sudo journalctl -u scan-agent -b
```

### Application Logs

All logs include structured format:
```
timestamp | level | session_id | mode | file:line | message
```

Example:
```
2024-01-20 10:30:45 | INFO | abc123 | scan_duplex | ftp_watcher.py:156 | Processing session abc123 with 10 files
```

---

## Backup and Restore

### Backup

```bash
# Backup configuration and data
tar -czf scan-agent-backup-$(date +%Y%m%d).tar.gz \
    config.yaml \
    scan_inbox/ \
    scan_out/

# Backup checkpoints (optional, if modified)
tar -czf checkpoints-backup.tar.gz checkpoints/
```

### Restore

```bash
# Extract backup
tar -xzf scan-agent-backup-YYYYMMDD.tar.gz

# Restart service
docker-compose restart  # Docker
sudo systemctl restart scan-agent  # Systemd
```

---

## Updates

### Docker

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d
```

### Systemd

```bash
# Stop service
sudo systemctl stop scan-agent

# Update code
git pull
sudo cp -r src /opt/scan-agent/
sudo chown -R scanagent:scanagent /opt/scan-agent/src

# Update dependencies
sudo -u scanagent /opt/scan-agent/.venv/bin/pip install -r /opt/scan-agent/requirements.txt

# Start service
sudo systemctl start scan-agent
```

---

## Security

### Docker Security

- Container runs as non-root user (`scanagent`, uid 1000)
- Read-only volumes for config and checkpoints
- Resource limits prevent DoS
- No privileged mode

### Systemd Security

Service includes hardening:
- `NoNewPrivileges=true` - Prevent privilege escalation
- `PrivateTmp=true` - Isolated /tmp
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to home directories
- `ReadWritePaths` - Explicit write permissions

### Network Security

```bash
# Limit FTP access to local network
sudo ufw allow from 192.168.1.0/24 to any port 2121

# Or specific scanner IP
sudo ufw allow from 192.168.1.50 to any port 2121
```

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/PrinterDuplexScanForCheapPrint/issues
- Documentation: See `README.md` and code comments
- Logs: Always include logs when reporting issues

Common log locations:
- Docker: `docker-compose logs scan-agent`
- Systemd: `journalctl -u scan-agent`
- CUPS: `/var/log/cups/error_log`
