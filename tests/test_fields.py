"""
Тесты для Django полей django-hlsfield
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from django.core.files.base import ContentFile
from django.db import models

from hlsfield.fields import (
    VideoField, VideoFieldFile,
    HLSVideoField, HLSVideoFieldFile,
    DASHVideoField, DASHVideoFieldFile,
    AdaptiveVideoField, AdaptiveVideoFieldFile,
    validate_ladder, get_optimal_ladder_for_resolution
)
from hlsfield.exceptions import InvalidVideoError, ConfigurationError


class TestVideoField:
    """Тесты базового VideoField"""

    def test_field_creation(self):
        """Тест создания поля"""
        field = VideoField(upload_to='videos/')
        assert field.upload_to == 'videos/'
        assert field.duration_field is None
        assert field.process_on_save is True

    def test_field_with_metadata_fields(self):
        """Тест поля с полями метаданных"""
        field = VideoField(
            upload_to='videos/',
            duration_field='duration',
            width_field='width',
            height_field='height',
            preview_field='preview'
        )
        assert field.duration_field == 'duration'
        assert field.width_field == 'width'
        assert field.height_field == 'height'
        assert field.preview_field == 'preview'

    def test_field_deconstruct(self):
        """Тест деконструкции поля для миграций"""
        field = VideoField(
            upload_to='videos/',
            duration_field='duration',
            preview_at=5.0
        )
        name, path, args, kwargs = field.deconstruct()

        assert path == 'hlsfield.fields.VideoField'
        assert 'duration_field' in kwargs
        assert kwargs['preview_at'] == 5.0

    @patch('hlsfield.defaults.USE_DEFAULT_UPLOAD_TO', True)
    def test_auto_upload_to(self):
        """Тест автоматического upload_to"""
        field = VideoField()  # Без указания upload_to
        assert field.upload_to is not None

    def test_contribute_to_class(self, test_model):
        """Тест интеграции поля в модель"""
        field = VideoField(upload_to='test/')
        field.contribute_to_class(test_model, 'test_video')

        assert hasattr(test_model, 'test_video')


class TestVideoFieldFile:
    """Тесты VideoFieldFile"""

    def test_metadata_from_model_fields(self):
        """Тест получения метаданных из полей модели"""
        # Создаем мок модели
        mock_instance = Mock()
        mock_instance.duration = 120  # секунды
        mock_instance.width = 1920
        mock_instance.height = 1080

        # Создаем поле с настройками
        field = VideoField(
            duration_field='duration',
            width_field='width',
            height_field='height'
        )

        # Создаем файловый объект
        file_obj = VideoFieldFile(mock_instance, field, 'test.mp4')

        # Тестируем получение метаданных
        metadata = file_obj.metadata()

        assert 'width' in metadata
        assert metadata['width'] == 1920
        assert 'height' in metadata
        assert metadata['height'] == 1080

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.pull_to_local')
    def test_process_video_metadata(self, mock_pull, mock_ffprobe, temp_dir):
        """Тест обработки метаданных видео"""
        # Настраиваем моки
        mock_pull.return_value = temp_dir / 'test.mp4'
        mock_ffprobe.return_value = {
            'streams': [{
                'codec_type': 'video',
                'width': 1920,
                'height': 1080,
            }],
            'format': {
                'duration': '120.0'
            }
        }

        # Создаем тестовый файл
        (temp_dir / 'test.mp4').write_bytes(b'video data')

        mock_instance = Mock()
        mock_storage = Mock()
        mock_storage.save.return_value = 'saved_path.mp4'

        field = VideoField(
            duration_field='duration',
            width_field='width',
            height_field='height'
        )

        file_obj = VideoFieldFile(mock_instance, field, 'test.mp4')
        file_obj.storage = mock_storage

        # Тестируем обработку
        with patch('hlsfield.utils.tempdir') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = temp_dir
            file_obj._process_video_metadata(field, mock_instance)

    def test_preview_url_from_field(self):
        """Тест получения URL превью из поля модели"""
        mock_instance = Mock()
        mock_instance.preview = 'path/to/preview.jpg'

        mock_storage = Mock()
        mock_storage.url.return_value = 'http://example.com/preview.jpg'

        field = VideoField(preview_field='preview')
        file_obj = VideoFieldFile(mock_instance, field, 'test.mp4')
        file_obj.storage = mock_storage

        url = file_obj.preview_url()
        assert url == 'http://example.com/preview.jpg'

    def test_save_validation(self):
        """Тест валидации при сохранении"""
        mock_instance = Mock()
        field = VideoField()
        file_obj = VideoFieldFile(mock_instance, field, 'test.mp4')

        # Тестируем слишком маленький файл
        small_content = ContentFile(b'x', name='small.mp4')
        small_content.size = 100  # Меньше минимума

        with pytest.raises(InvalidVideoError):
            file_obj._validate_file(small_content)

    def test_save_large_file_validation(self):
        """Тест валидации больших файлов"""
        mock_instance = Mock()
        field = VideoField()
        file_obj = VideoFieldFile(mock_instance, field, 'test.mp4')

        # Тестируем слишком большой файл
        large_content = ContentFile(b'x', name='large.mp4')
        large_content.size = 5 * 1024 ** 3  # 5GB - больше лимита

        with pytest.raises(InvalidVideoError):
            file_obj._validate_file(large_content)


class TestHLSVideoField:
    """Тесты HLSVideoField"""

    def test_hls_field_creation(self):
        """Тест создания HLS поля"""
        field = HLSVideoField(
            upload_to='videos/',
            hls_playlist_field='hls_master',
            ladder=[{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        )

        assert field.hls_playlist_field == 'hls_master'
        assert len(field.ladder) == 1
        assert field.ladder[0]['height'] == 720

    def test_hls_deconstruct(self):
        """Тест деконструкции HLS поля"""
        field = HLSVideoField(
            upload_to='videos/',
            hls_playlist_field='hls_master',
            segment_duration=8
        )

        name, path, args, kwargs = field.deconstruct()

        assert path == 'hlsfield.fields.HLSVideoField'
        assert 'hls_playlist_field' in kwargs
        assert kwargs['segment_duration'] == 8

    @patch('hlsfield.tasks.build_hls_for_field')
    def test_trigger_hls(self, mock_task, test_model):
        """Тест запуска HLS транскодинга"""
        mock_task.delay = Mock(return_value=Mock(id='task-123'))

        field = HLSVideoField(
            upload_to='test/',
            hls_playlist_field='hls_master'
        )

        # Создаем экземпляр модели
        instance = test_model(title='Test', pk=1)

        # Тестируем запуск
        field._trigger_hls(instance)

        # Проверяем что задача была поставлена в очередь
        mock_task.delay.assert_called_once()


class TestDASHVideoField:
    """Тесты DASHVideoField"""

    def test_dash_field_creation(self):
        """Тест создания DASH поля"""
        field = DASHVideoField(
            upload_to='videos/',
            dash_manifest_field='dash_manifest',
            segment_duration=4
        )

        assert field.dash_manifest_field == 'dash_manifest'
        assert field.segment_duration == 4

    @patch('hlsfield.tasks.build_dash_for_field')
    def test_trigger_dash(self, mock_task, test_model):
        """Тест запуска DASH транскодинга"""
        mock_task.delay = Mock(return_value=Mock(id='task-456'))

        field = DASHVideoField(
            upload_to='test/',
            dash_manifest_field='dash_manifest'
        )

        instance = test_model(title='Test', pk=1)
        field._trigger_dash(instance)

        mock_task.delay.assert_called_once()


class TestAdaptiveVideoField:
    """Тесты AdaptiveVideoField"""

    def test_adaptive_field_creation(self):
        """Тест создания адаптивного поля"""
        field = AdaptiveVideoField(
            upload_to='videos/',
            hls_playlist_field='hls_master',
            dash_manifest_field='dash_manifest'
        )

        assert field.hls_playlist_field == 'hls_master'
        assert field.dash_manifest_field == 'dash_manifest'
        assert field.adaptive_on_save is True

    @patch('hlsfield.tasks.build_adaptive_for_field')
    def test_trigger_adaptive(self, mock_task, test_model):
        """Тест запуска адаптивного транскодинга"""
        mock_task.delay = Mock(return_value=Mock(id='task-789'))

        field = AdaptiveVideoField(
            upload_to='test/',
            hls_playlist_field='hls_master',
            dash_manifest_field='dash_manifest'
        )

        instance = test_model(title='Test', pk=1)
        field._trigger_adaptive(instance)

        mock_task.delay.assert_called_once()


class TestAdaptiveVideoFieldFile:
    """Тесты AdaptiveVideoFieldFile"""

    def test_master_url(self):
        """Тест получения URL HLS мастер плейлиста"""
        mock_instance = Mock()
        mock_instance.hls_master = 'path/to/master.m3u8'

        mock_storage = Mock()
        mock_storage.url.return_value = 'http://example.com/master.m3u8'

        field = AdaptiveVideoField(hls_playlist_field='hls_master')
        file_obj = AdaptiveVideoFieldFile(mock_instance, field, 'test.mp4')
        file_obj.storage = mock_storage

        url = file_obj.master_url()
        assert url == 'http://example.com/master.m3u8'

    def test_dash_url(self):
        """Тест получения URL DASH манифеста"""
        mock_instance = Mock()
        mock_instance.dash_manifest = 'path/to/manifest.mpd'

        mock_storage = Mock()
        mock_storage.url.return_value = 'http://example.com/manifest.mpd'

        field = AdaptiveVideoField(dash_manifest_field='dash_manifest')
        file_obj = AdaptiveVideoFieldFile(mock_instance, field, 'test.mp4')
        file_obj.storage = mock_storage

        url = file_obj.dash_url()
        assert url == 'http://example.com/manifest.mpd'

    @patch('hlsfield.fields.VideoField.attr_class.save')
    def test_deferred_processing(self, mock_super_save):
        """Тест отложенной обработки для объектов без PK"""
        mock_instance = Mock()
        mock_instance.pk = None  # Нет PK - отложенная обработка

        field = AdaptiveVideoField(adaptive_on_save=True)
        field.attname = 'adaptive_video'

        file_obj = AdaptiveVideoFieldFile(mock_instance, field, 'test.mp4')

        content = ContentFile(b'video content', name='test.mp4')
        file_obj.save('test.mp4', content)

        # Проверяем что установлен флаг отложенной обработки
        assert hasattr(mock_instance, '__adaptive_pending__adaptive_video')
        assert getattr(mock_instance, '__adaptive_pending__adaptive_video') is True


class TestLadderValidation:
    """Тесты валидации лестницы качеств"""

    def test_valid_ladder(self, sample_ladder):
        """Тест валидной лестницы"""
        # Не должно бросать исключений
        assert validate_ladder(sample_ladder) is True

    def test_empty_ladder(self):
        """Тест пустой лестницы"""
        with pytest.raises(ValueError, match="must be a non-empty list"):
            validate_ladder([])

    def test_invalid_ladder_format(self):
        """Тест невалидного формата лестницы"""
        with pytest.raises(ValueError, match="must be a dictionary"):
            validate_ladder([360, 720, 1080])  # Числа вместо словарей

    def test_missing_required_fields(self):
        """Тест лестницы с отсутствующими полями"""
        invalid_ladder = [
            {"height": 360, "v_bitrate": 800},  # Нет a_bitrate
            {"v_bitrate": 2500, "a_bitrate": 128},  # Нет height
        ]

        with pytest.raises(ValueError, match="missing required field"):
            validate_ladder(invalid_ladder)

    def test_negative_values(self):
        """Тест отрицательных значений в лестнице"""
        invalid_ladder = [
            {"height": 360, "v_bitrate": -800, "a_bitrate": 96}
        ]

        with pytest.raises(ValueError, match="cannot be negative"):
            validate_ladder(invalid_ladder)

    def test_out_of_range_values(self):
        """Тест значений вне допустимых пределов"""
        invalid_ladder = [
            {"height": 100, "v_bitrate": 800, "a_bitrate": 96}  # Слишком низкое разрешение
        ]

        with pytest.raises(ValueError, match="out of range"):
            validate_ladder(invalid_ladder)


class TestOptimalLadder:
    """Тесты генерации оптимальной лестницы"""

    def test_hd_source(self):
        """Тест для HD источника"""
        ladder = get_optimal_ladder_for_resolution(1280, 720)

        # Проверяем что все качества не превышают источник
        assert all(rung['height'] <= 720 * 1.1 for rung in ladder)

        # Проверяем что есть исходное разрешение
        heights = [rung['height'] for rung in ladder]
        assert 720 in heights

    def test_4k_source(self):
        """Тест для 4K источника"""
        ladder = get_optimal_ladder_for_resolution(3840, 2160)

        # Должны быть все стандартные качества + 4K
        heights = [rung['height'] for rung in ladder]
        assert 2160 in heights
        assert 1080 in heights
        assert 720 in heights

    def test_low_res_source(self):
        """Тест для низкого разрешения"""
        ladder = get_optimal_ladder_for_resolution(640, 360)

        # Должен быть хотя бы один вариант качества
        assert len(ladder) >= 1

        # Все качества должны быть не выше источника
        heights = [rung['height'] for rung in ladder]
        assert max(heights) <= 360 * 1.1

    def test_estimated_bitrates(self):
        """Тест расчета битрейтов"""
        ladder = get_optimal_ladder_for_resolution(1920, 1080)

        # Битрейты должны возрастать с качеством
        bitrates = [rung['v_bitrate'] for rung in ladder]
        assert bitrates == sorted(bitrates)

        # Все битрейты должны быть положительными
        assert all(br > 0 for br in bitrates)


class TestFieldIntegration:
    """Интеграционные тесты полей"""

    def test_field_in_model_definition(self):
        """Тест использования поля в определении модели"""
        from django.db import models
        from hlsfield import VideoField

        class TestModel(models.Model):
            title = models.CharField(max_length=200)
            video = VideoField(upload_to='test/')

            class Meta:
                app_label = 'hlsfield'

        # Проверяем что поле корректно создано
        video_field = TestModel._meta.get_field('video')
        assert isinstance(video_field, VideoField)
        assert video_field.upload_to == 'test/'

    @patch('hlsfield.utils.ffprobe_streams')
    def test_model_save_with_video(self, mock_ffprobe, test_model):
        """Тест сохранения модели с видео"""
        mock_ffprobe.return_value = {
            'streams': [],
            'format': {'duration': '60.0'}
        }

        # Создаем экземпляр
        instance = test_model(title='Test Video')

        # Добавляем видеофайл
        video_content = ContentFile(b'fake video data', name='test.mp4')
        instance.video.save('test.mp4', video_content, save=False)

        # Проверяем что файл был сохранен
        assert instance.video.name is not None

    def test_field_choices_in_admin(self, test_model):
        """Тест отображения поля в Django admin"""
        from django.contrib import admin

        # Проверяем что поле может быть использовано в admin
        class TestAdmin(admin.ModelAdmin):
            list_display = ['title']
            fields = ['title', 'video', 'hls_video']

        # Не должно бросать исключений при создании
        admin_instance = TestAdmin(test_model, admin.site)
        assert admin_instance is not None
