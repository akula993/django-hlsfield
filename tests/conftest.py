import pytest
import tempfile
import shutil
from pathlib import Path
from django.conf import settings
from django.apps import apps


@pytest.fixture
def temp_media_root():
    """Фикстура для временной MEDIA_ROOT"""
    temp_dir = Path(tempfile.mkdtemp())

    # Временно меняем MEDIA_ROOT
    original_media_root = settings.MEDIA_ROOT
    settings.MEDIA_ROOT = str(temp_dir)

    yield temp_dir

    # Восстанавливаем и очищаем
    settings.MEDIA_ROOT = original_media_root
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_video_file():
    """Фикстура для создания тестового видео"""
    temp_dir = Path(tempfile.mkdtemp())
    video_path = temp_dir / "sample.mp4"

    # Создаем простейший MP4 файл для тестов
    with open(video_path, 'wb') as f:
        # MP4 signature
        f.write(b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41')
        f.write(b'\x00' * 1000)

    yield video_path

    shutil.rmtree(temp_dir, ignore_errors=True)

