import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Добавляем путь к src в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Настройка Django для тестов
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

import django

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture
def temp_video_file():
    """Создает временный видеофайл для тестов"""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        # Минимальный валидный MP4 заголовок
        f.write(b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isomiso2avc1mp41')
        f.write(b'\x00' * 1024)  # Добавляем немного данных
        temp_path = f.name

    yield Path(temp_path)

    # Очистка
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_video_file():
    """Mock видеофайла"""
    return SimpleUploadedFile(
        'test.mp4',
        b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isomiso2avc1mp41' + b'\x00' * 1024,
        content_type='video/mp4'
    )


@pytest.fixture
def mock_storage():
    """Mock storage для тестов"""
    storage = Mock()
    storage.exists.return_value = False
    storage.save.return_value = "saved/path/video.mp4"
    storage.url.return_value = "http://example.com/video.mp4"
    return storage
