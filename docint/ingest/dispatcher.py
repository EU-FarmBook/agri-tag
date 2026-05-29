from __future__ import annotations

from pathlib import Path

from docint.ingest.audio import ingest_audio
from docint.ingest.docx import ingest_docx
from docint.ingest.image import ingest_image
from docint.ingest.models import IngestedAsset
from docint.ingest.pdf import ingest_pdf
from docint.ingest.pptx import ingest_pptx
from docint.ingest.tabular import ingest_delimited_file, ingest_json, ingest_xlsx
from docint.ingest.text import ingest_text_file
from docint.ingest.video import ingest_video

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".docx", ".pptx", ".csv", ".tsv", ".xlsx", ".json", ".jpg", ".jpeg", ".png", ".mp3", ".wav", ".m4a", ".mp4", ".avi", ".mov", ".wmv", ".mpeg", ".mpg", ".mkv", ".flv", ".webm", ".3gp", ".mts", ".m2ts", ".vob", ".rmvb"}


def ingest_asset(file_path: str, filename: str) -> IngestedAsset:
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return ingest_pdf(file_path, filename)
    if suffix == ".txt":
        return ingest_text_file(file_path, filename)
    if suffix == ".docx":
        return ingest_docx(file_path, filename)
    if suffix == ".pptx":
        return ingest_pptx(file_path, filename)
    if suffix == ".csv":
        return ingest_delimited_file(file_path, filename, ",")
    if suffix == ".tsv":
        return ingest_delimited_file(file_path, filename, "\t")
    if suffix == ".xlsx":
        return ingest_xlsx(file_path, filename)
    if suffix == ".json":
        return ingest_json(file_path, filename)
    if suffix in {".jpg", ".jpeg"}:
        return ingest_image(file_path, filename, "image/jpeg")
    if suffix == ".png":
        return ingest_image(file_path, filename, "image/png")
    if suffix == ".mp3":
        return ingest_audio(file_path, filename, "audio/mpeg")
    if suffix == ".wav":
        return ingest_audio(file_path, filename, "audio/wav")
    if suffix == ".m4a":
        return ingest_audio(file_path, filename, "audio/mp4")
    if suffix == ".mp4":
        return ingest_video(file_path, filename, "video/mp4")
    if suffix == ".avi":
        return ingest_video(file_path, filename, "video/x-msvideo")
    if suffix == ".mov":
        return ingest_video(file_path, filename, "video/quicktime")
    if suffix == ".wmv":
        return ingest_video(file_path, filename, "video/x-ms-wmv")
    if suffix in {".mpeg", ".mpg"}:
        return ingest_video(file_path, filename, "video/mpeg")
    if suffix == ".mkv":
        return ingest_video(file_path, filename, "video/x-matroska")
    if suffix == ".flv":
        return ingest_video(file_path, filename, "video/x-flv")
    if suffix == ".webm":
        return ingest_video(file_path, filename, "video/webm")
    if suffix == ".3gp":
        return ingest_video(file_path, filename, "video/3gpp")
    if suffix == ".mts":
        return ingest_video(file_path, filename, "video/mp2t")
    if suffix == ".m2ts":
        return ingest_video(file_path, filename, "video/mp2t")
    if suffix == ".vob":
        return ingest_video(file_path, filename, "video/dvd")
    if suffix == ".rmvb":
        return ingest_video(file_path, filename, "application/vnd.rn-realmedia-vbr")

    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported types: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}"
    )
