import base64
import io
from typing import Annotated, Optional
from PIL import Image
from langchain_core.tools import tool


@tool
def get_image_metadata(
    base64_image: Annotated[str, "The base64 encoded image string."],
) -> str:
    """Extracts metadata such as format, size, and mode from a base64 encoded image."""
    try:
        image_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_data))
        return f"Format: {img.format}, Size: {img.size}, Mode: {img.mode}"
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
    """Resizes an image while maintaining aspect ratio and returns the new base64 string."""
    try:
        image_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_data))

        # Maintain aspect ratio
        img.thumbnail((max_width, max_height))

        buffered = io.BytesIO()
        # Save back to same format if possible, otherwise default to JPEG
        fmt = img.format if img.format else "JPEG"
        img.save(buffered, format=fmt)

        new_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"Image successfully resized to {img.size}. New Base64 length: {len(new_base64)}"
    except Exception as e:
        return f"Error resizing image: {str(e)}"
