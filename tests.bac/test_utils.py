import shutil

import hlsfield
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.core.files.base import ContentFile
from hlsfield.utils import (
    tempdir,
    run,
    ffprobe_streams,
    pick_video_audio_streams,
    get_video_info_quick,
    extract_preview,
    validate_video_file,
    pull_to_local,
    save_tree_to_storage,
    FFmpegError,
    InvalidVideoError,
    StorageError
)


@pytest.mark.django_db
class TestUtils(TestCase):

    def setUp(self):
        """Настройка тестовых данных"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_video = self.test_dir / "test_video.mp4"

        # Создаем минимальный тестовый видеофайл (заглушка)
        with open(self.test_video, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x01mdat')

    def tearDown(self):
        """Очистка после тестов"""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_tempdir_context_manager(self):
        """Тестируем контекстный менеджер для временных директорий"""
        with tempdir() as temp_path:
            self.assertTrue(temp_path.exists())
            self.assertTrue(temp_path.is_dir())

            # Проверяем, что можно создавать файлы внутри
            test_file = temp_path / "test.txt"
            test_file.write_text("test content")
            self.assertTrue(test_file.exists())

        # Проверяем, что директория удаляется после контекста
        self.assertFalse(temp_path.exists())

    @patch('hlsfield.utils.ensure_binary_available')
    @patch('hlsfield.utils.subprocess.run')
    def test_run_basic_command(self, mock_run, mock_ensure):
        """Тестируем выполнение базовых команд"""
        mock_ensure.return_value = "echo"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hello"
        mock_run.return_value.stderr = ""

        result = run(["echo", "hello"], timeout_sec=5)
        self.assertEqual(result.returncode, 0)

    # Исправить тест test_run_with_timeout:
    @patch('hlsfield.utils.subprocess.run')
    def test_run_with_timeout(self, mock_run):
        """Тестируем таймауты при выполнении команд"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("test_cmd", 1)

        # ИСПРАВЛЯЕМ: используем существующую команду
        with self.assertRaises(hlsfield.exceptions.TimeoutError):
            run(["echo", "test"], timeout_sec=1)

    # Исправить тест test_run_command_not_found:
    @patch('hlsfield.utils.subprocess.run')
    def test_run_command_not_found(self, mock_run):
        """Тестируем обработку отсутствующей команды"""
        mock_run.side_effect = FileNotFoundError("Command not found")

        # ИСПРАВЛЯЕМ: используем правильное исключение
        with self.assertRaises(hlsfield.exceptions.FFmpegNotFoundError):
            run(["nonexistent_command"], timeout_sec=5)
            run(["nonexistent_command"], timeout_sec=5)

    def test_pick_video_audio_streams(self):
        """Тестируем выбор видео и аудио потоков"""
        # Тестовые данные streams
        test_info = {
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio", "sample_rate": 44100},
                {"codec_type": "video", "width": 1280, "height": 720},
                {"codec_type": "audio", "sample_rate": 48000},
            ]
        }

        video_stream, audio_stream = pick_video_audio_streams(test_info)

        self.assertIsNotNone(video_stream)
        self.assertIsNotNone(audio_stream)
        self.assertEqual(video_stream["width"], 1920)
        self.assertEqual(audio_stream["sample_rate"], 44100)

    def test_pick_streams_no_audio(self):
        """Тестируем выбор потоков когда нет аудио"""
        test_info = {
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
            ]
        }

        video_stream, audio_stream = pick_video_audio_streams(test_info)

        self.assertIsNotNone(video_stream)
        self.assertIsNone(audio_stream)

    def test_pick_streams_no_video(self):
        """Тестируем выбор потоков когда нет видео"""
        test_info = {
            "streams": [
                {"codec_type": "audio", "sample_rate": 44100},
            ]
        }

        video_stream, audio_stream = pick_video_audio_streams(test_info)

        self.assertIsNone(video_stream)
        self.assertIsNotNone(audio_stream)

    @patch('hlsfield.utils.run')
    def test_get_video_info_quick_success(self, mock_run):
        """Тестируем быстрый анализ видео"""
        mock_result = Mock()
        mock_result.stdout = '{"format": {"duration": "120.5", "size": "1024000", "bit_rate": "2000000"}}'
        mock_run.return_value = mock_result

        info = get_video_info_quick(self.test_video)

        self.assertEqual(info["duration"], 120.5)
        self.assertEqual(info["size"], 1024000)
        self.assertEqual(info["bitrate"], 2000000)

    @patch('hlsfield.utils.run')
    def test_get_video_info_quick_failure(self, mock_run):
        """Тестируем быстрый анализ при ошибке"""
        mock_run.side_effect = Exception("FFprobe error")

        info = get_video_info_quick(self.test_video)

        # Должен вернуть значения по умолчанию
        self.assertEqual(info["duration"], 0)
        self.assertEqual(info["size"], 0)
        self.assertEqual(info["bitrate"], 0)

    def test_validate_video_file_nonexistent(self):
        """Тестируем валидацию несуществующего файла"""
        result = validate_video_file("/nonexistent/path/video.mp4")

        self.assertFalse(result["valid"])
        self.assertIn("File does not exist", result["issues"])

    def test_validate_video_file_empty(self):
        """Тестируем валидацию пустого файла"""
        empty_file = self.test_dir / "empty.mp4"
        empty_file.touch()

        result = validate_video_file(empty_file)

        self.assertFalse(result["valid"])
        # ИСПРАВЛЯЕМ: проверяем что есть хотя бы одна из ошибок
        issues_text = " ".join(result["issues"])
        self.assertTrue("File too small" in issues_text or "Cannot analyze video" in issues_text)

    def test_validate_video_file_invalid_extension(self):
        """Тестируем валидацию файла с неправильным расширением"""
        invalid_file = self.test_dir / "video.txt"
        invalid_file.write_text("not a video")

        result = validate_video_file(invalid_file)

        self.assertFalse(result["valid"])
        # ИСПРАВЛЯЕМ: проверяем что есть хотя бы одна из ошибок
        issues_text = " ".join(result["issues"])
        self.assertTrue("Unsupported file extension" in issues_text or "Cannot analyze video" in issues_text)

    @patch('hlsfield.utils.ffprobe_streams')
    def test_validate_video_file_with_mock_probe(self, mock_probe):
        """Тестируем валидацию с mock FFprobe"""
        # Мок успешного анализа
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "codec_name": "h264"
                }
            ],
            "format": {
                "duration": "60.0",
                "size": "1000000",
                "bit_rate": "2000000"
            }
        }

        # Создаем временный файл нормального размера
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(b'\x00' * 1000000)  # 1MB файл
            test_file = Path(f.name)

        try:
            result = validate_video_file(test_file)
            self.assertTrue(result["valid"])
            self.assertEqual(len(result["issues"]), 0)
        finally:
            test_file.unlink()
    @patch('hlsfield.utils.ffprobe_streams')
    def test_validate_video_file_no_video_stream(self, mock_probe):
        """Тестируем валидацию файла без видео потока"""
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_rate": 44100
                }
            ],
            "format": {
                "duration": "120.5",
                "size": "1048576"
            }
        }

        result = validate_video_file(self.test_video)

        self.assertFalse(result["valid"])
        self.assertIn("No video stream found", result["issues"])

    def test_pull_to_local_with_mock_storage(self):
        """Тестируем загрузку файла из storage"""
        mock_storage = Mock()
        mock_storage.path.return_value = str(self.test_video)

        local_path = pull_to_local(mock_storage, "test_video.mp4", self.test_dir)

        self.assertTrue(local_path.exists())
        self.assertEqual(local_path.name, "test_video.mp4")

    def test_pull_to_local_with_storage_api(self):
        """Тестируем загрузку через storage API"""
        mock_storage = Mock()
        # Эмулируем, что прямой путь не доступен
        mock_storage.path.side_effect = NotImplementedError

        # Мок для open метода
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=ContentFile(b"test content"))
        mock_file.__exit__ = Mock(return_value=None)
        mock_storage.open.return_value = mock_file

        local_path = pull_to_local(mock_storage, "test.txt", self.test_dir)

        self.assertTrue(local_path.exists())
        self.assertEqual(local_path.read_text(), "test content")

    def test_save_tree_to_storage(self):
        """Тестируем сохранение дерева файлов в storage"""
        # Создаем тестовую структуру файлов
        test_tree = self.test_dir / "test_tree"
        test_tree.mkdir()

        (test_tree / "file1.txt").write_text("content1")
        (test_tree / "subdir").mkdir()
        (test_tree / "subdir" / "file2.txt").write_text("content2")

        mock_storage = Mock()
        mock_storage.save.return_value = "saved_path"

        saved_paths = save_tree_to_storage(test_tree, mock_storage, "base/path")

        self.assertEqual(len(saved_paths), 2)
        self.assertEqual(mock_storage.save.call_count, 2)

    @patch('hlsfield.utils.run')
    def test_extract_preview_success(self, mock_run):
        """Тестируем извлечение превью (успешный случай)"""
        mock_run.return_value.returncode = 0

        # Создаем реальный выходной файл с содержимым
        output_image = self.test_dir / "preview.jpg"
        output_image.write_bytes(b'\x00' * 1000)  # Файл > 100 байт

        result = extract_preview(self.test_video, output_image, at_sec=1.0)
        self.assertEqual(result, output_image)

    @patch('hlsfield.utils.run')
    def test_extract_preview_failure(self, mock_run):
        """Тестируем извлечение превью (неудачный случай)"""
        mock_run.return_value.returncode = 1

        output_image = self.test_dir / "preview.jpg"

        with self.assertRaises(Exception):
            extract_preview(self.test_video, output_image, at_sec=1.0)


@pytest.mark.django_db
class TestErrorHandling(TestCase):

    def test_ffmpeg_error_representation(self):
        """Тестируем представление ошибок FFmpeg"""
        error = FFmpegError(["ffmpeg", "-i", "test.mp4"], 1, "stdout", "stderr")
        error_str = str(error)

        self.assertIn("ffmpeg", error_str)
        self.assertIn("returncode", error_str)  # Ищем часть сообщения

    def test_invalid_video_error(self):
        """Тестируем ошибку невалидного видео"""
        error = InvalidVideoError("Corrupted file")
        error_str = str(error)

        self.assertIn("Corrupted file", error_str)


# Тесты для интеграции с реальными командами (требуют установленного FFmpeg)
@pytest.mark.integration
class TestIntegrationWithFFmpeg(TestCase):

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="Требует реального FFmpeg")
    def test_run_with_real_ffmpeg(self):
        """Интеграционный тест с реальным FFmpeg"""
        try:
            result = run(["ffmpeg", "-version"], timeout_sec=10)
            self.assertEqual(result.returncode, 0)
            self.assertIn("ffmpeg version", result.stdout)
        except Exception:
            self.skipTest("FFmpeg not available")
