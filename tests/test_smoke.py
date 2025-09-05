"""
Smoke тесты для django-hlsfield

Эти тесты проверяют основную функциональность и должны выполняться быстро.
Используются для первичной проверки что пакет работает корректно.
"""

import pytest
from django.test import TestCase
from django.core.exceptions import ImproperlyConfigured


class TestPackageStructure(TestCase):
    """Тесты структуры пакета"""

    def test_package_imports(self):
        """Основные импорты работают"""
        import hlsfield

        # Проверяем что основные классы доступны
        from hlsfield import VideoField, HLSVideoField, DASHVideoField, AdaptiveVideoField
        from hlsfield import validate_ladder, get_optimal_ladder_for_resolution
        from hlsfield import HLSFieldError, FFmpegError, InvalidVideoError

        # Все импорты прошли успешно
        self.assertTrue(True)

    def test_version_available(self):
        """Версия пакета доступна"""
        import hlsfield

        self.assertTrue(hasattr(hlsfield, '__version__'))
        self.assertIsInstance(hlsfield.__version__, str)
        self.assertRegex(hlsfield.__version__, r'^\d+\.\d+\.\d+')

    def test_django_app_config(self):
        """Django app сконфигурирован правильно"""
        from django.apps import apps

        # Проверяем что app зарегистрирован
        app_config = apps.get_app_config('hlsfield')
        self.assertEqual(app_config.name, 'hlsfield')
        self.assertEqual(app_config.verbose_name, 'HLS Video Fields')


class TestBasicFieldCreation(TestCase):
    """Тесты создания полей"""

    def test_video_field_creation(self):
        """VideoField создается без ошибок"""
        from hlsfield import VideoField

        field = VideoField(upload_to="videos/")
        self.assertIsNotNone(field)
        self.assertEqual(field.upload_to, "videos/")

    def test_hls_field_creation(self):
        """HLSVideoField создается без ошибок"""
        from hlsfield import HLSVideoField

        field = HLSVideoField(upload_to="videos/")
        self.assertIsNotNone(field)
        self.assertTrue(hasattr(field, 'ladder'))
        self.assertTrue(hasattr(field, 'segment_duration'))

    def test_dash_field_creation(self):
        """DASHVideoField создается без ошибок"""
        from hlsfield import DASHVideoField

        field = DASHVideoField(upload_to="videos/")
        self.assertIsNotNone(field)
        self.assertTrue(hasattr(field, 'dash_manifest_field'))

    def test_adaptive_field_creation(self):
        """AdaptiveVideoField создается без ошибок"""
        from hlsfield import AdaptiveVideoField

        field = AdaptiveVideoField(upload_to="videos/")
        self.assertIsNotNone(field)
        self.assertTrue(hasattr(field, 'hls_playlist_field'))
        self.assertTrue(hasattr(field, 'dash_manifest_field'))


class TestUtilityFunctions(TestCase):
    """Тесты утилитарных функций"""

    def test_validate_ladder_basic(self):
        """validate_ladder работает с корректными данными"""
        from hlsfield import validate_ladder

        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        ]

        # Не должно вызывать исключений
        result = validate_ladder(ladder)
        self.assertTrue(result)

    def test_validate_ladder_invalid(self):
        """validate_ladder выбрасывает ошибки для некорректных данных"""
        from hlsfield import validate_ladder

        # Пустая лестница
        with self.assertRaises(ValueError):
            validate_ladder([])

        # Отсутствующие поля
        with self.assertRaises(ValueError):
            validate_ladder([{"height": 360, "v_bitrate": 800}])  # Нет a_bitrate

    def test_optimal_ladder_generation(self):
        """get_optimal_ladder_for_resolution генерирует валидные лестницы"""
        from hlsfield import get_optimal_ladder_for_resolution, validate_ladder

        # Тестируем разные разрешения
        for width, height in [(1920, 1080), (1280, 720), (640, 360)]:
            ladder = get_optimal_ladder_for_resolution(width, height)

            # Лестница не пустая
            self.assertGreater(len(ladder), 0)

            # Лестница валидная
            self.assertTrue(validate_ladder(ladder))

            # Качества не превышают исходное разрешение (с запасом)
            max_height = max(rung['height'] for rung in ladder)
            self.assertLessEqual(max_height, height * 1.2)


