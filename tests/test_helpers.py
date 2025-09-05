import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.core.files.storage import default_storage
from django.test import TestCase

from hlsfield.helpers import (
    video_upload_to,
    date_based_upload_to,
    user_based_upload_to,
    content_type_upload_to,
    get_video_upload_path,
    generate_video_id,
    generate_secure_video_id,
    generate_content_hash,
    extract_filename_metadata,
    combine_video_metadata,
    sanitize_metadata,
    format_duration,
    format_file_size,
    format_bitrate,
    format_video_info,
    ensure_directory_exists,
    clean_filename,
    get_file_extension_info,
    get_model_video_fields,
    get_video_field_metadata,
    create_video_upload_to_function,
)


class TestUploadToFunctions(TestCase):

    def test_video_upload_to_basic(self):
        """Тестируем базовую функцию upload_to"""
        result = video_upload_to(None, "my_video.mp4")

        self.assertTrue(result.startswith("videos/"))
        self.assertIn(".mp4", result)
        self.assertEqual(len(result.split("/")), 3)  # videos/uuid/filename

    def test_video_upload_to_special_chars(self):
        """Тестируем обработку специальных символов в имени файла"""
        result = video_upload_to(None, "My Video!@#$%^&().mp4")

        self.assertTrue(result.startswith("videos/"))
        self.assertTrue(result.endswith(".mp4"))
        # Должно быть очищено от специальных символов
        self.assertNotIn("!", result)
        self.assertNotIn("@", result)
        self.assertNotIn("#", result)

    def test_date_based_upload_to(self):
        """Тестируем upload_to на основе даты"""
        with patch('hlsfield.helpers.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.year = 2025
            mock_now.month = 1
            mock_now.day = 15
            mock_datetime.now.return_value = mock_now

            result = date_based_upload_to(None, "test.mp4")

            self.assertTrue(result.startswith("videos/2025/01/15/"))
            self.assertTrue(result.endswith(".mp4"))

    def test_user_based_upload_to_with_user(self):
        """Тестируем upload_to на основе пользователя"""
        mock_instance = Mock()
        mock_user = Mock()
        mock_user.id = 123
        mock_instance.user = mock_user

        result = user_based_upload_to(mock_instance, "user_video.mp4")

        self.assertTrue(result.startswith("videos/users/123/"))
        self.assertTrue(result.endswith(".mp4"))

    def test_user_based_upload_to_with_owner(self):
        """Тестируем upload_to на основе owner"""
        mock_instance = Mock()
        mock_owner = Mock()
        mock_owner.id = 456
        mock_instance.owner = mock_owner
        mock_instance.user = None

        result = user_based_upload_to(mock_instance, "owner_video.mp4")

        self.assertTrue(result.startswith("videos/users/456/"))

    def test_user_based_upload_to_anonymous(self):
        """Тестируем upload_to для анонимного пользователя"""
        mock_instance = Mock()
        mock_instance.user = None
        mock_instance.owner = None
        mock_instance.created_by = None

        result = user_based_upload_to(mock_instance, "anon_video.mp4")

        self.assertTrue(result.startswith("videos/users/anonymous/"))

    def test_content_type_upload_to_explicit(self):
        """Тестируем upload_to с явным content_type"""
        mock_instance = Mock()
        mock_instance.content_type = "movies"

        result = content_type_upload_to(mock_instance, "movie.mp4")

        self.assertTrue(result.startswith("videos/movies/"))

    def test_content_type_upload_by_category(self):
        """Тестируем upload_to с category"""
        mock_instance = Mock()
        mock_instance.content_type = None
        mock_instance.category = "tutorials"

        result = content_type_upload_to(mock_instance, "tutorial.mp4")

        self.assertTrue(result.startswith("videos/tutorials/"))

    def test_content_type_upload_by_model_name(self):
        """Тестируем upload_to с определением по имени модели"""
        mock_instance = Mock()
        mock_instance._meta.model_name = "lesson"
        mock_instance.content_type = None
        mock_instance.category = None

        result = content_type_upload_to(mock_instance, "lesson.mp4")

        self.assertTrue(result.startswith("videos/lessons/"))

    def test_get_video_upload_path_strategies(self):
        """Тестируем get_video_upload_path с разными стратегиями"""
        strategies = ["uuid", "date", "user", "content"]

        for strategy in strategies:
            result = get_video_upload_path(
                instance=None,
                filename="test.mp4",
                strategy=strategy
            )

            self.assertTrue(result.startswith("videos/"))
            self.assertTrue(result.endswith(".mp4"))

    def test_get_video_upload_path_custom_filename(self):
        """Тестируем get_video_upload_path с кастомным именем файла"""
        result = get_video_upload_path(filename="custom_video.avi", strategy="uuid")

        self.assertTrue(result.startswith("videos/"))
        self.assertTrue(result.endswith(".avi"))

    def test_create_video_upload_to_function(self):
        """Тестируем фабрику upload_to функций"""
        upload_func = create_video_upload_to_function("date")

        self.assertTrue(callable(upload_func))
        self.assertEqual(upload_func.strategy, "date")

        result = upload_func(None, "test.mp4")
        self.assertTrue(result.startswith("videos/"))


class TestIdGenerationFunctions(TestCase):

    def test_generate_video_id_default_length(self):
        """Тестируем генерацию ID по умолчанию"""
        video_id = generate_video_id()

        self.assertEqual(len(video_id), 8)
        # Должен быть hex (буквы и цифры)
        self.assertTrue(all(c in '0123456789abcdef' for c in video_id))

    def test_generate_video_id_custom_length(self):
        """Тестируем генерацию ID с кастомной длиной"""
        for length in [4, 12, 16]:
            video_id = generate_video_id(length)
            self.assertEqual(len(video_id), length)

    def test_generate_secure_video_id(self):
        """Тестируем генерацию безопасного ID"""
        secure_id = generate_secure_video_id()

        self.assertEqual(len(secure_id), 16)
        # Должен быть hex
        self.assertTrue(all(c in '0123456789abcdef' for c in secure_id))

    def test_generate_secure_video_id_with_seed(self):
        """Тестируем генерацию безопасного ID с seed"""
        seed = "test_seed_data"
        secure_id1 = generate_secure_video_id(seed)
        secure_id2 = generate_secure_video_id(seed)

        self.assertEqual(secure_id1, secure_id2)  # Должны быть одинаковые с одинаковым seed

    def test_generate_content_hash(self):
        """Тестируем генерацию хэша содержимого"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content for hashing")
            tmp_path = tmp.name

        try:
            content_hash = generate_content_hash(tmp_path)

            self.assertEqual(len(content_hash), 64)  # SHA256 длина
            # Должен быть hex
            self.assertTrue(all(c in '0123456789abcdef' for c in content_hash))
        finally:
            os.unlink(tmp_path)


class TestMetadataFunctions(TestCase):

    def test_extract_filename_metadata_basic(self):
        """Тестируем извлечение метаданных из простого имени"""
        metadata = extract_filename_metadata("my_video.mp4")

        self.assertEqual(metadata["title"], "My Video")
        self.assertIsNone(metadata["width"])
        self.assertIsNone(metadata["height"])
        self.assertIsNone(metadata["fps"])

    def test_extract_filename_metadata_with_resolution(self):
        """Тестируем извлечение метаданных с разрешением"""
        metadata = extract_filename_metadata("video_1920x1080.mp4")

        self.assertEqual(metadata["title"], "Video")
        self.assertEqual(metadata["width"], 1920)
        self.assertEqual(metadata["height"], 1080)

    def test_extract_filename_metadata_with_fps(self):
        """Тестируем извлечение метаданных с FPS"""
        metadata = extract_filename_metadata("video_30fps.mp4")

        self.assertEqual(metadata["title"], "Video")
        self.assertEqual(metadata["fps"], 30)

    def test_extract_filename_metadata_complex(self):
        """Тестируем извлечение метаданных из сложного имени"""
        metadata = extract_filename_metadata("my_movie_1280x720_24fps_final.mp4")

        self.assertEqual(metadata["title"], "My Movie Final")
        self.assertEqual(metadata["width"], 1280)
        self.assertEqual(metadata["height"], 720)
        self.assertEqual(metadata["fps"], 24)

    def test_combine_video_metadata(self):
        """Тестируем объединение метаданных"""
        meta1 = {"title": "Video", "width": 1920}
        meta2 = {"height": 1080, "fps": 30}
        meta3 = {"title": "Overridden", "duration": 120}

        combined = combine_video_metadata(meta1, meta2, meta3)

        # Проверяем, что последний аргумент имеет приоритет
        self.assertEqual(combined["title"], "Overridden")
        self.assertEqual(combined["width"], 1920)
        self.assertEqual(combined["height"], 1080)
        self.assertEqual(combined["fps"], 30)
        self.assertEqual(combined["duration"], 120)

    def test_sanitize_metadata_valid(self):
        """Тестируем очистку валидных метаданных"""
        input_meta = {
            "width": 1920,
            "height": 1080,
            "duration": 120.5,
            "fps": 30,
            "title": "My Video",
            "codec": "h264"
        }

        sanitized = sanitize_metadata(input_meta)

        self.assertEqual(sanitized["width"], 1920)
        self.assertEqual(sanitized["height"], 1080)
        self.assertEqual(sanitized["duration"], 120.5)
        self.assertEqual(sanitized["fps"], 30)
        self.assertEqual(sanitized["title"], "My Video")
        self.assertEqual(sanitized["codec"], "h264")

    def test_sanitize_metadata_invalid(self):
        """Тестируем очистку невалидных метаданных"""
        input_meta = {
            "width": -100,  # Отрицательное
            "height": 1000000,  # Слишком большое
            "title": "<script>alert('xss')</script>",  # Опасные символы
            "unknown": "value"  # Неизвестное поле
        }

        sanitized = sanitize_metadata(input_meta)

        self.assertNotIn("width", sanitized)  # Отрицательное значение отфильтровано
        self.assertNotIn("height", sanitized)  # Слишком большое значение отфильтровано
        self.assertNotIn("unknown", sanitized)  # Неизвестное поле отфильтровано
        # Опасные символы должны быть удалены
        if "title" in sanitized:
            self.assertNotIn("<", sanitized["title"])
            self.assertNotIn(">", sanitized["title"])


class TestFormattingFunctions(TestCase):

    def test_format_duration_seconds(self):
        """Тестируем форматирование секунд"""
        self.assertEqual(format_duration(0), "0:00")
        self.assertEqual(format_duration(59), "0:59")
        self.assertEqual(format_duration(65), "1:05")

    def test_format_duration_minutes(self):
        """Тестируем форматирование минут"""
        self.assertEqual(format_duration(125), "2:05")
        self.assertEqual(format_duration(3599), "59:59")  # 59 минут 59 секунд

    def test_format_duration_hours(self):
        """Тестируем форматирование часов"""
        self.assertEqual(format_duration(3600), "1:00:00")
        self.assertEqual(format_duration(3661), "1:01:01")  # 1 час 1 минута 1 секунда
        self.assertEqual(format_duration(45296), "12:34:56")  # 12 часов 34 минуты 56 секунд

    def test_format_duration_invalid(self):
        """Тестируем форматирование невалидной длительности"""
        self.assertEqual(format_duration(-10), "0:00")
        self.assertEqual(format_duration("invalid"), "0:00")
        self.assertEqual(format_duration(None), "0:00")

    def test_format_file_size_bytes(self):
        """Тестируем форматирование байтов"""
        self.assertEqual(format_file_size(0), "0 B")
        self.assertEqual(format_file_size(500), "500 B")
        self.assertEqual(format_file_size(1023), "1023 B")

    def test_format_file_size_kilobytes(self):
        """Тестируем форматирование килобайтов"""
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1536), "1.5 KB")  # 1.5 KB
        self.assertEqual(format_file_size(1048575), "1024.0 KB")  # Почти 1 MB

    def test_format_file_size_megabytes(self):
        """Тестируем форматирование мегабайтов"""
        self.assertEqual(format_file_size(1048576), "1.0 MB")  # 1 MB
        self.assertEqual(format_file_size(1572864), "1.5 MB")  # 1.5 MB
        self.assertEqual(format_file_size(1073741823), "1024.0 MB")  # Почти 1 GB

    def test_format_bitrate_bps(self):
        """Тестируем форматирование битрейта"""
        self.assertEqual(format_bitrate(0), "0 bps")
        self.assertEqual(format_bitrate(999), "999 bps")
        self.assertEqual(format_bitrate(1000), "1.0 Kbps")
        self.assertEqual(format_bitrate(2500), "2.5 Kbps")

    def test_format_bitrate_mbps(self):
        """Тестируем форматирование Mbps"""
        self.assertEqual(format_bitrate(1000000), "1.0 Mbps")
        self.assertEqual(format_bitrate(2500000), "2.5 Mbps")

    def test_format_video_info_complete(self):
        """Тестируем форматирование полной информации о видео"""
        metadata = {
            "width": 1920,
            "height": 1080,
            "duration": 3661,  # 1:01:01
            "bitrate": 2500000,  # 2.5 Mbps
            "fps": 30
        }

        result = format_video_info(metadata)

        self.assertIn("1920×1080", result)
        self.assertIn("1:01:01", result)
        self.assertIn("2.5 Mbps", result)
        self.assertIn("30 fps", result)

    def test_format_video_info_partial(self):
        """Тестируем форматирование частичной информации"""
        metadata = {"width": 1280, "height": 720}
        result = format_video_info(metadata)
        self.assertEqual(result, "1280×720")

        metadata = {"duration": 125}
        result = format_video_info(metadata)
        self.assertEqual(result, "2:05")

        metadata = {}
        result = format_video_info(metadata)
        self.assertEqual(result, "No info")


class TestFileAndStorageFunctions(TestCase):

    def test_ensure_directory_exists_local(self):
        """Тестируем создание локальной директории"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "test_subdir"

            # Используем default_storage для локального теста
            result = ensure_directory_exists(test_path, default_storage)
            self.assertTrue(result)
            self.assertTrue(test_path.exists())

    @patch('hlsfield.helpers.default_storage')
    def test_ensure_directory_exists_cloud(self, mock_storage):
        """Тестируем создание директории в облачном storage"""
        mock_storage.exists.return_value = False
        mock_storage.path.side_effect = NotImplementedError  # Эмулируем облачное хранилище
        mock_storage.save.return_value = "saved_path"

        result = ensure_directory_exists("cloud/path", mock_storage)
        self.assertTrue(result)
        # Проверяем, что save был вызван
        self.assertTrue(mock_storage.save.called)

    def test_clean_filename_basic(self):
        """Тестируем очистку простого имени файла"""
        result = clean_filename("my_video.mp4")
        self.assertEqual(result, "my_video.mp4")

    def test_clean_filename_special_chars(self):
        """Тестируем очистку имени с специальными символами"""
        result = clean_filename("My Video!@#$%^&().mp4")
        # Должно удалить небезопасные символы и заменить пробелы на подчеркивания
        self.assertTrue(result.endswith(".mp4"))
        self.assertNotIn("!", result)
        self.assertNotIn("@", result)
        self.assertNotIn(" ", result)

    def test_clean_filename_long_name(self):
        """Тестируем очистку длинного имени файла"""
        long_name = "a" * 200 + ".mp4"
        result = clean_filename(long_name)

        # Должно быть обрезано до max_length (по умолчанию 100)
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith(".mp4"))

    def test_clean_filename_empty_stem(self):
        """Тестируем очистку имени с пустым stem"""
        result = clean_filename("!@#$%^.mp4")
        self.assertTrue(result.startswith("file_"))
        self.assertTrue(result.endswith(".mp4"))

    def test_get_file_extension_info_mp4(self):
        """Тестируем информацию о MP4 файле"""
        info = get_file_extension_info("video.mp4")

        self.assertEqual(info["type"], "video/mp4")
        self.assertEqual(info["container"], "MP4")
        self.assertTrue(info["streaming_friendly"])
        self.assertEqual(info["extension"], ".mp4")

    def test_get_file_extension_info_webm(self):
        """Тестируем информацию о WebM файле"""
        info = get_file_extension_info("video.webm")

        self.assertEqual(info["type"], "video/webm")
        self.assertEqual(info["container"], "WebM")
        self.assertTrue(info["streaming_friendly"])

    def test_get_file_extension_info_unknown(self):
        """Тестируем информацию о неизвестном расширении"""
        info = get_file_extension_info("video.xyz")

        self.assertEqual(info["type"], "video/unknown")
        self.assertEqual(info["container"], "Unknown")
        self.assertFalse(info["streaming_friendly"])


