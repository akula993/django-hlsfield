"""
Pytest конфигурация для django-hlsfield тестов
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import django
import pytest
from django.conf import settings

# Добавляем путь к src для импортов
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


# Настройка Django перед всеми тестами
def pytest_configure():
    """Настраиваем Django для тестов"""
    if not settings.configured:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'
        django.setup()


@pytest.fixture(scope='session')
def django_db_setup():
    """Настройка тестовой БД"""
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Разрешаем доступ к БД для всех тестов"""
    pass


@pytest.fixture
def temp_video_file():
    """Создает временный видео файл для тестов"""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        # Минимальный валидный MP4 header
        f.write(b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00')
        f.write(b'\x00\x00\x00\x00' * 100)  # Padding
        path = Path(f.name)

    yield path

    # Cleanup
    try:
        path.unlink()
    except:
        pass


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Мокает FFmpeg команды"""
    from subprocess import CompletedProcess

    def mock_run(cmd, *args, **kwargs):
        # Эмулируем разные команды
        # Проверка на timeout команды
        if 'sleep' in str(cmd) or 'timeout' in str(cmd):
            import subprocess
            raise subprocess.TimeoutExpired(' '.join(cmd), 1)

        # Для echo команд
        if len(cmd) > 0 and ('echo' in cmd[0] or 'echo' in str(cmd)):
            return CompletedProcess(args=cmd, returncode=0, stdout='hello', stderr='')

        if len(cmd) > 0 and 'ffprobe' in cmd[0]:
            output = '''{
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "bit_rate": "5000000"
                    }
                ],
                "format": {
                    "duration": "60.0",
                    "size": "10000000",
                    "bit_rate": "1333333"
                }
            }'''
            return CompletedProcess(args=cmd, returncode=0, stdout=output, stderr='')

        # Для echo команд
        if len(cmd) > 0 and 'echo' in cmd[0]:
            return CompletedProcess(args=cmd, returncode=0, stdout='hello', stderr='')

        # Для sleep команд - эмулируем таймаут
        if len(cmd) > 0 and 'sleep' in str(cmd):
            import subprocess
            raise subprocess.TimeoutExpired(' '.join(cmd), 1)

        # По умолчанию успех
        return CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    def mock_ensure_binary(binary_name, path):
        # Для несуществующих команд
        if 'nonexistent' in path:
            from hlsfield.exceptions import FFmpegNotFoundError
            raise FFmpegNotFoundError(f"Command not found: {path}")
        return path  # Всегда возвращаем путь как есть

    monkeypatch.setattr('hlsfield.utils.run', mock_run)
    monkeypatch.setattr('hlsfield.utils.ensure_binary_available', mock_ensure_binary)


@pytest.fixture
def temp_storage():
    """Создает временное хранилище для тестов"""
    temp_dir = tempfile.mkdtemp()

    yield Path(temp_dir)

    # Cleanup
    import shutil
    try:
        shutil.rmtree(temp_dir)
    except:
        pass


@pytest.fixture
def sample_ladder():
    """Возвращает тестовую лестницу качеств"""
    return [
        {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
        {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
    ]


@pytest.fixture
def mock_video_file():
    """Создает mock видео файла для тестов"""
    video_file = Mock()
    video_file.name = "test_video.mp4"
    video_file.url = "/media/test_video.mp4"
    video_file.metadata = Mock(return_value={"duration": 120, "width": 1920})
    return video_file


@pytest.fixture
def mock_model_instance():
    """Создает mock экземпляра модели для тестов"""
    instance = Mock()
    instance._meta = Mock()
    instance._meta.model_name = "testmodel"
    return instance
