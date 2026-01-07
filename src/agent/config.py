from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict
from typing import Dict


@dataclass
class A4Page:
    width_pt: int = 595
    height_pt: int = 842


@dataclass
class PrinterConfig:
    enabled: bool = False
    name: str = ""
    ip: str = ""


@dataclass
class Config:
    inbox_base: str
    subdirs: Dict[str, str]
    output_dir: str
    session_timeout_seconds: int = 120
    a4_page: A4Page = field(default_factory=A4Page)
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    margin_pt: int = 10
    gutter_pt: int = 18
    delete_inbox_files_after_process: bool = True
    test_mode: bool = False

    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        a4 = raw.get("a4_page", {})
        printer_raw = raw.get("printer", {})
        cfg = Config(
            inbox_base=raw.get("inbox_base", "/scan_inbox"),
            subdirs=raw.get(
                "subdirs",
                {
                    "scan_duplex": "scan_duplex",
                    "copy_duplex": "copy_duplex",
                    "scan_document": "scan_document",
                    "card_2in1": "card_2in1",
                    "confirm": "confirm",
                    "confirm_print": "confirm_print",
                    "reject": "reject",
                    "test_print": "test_print",
                },
            ),
            output_dir=raw.get("output_dir", "/scan_out"),
            session_timeout_seconds=int(raw.get("session_timeout_seconds", 120)),
            a4_page=A4Page(
                width_pt=int(a4.get("width_pt", 595)),
                height_pt=int(a4.get("height_pt", 842)),
            ),
            printer=PrinterConfig(
                enabled=bool(printer_raw.get("enabled", False)),
                name=str(printer_raw.get("name", "")),
                ip=str(printer_raw.get("ip", "")),
            ),
            margin_pt=int(raw.get("margin_pt", 10)),
            gutter_pt=int(raw.get("gutter_pt", 18)),
            delete_inbox_files_after_process=bool(
                raw.get("delete_inbox_files_after_process", True)
            ),
            test_mode=bool(raw.get("test_mode", False)),
        )
        # Allow env overrides for base folders
        cfg.inbox_base = os.getenv("SCAN_INBOX_BASE", cfg.inbox_base)
        cfg.output_dir = os.getenv("SCAN_OUTPUT_DIR", cfg.output_dir)
        return cfg

    def path_for(self, key: str) -> str:
        """Absolute path for a subdir key."""
        name = self.subdirs.get(key, key)
        return os.path.join(self.inbox_base, name)
