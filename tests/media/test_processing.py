"""S2.4b `ham.media.processing` (Q-120): image path exercised fully; video path exercised
against real ffmpeg when available in this sandbox, otherwise a clear "unavailable" mock."""

from __future__ import annotations

import io
from unittest.mock import patch

import piexif
import pytest
from PIL import Image

from ham.media import processing


def _jpeg_with_gps(width=4000, height=3000) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 50, 50))
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((25, 1), (46, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: b"W",
        piexif.GPSIFD.GPSLongitude: ((80, 1), (11, 1), (0, 1)),
    }
    exif_dict = {"GPS": gps_ifd, "0th": {piexif.ImageIFD.Artist: b"Someone's Name"}}
    exif_bytes = piexif.dump(exif_dict)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes)
    return buf.getvalue()


def test_process_photo_strips_gps_and_exif():
    original = _jpeg_with_gps()
    assert Image.open(io.BytesIO(original)).getexif()  # sanity: source really has EXIF

    result = processing.process_photo(original)

    out_img = Image.open(io.BytesIO(result.data))
    assert not out_img.getexif()  # stripped
    assert "gps" not in {k.lower() for k in (out_img.info or {})}


def test_process_photo_resizes_to_long_edge_cap():
    original = _jpeg_with_gps(width=5000, height=2000)
    result = processing.process_photo(original)
    assert max(result.width, result.height) == processing.IMAGE_LONG_EDGE
    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.size == (result.width, result.height)


def test_process_photo_produces_a_smaller_thumbnail():
    original = _jpeg_with_gps()
    result = processing.process_photo(original)
    thumb_img = Image.open(io.BytesIO(result.thumbnail))
    assert max(thumb_img.size) == processing.THUMBNAIL_LONG_EDGE
    assert not thumb_img.getexif()


def test_process_photo_leaves_a_small_image_unscaled():
    original = _jpeg_with_gps(width=100, height=80)
    result = processing.process_photo(original)
    assert result.width == 100
    assert result.height == 80


def test_process_photo_rejects_corrupt_data():
    with pytest.raises(processing.ProcessingError) as exc_info:
        processing.process_photo(b"not an image")
    assert exc_info.value.code == "corrupt"


def test_probe_duration_raises_unavailable_without_ffprobe(tmp_path):
    with patch("ham.media.processing.shutil.which", return_value=None):
        with pytest.raises(processing.ProcessingUnavailable):
            processing.probe_duration_ms(tmp_path / "whatever.mp4")


def test_process_video_raises_unavailable_without_ffmpeg():
    with patch("ham.media.processing.ffmpeg_available", return_value=False):
        with pytest.raises(processing.ProcessingUnavailable):
            processing.process_video(b"fake video bytes", max_duration_ms=120_000)


@pytest.mark.skipif(not processing.ffmpeg_available(), reason="ffmpeg/ffprobe not installed")
def test_process_video_real_ffmpeg_rejects_too_long(tmp_path):
    import subprocess

    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10:duration=3",
            str(src),
        ],
        capture_output=True,
        check=True,
    )
    data = src.read_bytes()
    with pytest.raises(processing.ProcessingError) as exc_info:
        processing.process_video(data, max_duration_ms=1000)
    assert exc_info.value.code == "too_long"


@pytest.mark.skipif(not processing.ffmpeg_available(), reason="ffmpeg/ffprobe not installed")
def test_process_video_real_ffmpeg_reencodes(tmp_path):
    import subprocess

    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1280x720:rate=10:duration=1",
            str(src),
        ],
        capture_output=True,
        check=True,
    )
    data = src.read_bytes()
    result = processing.process_video(data, max_duration_ms=120_000)
    assert result.content_type == "video/mp4"
    assert result.duration_ms > 0
    assert result.height <= processing.VIDEO_MAX_HEIGHT
