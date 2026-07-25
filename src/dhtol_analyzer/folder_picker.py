from __future__ import annotations

import subprocess


def choose_directory() -> str | None:
    command = [
        "osascript",
        "-e",
        'POSIX path of (choose folder with prompt "Select measurement folder")',
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    selected = completed.stdout.strip()
    return selected or None
