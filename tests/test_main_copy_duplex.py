#!/usr/bin/env python3
"""
Test main.py logic with copy_duplex mode (respects test_mode: skips printing)
"""
import sys
from pathlib import Path

current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent if current_dir.name == "tests" else current_dir
sys.path.insert(0, str(project_root / "src"))
#Resolve imports for src files

from agent.config import Config
from agent.session_manager import Session

# Load config
cfg = Config.load("config.yaml")

# Create mock session with copy_duplex mode
scan_dir = Path("scan_inbox_to_test/copy_duplex")
images = sorted(scan_dir.glob("*.jpg"))

if not images:
    print("❌ No images found in scan_inbox/copy_duplex/")
    sys.exit(1)

print(f"📁 Found {len(images)} images in copy_duplex folder\n")

# Create session
session = Session(
    id="test_copy_duplex",
    mode="copy_duplex",
    images=[str(p) for p in images]
)

# Process using main logic
print("🔄 Processing with main.py logic (copy_duplex mode)...\n")

from main import process_session
process_session(cfg, session)

print(f"\n✅ Done! Check scan_out/ for output PDF (no print in test_mode)")