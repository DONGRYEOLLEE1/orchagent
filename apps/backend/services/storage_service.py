import os
import base64
import uuid
from pathlib import Path

# Base directory for storing images
IMAGE_STORAGE_DIR = Path(
    os.environ.get("IMAGE_STORAGE_DIR", "apps/backend/data/images")
)
IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class StorageService:
    @staticmethod
    def save_base64_image(base64_string: str) -> str:
        """
        Saves a base64 encoded image to the local storage.
        Returns the local relative path to the saved image.
        """
        try:
            # Generate a unique filename
            filename = f"{uuid.uuid4()}.jpg"
            filepath = IMAGE_STORAGE_DIR / filename

            # Decode and save
            image_data = base64.b64decode(base64_string)
            with open(filepath, "wb") as f:
                f.write(image_data)

            return str(filepath)
        except Exception as e:
            # Log error and return a placeholder or re-raise
            print(f"Error saving image: {e}")
            return "error_saving_image"

    @staticmethod
    def get_storage_path() -> Path:
        return IMAGE_STORAGE_DIR
