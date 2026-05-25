import base64
import io
from typing import Annotated, Optional

from PIL import Image, ImageOps
from langchain_core.tools import tool


def _exif_corrected(img: Image.Image) -> Image.Image:
    """Rotate/flip per the EXIF Orientation tag so portrait photos read upright.

    Without this, a phone photo whose EXIF says "rotate 90 CW for display"
    stays in its stored orientation and downstream LLM vision misreads the
    scene (people lying down, text rotated, etc.).
    """
    return ImageOps.exif_transpose(img) or img


@tool
def get_image_metadata(
    base64_image: Annotated[str, "The base64 encoded image string."],
) -> str:
    """Extract format, size, color mode, file size, EXIF, and alpha info from a base64 image."""
    try:
        image_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_data))
        has_exif = bool(
            getattr(img, "_getexif", lambda: None)() or img.info.get("exif")
        )
        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
        return (
            f"Format: {img.format}, Size: {img.size}, Mode: {img.mode}, "
            f"FileSize: {len(image_data)} bytes, EXIF: {has_exif}, Alpha: {has_alpha}"
        )
    except Exception as e:
        return f"Error extracting metadata: {str(e)}"


@tool
def resize_image(
    base64_image: Annotated[str, "The base64 encoded image string."],
    max_width: Annotated[
        Optional[int], "Maximum width for the resized image. Defaults to 1024."
    ] = 1024,
    max_height: Annotated[
        Optional[int], "Maximum height for the resized image. Defaults to 1024."
    ] = 1024,
) -> str:
    """Resize an image (aspect-preserving, EXIF-orientation aware).

    Returns a short factual summary: original size → new size and file-size
    delta. The new base64 is intentionally not returned to avoid blowing up
    the LLM context window — vision_analyst already has the original image
    in its input messages; this tool exists so the analyst can confirm that
    a smaller copy is feasible and reason about it.
    """
    try:
        image_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_data))
        original_size = img.size
        original_fmt = img.format if img.format else "JPEG"
        img = _exif_corrected(img)

        img.thumbnail((max_width, max_height))

        buffered = io.BytesIO()
        img.save(buffered, format=original_fmt)
        new_bytes = buffered.getvalue()

        return (
            f"Image successfully resized to {img.size} from {original_size}. "
            f"FileSize: {len(image_data)} -> {len(new_bytes)} bytes."
        )
    except Exception as e:
        return f"Error resizing image: {str(e)}"
