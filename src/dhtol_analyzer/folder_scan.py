from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SUFFIXES = {".json", ".mtpx", ".data", ".log"}


@dataclass
class FolderScan:
    root: Path
    files: list[Path]
    counts: dict[str, int]
    total_bytes: int


def validate_folder(value: str) -> tuple[Path | None, str | None]:
    text = value.strip()
    if not text:
        return None, "Select or enter a measurement folder."

    root = Path(text).expanduser()
    if not root.exists():
        return None, "Folder does not exist."
    if not root.is_dir():
        return None, "Selected path is not a folder."
    if not os.access(root, os.R_OK):
        return None, "Folder is not readable."
    return root.resolve(), None


def scan_folder(root: Path) -> FolderScan:
    files: list[Path] = []
    counts: Counter[str] = Counter()
    total_bytes = 0

    for current_root, directory_names, file_names in os.walk(root):
        directory_names[:] = [
            name for name in directory_names if not name.startswith(".")
        ]
        current = Path(current_root)

        for name in file_names:
            path = current / name
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                continue
            files.append(path)
            counts[suffix] += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue

    files.sort(key=lambda path: str(path.relative_to(root)).lower())
    return FolderScan(
        root=root,
        files=files,
        counts=dict(counts),
        total_bytes=total_bytes,
    )