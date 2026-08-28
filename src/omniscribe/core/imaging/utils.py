import base64
import io

from PIL import Image


def decode_base64_image(data: str) -> Image.Image:
    """Decodes a base64 encoded image string to a PIL Image.

    Uses a ``with Image.open(...)`` block so the underlying buffer is closed
    on return. H1 audit fix: a bare ``Image.open(...).convert(...)`` chain
    keeps the buffer alive until GC, which leaks memory in long-running OCR
    runs (200+ pages). The ``with`` block makes cleanup intent explicit and
    protects against future refactors that change the call pattern.
    """
    raw = base64.b64decode(data)
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        return img.copy()


def encode_image_base64(img: Image.Image, format: str = "PNG") -> str:
    """Encodes a PIL Image to a base64 string."""
    buf = io.BytesIO()
    img.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode("ascii")
