# src/hlsfield/upload_to.py
import os, uuid

def video_upload_to(instance, filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    folder = uuid.uuid4().hex[:8]
    return f"videos/{folder}/{stem}{ext}"