class TestDjangoIntegrationFunctions(TestCase):

    def test_get_model_video_fields(self):
        """Тестируем получение video полей модели"""
        from django.db import models
        from hlsfield.fields import VideoField, HLSVideoField

        class TestModel1(models.Model):
            title = models.CharField(max_length=100)
            video = VideoField(upload_to="videos/")
            hls_video = HLSVideoField(upload_to="hls/")
            description = models.TextField()

            class Meta:
                app_label = 'tests'

        video_fields = get_model_video_fields(TestModel1)

        self.assertEqual(len(video_fields), 2)
        self.assertIn("video", video_fields)
        self.assertIn("hls_video", video_fields)
        self.assertNotIn("title", video_fields)
        self.assertNotIn("description", video_fields)

    def test_get_video_field_metadata(self):
        """Тестируем получение метаданных video поля"""
        from django.db import models

        class TestModel2(models.Model):
            video = models.FileField(upload_to="videos/")

            class Meta:
                app_label = 'tests'

        instance = TestModel2()
        instance.video = Mock()
        instance.video.name = "videos/test.mp4"
        instance.video.url = "/media/videos/test.mp4"

        # Мокируем методы, которые могут быть у video файлов
        instance.video.metadata = Mock(return_value={"duration": 120, "width": 1920})
        instance.video.master_url = Mock(return_value="/media/hls/master.m3u8")
        instance.video.preview_url = Mock(return_value="/media/previews/test.jpg")

        metadata = get_video_field_metadata(instance, "video")

        self.assertEqual(metadata["filename"], "test.mp4")
        self.assertEqual(metadata["path"], "videos/test.mp4")
        self.assertEqual(metadata["url"], "/media/videos/test.mp4")
        self.assertEqual(metadata["duration"], 120)
        self.assertEqual(metadata["width"], 1920)
        self.assertEqual(metadata["hls_url"], "/media/hls/master.m3u8")
        self.assertEqual(metadata["preview_url"], "/media/previews/test.jpg")

    def test_get_video_field_metadata_empty(self):
        """Тестируем получение метаданных для пустого поля"""
        from django.db import models

        class TestModel3(models.Model):
            video = models.FileField(upload_to="videos/", blank=True, null=True)

            class Meta:
                app_label = 'tests'

        instance = TestModel3()
        instance.video = None

        metadata = get_video_field_metadata(instance, "video")

        self.assertEqual(metadata, {})


