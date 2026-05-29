from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlparse, unquote

from docint.ingest.models import IngestedAsset


@dataclass
class CategoryInferenceResult:
    category: str
    confidence: float
    rationale: str


DOCUMENT_URL_SUFFIXES = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt")
DATASET_URL_SUFFIXES = (".csv", ".tsv", ".xlsx", ".xls", ".json")


def _normalized_url_target(url: str) -> str:
    parsed = urlparse((url or "").strip())
    query = parse_qs(parsed.query or "", keep_blank_values=False)
    for key in ("filename", "file", "attachment", "download", "name"):
        for value in query.get(key, []):
            candidate = unquote((value or "").strip())
            if "." in candidate:
                return candidate.lower()
    return unquote(parsed.path or "").lower()


def _count_term_hits(haystack: str, terms: tuple[str, ...]) -> int:
    hits = 0
    for term in terms:
        if " " in term or "-" in term:
            if term in haystack:
                hits += 1
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, haystack):
            hits += 1
    return hits


def infer_file_category(asset: IngestedAsset, upload_content_type: str | None = None) -> CategoryInferenceResult:
    mime = (upload_content_type or asset.mime_type or "").lower().strip()

    if mime in {
        "text/csv",
        "text/tab-separated-values",
        "application/json",
        "text/json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }:
        return CategoryInferenceResult(
            category="Dataset",
            confidence=0.98,
            rationale=f"File MIME {mime or asset.mime_type} is routed as Dataset",
        )

    if mime == "application/pdf" or mime.startswith("text/") or mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword",
        "application/vnd.ms-powerpoint",
    }:
        return CategoryInferenceResult(
            category="Document",
            confidence=0.98,
            rationale=f"File MIME {mime or asset.mime_type} is routed as Document",
        )

    if mime.startswith("image/"):
        return CategoryInferenceResult(
            category="Image",
            confidence=0.98,
            rationale=f"File MIME {mime or asset.mime_type} is routed as Image",
        )

    if mime.startswith("audio/"):
        return CategoryInferenceResult(
            category="Audio",
            confidence=0.98,
            rationale=f"File MIME {mime or asset.mime_type} is routed as Audio",
        )

    if mime.startswith("video/"):
        return CategoryInferenceResult(
            category="Video",
            confidence=0.98,
            rationale=f"File MIME {mime or asset.mime_type} is routed as Video",
        )

    return infer_category(asset)


def infer_url_category(url: str, text: str) -> CategoryInferenceResult:
    haystack = f"{url}\n{text}".lower()
    normalized_target = _normalized_url_target(url)

    if normalized_target.endswith(DOCUMENT_URL_SUFFIXES):
        return CategoryInferenceResult(
            category="Document",
            confidence=0.96,
            rationale=f"URL target resolves to a document-like file ({normalized_target.split('.')[-1]})",
        )

    if normalized_target.endswith(DATASET_URL_SUFFIXES):
        return CategoryInferenceResult(
            category="Dataset",
            confidence=0.96,
            rationale=f"URL target resolves to a dataset-like file ({normalized_target.split('.')[-1]})",
        )

    dataset_terms = (
        "dataset", "data catalogue", "data catalog", "schema", "csv", "tsv", "xlsx",
        "download data", "observations", "variables", "records", "tabular",
    )
    software_terms = (
        "software", "tool", "platform", "application", "app", "repository", "github",
        "gitlab", "documentation", "api", "plugin", "dashboard", "install",
    )

    dataset_hits = _count_term_hits(haystack, dataset_terms)
    software_hits = _count_term_hits(haystack, software_terms)

    if dataset_hits >= 2 and dataset_hits >= software_hits:
        return CategoryInferenceResult(
            category="Dataset",
            confidence=0.8,
            rationale="URL text shows dataset-oriented signals such as schema, records, or downloadable tabular content",
        )

    if software_hits >= 2 and software_hits > dataset_hits:
        return CategoryInferenceResult(
            category="Software Application",
            confidence=0.78,
            rationale="URL text looks like a software, tool, repository, or product page rather than a document body",
        )

    return CategoryInferenceResult(
        category="Document",
        confidence=0.68,
        rationale="URL text is routed as Document by default because it reads more like narrative page content than dataset or software metadata",
    )


def infer_category(asset: IngestedAsset) -> CategoryInferenceResult:
    if asset.asset_type in {"pdf", "txt", "docx", "pptx"}:
        return CategoryInferenceResult(
            category="Document",
            confidence=0.95,
            rationale=f"File type .{asset.asset_type} is currently routed as Document",
        )

    if asset.asset_type in {"jpeg", "jpg", "png"}:
        return CategoryInferenceResult(
            category="Image",
            confidence=0.98,
            rationale=f"Image file type .{asset.asset_type} is routed as Image",
        )

    if asset.asset_type in {"mp3", "wav", "m4a"}:
        return CategoryInferenceResult(
            category="Audio",
            confidence=0.98,
            rationale=f"Audio file type .{asset.asset_type} is routed as Audio",
        )

    if asset.asset_type in {"mp4", "avi", "mov", "wmv", "mpeg", "mpg", "mkv", "flv", "webm", "3gp", "mts", "m2ts", "vob", "rmvb"}:
        return CategoryInferenceResult(
            category="Video",
            confidence=0.98,
            rationale=f"Video file type .{asset.asset_type} is routed as Video",
        )

    if asset.asset_type in {"csv", "tsv", "json"}:
        return CategoryInferenceResult(
            category="Dataset",
            confidence=0.98,
            rationale=f"Structured dataset file .{asset.asset_type} is routed as Dataset",
        )

    if asset.asset_type == "xlsx":
        sheet_count = int(asset.meta.get("sheet_count", 1))
        preview_rows = int(asset.meta.get("preview_rows", 0))
        max_columns = int(asset.meta.get("max_columns", 0))
        if sheet_count > 1 or preview_rows >= 6 or max_columns >= 4:
            return CategoryInferenceResult(
                category="Dataset",
                confidence=0.82,
                rationale="Spreadsheet shows tabular dataset signals such as multiple sheets, several rows, or multiple columns",
            )
        return CategoryInferenceResult(
            category="Document",
            confidence=0.58,
            rationale="Spreadsheet looks lightweight enough to remain document-like; category remains tentative",
        )

    return CategoryInferenceResult(
        category="Document",
        confidence=0.5,
        rationale=f"Fallback category routing applied for .{asset.asset_type}",
    )
