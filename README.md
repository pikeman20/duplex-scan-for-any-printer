# PrinterDuplexScanForCheapPrint

A lightweight server-side agent to extend Brother MFC-7860DW "Scan to FTP" into predictable duplex scanning, copying, small-document layout, and 2-in-1 card scanning.

Core philosophy: reflect physical intent; do not guess, beautify, or auto-center.

## Features

- **Scan duplex** - Pair fronts/backs, interleaved PDF with auto-orientation correction
- **Copy duplex** - Render PDF, print via CUPS `lp` two-sided
- **Scan small documents** - Strict 2×2 quadrant layout, respects physical placement
- **Card/ID 2-in-1** - Pair images per page (left-right or top-bottom)
- **Session management** - Explicit Confirm/Reject with timeout fallback and mode switching
- **Fast PDF generation** - PyMuPDF with in-memory buffers (5-20x faster than ReportLab)

## Performance

- **PDF Generation**: PyMuPDF with C++ backend
  - scan_duplex: ~2-3s for 10 pages
  - scan_document: ~7s for 32 documents across 13 pages
  - In-memory processing (no temp files)
- **Image optimization**: Auto-downscale to 150-200 DPI for print
- **Background removal**: V2 with withoutbg library for accurate document detection

## Folder Convention

```text
/scan_inbox/
 ├─ scan_duplex/      # Duplex scanning with auto-orientation
 ├─ copy_duplex/      # Duplex scanning + auto-print
 ├─ scan_document/    # Multi-document layout (2×2 grid)
 ├─ card_2in1/        # ID/card scanning (2 cards per page)
 ├─ test_print/       # 🆕 Quick printer test (direct print)
 ├─ confirm/          # Confirm session processing
 └─ reject/           # Cancel session
```
Each FTP profile should point to a specific subfolder.

### Test Print Mode

For quick printer verification, drop any image into `test_print/`:
- No image processing (direct conversion to PDF)
- Instant print if printer configured
- See [PRINTER_TEST.md](PRINTER_TEST.md) for details

```bash
# Quick test via command line
cp test.jpg /share/scan_inbox/test_print/
```

## Quick Start

1. Configure `config.yaml` paths for your Linux server (defaults assume `/scan_inbox` and `/scan_out`).
1. Activate your Python venv (this project assumes `.venv`):

 
```powershell
# Windows PowerShell (development)
E:/WorkSpace/PrinterDuplexScanForCheapPrint/.venv/Scripts/Activate.ps1
```

1. Run the agent:

 
```powershell
E:/WorkSpace/PrinterDuplexScanForCheapPrint/.venv/Scripts/python.exe src/main.py --config config.yaml
```

On Linux deployment:

 
```bash
source .venv/bin/activate
python3 src/main.py --config config.yaml
```

## Notes

- Duplex scan assumes user scans fronts first, then backs; images are interleaved in the final PDF as `1F, 1B, 2F, 2B, ...`.
- Card 2-in-1 pairs two images per page: landscape → left-right, portrait → top-bottom.
- Scan Document mode uses a 2×2 logical grid; documents are placed in quadrants based on their bounding box center; no auto-centering or beautification.
- Confirm/Reject is driven by the arrival of any file in `confirm/` or `reject/`.
- Printing uses `lp` and only runs on Linux.

## Systemd (optional)

Create a service to run on boot (edit paths):

```ini
[Unit]
Description=Scan Agent
After=network.target

[Service]
WorkingDirectory=/opt/PrinterDuplexScanForCheapPrint
ExecStart=/opt/PrinterDuplexScanForCheapPrint/.venv/bin/python /opt/PrinterDuplexScanForCheapPrint/src/main.py --config /opt/PrinterDuplexScanForCheapPrint/config.yaml
Restart=always
User=scanagent

[Install]
WantedBy=multi-user.target
```

## License

Internal deployment; no external license headers added.
