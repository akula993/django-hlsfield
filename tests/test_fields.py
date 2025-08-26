# tests/test_fields.py
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.contrib.auth.models import User

from hlsfield import VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField
from hlsfield.fields import VideoFieldFile


class TestVideoModel(models.Model):
    """Тестовая модель для VideoField"""
    title = models.CharField(max_length=100)
    video = VideoField(
        upload_to="test_videos/",
        duration_field="duration",
        width_field="width",
        height_field="height",
        preview_field="preview"
    )
    duration = models.DurationField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    preview = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        app_label = 'test_app'


class TestHLSVideoModel(models.Model):
    """Тестовая модель для HLSVideoField"""
    title = models.CharField(max_length=100)
    video = HLSVideoField(
        upload_to="hls_videos/",
        hls_playlist_field="hls_playlist"
    )
    hls_playlist = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        app_label = 'test_app'


class BaseVideoFieldTest(TestCase):
    """Базовый класс для тестирования video fields"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sample_video = self.create_sample_video()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_sample_video(self):
        """Создает тестовый видеофайл"""
        video_path = self.temp_dir / "sample.mp4"

        # Создаем минимальный MP4 заголовок для тестов
        # В реальных тестах используйте настоящие видеофайлы
        with open(video_path, 'wb') as f:
            # Минимальные MP4 байты (ftyp box)
            f.write(b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41')
            f.write(b'\x00' * 1000)  # Dummy data

        return video_path

    def create_uploaded_file(self, filename="test_video.mp4"):
        """Создает объект UploadedFile для тестов"""
        with open(self.sample_video, 'rb') as f:
            return SimpleUploadedFile(filename, f.read(), content_type='video/mp4')


class VideoFieldTest(BaseVideoFieldTest):
    """Тесты для базового VideoField"""

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.extract_preview')
    def test_video_field_save_with_metadata_extraction(self, mock_extract_preview, mock_ffprobe):
        """Тест сохранения видео с извлечением метаданных"""

        # Мокаем ffprobe ответ
        mock_ffprobe.return_value = {
            'format': {'duration': '120.5'},
            'streams': [
                {
                    'codec_type': 'video',
                    'width': 1920,
                    'height': 1080
                }
            ]
        }

        # Создаем тестовую модель
        video_obj = TestVideoModel.objects.create(
            title="Test Video",
            video=self.create_uploaded_file()
        )

        # Проверяем что метаданные извлечены
        self.assertEqual(video_obj.width, 1920)
        self.assertEqual(video_obj.height, 1080)
        self.assertEqual(video_obj.duration.total_seconds(), 120.5)

        # Проверяем что превью создано
        mock_extract_preview.assert_called_once()

    def test_video_field_file_methods(self):
        """Тест методов VideoFieldFile"""

        video_obj = TestVideoModel(title="Test")
        video_obj.video.name = "test_videos/sample.mp4"

        field_file = video_obj.video

        # Тестируем _base_key
        self.assertEqual(field_file._base_key(), "test_videos/sample")

        # Тестируем _meta_key для nested layout
        video_obj.video.field.sidecar_layout = "nested"
        expected_meta = "test_videos/sample/meta.json"
        self.assertEqual(field_file._meta_key(), expected_meta)

        # Тестируем _meta_key для flat layout
        video_obj.video.field.sidecar_layout = "flat"
        expected_meta = "test_videos/sample_meta.json"
        self.assertEqual(field_file._meta_key(), expected_meta)

    @patch('hlsfield.fields.VideoFieldFile.storage')
    def test_metadata_from_model_fields(self, mock_storage):
        """Тест получения метаданных из полей модели"""

        import datetime

        video_obj = TestVideoModel(
            title="Test",
            duration=datetime.timedelta(seconds=180),
            width=1280,
            height=720,
            preview="preview.jpg"
        )

        metadata = video_obj.video.metadata()

        expected = {
            'duration_seconds': 180,
            'width': 1280,
            'height': 720,
            'preview_name': 'preview.jpg'
        }

        self.assertEqual(metadata, expected)

    def test_preview_url_from_field(self):
        """Тест получения URL превью из поля модели"""

        video_obj = TestVideoModel(title="Test", preview="previews/thumb.jpg")

        with patch.object(video_obj.video.storage, 'url', return_value='/media/previews/thumb.jpg'):
            url = video_obj.video.preview_url()
            self.assertEqual(url, '/media/previews/thumb.jpg')


class HLSVideoFieldTest(BaseVideoFieldTest):
    """Тесты для HLSVideoField"""

    def test_hls_field_initialization(self):
        """Тест инициализации HLS поля"""

        field = HLSVideoField(
            upload_to="videos/",
            hls_playlist_field="playlist",
            ladder=[{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}],
            segment_duration=10
        )

        self.assertEqual(field.hls_playlist_field, "playlist")
        self.assertEqual(field.segment_duration, 10)
        self.assertEqual(len(field.ladder), 1)
        self.assertEqual(field.ladder[0]["height"], 720)

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    def test_hls_processing_trigger(self, mock_build_hls):
        """Тест запуска HLS обработки"""

        video_obj = TestHLSVideoModel.objects.create(
            title="HLS Test",
            video=self.create_uploaded_file()
        )

        # Проверяем что обработка запустилась
        mock_build_hls.assert_called_once()

        # Проверяем параметры вызова
        call_args = mock_build_hls.call_args[0]
        self.assertEqual(call_args[0], video_obj._meta.label)
        self.assertEqual(call_args[1], video_obj.pk)
        self.assertEqual(call_args[2], 'video')

    def test_master_url_method(self):
        """Тест получения URL master плейлиста"""

        video_obj = TestHLSVideoModel(
            title="Test",
            hls_playlist="videos/abc123/hls/master.m3u8"
        )

        with patch.object(video_obj.video.storage, 'url', return_value='/media/videos/abc123/hls/master.m3u8'):
            url = video_obj.video.master_url()
            self.assertEqual(url, '/media/videos/abc123/hls/master.m3u8')


class DefaultsTest(TestCase):
    """Тесты для модуля defaults"""

    def test_defaults_without_django_settings(self):
        """Тест что defaults работают без Django settings"""

        from hlsfield import defaults

        # Базовые значения должны быть установлены
        self.assertEqual(defaults.FFMPEG, "ffmpeg")
        self.assertEqual(defaults.FFPROBE, "ffprobe")
        self.assertEqual(defaults.SEGMENT_DURATION, 6)
        self.assertTrue(len(defaults.DEFAULT_LADDER) > 0)

    @patch('hlsfield.defaults._settings')
    def test_defaults_with_custom_settings(self, mock_settings):
        """Тест переопределения через Django settings"""

        # Мокаем настройки
        mock_settings.HLSFIELD_FFMPEG = "/custom/path/ffmpeg"
        mock_settings.HLSFIELD_SEGMENT_DURATION = 10
        mock_settings.configured = True

        # Импортируем заново чтобы применились настройки
        import importlib
        from hlsfield import defaults
        importlib.reload(defaults)

        self.assertEqual(defaults.FFMPEG, "/custom/path/ffmpeg")
        self.assertEqual(defaults.SEGMENT_DURATION, 10)


class UtilsTest(BaseVideoFieldTest):
    """Тесты для модуля utils"""

    def test_tempdir_context_manager(self):
        """Тест временной директории"""

        from hlsfield.utils import tempdir

        temp_path = None
        with tempdir() as td:
            temp_path = td
            self.assertTrue(td.exists())
            self.assertTrue(td.is_dir())

        # После выхода из контекста директория должна быть удалена
        self.assertFalse(temp_path.exists())

    @patch('subprocess.run')
    def test_run_command_success(self, mock_subprocess):
        """Тест успешного выполнения команды"""

        from hlsfield.utils import run

        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="success",
            stderr=""
        )

        result = run(["echo", "test"])
        self.assertEqual(result.stdout, "success")

    @patch('subprocess.run')
    def test_run_command_failure(self, mock_subprocess):
        """Тест обработки ошибки команды"""

        from hlsfield.utils import run

        mock_subprocess.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message"
        )

        with self.assertRaises(RuntimeError) as context:
            run(["false"])

        self.assertIn("Command failed", str(context.exception))
        self.assertIn("error message", str(context.exception))

    @patch('hlsfield.utils.run')
    def test_ffprobe_streams(self, mock_run):
        """Тест парсинга ffprobe вывода"""

        from hlsfield.utils import ffprobe_streams

        # Мокаем JSON ответ ffprobe
        mock_run.return_value = MagicMock(
            stdout='{"streams": [{"codec_type": "video", "width": 1920}]}'
        )

        result = ffprobe_streams("/path/to/video.mp4")

        self.assertIn("streams", result)
        self.assertEqual(len(result["streams"]), 1)
        self.assertEqual(result["streams"][0]["codec_type"], "video")

    def test_pick_video_audio_streams(self):
        """Тест выбора видео и аудио потоков"""

        from hlsfield.utils import pick_video_audio_streams

        info = {
            "streams": [
                {"codec_type": "video", "width": 1920},
                {"codec_type": "audio", "channels": 2},
                {"codec_type": "subtitle"}
            ]
        }

        video, audio = pick_video_audio_streams(info)

        self.assertEqual(video["codec_type"], "video")
        self.assertEqual(video["width"], 1920)

        self.assertEqual(audio["codec_type"], "audio")
        self.assertEqual(audio["channels"], 2)


class ErrorHandlingTest(BaseVideoFieldTest):
    """Тесты обработки ошибок"""

    @patch('hlsfield.utils.ffprobe_streams')
    def test_invalid_video_file(self, mock_ffprobe):
        """Тест обработки невалидного видеофайла"""

        # ffprobe возвращает ошибку
        mock_ffprobe.side_effect = RuntimeError("Invalid file format")

        # Создание объекта не должно падать
        video_obj = TestVideoModel(title="Invalid Video")

        # Метаданные должны быть пустыми при ошибке
        with patch.object(video_obj.video, '_meta_key', return_value='meta.json'):
            with patch.object(video_obj.video.storage, 'open', side_effect=FileNotFoundError):
                metadata = video_obj.video.metadata()
                self.assertEqual(metadata, {})

    @patch('hlsfield.utils.extract_preview')
    def test_preview_extraction_failure(self, mock_extract):
        """Тест обработки ошибки создания превью"""

        mock_extract.side_effect = RuntimeError("Preview extraction failed")

        # Сохранение должно пройти успешно даже если превью не создалось
        with patch('hlsfield.utils.ffprobe_streams', return_value={'format': {}, 'streams': []}):
            video_obj = TestVideoModel.objects.create(
                title="No Preview",
                video=self.create_uploaded_file()
            )

        # Объект должен быть создан
        self.assertEqual(video_obj.title, "No Preview")

    def test_storage_errors(self):
        """Тест обработки ошибок storage"""

        video_obj = TestVideoModel(title="Storage Error")

        # Мокаем ошибку storage
        with patch.object(video_obj.video.storage, 'exists', side_effect=Exception("Storage error")):
            # preview_url не должен падать при ошибке storage
            url = video_obj.video.preview_url()
            self.assertIsNone(url)
