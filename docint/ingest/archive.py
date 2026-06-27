from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from docint.ingest.dispatcher import SUPPORTED_DOCUMENT_EXTENSIONS
from docint.security.upload_security import get_archive_suffix, get_blocked_suffix


ARCHIVE_UPLOAD_EXTENSIONS = {".zip", ".tar", ".rar"}
ARCHIVE_MAX_FILES = int(os.getenv("ARCHIVE_MAX_FILES", "100"))
ARCHIVE_MAX_EXTRACTED_BYTES = int(os.getenv("ARCHIVE_MAX_EXTRACTED_MB", "100")) * 1024 * 1024
ARCHIVE_MAX_SUPPORTED_FILES = int(os.getenv("ARCHIVE_MAX_SUPPORTED_FILES", "10"))


@dataclass
class ExtractedArchive:
    archive_type: str
    extract_dir: str
    supported_files: list[tuple[str, str]]
    total_files: int
    total_extracted_bytes: int
    skipped_files: list[str]


def is_supported_archive_name(name: str) -> bool:
    return (get_archive_suffix(name) or Path(name).suffix.lower()) in ARCHIVE_UPLOAD_EXTENSIONS


def _validate_member_name(name: str) -> str:
    normalized = (name or "").replace("\\", "/").strip()
    if not normalized or normalized.endswith("/"):
        return normalized
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Archive contains unsafe path '{name}'")
    blocked = get_blocked_suffix(normalized)
    if blocked:
        raise ValueError(f"Archive contains blocked file type '{blocked}' in '{name}'")
    nested_archive = get_archive_suffix(normalized)
    if nested_archive:
        raise ValueError(f"Archive contains nested archive '{name}'")
    return normalized


def _check_limits(total_files: int, total_bytes: int) -> None:
    if total_files > ARCHIVE_MAX_FILES:
        raise ValueError(f"Archive contains too many files ({total_files}); maximum is {ARCHIVE_MAX_FILES}")
    if total_bytes > ARCHIVE_MAX_EXTRACTED_BYTES:
        mb = round(total_bytes / (1024 * 1024), 2)
        max_mb = round(ARCHIVE_MAX_EXTRACTED_BYTES / (1024 * 1024), 2)
        raise ValueError(f"Archive expands to {mb} MB; maximum is {max_mb} MB")


def _safe_destination(root: Path, member_name: str) -> Path:
    destination = (root / member_name).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ValueError(f"Archive contains unsafe path '{member_name}'")
    return destination


def _collect_supported(root: Path) -> tuple[list[tuple[str, str]], list[str], int, int]:
    supported: list[tuple[str, str]] = []
    skipped: list[str] = []
    total_files = 0
    total_bytes = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        _validate_member_name(relative)
        total_files += 1
        total_bytes += path.stat().st_size
        suffix = path.suffix.lower()
        if suffix in SUPPORTED_DOCUMENT_EXTENSIONS:
            supported.append((str(path), relative))
        else:
            skipped.append(relative)

    _check_limits(total_files, total_bytes)
    if len(supported) > ARCHIVE_MAX_SUPPORTED_FILES:
        raise ValueError(
            f"Archive contains too many supported files ({len(supported)}); "
            f"maximum is {ARCHIVE_MAX_SUPPORTED_FILES} for synchronous classification"
        )
    return supported, skipped, total_files, total_bytes


def _extract_zip(file_path: str, extract_dir: Path) -> tuple[int, int]:
    total_files = 0
    total_bytes = 0
    with zipfile.ZipFile(file_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member_name = _validate_member_name(info.filename)
            total_files += 1
            total_bytes += int(info.file_size)
            _check_limits(total_files, total_bytes)
            destination = _safe_destination(extract_dir, member_name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    return total_files, total_bytes


def _extract_tar(file_path: str, extract_dir: Path) -> tuple[int, int]:
    total_files = 0
    total_bytes = 0
    with tarfile.open(file_path) as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Archive contains unsupported special entry '{member.name}'")
            member_name = _validate_member_name(member.name)
            total_files += 1
            total_bytes += int(member.size)
            _check_limits(total_files, total_bytes)
            source = tf.extractfile(member)
            if source is None:
                continue
            destination = _safe_destination(extract_dir, member_name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    return total_files, total_bytes


def _extract_rar(file_path: str, extract_dir: Path) -> None:
    unar = shutil.which("unar")
    if not unar:
        raise RuntimeError("RAR extraction requires unar on PATH")
    result = subprocess.run(
        [unar, "-quiet", "-force-overwrite", "-output-directory", str(extract_dir), file_path],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"RAR extraction failed: {stderr or 'unknown unar error'}")


def extract_supported_archive(file_path: str, filename: str) -> ExtractedArchive:
    archive_type = get_archive_suffix(filename) or Path(filename).suffix.lower()
    if archive_type not in ARCHIVE_UPLOAD_EXTENSIONS:
        raise ValueError(f"Unsupported archive type '{archive_type}'")

    extract_dir = Path(os.path.abspath(file_path)).parent / f"{Path(file_path).name}.extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    if archive_type == ".zip":
        total_files, total_bytes = _extract_zip(file_path, extract_dir)
    elif archive_type == ".tar":
        total_files, total_bytes = _extract_tar(file_path, extract_dir)
    elif archive_type == ".rar":
        _extract_rar(file_path, extract_dir)
        supported, skipped, total_files, total_bytes = _collect_supported(extract_dir)
        if not supported:
            raise ValueError("Archive does not contain any supported files to classify")
        return ExtractedArchive(archive_type, str(extract_dir), supported, total_files, total_bytes, skipped)
    else:
        raise ValueError(f"Unsupported archive type '{archive_type}'")

    supported, skipped, collected_files, collected_bytes = _collect_supported(extract_dir)
    total_files = max(total_files, collected_files)
    total_bytes = max(total_bytes, collected_bytes)
    if not supported:
        raise ValueError("Archive does not contain any supported files to classify")

    return ExtractedArchive(archive_type, str(extract_dir), supported, total_files, total_bytes, skipped)
