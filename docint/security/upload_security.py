from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote


WINDOWS_BLOCKED_EXTENSIONS = {
    ".exe",
    ".msi",
    ".msp",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".ps1",
    ".psm1",
    ".vbs",
    ".vb",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".dll",
}

MACOS_BLOCKED_EXTENSIONS = {
    ".app",
    ".pkg",
    ".mpkg",
    ".dmg",
    ".command",
    ".workflow",
    ".scpt",
    ".applescript",
    ".kext",
}

LINUX_BLOCKED_EXTENSIONS = {
    ".deb",
    ".rpm",
    ".appimage",
    ".sh",
    ".bash",
    ".zsh",
    ".run",
    ".bin",
    ".so",
}

CROSS_PLATFORM_BLOCKED_EXTENSIONS = {
    ".jar",
    ".py",
    ".pyc",
    ".pyo",
    ".php",
    ".pl",
    ".rb",
    ".cgi",
}

BLOCKED_UPLOAD_EXTENSIONS = {
    *WINDOWS_BLOCKED_EXTENSIONS,
    *MACOS_BLOCKED_EXTENSIONS,
    *LINUX_BLOCKED_EXTENSIONS,
    *CROSS_PLATFORM_BLOCKED_EXTENSIONS,
}

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tgz",
    ".gz",
    ".bz2",
    ".xz",
}

MULTIPART_ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.xz",
)


def _normalized_suffixes(name: str) -> list[str]:
    lower_name = (name or "").lower().strip()
    if not lower_name:
        return []

    suffixes = []
    for multi in MULTIPART_ARCHIVE_SUFFIXES:
        if lower_name.endswith(multi):
            suffixes.append(multi)
    suffixes.extend(Path(lower_name).suffixes)
    return list(dict.fromkeys(suffixes))


def get_blocked_suffix(name: str) -> str | None:
    for suffix in _normalized_suffixes(name):
        if suffix in BLOCKED_UPLOAD_EXTENSIONS:
            return suffix
    return None


def get_archive_suffix(name: str) -> str | None:
    for suffix in _normalized_suffixes(name):
        if suffix in ARCHIVE_EXTENSIONS or suffix in MULTIPART_ARCHIVE_SUFFIXES:
            return suffix
    return None


def is_blocked_upload_extension(name: str) -> bool:
    return get_blocked_suffix(name) is not None


def is_archive_extension(name: str) -> bool:
    return get_archive_suffix(name) is not None


DOWNLOAD_QUERY_KEYS = (
    "filename",
    "file",
    "attachment",
    "download",
    "name",
)


def normalized_url_target(url: str) -> str:
    parsed = urlparse((url or "").strip())
    path = unquote(parsed.path or "")
    query = parse_qs(parsed.query or "", keep_blank_values=False)

    for key in DOWNLOAD_QUERY_KEYS:
        values = query.get(key, [])
        for value in values:
            candidate = unquote((value or "").strip())
            if "." in candidate:
                return candidate.lower()

    return path.lower()


def get_blocked_url_suffix(url: str) -> str | None:
    return get_blocked_suffix(normalized_url_target(url))


def get_archive_url_suffix(url: str) -> str | None:
    return get_archive_suffix(normalized_url_target(url))


def is_blocked_url(url: str) -> bool:
    return get_blocked_url_suffix(url) is not None


def is_archive_url(url: str) -> bool:
    return get_archive_url_suffix(url) is not None
