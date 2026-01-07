# Docker Test Guide

## Quick Test (Windows)

```powershell
# Run test script
.\test-docker.ps1
```

Hoặc manual:

```powershell
# 1. Build image
docker build `
    --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest `
    -t scan-agent:test `
    .

# 2. Create test directories
mkdir -p test_share/scan_inbox/scan_duplex
mkdir -p test_share/scan_out
mkdir -p test_data

# 3. Run container
docker run --rm -it `
    --name scan-agent-test `
    -v "${PWD}/test_share:/share" `
    -v "${PWD}/test_data:/data" `
    -p 2121:2121 `
    -p 30000-30009:30000-30009 `
    scan-agent:test
```

## Test Workflow

### 1. Start Container

```powershell
.\test-docker.ps1
```

Container sẽ:
- Build image từ Dockerfile
- Tạo test directories
- Mount volumes (test_share, test_data)
- Expose port 2121 (FTP)
- Start FTP server + Scan agent

### 2. Test FTP Upload

**Option A: Brother Scanner**
- Server: `<your-pc-ip>:2121`
- Username: `anonymous`
- Password: (blank)
- Directory: `/scan_duplex`

**Option B: FTP Client (FileZilla, WinSCP)**
```
Host: localhost
Port: 2121
User: anonymous
Password: (blank)
```

Upload ảnh vào `/scan_duplex`

**Option C: Command line**
```powershell
# Test FTP connection
ftp localhost 2121
# Login: anonymous, no password
# cd scan_duplex
# put test.jpg
```

### 3. Test File Processing

```powershell
# Copy test images (sử dụng folder hiện có)
Copy-Item "scan_inbox_to_test/scan_duplex/*" "scan_inbox/scan_duplex/"

# Wait for processing (check logs in terminal)

# Check output
ls scan_out/*.pdf
```

### 4. Check Logs

Container logs hiển thị real-time:
```
2026-01-04 10:30:45 | INFO | Starting Scan Agent...
2026-01-04 10:30:46 | INFO | FTP server started (PID: 123)
2026-01-04 10:30:48 | INFO | Scan Agent service started
2026-01-04 10:31:00 | INFO | abc123 | scan_duplex | Processing session with 10 files
2026-01-04 10:31:15 | INFO | abc123 | scan_duplex | PDF generated: /share/scan_out/scan_duplex_20260104_103100.pdf
```

## Test Cases

### Test 1: FTP Connection
```powershell
# Should succeed
ftp localhost 2121
# Login: anonymous
# cd scan_duplex
# ls
```

### Test 2: File Upload & Processing
```powershell
# Upload test images (dùng folder hiện có)
Copy-Item "scan_inbox_to_test/scan_duplex/*" "scan_inbox/scan_duplex/"

# Wait ~10s

# Check output
ls scan_out/*.pdf
```

### Test 3: Multiple Scan Modes
```powershell
# Test scan_duplex
Copy-Item "scan_inbox_to_test/scan_duplex/*" "scan_inbox/scan_duplex/"

# Test scan_document
Copy-Item "scan_inbox_to_test/scan_document/*" "scan_inbox/scan_document/"

# Test card_2in1
Copy-Item "scan_inbox_to_test/card_2in1/*" "scan_inbox/card_2in1/"

# Check outputs
ls scan_out/
```

### Test 4: Image Processing Quality
```powershell
# Upload low-quality scans
# Check if background removal works
# Verify PDF quality in test_share/scan_out/
```

## Troubleshooting

### Port 2121 already in use
```powershell
# Find process
netstat -ano | findstr :2121

# Kill process
taskkill /PID <pid> /F

# Or change port in test-docker.ps1
-p 2122:2121
```

### Container won't start
```powershell
# Check Docker logs
docker logs scan-agent-test

# Check if base image exists
docker pull ghcr.io/home-assistant/amd64-base:latest

# Rebuild without cache
docker build --no-cache --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest -t scan-agent:test .
```

### Files uploaded but not processed
```powershell
# Check if files exist
ls scan_inbox/scan_duplex/

# Check container logs for errors
docker logs scan-agent-test

# Verify checkpoint models
ls checkpoints/
# Should have 4 .onnx files (~300MB)
```

### Permission errors
```powershell
# On Windows, ensure Docker has access to drive
# Docker Desktop → Settings → Resources → File Sharing
# Add E:\ drive
```

## Stop Container

```powershell
# Ctrl+C in terminal
# Or
docker stop scan-agent-test
```

## Cleanup

```powershell
# Remove test config only (giữ scan_inbox, scan_out cho development)
Remove-Item -Recurse -Force test_data

# Remove Docker image
docker rmi scan-agent:test
```

## Differences: Docker Test vs HAOS Addon

| Aspect | Docker Test | HAOS Addon |
|--------|-------------|------------|
| **Volumes** | `./scan_inbox:/share/scan_inbox` | HAOS `/share/scan_inbox` |
| **Config** | `test_data/options.json` | HAOS UI config |
| **Logs** | Terminal stdout | HAOS Log tab |
| **Restart** | Manual | Auto (S6) |
| **Updates** | Rebuild image | HAOS update button |
| **Checkpoints** | Local `./checkpoints` | Copied to `/data/checkpoints` |

## Next Steps

1. ✅ Test local với Docker
2. ✅ Verify all scan modes work
3. ✅ Check PDF quality
4. ✅ Test FTP with scanner
5. 🚀 Publish to GitHub
6. 📦 Install as HAOS addon

## References

- [Docker Documentation](https://docs.docker.com/)
- [HAOS Add-on Development](https://developers.home-assistant.io/docs/add-ons)
