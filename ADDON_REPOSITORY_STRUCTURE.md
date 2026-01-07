# Home Assistant Add-on Repository Structure

This folder is structured as a **standalone Home Assistant add-on** repository.

## File Structure (Add-on Root)

```
hassio-scan-agent/               # This folder = addon root
├── config.json                  # ✅ Addon metadata (REQUIRED)
├── Dockerfile                   # ✅ Build instructions (REQUIRED)
├── README.md                    # ✅ Repository README (REQUIRED)
├── CHANGELOG.md                 # ✅ Version history
├── LICENSE                      # ✅ MIT License
├── icon.png                     # ⚠️  TODO: 128x128 addon icon
├── logo.png                     # ⚠️  TODO: Optional addon logo
├── repository.json              # ✅ Repository metadata
├── .github/
│   └── workflows/
│       ├── build.yml            # ✅ Auto-build on push
│       └── lint.yml             # ✅ Config validation
├── rootfs/                      # ✅ Container filesystem
│   └── etc/
│       ├── cont-init.d/
│       │   └── 00-prepare.sh    # Init script
│       └── services.d/
│           ├── ftp-server/      # FTP service
│           │   ├── run
│           │   └── finish
│           └── scan-agent/      # Scan agent service
│               ├── run
│               └── finish
├── src/                         # ✅ Python application
│   ├── main.py
│   └── agent/
│       ├── ftp_server.py
│       ├── image_processing.py
│       └── ...
├── checkpoints/                 # ✅ ONNX models (~300MB)
│   ├── depth_anything_v2_vits_slim.onnx
│   ├── isnet.onnx
│   ├── focus_matting_1.0.0.onnx
│   └── focus_refiner_1.0.0.onnx
├── requirements.txt             # ✅ Python dependencies
├── README_ADDON.md              # User documentation
├── S6_STRUCTURE.md              # Developer guide
└── .dockerignore                # ✅ Build exclusions
```

## Publishing to GitHub

### 1. Create GitHub Repository

```bash
# Initialize git (if not already)
cd PrinterDuplexScanForCheapPrint
git init
git add .
git commit -m "Initial addon release"

# Create repository on GitHub: hassio-scan-agent
# Then push
git remote add origin https://github.com/yourusername/hassio-scan-agent.git
git branch -M main
git push -u origin main
```

### 2. Enable GitHub Actions

- Go to repo Settings → Actions → General
- Enable "Allow all actions and reusable workflows"
- GitHub Actions will auto-build on push

### 3. Tag Release

```bash
# Tag version (must match config.json version)
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

### 4. Add to Home Assistant

Users add your repository:
```
https://github.com/yourusername/hassio-scan-agent
```

Then install "Scan Agent" from Add-on Store.

## Important Notes

### Before Publishing

1. **Create icon.png** (128x128 PNG)
   - Use scanner/document icon
   - Place in root directory

2. **Update URLs in config.json**
   ```json
   "url": "https://github.com/yourusername/hassio-scan-agent",
   "image": "ghcr.io/yourusername/hassio-scan-agent-{arch}"
   ```

3. **Update README.md shields**
   - Replace `yourusername` with actual GitHub username

4. **Test build locally**
   ```bash
   docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest -t test .
   ```

### Files to Remove (Not Needed for Addon)

These files are for development only:
- `docker-compose.yml` (for standalone Docker)
- `deploy/` folder (deployment scripts)
- `tests/` folder (development tests)
- `scan_inbox/`, `scan_out/` (data folders)
- `config.yaml` (will be auto-generated)
- `.venv/` (Python virtual environment)

Already excluded via `.dockerignore`.

### What Happens After Push

1. GitHub Actions builds multi-arch images
2. Images pushed to `ghcr.io/yourusername/hassio-scan-agent-{arch}`
3. Users add repository to HAOS
4. Addon appears in Add-on Store
5. Click install → Download image → Configure → Start

## Addon Configuration Flow

When user installs addon:

1. HAOS downloads image from `ghcr.io`
2. Mounts volumes: `/share`, `/data`
3. Runs `cont-init.d/00-prepare.sh`:
   - Creates `/share/scan_inbox` subdirectories
   - Copies checkpoints to `/data/checkpoints`
   - Generates `/data/config.yaml` from UI options
4. Starts services:
   - `ftp-server` (port 2121)
   - `scan-agent` (monitors inbox)
5. User configures scanner FTP settings
6. Scanner uploads → Agent processes → PDF in `/share/scan_out`

## Support

After publishing:
- Users report issues: GitHub Issues
- Questions: GitHub Discussions
- Updates: Push commits, tag new versions
- CI/CD: Automatic builds via GitHub Actions

## References

- [HAOS Add-on Development](https://developers.home-assistant.io/docs/add-ons)
- [Add-on Configuration](https://developers.home-assistant.io/docs/add-ons/configuration)
- [S6 Overlay](https://github.com/just-containers/s6-overlay)
