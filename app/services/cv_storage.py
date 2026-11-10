import re
import uuid
from pathlib import Path

from app.core.config import get_settings

STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{32}-[12]-[1-9][0-9]*-[0-9a-f]{32}\.(pdf|docx)$"
)


def make_storage_key(user_id: uuid.UUID, slot: int, version: int, extension: str) -> str:
    return f"{user_id.hex}-{slot}-{version}-{uuid.uuid4().hex}{extension}"


def storage_path(storage_key: str) -> Path:
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise ValueError("Invalid CV storage key.")
    root = Path(get_settings().upload_dir).resolve()
    path = (root / storage_key).resolve()
    if path.parent != root:
        raise ValueError("Invalid CV storage path.")
    return path