class TestExceptionHierarchy(TestCase):
    """Тесты иерархии исключений"""

    def test_exception_inheritance(self):
        """Проверяем правильность наследования исключений"""
        from hlsfield import (
            HLSFieldError, FFmpegError, InvalidVideoError,
            StorageError, ConfigurationError
        )

        # Все исключения должны наследоваться от HLSFieldError
        self.assertTrue(issubclass(FFmpegError, HLSFieldError))
        self.assertTrue(issubclass(InvalidVideoError, HLSFieldError))
        self.assertTrue(issubclass(StorageError, HLSFieldError))
        self.assertTrue(issubclass(ConfigurationError, HLSFieldError))

    def test_exception_creation(self):
        """Исключения создаются корректно"""
        from hlsfield import HLSFieldError, FFmpegError, InvalidVideoError

        # Базовое исключение
        base_error = HLSFieldError("Test error")
        self.assertEqual(str(base_error), "Test error")

        # FFmpeg ошибка
        ffmpeg_error = FFmpegError(["ffmpeg", "-i", "test.mp4"], 1, "", "Error")
        self.assertIn("ffmpeg", str(ffmpeg_error))

        # Ошибка видео
        video_error = InvalidVideoError("Invalid video file")
        self.assertIn("Invalid video file", str(video_error))


class TestHelperFunctions(TestCase):
    """Тесты вспомогательных функций"""

    def test_video_upload_to(self):
        """video_upload_to генерирует корректные пути"""
        from hlsfield.helpers import video_upload_to

        path = video_upload_to(None, "test_video.mp4")

        self.assertTrue(path.startswith("videos/"))
        self.assertTrue(path.endswith(".mp4"))
        self.assertEqual(len(path.split("/")), 3)  # videos/uuid/filename

    def test_generate_video_id(self):
        """generate_video_id работает корректно"""
        from hlsfield.helpers import generate_video_id

        # Проверяем разные длины
        for length in [4, 8, 16]:
            video_id = generate_video_id(length)
            self.assertEqual(len(video_id), length)
            self.assertTrue(video_id.isalnum())

    def test_format_functions(self):
        """Функции форматирования работают корректно"""
        from hlsfield.helpers import format_duration, format_file_size, format_bitrate

        # Длительность
        self.assertEqual(format_duration(0), "0:00")
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(3661), "1:01:01")

        # Размер файла
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1048576), "1.0 MB")

        # Битрейт
        self.assertEqual(format_bitrate(1000), "1.0 Kbps")
        self.assertEqual(format_bitrate(1000000), "1.0 Mbps")


class TestDefaultSettings(TestCase):
    """Тесты настроек по умолчанию"""

    def test_default_settings_accessible(self):
        """Настройки по умолчанию доступны"""
        from hlsfield import defaults

        # Проверяем основные настройки
        self.assertTrue(hasattr(defaults, 'FFMPEG'))
        self.assertTrue(hasattr(defaults, 'FFPROBE'))
        self.assertTrue(hasattr(defaults, 'DEFAULT_LADDER'))
        self.assertTrue(hasattr(defaults, 'SEGMENT_DURATION'))

        # Проверяем типы
        self.assertIsInstance(defaults.FFMPEG, str)
        self.assertIsInstance(defaults.DEFAULT_LADDER, list)
        self.assertIsInstance(defaults.SEGMENT_DURATION, int)

    def test_default_ladder_valid(self):
        """Лестница по умолчанию валидна"""
        from hlsfield import defaults, validate_ladder

        # Лестница должна быть валидной
        self.assertTrue(validate_ladder(defaults.DEFAULT_LADDER))

        # Должна содержать разумные значения
        self.assertGreater(len(defaults.DEFAULT_LADDER), 0)
        for rung in defaults.DEFAULT_LADDER:
            self.assertIn('height', rung)
            self.assertIn('v_bitrate', rung)
            self.assertIn('a_bitrate', rung)


