"""Fix round FIX-B, security review L1: JPEG COM comment segments used to survive
re-encoding, and EXIF orientation was dropped without first being baked into the pixels.
New file -- `tests/media/test_processing.py` already covers plain GPS/EXIF stripping; this
adds the COM-comment and orientation-preserving cases the review specifically asked for, plus
a combined "GPS EXIF + XMP + COM" case.
"""

from __future__ import annotations

import io

import piexif
import pytest
from PIL import Image

from ham.media import processing

_XMP_PACKET = (
    b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description rdf:about="" '
    b'xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:creator>Someone Identifiable</dc:creator>"
    b"</rdf:Description></rdf:RDF></x:xmpmeta>"
    b'<?xpacket end="w"?>'
)
_XMP_APP1_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"


def _insert_app1_xmp(jpeg_bytes: bytes) -> bytes:
    """Splices a raw XMP APP1 segment right after the SOI marker (0xFFD8) -- Pillow's
    ``Image.save`` has no ``xmp=`` kwarg for plain JPEG, so this reproduces what a phone/
    editor's XMP metadata block looks like on the wire without needing one."""
    assert jpeg_bytes[:2] == b"\xff\xd8"
    payload = _XMP_APP1_HEADER + _XMP_PACKET
    length = len(payload) + 2  # length field includes itself, per the JPEG spec
    segment = b"\xff\xe1" + length.to_bytes(2, "big") + payload
    return jpeg_bytes[:2] + segment + jpeg_bytes[2:]


def _jpeg_with_gps_xmp_and_comment(width=200, height=100) -> bytes:
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
    img.save(buf, format="JPEG", exif=exif_bytes, comment=b"Taken at 123 Main St, unit 4B")
    return _insert_app1_xmp(buf.getvalue())


def test_process_photo_strips_gps_exif_xmp_and_comment_together():
    original = _jpeg_with_gps_xmp_and_comment()
    # Sanity: the source really carries all three.
    opened = Image.open(io.BytesIO(original))
    assert opened.getexif()
    assert opened.info.get("comment") == b"Taken at 123 Main St, unit 4B"
    assert b"Someone Identifiable" in original

    result = processing.process_photo(original)

    out_img = Image.open(io.BytesIO(result.data))
    assert not out_img.getexif()
    assert "comment" not in (out_img.info or {})
    assert b"Taken at 123 Main St" not in result.data
    assert b"Someone Identifiable" not in result.data
    assert b"http://ns.adobe.com/xap/1.0/" not in result.data
    # And the thumbnail too, not just the full-size derivative.
    thumb_img = Image.open(io.BytesIO(result.thumbnail))
    assert not thumb_img.getexif()
    assert b"Taken at 123 Main St" not in result.thumbnail


def _jpeg_with_comment_only() -> bytes:
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", comment=b"private note")
    return buf.getvalue()


def test_process_photo_strips_a_jpeg_comment_with_no_exif_at_all():
    """Security review L1: a comment segment with no EXIF alongside it still has to go --
    guards against a fix that only clears `.info` when EXIF happens to be present."""
    original = _jpeg_with_comment_only()
    assert Image.open(io.BytesIO(original)).info.get("comment") == b"private note"

    result = processing.process_photo(original)

    out_img = Image.open(io.BytesIO(result.data))
    assert "comment" not in (out_img.info or {})
    assert b"private note" not in result.data


@pytest.mark.parametrize("orientation", [3, 6, 8])
def test_process_photo_bakes_in_exif_orientation_before_dropping_it(orientation):
    """Security review L1 "apply exif_transpose before dropping EXIF": a wide (landscape)
    source tagged as needing a 90-degree rotation must come out portrait-shaped, not
    landscape-shaped-but-EXIF-less (which would look sideways in any viewer once the
    orientation tag is gone)."""
    img = Image.new("RGB", (120, 80), color=(1, 2, 3))  # landscape source
    exif_dict = {"0th": {piexif.ImageIFD.Orientation: orientation}}
    exif_bytes = piexif.dump(exif_dict)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes)
    original = buf.getvalue()

    result = processing.process_photo(original)

    out_img = Image.open(io.BytesIO(result.data))
    if orientation in (6, 8):  # a 90/270-degree turn swaps width and height
        assert out_img.width == 80
        assert out_img.height == 120
    else:  # 3: a 180-degree turn keeps the same dimensions
        assert out_img.width == 120
        assert out_img.height == 80
    assert not out_img.getexif()
