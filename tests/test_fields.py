import pytest
from django.test import TestCase
from django.db import models
from django.core.files.base import ContentFile
from pathlib import Path
import tempfile

from hlsfield import (
    VideoField,
    HLSVideoField,
    DASHVideoField,
    AdaptiveVideoField,
    validate_ladder,
    get_optimal_ladder_for_resolution
)


class TestVideoModel(models.Model):
    """Тестовая модель для проверки полей"""
    title = models.CharField(max_length=100)
    video = VideoField(upload_to="test_videos/")
    duration = models.DurationField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_video_model'


class TestHLSModel(models.Model):
    """Тестовая модель для HLS поля"""
    video = HLSVideoField(
        upload_to="test_hls/",
        hls_playlist_field="hls_master"
    )
    hls_master = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_hls_model'


class TestVideoFieldBasics(TestCase):
    """Базовые тесты VideoField"""

    def test_field_creation(self):
        """Тест создания поля"""
        field = VideoField()
        assert field is not None
        assert field.attr_class.__name__ == 'VideoFieldFile'

    def test_field_with_metadata_fields(self):
        """Тест поля с метаданными"""
        field = VideoField(
            duration_field="duration",
            width_field="width",
            height_field="height"
        )
        assert field.duration_field == "duration"
        assert field.width_field == "width"
        assert field.height_field == "height"

    def test_default_upload_to(self):
        """Тест автоматического upload_to"""
        field = VideoField()
        # Должен использовать default upload_to если не указан
        assert field.upload_to is not None


class TestHLSVideoField(TestCase):
    """Тесты HLSVideoField"""

    def test_field_creation(self):
        """Тест создания HLS поля"""
        field = HLSVideoField()
        assert field is not None
        assert hasattr(field, 'ladder')
        assert hasattr(field, 'segment_duration')

    def test_field_with_custom_ladder(self):
        """Тест с кастомной лестницей качеств"""
        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128}
        ]
        field = HLSVideoField(ladder=ladder)
        assert field.ladder == ladder

    def test_segment_duration(self):
        """Тест настройки длительности сегментов"""
        field = HLSVideoField(segment_duration=10)
        assert field.segment_duration == 10


class TestDASHVideoField(TestCase):
    """Тесты DASHVideoField"""

    def test_field_creation(self):
        """Тест создания DASH поля"""
        field = DASHVideoField()
        assert field is not None
        assert hasattr(field, 'dash_manifest_field')

    def test_dash_specific_settings(self):
        """Тест DASH-специфичных настроек"""
        field = DASHVideoField(
            dash_manifest_field="manifest",
            segment_duration=4
        )
        assert field.dash_manifest_field == "manifest"
        assert field.segment_duration == 4


class TestAdaptiveVideoField(TestCase):
    """Тесты AdaptiveVideoField"""

    def test_field_creation(self):
        """Тест создания адаптивного поля"""
        field = AdaptiveVideoField()
        assert field is not None
        assert hasattr(field, 'hls_playlist_field')
        assert hasattr(field, 'dash_manifest_field')

    def test_combined_fields(self):
        """Тест комбинированных полей"""
        field = AdaptiveVideoField(
            hls_playlist_field="hls",
            dash_manifest_field="dash"
        )
        assert field.hls_playlist_field == "hls"
        assert field.dash_manifest_field == "dash"


class TestLadderValidation(TestCase):
    """Тесты валидации лестницы качеств"""

    def test_valid_ladder(self):
        """Тест валидной лестницы"""
        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160}
        ]
        assert validate_ladder(ladder) is True

    def test_invalid_ladder_missing_fields(self):
        """Тест невалидной лестницы - отсутствуют поля"""
        ladder = [
            {"height": 360, "v_bitrate": 800}  # Нет a_bitrate
        ]
        with pytest.raises(ValueError) as exc:
            validate_ladder(ladder)
        assert "missing required field" in str(exc.value)

    def test_invalid_ladder_negative_values(self):
        """Тест невалидной лестницы - отрицательные значения"""
        ladder = [
            {"height": 360, "v_bitrate": -800, "a_bitrate": 96}
        ]
        with pytest.raises(ValueError):
            validate_ladder(ladder)

    def test_empty_ladder(self):
        """Тест пустой лестницы"""
        with pytest.raises(ValueError) as exc:
            validate_ladder([])
        assert "non-empty list" in str(exc.value)


class TestOptimalLadder(TestCase):
    """Тесты генерации оптимальной лестницы"""

    def test_optimal_ladder_for_hd(self):
        """Тест для HD видео"""
        ladder = get_optimal_ladder_for_resolution(1920, 1080)
        assert len(ladder) > 0
        # Не должно быть качеств выше исходного
        assert all(rung['height'] <= 1080 * 1.1 for rung in ladder)

    def test_optimal_ladder_for_4k(self):
        """Тест для 4K видео"""
        ladder = get_optimal_ladder_for_resolution(3840, 2160)
        assert len(ladder) > 0
        # Должны быть высокие качества
        assert any(rung['height'] >= 1080 for rung in ladder)

    def test_optimal_ladder_for_low_res(self):
        """Тест для низкого разрешения"""
        ladder = get_optimal_ladder_for_resolution(640, 360)
        assert len(ladder) > 0
        # Не должно быть качеств намного выше исходного
        assert all(rung['height'] <= 360 * 1.5 for rung in ladder)


class TestFieldDeconstruct(TestCase):
    """Тесты декомпозиции полей для миграций"""

    def test_video_field_deconstruct(self):
        """Тест декомпозиции VideoField"""
        field = VideoField(
            duration_field="duration",
            preview_at=5.0
        )
        name, path, args, kwargs = field.deconstruct()
        assert kwargs['duration_field'] == "duration"
        assert kwargs['preview_at'] == 5.0

    def test_hls_field_deconstruct(self):
        """Тест декомпозиции HLSVideoField"""
        ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        field = HLSVideoField(
            ladder=ladder,
            segment_duration=8
        )
        name, path, args, kwargs = field.deconstruct()
        assert kwargs['ladder'] == ladder
        assert kwargs['segment_duration'] == 8


class TestFieldFileObjects(TestCase):
    """Тесты файловых объектов полей"""

    def setUp(self):
        """Подготовка для тестов"""
        self.temp_dir = tempfile.mkdtemp()

    def test_video_field_file_metadata(self):
        """Тест методов VideoFieldFile"""
        model = TestVideoModel(title="Test")
        field_file = model.video

        # Проверяем наличие методов
        assert hasattr(field_file, 'metadata')
        assert hasattr(field_file, 'preview_url')
        assert callable(field_file.metadata)
        assert callable(field_file.preview_url)

    def test_hls_field_file_methods(self):
        """Тест методов HLSVideoFieldFile"""
        model = TestHLSModel()
        field_file = model.video

        # Проверяем наличие HLS-специфичных методов
        assert hasattr(field_file, 'master_url')
        assert callable(field_file.master_url)


# Интеграционные тесты (пропускаются если нет FFmpeg)
import shutil


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason="FFmpeg not available")
class TestFFmpegIntegration(TestCase):
    """Интеграционные тесты с FFmpeg"""

    def test_ffmpeg_available(self):
        """Проверка доступности FFmpeg"""
        from hlsfield.utils import ensure_binary_available
        try:
            ffmpeg_path = ensure_binary_available('ffmpeg', 'ffmpeg')
            assert ffmpeg_path is not None
        except Exception:
            pytest.skip("FFmpeg not found")
