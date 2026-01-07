# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-01-04

### Added
- Initial Home Assistant Add-on release
- FTP server (port 2121) for Brother scanner integration
- PDF generation with PyMuPDF (10x faster than ReportLab)
- 4 scan modes:
  - `scan_duplex` - Duplex scanning with PDF output
  - `scan_document` - Single page scanning
  - `copy_duplex` - Scan and auto-print duplex
  - `card_2in1` - ID card scanning (2 sides on 1 A4 page)
- Image processing features:
  - Background removal (ISNet)
  - Depth estimation (Depth Anything V2)
  - Auto crop and deskew
- CUPS printing integration
- Configurable auto-print per scan mode
- Automatic old file cleanup (configurable retention days)
- Structured console logging for HAOS
- Error handling with retry logic
- Resource monitoring (disk/memory)
- Configuration validation on startup

### Technical
- Python 3.10+ with ONNX Runtime
- Alpine-based Docker image (~500MB with models)
- Multi-architecture support (armhf, armv7, aarch64, amd64, i386)
- S6 overlay for process management
- Health checks every 30s
- Persistent storage via Home Assistant `/share` and `/data`

### Configuration
- JSON schema validation for addon config
- Options exposed in Home Assistant UI:
  - Log level (trace, debug, info, warning, error)
  - Scan mode toggles and auto-print settings
  - Printer name and enable/disable
  - Image processing options
  - Retention days (1-30)

## [Unreleased]

### Planned
- Web dashboard for monitoring scan sessions
- Email/webhook notifications on scan completion
- Multi-printer support
- Custom PDF metadata (author, title, keywords)
- OCR text extraction (optional)
- Mobile app integration
