import base64
import io

from PIL import Image


def decode_base64_image(data: str) -> Image.Image:
    """Decodes a base64 encoded image string to a PIL Image."""
    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")


def encode_image_base64(img: Image.Image, format: str = "PNG") -> str:
    """Encodes a PIL Image to a base64 string."""
    buf = io.BytesIO()
    img.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode("ascii")
