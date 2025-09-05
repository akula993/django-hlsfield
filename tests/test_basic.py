import pytest
from django.test import TestCase

from hlsfield import VideoField, HLSVideoField


class TestBasicImports(TestCase):
    """Тесты базового импорта и функциональности"""

    def test_imports(self):
        """Тест базового импорта"""
        from hlsfield import VideoField, HLSVideoField
        assert VideoField is not None
        assert HLSVideoField is not None

    def test_version(self):
        """Тест версии"""
        import hlsfield
        assert hasattr(hlsfield, '__version__')
        assert isinstance(hlsfield.__version__, str)
        assert len(hlsfield.__version__) > 0

    def test_all_exports(self):
        """Тест что все основные экспорты доступны"""
        import hlsfield

        # Основные поля
        assert hasattr(hlsfield, 'VideoField')
        assert hasattr(hlsfield, 'HLSVideoField')
        assert hasattr(hlsfield, 'DASHVideoField')
        assert hasattr(hlsfield, 'AdaptiveVideoField')

        # Утилиты
        assert hasattr(hlsfield, 'validate_ladder')
        assert hasattr(hlsfield, 'get_optimal_ladder_for_resolution')

        # Исключения
        assert hasattr(hlsfield, 'HLSFieldError')
        assert hasattr(hlsfield, 'FFmpegError')


class TestVideoFieldBasics(TestCase):
    """Базовые тесты полей"""

    def test_field_creation(self):
        """Тест создания базового VideoField"""
        from hlsfield import VideoField
        field = VideoField(upload_to="videos/")
        assert field is not None
        assert hasattr(field, 'upload_to')

    def test_hls_field_creation(self):
        """Тест создания HLSVideoField"""
        from hlsfield import HLSVideoField
        field = HLSVideoField(upload_to="videos/")
        assert field is not None
        assert hasattr(field, 'ladder')
        assert hasattr(field, 'segment_duration')

    def test_field_inheritance(self):
        """Тест наследования полей"""
        from hlsfield import VideoField, HLSVideoField
        from django.db import models

        # VideoField наследуется от FileField
        assert issubclass(VideoField, models.FileField)

        # HLSVideoField наследуется от VideoField
        assert issubclass(HLSVideoField, VideoField)
