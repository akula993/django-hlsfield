import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import SimpleVideo, HLSVideo, DASHVideo, AdaptiveVideo
from .utils import get_test_video_content


class SimpleVideoTestCase(TestCase):
    """Тесты для SimpleVideo модели"""

    def setUp(self):
        self.video_content = get_test_video_content()

    @patch('hlsfield.fields.VideoFieldFile._process_video_metadata')
    def test_simple_video_creation(self, mock_process):
        """Тест создания SimpleVideo"""
        video = SimpleVideo.objects.create(title="Test Video")

        # Создаем mock файл
        video_file = SimpleUploadedFile(
            'test.mp4',
            self.video_content,
            content_type='video/mp4'
        )

        # Сохраняем видео
        video.video.save('test.mp4', video_file, save=True)

        self.assertEqual(video.title, "Test Video")
        self.assertTrue(mock_process.called)


class HLSVideoTestCase(TestCase):
    """Тесты для HLSVideo модели"""

    def setUp(self):
        self.video_content = get_test_video_content()

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    def test_hls_video_creation(self, mock_build):
        """Тест создания HLSVideo"""
        video = HLSVideo.objects.create(title="Test HLS Video")

        video_file = SimpleUploadedFile(
            'test.mp4',
            self.video_content,
            content_type='video/mp4'
        )

        video.video.save('test.mp4', video_file, save=True)

        self.assertEqual(video.title, "Test HLS Video")
        # Проверяем что задача HLS обработки была запущена
        self.assertTrue(mock_build.called)
        mock_build.assert_called_with('examples.HLSVideo', video.pk, 'video')


class MockFFmpegTestCase(TestCase):
    """Базовый класс для тестов с mock FFmpeg"""

    def setUp(self):
        self.video_content = get_test_video_content()

        # Mock FFmpeg функции
        self.ffprobe_patch = patch('hlsfield.utils.ffprobe_streams')
        self.extract_preview_patch = patch('hlsfield.utils.extract_preview')
        self.transcode_patch = patch('hlsfield.utils.transcode_to_hls')

        self.mock_ffprobe = self.ffprobe_patch.start()
        self.mock_extract = self.extract_preview_patch.start()
        self.mock_transcode = self.transcode_patch.start()

        # Настраиваем mock
        self.mock_ffprobe.return_value = {
            "format": {"duration": "10.5"},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio", "sample_rate": "48000"}
            ]
        }

    def tearDown(self):
        self.ffprobe_patch.stop()
        self.extract_preview_patch.stop()
        self.transcode_patch.stop()


class HLSVideoWithMockFFmpegTestCase(MockFFmpegTestCase):
    """Тесты HLSVideo с mock FFmpeg"""

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    def test_hls_video_with_mock_ffmpeg(self, mock_build):
        """Тест HLSVideo с mock FFmpeg"""
        video = HLSVideo.objects.create(title="Test HLS Video")

        video_file = SimpleUploadedFile(
            'test.mp4',
            self.video_content,
            content_type='video/mp4'
        )

        video.video.save('test.mp4', video_file, save=True)

        self.assertEqual(video.title, "Test HLS Video")
        # Проверяем что FFmpeg функции были вызваны
        self.assertTrue(self.mock_ffprobe.called)
        self.assertTrue(self.mock_extract.called)
        # Проверяем что задача HLS обработки была запущена
        self.assertTrue(mock_build.called)


class ModelIntegrationTestCase(TestCase):
    """Интеграционные тесты всех моделей"""

    def test_model_creation(self):
        """Тест создания всех типов моделей"""
        # SimpleVideo
        simple = SimpleVideo.objects.create(title="Simple")
        self.assertEqual(simple.title, "Simple")

        # HLSVideo
        hls = HLSVideo.objects.create(title="HLS")
        self.assertEqual(hls.title, "HLS")

        # DASHVideo
        dash = DASHVideo.objects.create(title="DASH")
        self.assertEqual(dash.title, "DASH")

        # AdaptiveVideo
        adaptive = AdaptiveVideo.objects.create(title="Adaptive")
        self.assertEqual(adaptive.title, "Adaptive")

        # Проверяем что все объекты создались
        self.assertEqual(SimpleVideo.objects.count(), 1)
        self.assertEqual(HLSVideo.objects.count(), 1)
        self.assertEqual(DASHVideo.objects.count(), 1)
        self.assertEqual(AdaptiveVideo.objects.count(), 1)


class FieldMethodsTestCase(TestCase):
    """Тесты методов полей"""

    def test_video_field_methods(self):
        """Тест методов VideoField"""
        video = SimpleVideo.objects.create(title="Test Methods")

        # Mock storage и файл
        video.video.storage = Mock()
        video.video.storage.url.return_value = "http://example.com/video.mp4"
        video.video.storage.exists.return_value = True
        video.video.name = "test.mp4"

        # Тестируем методы
        metadata = video.video.metadata()
        self.assertIsInstance(metadata, dict)

        preview_url = video.video.preview_url()
        self.assertIsNotNone(preview_url)
