"""
Pytest конфигурация для django-hlsfield тестов
"""
import os
import sys
import tempfile
from pathlib import Path

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
    """Настройка базы данных для тестов"""
    from django.core.management import call_command
    call_command('migrate', '--run-syncdb', verbosity=0)


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

    def mock_run(cmd, *args, **kwargs):
        from subprocess import CompletedProcess

        # Эмулируем разные команды
        if 'ffprobe' in cmd[0]:
            # Возвращаем мок данные для ffprobe
            output = '''
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "bit_rate": "5000000"
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "bit_rate": "128000"
                    }
                ],
                "format": {
                    "duration": "60.0",
                    "size": "10000000",
                    "bit_rate": "1333333"
                }
            }
            '''
            return CompletedProcess(args=cmd, returncode=0,
                                    stdout=output, stderr='')

        # Для других команд
        return CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr('hlsfield.utils.run', mock_run)
    monkeypatch.setattr('subprocess.run', mock_run)


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


