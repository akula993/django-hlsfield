"""
Общие фикстуры для тестирования django-hlsfield
"""
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from django.test import TestCase, override_settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models

# Настройки для тестов
TEST_SETTINGS = {
    'USE_TZ': True,
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    },
    'INSTALLED_APPS': [
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'hlsfield',
    ],
    'MEDIA_ROOT': tempfile.mkdtemp(prefix='hlsfield_test_'),
    'SECRET_KEY': 'test-secret-key',
    'HLSFIELD_FFMPEG': 'ffmpeg',
    'HLSFIELD_FFPROBE': 'ffprobe',
    'HLSFIELD_PROCESS_ON_SAVE': False,  # Отключаем автоматическую обработку
}


@pytest.fixture
def temp_dir():
    """Временная директория для тестов"""
    with tempfile.TemporaryDirectory(prefix='hlsfield_test_') as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_video_file():
    """Создает тестовый видеофайл"""
    content = b'\x00' * 1024  # Простой бинарный контент
    return ContentFile(content, name='test_video.mp4')


@pytest.fixture
def mock_ffmpeg():
    """Мок для FFmpeg команд"""
    with patch('hlsfield.utils.run') as mock_run:
        # Настраиваем стандартные ответы
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"streams": [], "format": {}}',
            stderr=''
        )
        yield mock_run


@pytest.fixture
def mock_ffprobe_output():
    """Стандартный output FFprobe для тестов"""
    return {
        "streams": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "duration": "60.0",
                "bit_rate": "5000000"
            },
            {
                "index": 1,
                "codec_name": "aac",
                "codec_type": "audio",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "128000"
            }
        ],
        "format": {
            "duration": "60.0",
            "size": "37500000",
            "bit_rate": "5000000",
            "format_name": "mp4,m4a,3gp,3g2,mj2"
        }
    }


@pytest.fixture
def mock_storage():
    """Мок для Django storage"""
    storage = Mock()
    storage.exists.return_value = True
    storage.save.return_value = 'saved_path.mp4'
    storage.url.return_value = 'http://example.com/media/saved_path.mp4'
    storage.size.return_value = 1024 * 1024  # 1MB
    storage.open.return_value.__enter__.return_value.read.return_value = b'video data'
    storage.path.return_value = '/tmp/test_file.mp4'
    return storage


@pytest.fixture
def sample_ladder():
    """Стандартная лестница качеств для тестов"""
    return [
        {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
        {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
    ]


@pytest.fixture
def django_db_setup():
    """Настройка тестовой БД"""
    from django.test.utils import setup_test_environment, teardown_test_environment
    from django.db import connection
    from django.core.management.color import no_style
    from django.core.management.sql import sql_create_index

    setup_test_environment()

    # Создаем таблицы
    with connection.schema_editor() as schema_editor:
        schema_editor.execute("PRAGMA foreign_keys = OFF")

    yield

    teardown_test_environment()


@pytest.fixture
def test_model(db):
    """Создает тестовую модель с video полями"""
    from django.db import models
    from hlsfield import VideoField, HLSVideoField, AdaptiveVideoField

    class TestVideoModel(models.Model):
        title = models.CharField(max_length=200)
        video = VideoField(upload_to='test/')
        hls_video = HLSVideoField(
            upload_to='test/',
            hls_playlist_field='hls_master'
        )
        adaptive_video = AdaptiveVideoField(
            upload_to='test/',
            hls_playlist_field='hls_master',
            dash_manifest_field='dash_manifest'
        )
        hls_master = models.CharField(max_length=500, null=True, blank=True)
        dash_manifest = models.CharField(max_length=500, null=True, blank=True)

        class Meta:
            app_label = 'hlsfield'

    # Создаем таблицу в тестовой БД
    from django.db import connection
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(TestVideoModel)

    yield TestVideoModel

    # Удаляем таблицу
    with connection.schema_editor() as schema_editor:
        schema_editor.delete_model(TestVideoModel)


@pytest.fixture
def celery_worker():
    """Мок для Celery worker"""
    with patch('hlsfield.tasks.shared_task') as mock_task:
        def task_decorator(func):
            func.delay = Mock(return_value=Mock(id='task-123'))
            return func

        mock_task.side_effect = task_decorator
        yield mock_task


@pytest.fixture
def mock_video_analysis():
    """Мок для анализа видео"""
    return {
        'width': 1920,
        'height': 1080,
        'duration': 60.0,
        'complexity': 'medium',
        'has_video': True,
        'has_audio': True,
        'recommended_preset': 'veryfast',
        'estimated_transcode_time': 1.5
    }


@pytest.fixture
def mock_hls_output(temp_dir):
    """Создает структуру HLS файлов для тестов"""
    hls_dir = temp_dir / 'hls'
    hls_dir.mkdir()

    # Создаем варианты качества
    for height in [360, 720, 1080]:
        variant_dir = hls_dir / f'v{height}'
        variant_dir.mkdir()

        # Создаем плейлист
        playlist = variant_dir / 'index.m3u8'
        playlist.write_text(f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
seg_0000.ts
#EXTINF:6.0,
seg_0001.ts
#EXT-X-ENDLIST
""")

        # Создаем сегменты
        for i in range(2):
            seg_file = variant_dir / f'seg_{i:04d}.ts'
            seg_file.write_bytes(b'TS_DATA' * 100)

    # Создаем master плейлист
    master = hls_dir / 'master.m3u8'
    master.write_text("""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=896000,RESOLUTION=640x360
v360/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2628000,RESOLUTION=1280x720
v720/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4660000,RESOLUTION=1920x1080
v1080/index.m3u8
""")

    return hls_dir


@pytest.fixture
def mock_dash_output(temp_dir):
    """Создает структуру DASH файлов для тестов"""
    dash_dir = temp_dir / 'dash'
    dash_dir.mkdir()

    # Создаем манифест
    manifest = dash_dir / 'manifest.mpd'
    manifest.write_text("""<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-live:2011">
  <Period>
    <AdaptationSet mimeType="video/mp4">
      <Representation id="1" bandwidth="896000" width="640" height="360"/>
      <Representation id="2" bandwidth="2628000" width="1280" height="720"/>
      <Representation id="3" bandwidth="4660000" width="1920" height="1080"/>
    </AdaptationSet>
  </Period>
</MPD>
""")

    # Создаем init сегменты
    for i in [1, 2, 3]:
        init_file = dash_dir / f'init-{i}.m4s'
        init_file.write_bytes(b'INIT_DATA' * 50)

        # Создаем media сегменты
        for j in range(10):
            chunk_file = dash_dir / f'chunk-{i}-{j:05d}.m4s'
            chunk_file.write_bytes(b'CHUNK_DATA' * 100)

    return dash_dir


@pytest.fixture(scope='session')
def django_settings():
    """Настройки Django для тестов"""
    from django.conf import settings
    if not settings.configured:
        settings.configure(**TEST_SETTINGS)

    import django
    django.setup()

    return settings


class MockFFmpegProcess:
    """Мок для subprocess.run при вызове FFmpeg"""

    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, *args, **kwargs):
        return self


@pytest.fixture
def mock_successful_ffmpeg():
    """Мок для успешного выполнения FFmpeg"""
    return MockFFmpegProcess(
        returncode=0,
        stdout='Success',
        stderr=''
    )


@pytest.fixture
def mock_failed_ffmpeg():
    """Мок для неуспешного выполнения FFmpeg"""
    return MockFFmpegProcess(
        returncode=1,
        stdout='',
        stderr='FFmpeg error occurred'
    )