# Тесты для edge cases
class TestEdgeCases(TestCase):

    def test_upload_to_very_long_filename(self):
        """Тестируем обработку очень длинных имен файлов"""
        long_filename = "a" * 300 + ".mp4"
        result = video_upload_to(None, long_filename)

        # Должно быть обрезано, но оставаться валидным
        self.assertTrue(result.startswith("videos/"))
        self.assertTrue(result.endswith(".mp4"))
        self.assertLess(len(result), 200)  # Должно быть разумной длины

    def test_generate_content_hash_large_file(self):
        """Тестируем хэширование большого файла"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # Создаем файл с повторяющимся содержимым
            content = b"test" * 10000  # 40KB
            tmp.write(content)
            tmp_path = tmp.name

        try:
            hash1 = generate_content_hash(tmp_path)
            hash2 = generate_content_hash(tmp_path)

            self.assertEqual(hash1, hash2)  # Хэши должны быть одинаковыми
            self.assertEqual(len(hash1), 64)  # SHA256 длина
        finally:
            os.unlink(tmp_path)

    def test_sanitize_metadata_extreme_values(self):
        """Тестируем очистку экстремальных значений"""
        extreme_meta = {
            "width": 9999999,  # Слишком большое
            "height": -100,  # Отрицательное
            "duration": 1e10,  # Очень большое
            "title": "x" * 1000,  # Очень длинное
            "malicious": "<script>",  # Опасное
        }

        sanitized = sanitize_metadata(extreme_meta)

        # Все экстремальные значения должны быть отфильтрованы
        self.assertNotIn("width", sanitized)
        self.assertNotIn("height", sanitized)
        self.assertNotIn("duration", sanitized)
        self.assertNotIn("malicious", sanitized)

        # Title должен быть обрезан и очищен
        if "title" in sanitized:
            self.assertLessEqual(len(sanitized["title"]), 100)

    def test_format_edge_cases(self):
        """Тестируем форматирование edge cases"""
        # Очень большие значения
        self.assertEqual(format_file_size(10 ** 15), "909.5 TB")
        self.assertEqual(format_bitrate(10 ** 12), "1000000.0 Mbps")

        # Float значения
        self.assertEqual(format_duration(3661.5), "1:01:01")  # Должно округлить

        # Нулевые значения
        self.assertEqual(format_file_size(0), "0 B")
        self.assertEqual(format_bitrate(0), "0 bps")
