"""Re-encoding (S2.4b, Q-120): "re-encode everything, strip metadata incl. GPS, delete
originals, serve only HAM-made copies; no AV service in V1".

Image derivative size/quality (long edge, thumbnail size, JPEG quality) and video derivative
size/codec are **technical** settings, not PRD business rules (architecture plan §9: "Image
derivative size and quality ... are technical settings in ham/media/processing.py, not
business rules") — they live here as plain module constants, not in `ham.rules`. The one
*business* rule this module enforces (the 2-minute video length cap) comes from
`ham.rules.RULES.media.REQUESTER_MEDIA_MAX_VIDEO_DURATION`, passed in by the caller
(`ham.media.jobs`) rather than imported here, so this module stays pure/no-Django and easy to
unit test without the app registry.

Pillow drops EXIF automatically on a plain re-save unless `exif=...` is explicitly passed to
`Image.save()` — this module never does that, so GPS/EXIF is stripped for free by the
re-encode itself, not by a separate "scrub" step that could be forgotten.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

try:  # HEIC/HEIF (iPhone) support for Pillow.
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - always installed (pyproject), defensive only
    pass

# Technical settings (architecture plan §9), not PRD rules.
IMAGE_LONG_EDGE = 2560
THUMBNAIL_LONG_EDGE = 480
IMAGE_JPEG_QUALITY = 80
VIDEO_MAX_HEIGHT = 720
VIDEO_CODEC = "libx264"
VIDEO_AUDIO_CODEC = "aac"


class ProcessingError(Exception):
    """A file was processed but failed a check. `code` matches `RequestMedia.failure_code`
    (`too_long`, `too_large`, `unsupported`, `corrupt`)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class ProcessingUnavailable(Exception):
    """The tool needed to process this file isn't installed on this worker (e.g. no ffmpeg).
    The caller marks the item `processing_unavailable` and still deletes the original — never
    serves an unprocessed file (Q-120)."""


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    thumbnail: bytes


@dataclass(frozen=True, slots=True)
class ProcessedVideo:
    data: bytes
    content_type: str
    width: int
    height: int
    duration_ms: int


def _resized(img: Image.Image, long_edge: int) -> Image.Image:
    w, h = img.size
    scale = long_edge / max(w, h)
    if scale >= 1:
        return img
    return img.resize(
        (max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS
    )


def process_photo(original: bytes) -> ProcessedImage:
    """Re-encodes to JPEG, long edge capped at `IMAGE_LONG_EDGE`, no EXIF/GPS/COM comment
    copied, plus a `THUMBNAIL_LONG_EDGE` thumbnail. Raises `ProcessingError("corrupt")` for an
    unreadable file, `ProcessingError("unsupported")` for a format Pillow can't decode at
    all."""
    import io

    try:
        opened = Image.open(io.BytesIO(original))
        opened.load()
    except Exception as exc:  # Pillow raises many exception types for bad input
        raise ProcessingError("corrupt", str(exc)) from exc

    img: Image.Image = opened
    # Security review L1: bake the EXIF orientation into the pixels *before* EXIF is dropped
    # (otherwise a sideways/upside-down phone photo would look correct to a viewer that reads
    # EXIF orientation, then look wrong the moment EXIF is gone). `exif_transpose` returns a
    # new image, or the original unchanged if there was no orientation tag to apply.
    img = ImageOps.exif_transpose(img) or img
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    full = _resized(img, IMAGE_LONG_EDGE)
    # Security review L1: `.resize()`/`.convert()` carry the source image's `.info` dict
    # forward, which can include a JPEG COM comment segment (`info["comment"]`) -- Pillow's
    # JPEG encoder re-embeds it on save if present, even though `Image.save()` here is never
    # given `exif=`/`comment=` explicitly. Clearing `.info` strips it (and anything else that
    # rode along in it) for good, the same way EXIF is stripped by omission.
    full.info = {}
    full_buf = io.BytesIO()
    full.save(full_buf, format="JPEG", quality=IMAGE_JPEG_QUALITY)

    thumb = _resized(img, THUMBNAIL_LONG_EDGE)
    thumb.info = {}
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=IMAGE_JPEG_QUALITY)

    return ProcessedImage(
        data=full_buf.getvalue(),
        content_type="image/jpeg",
        width=full.width,
        height=full.height,
        thumbnail=thumb_buf.getvalue(),
    )


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration_ms(path: Path) -> int:
    """Runs `ffprobe`; raises `ProcessingUnavailable` if it isn't installed,
    `ProcessingError("corrupt")` if the file can't be probed."""
    if shutil.which("ffprobe") is None:
        raise ProcessingUnavailable("ffprobe not installed")
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ProcessingError("corrupt", str(exc)) from exc
    try:
        return round(float(result.stdout.strip()) * 1000)
    except ValueError as exc:
        raise ProcessingError("corrupt", "ffprobe returned no duration") from exc


def process_video(original: bytes, *, max_duration_ms: int) -> ProcessedVideo:
    """Re-encodes to H.264/AAC MP4 at up to `VIDEO_MAX_HEIGHT`p, metadata stripped
    (`-map_metadata -1`). Raises `ProcessingUnavailable` if ffmpeg/ffprobe aren't installed on
    this worker (task brief's degrade path — never serves the original), `ProcessingError
    ("too_long")` if the source exceeds `max_duration_ms` (Q-120 server-side enforcement),
    `ProcessingError("corrupt")` for anything ffmpeg/ffprobe can't read."""
    if not ffmpeg_available():
        raise ProcessingUnavailable("ffmpeg/ffprobe not installed")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in"
        src.write_bytes(original)
        duration_ms = probe_duration_ms(src)
        if duration_ms > max_duration_ms:
            raise ProcessingError("too_long", f"{duration_ms}ms > {max_duration_ms}ms")

        dest = Path(tmp) / "out.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-map_metadata",
                    "-1",
                    "-vf",
                    f"scale=-2:'min({VIDEO_MAX_HEIGHT},ih)'",
                    "-c:v",
                    VIDEO_CODEC,
                    "-c:a",
                    VIDEO_AUDIO_CODEC,
                    str(dest),
                ],
                capture_output=True,
                timeout=600,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ProcessingError("corrupt", str(exc)) from exc

        out_duration_ms = probe_duration_ms(dest)
        width, height = _probe_dimensions(dest)
        return ProcessedVideo(
            data=dest.read_bytes(),
            content_type="video/mp4",
            width=width,
            height=height,
            duration_ms=out_duration_ms,
        )


def _probe_dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    raw = result.stdout.strip()
    w_str, _, h_str = raw.partition("x")
    return int(w_str), int(h_str)