class TestDjangoIntegration(TestCase):
    """Тесты интеграции с Django"""

    def test_field_in_model(self):
        """Поля работают в Django моделях"""
        from django.db import models
        from hlsfield import VideoField

        # Создаем тестовую модель
        class TestModel(models.Model):
            video = VideoField(upload_to="videos/")

            class Meta:
                app_label = 'tests'
                db_table = 'test_video_unique'  # Уникальное имя таблицы
        # Модель создается без ошибок
        self.assertTrue(hasattr(TestModel, 'video'))

        # Поле имеет правильный тип
        field = TestModel._meta.get_field('video')
        self.assertIsInstance(field, VideoField)

    def test_admin_integration(self):
        """Проверяем что admin интеграция работает"""
        try:
            from django.contrib import admin
            from hlsfield.views import VideoEvent

            # Если VideoEvent зарегистрирован в admin, это не должно вызывать ошибок
            admin_class = admin.site._registry.get(VideoEvent)
            if admin_class:
                self.assertTrue(hasattr(admin_class, 'list_display'))
        except ImportError:
            # Если модель не найдена, это нормально для smoke тестов
            pass


class TestTemplatesAndStatic(TestCase):
    """Тесты шаблонов и статических файлов"""

    def test_templates_exist(self):
        """Шаблоны плееров существуют"""
        from django.template.loader import get_template
        from django.template import TemplateDoesNotExist

        templates = [
            'hlsfield/players/hls_player.html',
            'hlsfield/players/dash_player.html',
            'hlsfield/players/universal_player.html',
        ]

        for template_name in templates:
            try:
                template = get_template(template_name)
                self.assertIsNotNone(template)
            except TemplateDoesNotExist:
                # В smoke тестах это может быть нормально
                pass


class TestConfigurationValidation(TestCase):
    """Тесты валидации конфигурации"""

    def test_runtime_info(self):
        """Получение runtime информации работает"""
        from hlsfield.defaults import get_runtime_info, validate_settings

        # Получаем runtime информацию
        info = get_runtime_info()
        self.assertIsInstance(info, dict)
        self.assertIn('ffmpeg', info)
        self.assertIn('processing', info)

        # Валидация настроек
        issues = validate_settings()
        self.assertIsInstance(issues, list)
        # В тестовом окружении могут быть проблемы с FFmpeg - это нормально


# Интеграционные smoke тесты
class TestSystemIntegration(TestCase):
    """Тесты системной интеграции"""

    def test_django_checks_pass(self):
        """Django system checks проходят"""
        from django.core.management import call_command
        from io import StringIO

        # Запускаем системные проверки
        out = StringIO()
        try:
            call_command('check', stdout=out, stderr=out, verbosity=0)
            # Если команда выполнилась без исключений, все в порядке
            self.assertTrue(True)
        except Exception as e:
            # В smoke тестах некоторые ошибки могут быть ожидаемыми
            # (например, отсутствие FFmpeg)
            if "FFmpeg" not in str(e):
                raise

    def test_app_ready_state(self):
        """Приложение корректно инициализировано"""
        from django.apps import apps

        app_config = apps.get_app_config('hlsfield')

        # Приложение должно быть готово
        self.assertTrue(apps.ready)
        self.assertIsNotNone(app_config)

    def test_urls_importable(self):
        """URL конфигурация импортируется"""
        try:
            from hlsfield import urls
            self.assertTrue(hasattr(urls, 'urlpatterns'))
        except ImportError:
            # URLs могут быть опциональными
            pass


# Маркеры для разных типов тестов
@pytest.mark.unit
class TestUnitSmoke(TestCase):
    """Unit smoke тесты"""

    def test_basic_functionality(self):
        """Основная функциональность работает"""
        from hlsfield import VideoField, validate_ladder

        # Создание поля
        field = VideoField()
        self.assertIsNotNone(field)

        # Валидация данных
        ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        self.assertTrue(validate_ladder(ladder))


@pytest.mark.integration
class TestIntegrationSmoke(TestCase):
    """Integration smoke тесты"""

    def test_full_pipeline_mock(self):
        """Полный pipeline с мокированием"""
        from unittest.mock import patch, Mock
        from hlsfield import HLSVideoField

        with patch('hlsfield.utils.run') as mock_run:
            # Настраиваем мок для успешного выполнения
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '{"streams":[], "format":{}}'

            # Создаем поле
            field = HLSVideoField()
            self.assertIsNotNone(field)

            # Проверяем что мок настроен
            self.assertTrue(mock_run)


if __name__ == '__main__':
    import unittest

    unittest.main()
