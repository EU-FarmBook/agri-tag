from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from docint.audio.transcribe import AudioTranscriptionResult, transcribe_audio_file


@dataclass
class VideoFrameSamplingResult:
    available: bool
    used: bool
    frame_paths: List[str]
    method: str
    rationale: str


def _has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def _video_has_audio_stream(video_path: str) -> Optional[bool]:
    if not _has_ffmpeg():
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "{}")
        return bool(data.get("streams"))
    except Exception:
        return None


def media_duration_seconds(media_path: str) -> Optional[float]:
    if not _has_ffmpeg():
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            media_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "{}")
        return float(data.get("format", {}).get("duration"))
    except Exception:
        return None


def sample_video_frames(video_path: str, max_frames: int = 6) -> VideoFrameSamplingResult:
    if not _has_ffmpeg():
        return VideoFrameSamplingResult(
            available=False,
            used=False,
            frame_paths=[],
            method="ffmpeg_unavailable",
            rationale="FFmpeg/ffprobe not available for video frame sampling",
        )

    duration = media_duration_seconds(video_path)
    if not duration or duration <= 0:
        return VideoFrameSamplingResult(
            available=False,
            used=False,
            frame_paths=[],
            method="ffprobe_failed",
            rationale="Could not determine video duration for frame sampling",
        )

    sample_size = max(1, min(max_frames, 8))
    if sample_size == 1:
        positions = [0.5]
    else:
        positions = [i / (sample_size - 1) for i in range(sample_size)]

    temp_dir = tempfile.mkdtemp(prefix="video_frames_")
    frame_paths: List[str] = []
    for idx, pos in enumerate(positions, start=1):
        seconds = max(0.0, min(duration, duration * pos))
        output_path = str(Path(temp_dir) / f"frame_{idx:02d}.png")
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{seconds:.3f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                output_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and Path(output_path).exists():
            frame_paths.append(output_path)

    if not frame_paths:
        return VideoFrameSamplingResult(
            available=True,
            used=False,
            frame_paths=[],
            method="ffmpeg_sampling_failed",
            rationale="Frame extraction did not produce any usable sampled frames",
        )

    return VideoFrameSamplingResult(
        available=True,
        used=True,
        frame_paths=frame_paths,
        method="ffmpeg_stratified_frames",
        rationale=f"Sampled {len(frame_paths)} representative frames across the video",
    )


def transcribe_video_audio(video_path: str, transcriber=None) -> AudioTranscriptionResult:
    """Extract the audio track from a video and transcribe it.

    Args:
        video_path: path to the video file
        transcriber: optional callable(audio_path) -> AudioTranscriptionResult used
            to transcribe the extracted audio. Defaults to the Whisper-backed
            ``transcribe_audio_file``; pass the Mistral Voxtral adapter to route
            video transcription through Mistral.
    """
    if transcriber is None:
        transcriber = transcribe_audio_file
    if not shutil.which("ffmpeg"):
        return AudioTranscriptionResult(
            available=False,
            used=False,
            text="",
            method="ffmpeg_unavailable",
            model=None,
            rationale="FFmpeg not available for audio extraction from video",
        )

    has_audio_stream = _video_has_audio_stream(video_path)
    if has_audio_stream is False:
        return AudioTranscriptionResult(
            available=True,
            used=False,
            text="",
            method="no_audio_stream",
            model=None,
            rationale="The uploaded video does not contain an audio stream to transcribe.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        audio_path = tmp.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "mp3",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not Path(audio_path).exists():
            return AudioTranscriptionResult(
                available=False,
                used=False,
                text="",
                method="audio_extract_failed",
                model=None,
                rationale="Could not extract an audio track from the video for transcription.",
            )

        if Path(audio_path).stat().st_size == 0:
            return AudioTranscriptionResult(
                available=True,
                used=False,
                text="",
                method="empty_extracted_audio",
                model=None,
                rationale="Audio extraction completed, but the resulting track was empty.",
            )

        result = transcriber(audio_path)
        if result.available and result.used and not result.text.strip():
            return AudioTranscriptionResult(
                available=True,
                used=True,
                text="",
                method=result.method,
                model=result.model,
                rationale="Media transcriber ran, but returned no usable transcript text for the extracted video audio.",
            )
        return result
    finally:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass
