from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_legacy_office(file_path: str, *, target_extension: str) -> str:
    """Convert a legacy Office binary file with LibreOffice and return the converted path."""
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise RuntimeError("Legacy Office conversion requires LibreOffice/soffice on PATH")

    target_extension = target_extension.lower().lstrip(".")
    out_dir = tempfile.mkdtemp(prefix="agritag-office-")
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            target_extension,
            "--outdir",
            out_dir,
            file_path,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Legacy Office conversion failed: {stderr or 'unknown LibreOffice error'}")

    converted = Path(out_dir) / f"{Path(file_path).stem}.{target_extension}"
    if not converted.exists():
        matches = list(Path(out_dir).glob(f"*.{target_extension}"))
        if matches:
            converted = matches[0]
    if not converted.exists():
        raise RuntimeError(f"Legacy Office conversion did not produce a .{target_extension} file")

    return str(converted)
