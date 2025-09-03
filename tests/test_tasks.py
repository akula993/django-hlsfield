"""
Тесты Celery задач для обработки видео
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from hlsfield import tasks
from hlsfield.exceptions import TranscodingError, FFmpegError, StorageError


class TestBasicTasks:
    """Тесты базовых задач транскодинга"""

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.utils.tempdir')
    @patch('hlsfield.utils.pull_to_local')
    @patch('hlsfield.utils.transcode_hls_variants')
    @patch('hlsfield.utils.save_tree_to_storage')
    def test_build_hls_for_field_sync(self, mock_save_tree, mock_transcode,
                                      mock_pull, mock_tempdir, mock_get_model, temp_dir):
        """Тест синхронной задачи создания HLS"""
        # Настраиваем моки
        mock_model = Mock()
        mock_instance = Mock()
        mock_instance.pk = 1
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        # Мокаем поле
        mock_field = Mock()
        mock_field.ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        mock_field.segment_duration = 6
        mock_field.hls_playlist_field = 'hls_master'
        mock_field.hls_base_subdir = 'hls'

        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'test.mp4'

        # Настраиваем _resolve_field
        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'test.mp4')

            # Настраиваем остальные моки
            mock_tempdir.return_value.__enter__.return_value = temp_dir
            mock_pull.return_value = temp_dir / 'input.mp4'

            master_file = temp_dir / 'master.m3u8'
            master_file.write_text('#EXTM3U\n')
            mock_transcode.return_value = master_file

            mock_save_tree.return_value = ['saved/master.m3u8']

            # Выполняем задачу
            result = tasks.build_hls_for_field_sync('testapp.Video', 1, 'video')

            # Проверяем результат
            assert result['status'] == 'success'
            assert 'master_playlist' in result
            assert 'transcoding_time' in result
            assert 'variants' in result

            # Проверяем что были вызваны нужные функции
            mock_pull.assert_called_once()
            mock_transcode.assert_called_once()
            mock_save_tree.assert_called_once()

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.tasks._handle_task_error')
    def test_build_hls_for_field_sync_error(self, mock_handle_error, mock_get_model):
        """Тест обработки ошибок в HLS задаче"""
        mock_model = Mock()
        mock_instance = Mock()
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        # Симулируем ошибку при получении поля
        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.side_effect = Exception("Field resolution failed")

            with pytest.raises(Exception):
                tasks.build_hls_for_field_sync('testapp.Video', 1, 'video')

            # Проверяем что была вызвана обработка ошибки
            mock_handle_error.assert_called_once()

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.utils.tempdir')
    @patch('hlsfield.utils.pull_to_local')
    @patch('hlsfield.utils.transcode_dash_variants')
    @patch('hlsfield.utils.save_tree_to_storage')
    def test_build_dash_for_field_sync(self, mock_save_tree, mock_transcode,
                                       mock_pull, mock_tempdir, mock_get_model, temp_dir):
        """Тест синхронной задачи создания DASH"""
        # Настраиваем моки аналогично HLS тесту
        mock_model = Mock()
        mock_instance = Mock()
        mock_instance.pk = 1
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_field = Mock()
        mock_field.ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        mock_field.segment_duration = 4
        mock_field.dash_manifest_field = 'dash_manifest'
        mock_field.dash_base_subdir = 'dash'

        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'test.mp4'

        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'test.mp4')

            mock_tempdir.return_value.__enter__.return_value = temp_dir
            mock_pull.return_value = temp_dir / 'input.mp4'

            manifest_file = temp_dir / 'manifest.mpd'
            manifest_file.write_text('<?xml version="1.0"?><MPD></MPD>')
            mock_transcode.return_value = manifest_file

            mock_save_tree.return_value = ['saved/manifest.mpd']

            result = tasks.build_dash_for_field_sync('testapp.Video', 1, 'video')

            assert result['status'] == 'success'
            assert 'manifest' in result
            assert 'transcoding_time' in result
            assert 'representations' in result

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.utils.tempdir')
    @patch('hlsfield.utils.pull_to_local')
    @patch('hlsfield.utils.transcode_adaptive_variants')
    @patch('hlsfield.utils.save_tree_to_storage')
    def test_build_adaptive_for_field_sync(self, mock_save_tree, mock_transcode,
                                           mock_pull, mock_tempdir, mock_get_model, temp_dir):
        """Тест синхронной задачи создания адаптивного видео"""
        mock_model = Mock()
        mock_instance = Mock()
        mock_instance.pk = 1
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_field = Mock()
        mock_field.ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]
        mock_field.segment_duration = 6
        mock_field.hls_playlist_field = 'hls_master'
        mock_field.dash_manifest_field = 'dash_manifest'
        mock_field.adaptive_base_subdir = 'adaptive'

        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'test.mp4'

        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'test.mp4')

            mock_tempdir.return_value.__enter__.return_value = temp_dir
            mock_pull.return_value = temp_dir / 'input.mp4'

            # Создаем структуру результата
            hls_dir = temp_dir / 'hls'
            dash_dir = temp_dir / 'dash'
            hls_dir.mkdir()
            dash_dir.mkdir()

            hls_master = hls_dir / 'master.m3u8'
            dash_manifest = dash_dir / 'manifest.mpd'
            hls_master.write_text('#EXTM3U\n')
            dash_manifest.write_text('<MPD></MPD>')

            mock_transcode.return_value = {
                'hls_master': hls_master,
                'dash_manifest': dash_manifest
            }

            mock_save_tree.return_value = ['saved/hls/master.m3u8', 'saved/dash/manifest.mpd']

            result = tasks.build_adaptive_for_field_sync('testapp.Video', 1, 'video')

            assert result['status'] == 'success'
            assert 'hls_master' in result
            assert 'dash_manifest' in result
            assert 'transcoding_time' in result
            assert 'variants' in result


class TestProgressiveTasks:
    """Тесты прогрессивных задач"""

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.tasks._build_single_quality')
    def test_build_progressive_for_field_sync(self, mock_build_single, mock_get_model, temp_dir):
        """Тест прогрессивной обработки видео"""
        mock_model = Mock()
        mock_instance = Mock()
        mock_instance.pk = 1
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_field = Mock()
        mock_field.ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
        ]

        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'test.mp4'

        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'test.mp4')

            with patch('hlsfield.utils.tempdir') as mock_tempdir:
                mock_tempdir.return_value.__enter__.return_value = temp_dir

                with patch('hlsfield.utils.pull_to_local') as mock_pull:
                    mock_pull.return_value = temp_dir / 'input.mp4'

                    options = {
                        'preview_first': True,
                        'progressive_delay': 0,  # Без задержки в тестах
                        'priority_heights': [360, 720]
                    }

                    result = tasks.build_progressive_for_field_sync(
                        'testapp.Video', 1, 'video', options
                    )

                    assert result['status'] == 'success'
                    assert result['total_qualities'] == 3

                    # Проверяем что _build_single_quality вызывалась
                    # (один раз для превью + количество остальных качеств)
                    assert mock_build_single.call_count > 1

    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.utils.analyze_video_complexity')
    @patch('hlsfield.tasks._build_single_quality')
    def test_optimize_existing_video(self, mock_build_single, mock_analyze, mock_get_model, temp_dir):
        """Тест оптимизации существующего видео"""
        mock_model = Mock()
        mock_instance = Mock()
        mock_instance.pk = 1
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_field = Mock()
        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'test.mp4'

        # Мокаем анализ видео
        mock_analyze.return_value = {
            'duration': 120.0,
            'complexity': 'medium'
        }

        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'test.mp4')

            with patch('hlsfield.utils.tempdir') as mock_tempdir:
                mock_tempdir.return_value.__enter__.return_value = temp_dir

                with patch('hlsfield.utils.pull_to_local') as mock_pull:
                    mock_pull.return_value = temp_dir / 'input.mp4'

                    with patch('hlsfield.utils.ffprobe_streams') as mock_ffprobe:
                        mock_ffprobe.return_value = {
                            'streams': [{
                                'codec_type': 'video',
                                'width': 1920,
                                'height': 1080
                            }]
                        }

                        with patch('hlsfield.utils.pick_video_audio_streams') as mock_pick:
                            mock_pick.return_value = ({'width': 1920, 'height': 1080}, None)

                            result = tasks.optimize_existing_video(
                                'testapp.Video', 1, 'video', target_qualities=3
                            )

                            assert result['status'] == 'success'
                            assert result['optimized_qualities'] == 3

    @patch('hlsfield.tasks.apps.get_model')
    def test_health_check_videos(self, mock_get_model):
        """Тест проверки состояния видео"""
        # Создаем несколько экземпляров с разными проблемами
        mock_model = Mock()

        # Здоровый экземпляр
        healthy_instance = Mock()
        healthy_instance.pk = 1

        # Экземпляр с отсутствующим файлом
        broken_instance = Mock()
        broken_instance.pk = 2

        mock_model.objects.all.return_value = [healthy_instance, broken_instance]
        mock_get_model.return_value = mock_model

        # Настраиваем поля
        mock_field = Mock()
        mock_field.hls_playlist_field = 'hls_master'
        mock_field.dash_manifest_field = None

        mock_healthy_file = Mock()
        mock_healthy_file.storage = Mock()
        mock_healthy_file.name = 'healthy.mp4'
        mock_healthy_file.storage.exists.return_value = True

        mock_broken_file = Mock()
        mock_broken_file.storage = Mock()
        mock_broken_file.name = 'broken.mp4'
        mock_broken_file.storage.exists.return_value = False

        # Настраиваем поля экземпляров
        healthy_instance.hls_master = 'path/to/master.m3u8'
        broken_instance.hls_master = 'path/to/missing_master.m3u8'

        def mock_resolve_field(instance, field_name):
            if instance.pk == 1:
                return mock_field, mock_healthy_file, mock_healthy_file.storage, 'healthy.mp4'
            else:
                return mock_field, mock_broken_file, mock_broken_file.storage, 'broken.mp4'

        with patch('hlsfield.tasks._resolve_field', side_effect=mock_resolve_field):
            # Для broken instance storage.exists возвращает False для манифеста
            def mock_exists(path):
                if 'broken' in path or 'missing_master' in path:
                    return False
                return True

            mock_healthy_file.storage.exists.side_effect = mock_exists
            mock_broken_file.storage.exists.side_effect = mock_exists

            result = tasks.health_check_videos('testapp.Video', 'video')

            assert result['total_checked'] == 2
            assert result['issues_found'] == 1
            assert result['healthy_videos'] == 1
            assert len(result['issues']) == 1

            # Проверяем что проблемы корректно идентифицированы
            issue = result['issues'][0]
            assert issue['pk'] == 2
            assert len(issue['problems']) > 0


class TestBatchTasks:
    """Тесты пакетных операций"""

    @patch('hlsfield.tasks.optimize_existing_video')
    @patch('hlsfield.tasks.apps.get_model')
    def test_batch_optimize_videos(self, mock_get_model, mock_optimize):
        """Тест массовой оптимизации видео"""
        mock_model = Mock()

        # Настраиваем mock для optimize_existing_video
        mock_optimize.delay = Mock(return_value=Mock(id='task-123'))

        video_ids = [1, 2, 3]

        result = tasks.batch_optimize_videos(
            'testapp.Video', video_ids, 'video', target_qualities=3
        )

        assert result['total_processed'] == 3
        assert result['successful'] == 3
        assert result['failed'] == 0
        assert len(result['results']) == 3

        # Проверяем что все задачи были поставлены в очередь
        for result_item in result['results']:
            assert result_item['status'] == 'queued'
            assert 'task_id' in result_item

    @patch('hlsfield.tasks.apps.get_model')
    def test_batch_optimize_with_errors(self, mock_get_model):
        """Тест массовой оптимизации с ошибками"""
        mock_model = Mock()

        # Первый экземпляр OK, второй вызывает ошибку
        def mock_get_instance(pk):
            if pk == 2:
                raise Exception("Instance not found")
            return Mock(pk=pk)

        mock_model.objects.get.side_effect = mock_get_instance
        mock_get_model.return_value = mock_model

        video_ids = [1, 2]

        with patch('hlsfield.tasks.optimize_existing_video') as mock_optimize:
            mock_optimize.delay = Mock(return_value=Mock(id='task-456'))

            result = tasks.batch_optimize_videos(
                'testapp.Video', video_ids, 'video'
            )

            assert result['total_processed'] == 2
            assert result['successful'] == 1
            assert result['failed'] == 1

            # Проверяем результаты
            results = result['results']
            success_result = next(r for r in results if r['pk'] == 1)
            error_result = next(r for r in results if r['pk'] == 2)

            assert success_result['status'] == 'queued'
            assert error_result['status'] == 'error'


class TestUtilityTasks:
    """Тесты вспомогательных задач"""

    @patch('glob.glob')
    @patch('os.path.isdir')
    @patch('shutil.rmtree')
    @patch('pathlib.Path.unlink')
    def test_cleanup_old_temp_files(self, mock_unlink, mock_rmtree, mock_isdir, mock_glob):
        """Тест очистки старых временных файлов"""
        # Настраиваем возвращаемые файлы
        old_files = [
            '/tmp/hlsfield_old_dir',
            '/tmp/hls_old_file.mp4',
            '/tmp/dash_old_file.mpd'
        ]

        mock_glob.return_value = old_files

        # Первый путь - директория, остальные - файлы
        def mock_isdir_check(path):
            return path == '/tmp/hlsfield_old_dir'

        mock_isdir.side_effect = mock_isdir_check

        # Мокаем stat для проверки времени модификации
        import time
        old_time = time.time() - 90000  # Больше 24 часов назад

        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_mtime = old_time

            result = tasks.cleanup_old_temp_files()

            assert result['cleaned'] > 0
            assert result['errors'] >= 0

            # Проверяем что были вызваны функции очистки
            mock_rmtree.assert_called()  # Для директории
            mock_unlink.assert_called()  # Для файлов

    @patch('hlsfield.views.VideoEvent.objects')
    def test_generate_video_analytics_report(self, mock_events):
        """Тест генерации отчета аналитики"""
        # Настраиваем данные событий
        mock_events.filter.return_value = mock_events
        mock_events.count.return_value = 100
        mock_events.values.return_value.distinct.return_value.count.return_value = 25

        # Настраиваем события по типам
        mock_play_events = Mock()
        mock_play_events.count.return_value = 60
        mock_events.filter.return_value = mock_play_events

        mock_end_events = Mock()
        mock_end_events.count.return_value = 40

        mock_error_events = Mock()
        mock_error_events.count.return_value = 5

        mock_buffer_events = Mock()
        mock_buffer_events.count.return_value = 15

        # Настраиваем цепочку вызовов
        def mock_filter(**kwargs):
            event_type = kwargs.get('event_type')
            if event_type == 'play':
                return mock_play_events
            elif event_type == 'ended':
                return mock_end_events
            elif event_type == 'error':
                return mock_error_events
            elif event_type == 'buffer_start':
                return mock_buffer_events
            return mock_events

        mock_events.filter.side_effect = mock_filter

        # Топ видео
        mock_top_videos = [
            {'video_id': 'video1', 'views': 50},
            {'video_id': 'video2', 'views': 30}
        ]

        mock_play_events.values.return_value.annotate.return_value.order_by.return_value.__getitem__ = \
            lambda x: mock_top_videos

        # Распределение по качеству
        mock_quality_dist = [
            {'quality': '720p', 'count': 40},
            {'quality': '1080p', 'count': 30}
        ]

        mock_events.exclude.return_value.values.return_value.annotate.return_value.order_by.return_value = \
            mock_quality_dist

        result = tasks.generate_video_analytics_report(days=7)

        assert 'period' in result
        assert result['total_events'] == 100
        assert result['unique_videos'] == 25
        assert result['play_events'] == 60
        assert result['error_events'] == 5
        assert 'top_videos' in result
        assert 'quality_distribution' in result

    @patch('celery.current_app.control.inspect')
    def test_monitor_transcoding_performance(self, mock_inspect):
        """Тест мониторинга производительности"""
        # Настраиваем данные активных задач
        mock_inspector = Mock()
        mock_inspector.active.return_value = {
            'worker1': [{'id': 'task1'}, {'id': 'task2'}],
            'worker2': [{'id': 'task3'}]
        }
        mock_inspect.return_value = mock_inspector

        result = tasks.monitor_transcoding_performance()

        assert 'queue_length' in result
        assert result['queue_length'] == 3  # Общее количество активных задач
        assert 'average_hls_time' in result
        assert 'success_rate' in result

    @patch('hlsfield.tasks.apps.get_model')
    def test_regenerate_missing_previews(self, mock_get_model, temp_dir):
        """Тест восстановления отсутствующих превью"""
        mock_model = Mock()

        # Экземпляр без превью
        instance_without_preview = Mock()
        instance_without_preview.pk = 1
        instance_without_preview.preview = None  # Нет превью

        mock_model.objects.all.return_value = [instance_without_preview]
        mock_get_model.return_value = mock_model

        mock_field = Mock()
        mock_field.preview_field = 'preview'
        mock_field.preview_at = 3.0
        mock_field.sidecar_layout = 'flat'
        mock_field.preview_filename = 'preview.jpg'

        mock_file = Mock()
        mock_file.storage = Mock()
        mock_file.name = 'video.mp4'
        mock_file._base_key.return_value = 'video'
        mock_file.preview_url.return_value = None  # Нет превью

        with patch('hlsfield.tasks._resolve_field') as mock_resolve:
            mock_resolve.return_value = (mock_field, mock_file, mock_file.storage, 'video.mp4')

            with patch('hlsfield.utils.tempdir') as mock_tempdir:
                mock_tempdir.return_value.__enter__.return_value = temp_dir

                with patch('hlsfield.utils.pull_to_local') as mock_pull:
                    mock_pull.return_value = temp_dir / 'video.mp4'

                    with patch('hlsfield.utils.extract_preview') as mock_extract:
                        preview_file = temp_dir / 'preview.jpg'
                        preview_file.write_bytes(b'preview data')
                        mock_extract.return_value = None

                        # Мокаем существование созданного превью
                        def mock_exists(path):
                            return 'preview.jpg' in str(path)

                        preview_file.exists = Mock(return_value=True)

                        with patch.object(preview_file, 'open'):
                            mock_file.storage.save.return_value = 'saved_preview.jpg'

                            result = tasks.regenerate_missing_previews(
                                'testapp.Video', 'video'
                            )

                            assert result['regenerated'] >= 0
                            assert result['errors'] >= 0


class TestTaskHelpers:
    """Тесты вспомогательных функций задач"""

    def test_resolve_field(self, test_model):
        """Тест функции _resolve_field"""
        instance = test_model(title='Test')

        # Добавляем мок видео файл
        mock_video_file = Mock()
        mock_video_file.storage = Mock()
        mock_video_file.name = 'test.mp4'

        instance.video = mock_video_file

        field, file, storage, name = tasks._resolve_field(instance, 'video')

        assert field is not None
        assert file == mock_video_file
        assert storage == mock_video_file.storage
        assert name == 'test.mp4'

    def test_update_instance_status(self):
        """Тест обновления статуса экземпляра"""
        mock_instance = Mock()
        mock_instance.processing_status = 'old_status'

        # Мокаем save чтобы не было реального сохранения в БД
        mock_instance.save = Mock()

        tasks._update_instance_status(
            mock_instance,
            'new_status',
            transcoding_time=120
        )

        # Проверяем что статус обновился
        assert mock_instance.processing_status == 'new_status'

        # Проверяем что save был вызван
        mock_instance.save.assert_called_once()

    def test_handle_task_error(self):
        """Тест обработки ошибок задач"""
        mock_instance = Mock()
        mock_instance.__str__ = Mock(return_value='Video instance')

        error = TranscodingError("Transcoding failed")

        with patch('hlsfield.tasks._update_instance_status') as mock_update:
            tasks._handle_task_error(mock_instance, error, 'HLS')

            # Проверяем что статус ошибки был установлен
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert 'error_HLS' in call_args[0][1]  # Статус содержит 'error_HLS'

    def test_get_base_key(self):
        """Тест генерации базового ключа"""
        base_key = tasks._get_base_key('path/to/video.mp4', 'hls')
        assert base_key == 'path/to/video/hls/'

    def test_get_base_key_no_extension(self):
        """Тест базового ключа без расширения"""
        base_key = tasks._get_base_key('video_without_ext', 'dash')
        assert base_key == 'video_without_ext/dash/'


class TestAsyncTasks:
    """Тесты асинхронных задач Celery"""

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    def test_build_hls_for_field_async(self, mock_sync_task):
        """Тест асинхронной wrapper задачи для HLS"""
        mock_sync_task.return_value = {'status': 'success'}

        # Создаем мок для self (Celery task instance)
        mock_self = Mock()
        mock_self.request.retries = 0
        mock_self.max_retries = 3
        mock_self.retry = Mock(side_effect=Exception("Retry called"))

        # Тестируем успешное выполнение
        result = tasks.build_hls_for_field(
            mock_self, 'testapp.Video', 1, 'video'
        )

        assert result == {'status': 'success'}
        mock_sync_task.assert_called_once_with('testapp.Video', 1, 'video')

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    @patch('hlsfield.tasks.apps.get_model')
    def test_build_hls_for_field_retry_logic(self, mock_get_model, mock_sync_task):
        """Тест логики повторов в асинхронной задаче"""
        # Настраиваем ошибку которая должна вызвать повтор
        mock_sync_task.side_effect = StorageError("Temporary storage issue")

        # Настраиваем модель для обработки финальной ошибки
        mock_model = Mock()
        mock_instance = Mock()
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_self = Mock()
        mock_self.request.retries = 1  # Первый повтор
        mock_self.max_retries = 3

        # Создаем исключение для повтора
        retry_exception = Exception("Retrying")
        mock_self.retry.side_effect = retry_exception

        with pytest.raises(Exception):  # Ожидаем retry exception
            tasks.build_hls_for_field(
                mock_self, 'testapp.Video', 1, 'video'
            )

        # Проверяем что retry был вызван
        mock_self.retry.assert_called_once()

    @patch('hlsfield.tasks.build_hls_for_field_sync')
    @patch('hlsfield.tasks.apps.get_model')
    @patch('hlsfield.tasks._handle_task_error')
    def test_build_hls_for_field_max_retries(self, mock_handle_error,
                                             mock_get_model, mock_sync_task):
        """Тест достижения максимального количества повторов"""
        mock_sync_task.side_effect = TranscodingError("Persistent error")

        mock_model = Mock()
        mock_instance = Mock()
        mock_model.objects.get.return_value = mock_instance
        mock_get_model.return_value = mock_model

        mock_self = Mock()
        mock_self.request.retries = 3  # Максимум достигнут
        mock_self.max_retries = 3

        # Должна быть вызвана обработка финальной ошибки
        with pytest.raises(TranscodingError):
            tasks.build_hls_for_field(
                mock_self, 'testapp.Video', 1, 'video'
            )

        # Проверяем что была вызвана обработка ошибки
        mock_handle_error.assert_called_once()
