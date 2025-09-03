"""
Тесты для утилит и работы с FFmpeg
"""
import pytest
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from hlsfield import utils
from hlsfield.exceptions import (
    FFmpegError, FFmpegNotFoundError, InvalidVideoError,
    TranscodingError, StorageError, TimeoutError
)


class TestTempdir:
    """Тесты контекстного менеджера временных директорий"""

    def test_tempdir_creation(self):
        """Тест создания временной директории"""
        with utils.tempdir() as temp_path:
            assert temp_path.exists()
            assert temp_path.is_dir()
            assert 'hlsfield_' in temp_path.name

    def test_tempdir_cleanup(self):
        """Тест очистки временной директории"""
        temp_path = None
        with utils.tempdir() as temp_dir:
            temp_path = temp_dir
            # Создаем файл в директории
            test_file = temp_dir / 'test.txt'
            test_file.write_text('test data')
            assert test_file.exists()

        # После выхода из контекста директория должна быть удалена
        assert not temp_path.exists()

    @patch('hlsfield.defaults.KEEP_TEMP_FILES', True)
    def test_tempdir_keep_files(self):
        """Тест сохранения временных файлов в debug режиме"""
        temp_path = None
        with utils.tempdir() as temp_dir:
            temp_path = temp_dir
            test_file = temp_dir / 'test.txt'
            test_file.write_text('debug data')

        # В режиме отладки файлы должны сохраняться
        assert temp_path.exists()

        # Очищаем вручную
        import shutil
        shutil.rmtree(temp_path, ignore_errors=True)


class TestBinaryAvailability:
    """Тесты проверки доступности бинарных файлов"""

    def test_existing_binary(self):
        """Тест существующего бинарного файла"""
        # Используем стандартную команду которая точно есть
        import sys
        python_path = utils.ensure_binary_available('python', sys.executable)
        assert python_path == sys.executable

    def test_binary_in_path(self):
        """Тест поиска бинарного файла в PATH"""
        # Тестируем с командой которая должна быть в PATH
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/ls'
            path = utils.ensure_binary_available('ls', 'ls')
            assert path == '/usr/bin/ls'

    def test_missing_binary(self):
        """Тест отсутствующего бинарного файла"""
        with pytest.raises(FFmpegNotFoundError):
            utils.ensure_binary_available('nonexistent', 'nonexistent_binary_xyz')

    def test_absolute_path_binary(self, temp_dir):
        """Тест с абсолютным путем"""
        # Создаем исполняемый файл
        binary_path = temp_dir / 'test_binary'
        binary_path.write_text('#!/bin/bash\necho test')
        binary_path.chmod(0o755)

        result = utils.ensure_binary_available('test', str(binary_path))
        assert result == str(binary_path)


class TestCommandExecution:
    """Тесты выполнения команд"""

    @patch('subprocess.run')
    def test_successful_command(self, mock_run):
        """Тест успешного выполнения команды"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='success output',
            stderr='',
        )

        result = utils.run(['echo', 'test'])

        assert result.returncode == 0
        assert result.stdout == 'success output'
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_command_with_error(self, mock_run):
        """Тест команды с ошибкой"""
        mock_run.return_value = Mock(
            returncode=1,
            stdout='',
            stderr='command failed',
        )

        with pytest.raises(FFmpegError) as exc_info:
            utils.run(['false'])

        error = exc_info.value
        assert error.returncode == 1
        assert 'command failed' in error.stderr

    @patch('subprocess.run')
    def test_command_timeout(self, mock_run):
        """Тест таймаута команды"""
        mock_run.side_effect = subprocess.TimeoutExpired(['sleep', '100'], 5)

        with pytest.raises(TimeoutError):
            utils.run(['sleep', '100'], timeout_sec=5)

    @patch('subprocess.run')
    def test_command_not_found(self, mock_run):
        """Тест команды которая не найдена"""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(FFmpegNotFoundError):
            utils.run(['nonexistent_command'])

    def test_empty_command(self):
        """Тест пустой команды"""
        with pytest.raises(ValueError, match="Command cannot be empty"):
            utils.run([])


class TestFFprobe:
    """Тесты анализа видео через FFprobe"""

    @patch('hlsfield.utils.run')
    def test_ffprobe_successful(self, mock_run, mock_ffprobe_output):
        """Тест успешного анализа FFprobe"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(mock_ffprobe_output),
            stderr=''
        )

        result = utils.ffprobe_streams('test.mp4')

        assert 'streams' in result
        assert 'format' in result
        assert len(result['streams']) == 2

        # Проверяем что вызвали правильную команду
        call_args = mock_run.call_args[0][0]
        assert 'ffprobe' in call_args[0]
        assert 'test.mp4' in call_args

    @patch('hlsfield.utils.run')
    def test_ffprobe_invalid_json(self, mock_run):
        """Тест невалидного JSON от FFprobe"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='invalid json{',
            stderr=''
        )

        with pytest.raises(InvalidVideoError, match="invalid JSON"):
            utils.ffprobe_streams('test.mp4')

    @patch('hlsfield.utils.run')
    def test_ffprobe_no_streams(self, mock_run):
        """Тест файла без потоков"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"format": {}}',  # Нет streams
            stderr=''
        )

        with pytest.raises(InvalidVideoError, match="No streams found"):
            utils.ffprobe_streams('test.mp4')

    @patch('hlsfield.utils.run')
    def test_ffprobe_file_not_found(self, mock_run):
        """Тест несуществующего файла"""
        mock_run.side_effect = FFmpegError(
            ['ffprobe', 'missing.mp4'], 1, '', 'No such file'
        )

        with pytest.raises(InvalidVideoError, match="not found"):
            utils.ffprobe_streams('missing.mp4')

    def test_pick_video_audio_streams(self, mock_ffprobe_output):
        """Тест выбора видео и аудио потоков"""
        video_stream, audio_stream = utils.pick_video_audio_streams(mock_ffprobe_output)

        # Проверяем видео поток
        assert video_stream is not None
        assert video_stream['codec_type'] == 'video'
        assert video_stream['width'] == 1920
        assert video_stream['height'] == 1080

        # Проверяем аудио поток
        assert audio_stream is not None
        assert audio_stream['codec_type'] == 'audio'
        assert audio_stream['channels'] == 2

    def test_pick_streams_no_video(self):
        """Тест выбора потоков когда нет видео"""
        audio_only = {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3"
                }
            ]
        }

        video_stream, audio_stream = utils.pick_video_audio_streams(audio_only)

        assert video_stream is None
        assert audio_stream is not None

    def test_pick_streams_no_audio(self):
        """Тест выбора потоков когда нет аудио"""
        video_only = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720
                }
            ]
        }

        video_stream, audio_stream = utils.pick_video_audio_streams(video_only)

        assert video_stream is not None
        assert audio_stream is None


class TestVideoAnalysis:
    """Тесты анализа сложности видео"""

    @patch('hlsfield.utils.ffprobe_streams')
    def test_analyze_video_complexity(self, mock_ffprobe, mock_ffprobe_output):
        """Тест анализа сложности видео"""
        mock_ffprobe.return_value = mock_ffprobe_output

        analysis = utils.analyze_video_complexity('test.mp4')

        assert 'has_video' in analysis
        assert 'has_audio' in analysis
        assert 'complexity' in analysis
        assert 'estimated_transcode_time' in analysis
        assert analysis['has_video'] is True
        assert analysis['has_audio'] is True

    @patch('hlsfield.utils.ffprobe_streams')
    def test_analyze_4k_video(self, mock_ffprobe):
        """Тест анализа 4K видео (высокая сложность)"""
        mock_ffprobe.return_value = {
            "streams": [{
                "codec_type": "video",
                "width": 3840,
                "height": 2160,
                "bit_rate": "15000000"
            }],
            "format": {"duration": "120.0"}
        }

        analysis = utils.analyze_video_complexity('4k.mp4')

        assert analysis['complexity'] == 'high'
        assert analysis['estimated_transcode_time'] > 1.0

    @patch('hlsfield.utils.ffprobe_streams')
    def test_analyze_low_res_video(self, mock_ffprobe):
        """Тест анализа видео низкого разрешения"""
        mock_ffprobe.return_value = {
            "streams": [{
                "codec_type": "video",
                "width": 480,
                "height": 360,
                "bit_rate": "500000"
            }],
            "format": {"duration": "30.0"}
        }

        analysis = utils.analyze_video_complexity('lowres.mp4')

        assert analysis['complexity'] == 'low'
        assert analysis['recommended_preset'] == 'medium'

    @patch('hlsfield.utils.ffprobe_streams')
    def test_analyze_error_handling(self, mock_ffprobe):
        """Тест обработки ошибок анализа"""
        mock_ffprobe.side_effect = Exception("Analysis failed")

        analysis = utils.analyze_video_complexity('error.mp4')

        # Должны получить значения по умолчанию
        assert analysis['has_video'] is True
        assert analysis['complexity'] == 'medium'
        assert analysis['estimated_transcode_time'] == 1.0


class TestPreviewExtraction:
    """Тесты извлечения превью кадров"""

    @patch('hlsfield.utils.run')
    def test_extract_preview_success(self, mock_run, temp_dir):
        """Тест успешного извлечения превью"""
        input_file = temp_dir / 'input.mp4'
        output_file = temp_dir / 'preview.jpg'

        input_file.write_bytes(b'fake video')

        # Мокаем успешное выполнение FFmpeg
        def mock_ffmpeg_call(*args, **kwargs):
            # Создаем файл превью
            output_file.write_bytes(b'fake jpeg data' * 100)  # Достаточно большой файл
            return Mock(returncode=0)

        mock_run.side_effect = mock_ffmpeg_call

        result = utils.extract_preview(input_file, output_file, at_sec=5.0)

        assert result == output_file
        assert output_file.exists()
        assert output_file.stat().st_size > 100

    @patch('hlsfield.utils.run')
    def test_extract_preview_with_scaling(self, mock_run, temp_dir):
        """Тест извлечения превью с масштабированием"""
        input_file = temp_dir / 'input.mp4'
        output_file = temp_dir / 'preview.jpg'

        input_file.write_bytes(b'fake video')

        def mock_ffmpeg_call(*args, **kwargs):
            # Проверяем что в команде есть параметры масштабирования
            cmd = args[0]
            assert '-vf' in cmd
            scale_idx = cmd.index('-vf') + 1
            assert 'scale=' in cmd[scale_idx]

            output_file.write_bytes(b'scaled jpeg' * 50)
            return Mock(returncode=0)

        mock_run.side_effect = mock_ffmpeg_call

        result = utils.extract_preview(input_file, output_file, width=640, height=360)

        assert result == output_file
        mock_run.assert_called()

    @patch('hlsfield.utils.run')
    def test_extract_preview_retry_logic(self, mock_run, temp_dir):
        """Тест логики повторных попыток"""
        input_file = temp_dir / 'input.mp4'
        output_file = temp_dir / 'preview.jpg'

        input_file.write_bytes(b'fake video')

        call_count = 0
        def mock_ffmpeg_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count < 3:  # Первые две попытки неудачны
                if output_file.exists():
                    output_file.unlink()
                return Mock(returncode=0)
            else:  # Третья попытка успешна
                output_file.write_bytes(b'success jpeg' * 50)
                return Mock(returncode=0)

        mock_run.side_effect = mock_ffmpeg_call

        result = utils.extract_preview(input_file, output_file)

        assert result == output_file
        assert call_count == 3  # Должно быть 3 попытки

    @patch('hlsfield.utils.run')
    def test_extract_preview_all_attempts_fail(self, mock_run, temp_dir):
        """Тест когда все попытки неудачны"""
        input_file = temp_dir / 'input.mp4'
        output_file = temp_dir / 'preview.jpg'

        input_file.write_bytes(b'fake video')

        # Все попытки создают пустой или маленький файл
        def mock_ffmpeg_call(*args, **kwargs):
            output_file.write_bytes(b'x')  # Слишком маленький файл
            return Mock(returncode=0)

        mock_run.side_effect = mock_ffmpeg_call

        with pytest.raises(TranscodingError, match="Failed to extract preview"):
            utils.extract_preview(input_file, output_file)


class TestStorageOperations:
    """Тесты операций с файловым хранилищем"""

    @patch('hlsfield.utils.get_file_info_from_storage')
    def test_pull_to_local_direct_access(self, mock_get_info, temp_dir):
        """Тест прямого доступа к локальному файлу"""
        # Создаем тестовый файл
        source_file = temp_dir / 'source.mp4'
        source_file.write_bytes(b'video data' * 1000)

        # Мокаем storage с прямым доступом
        mock_storage = Mock()
        mock_storage.path.return_value = str(source_file)
        mock_get_info.return_value = {'size': source_file.stat().st_size}

        dst_dir = temp_dir / 'dst'
        dst_dir.mkdir()

        result = utils.pull_to_local(mock_storage, 'test.mp4', dst_dir)

        # Должен вернуть прямой путь
        assert result == source_file

    def test_pull_to_local_copy_through_storage(self, temp_dir):
        """Тест копирования через storage API"""
        # Создаем source данные
        source_data = b'video content' * 500

        # Мокаем storage без прямого доступа
        mock_storage = Mock()
        mock_storage.path.side_effect = NotImplementedError()  # Нет прямого доступа

        # Настраиваем файловый объект для чтения
        mock_file = Mock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.side_effect = [source_data[:1024], source_data[1024:], b'']  # Читаем по чанкам
        mock_storage.open.return_value = mock_file

        dst_dir = temp_dir / 'dst'
        dst_dir.mkdir()

        with patch('hlsfield.utils.get_file_info_from_storage') as mock_get_info:
            mock_get_info.return_value = {'size': len(source_data)}

            result = utils.pull_to_local(mock_storage, 'remote.mp4', dst_dir)

        # Проверяем что файл был скопирован
        assert result.name == 'remote.mp4'
        assert result.exists()
        assert result.read_bytes() == source_data

    def test_pull_to_local_error_handling(self, temp_dir):
        """Тест обработки ошибок при копировании"""
        mock_storage = Mock()
        mock_storage.path.side_effect = NotImplementedError()
        mock_storage.open.side_effect = Exception("Storage error")

        dst_dir = temp_dir / 'dst'
        dst_dir.mkdir()

        with pytest.raises(StorageError, match="Cannot download file"):
            utils.pull_to_local(mock_storage, 'error.mp4', dst_dir)

    def test_save_tree_to_storage(self, temp_dir):
        """Тест сохранения дерева файлов в storage"""
        # Создаем структуру файлов
        source_dir = temp_dir / 'source'
        source_dir.mkdir()

        (source_dir / 'file1.txt').write_text('content1')
        (source_dir / 'subdir').mkdir()
        (source_dir / 'subdir' / 'file2.txt').write_text('content2')

        # Мокаем storage
        mock_storage = Mock()
        saved_paths = ['base/file1.txt', 'base/subdir/file2.txt']
        mock_storage.save.side_effect = saved_paths

        result = utils.save_tree_to_storage(source_dir, mock_storage, 'base/')

        assert result == saved_paths
        assert mock_storage.save.call_count == 2

    def test_cleanup_storage_path(self):
        """Тест очистки путей в storage"""
        mock_storage = Mock()
        mock_storage.exists.return_value = True

        result = utils.cleanup_storage_path(mock_storage, 'path/to/file.mp4')

        assert result is True
        mock_storage.delete.assert_called_once_with('path/to/file.mp4')

    def test_cleanup_storage_path_retry(self):
        """Тест retry логики при очистке"""
        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_storage.delete.side_effect = [Exception("First fail"), Exception("Second fail"), None]

        result = utils.cleanup_storage_path(mock_storage, 'retry.mp4', max_attempts=3)

        assert result is True
        assert mock_storage.delete.call_count == 3


class TestVideoValidation:
    """Тесты валидации видеофайлов"""

    @patch('hlsfield.utils.ffprobe_streams')
    def test_validate_valid_video(self, mock_ffprobe, temp_dir, mock_ffprobe_output):
        """Тест валидации корректного видео"""
        # Создаем тестовый файл подходящего размера
        test_file = temp_dir / 'valid.mp4'
        test_file.write_bytes(b'x' * 10000)  # 10KB - подходящий размер

        mock_ffprobe.return_value = mock_ffprobe_output

        result = utils.validate_video_file(test_file)

        assert result['valid'] is True
        assert len(result['issues']) == 0
        assert result['info']['has_video'] is True
        assert result['info']['has_audio'] is True

    def test_validate_nonexistent_file(self, temp_dir):
        """Тест валидации несуществующего файла"""
        missing_file = temp_dir / 'missing.mp4'

        result = utils.validate_video_file(missing_file)

        assert result['valid'] is False
        assert 'File does not exist' in result['issues']

    def test_validate_too_small_file(self, temp_dir):
        """Тест валидации слишком маленького файла"""
        small_file = temp_dir / 'small.mp4'
        small_file.write_bytes(b'x' * 100)  # Меньше минимума

        with patch('hlsfield.utils.ffprobe_streams') as mock_ffprobe:
            mock_ffprobe.return_value = {'streams': [], 'format': {}}

            result = utils.validate_video_file(small_file)

        assert result['valid'] is False
        assert any('too small' in issue for issue in result['issues'])

    @patch('hlsfield.utils.ffprobe_streams')
    def test_validate_unsupported_extension(self, mock_ffprobe, temp_dir):
        """Тест неподдерживаемого расширения"""
        unsupported_file = temp_dir / 'video.xyz'
        unsupported_file.write_bytes(b'x' * 10000)

        result = utils.validate_video_file(unsupported_file)

        assert result['valid'] is False
        assert any('Unsupported extension' in issue for issue in result['issues'])

    @patch('hlsfield.utils.ffprobe_streams')
    def test_validate_no_video_stream(self, mock_ffprobe, temp_dir):
        """Тест файла без видео потока"""
        test_file = temp_dir / 'audio_only.mp4'
        test_file.write_bytes(b'x' * 10000)

        # Только аудио поток
        mock_ffprobe.return_value = {
            'streams': [{'codec_type': 'audio'}],
            'format': {}
        }

        result = utils.validate_video_file(test_file)

        assert result['valid'] is False
        assert 'No video stream found' in result['issues']


class TestUtilityFunctions:
    """Тесты вспомогательных функций"""

    def test_get_file_info(self, temp_dir):
        """Тест получения информации о файле"""
        test_file = temp_dir / 'info_test.mp4'
        test_content = b'test video content'
        test_file.write_bytes(test_content)

        info = utils.get_file_info(test_file)

        assert info['size'] == len(test_content)
        assert info['extension'] == '.mp4'
        assert info['name'] == 'info_test.mp4'
        assert info['stem'] == 'info_test'

    def test_get_file_info_missing(self, temp_dir):
        """Тест получения информации о несуществующем файле"""
        missing_file = temp_dir / 'missing.mp4'

        with pytest.raises(InvalidVideoError, match="does not exist"):
            utils.get_file_info(missing_file)

    def test_calculate_optimal_bitrates(self):
        """Тест расчета оптимальных битрейтов"""
        bitrates = utils.calculate_optimal_bitrates(1920, 1080, fps=30.0)

        assert 'low' in bitrates
        assert 'high' in bitrates
        assert bitrates['high'] > bitrates['medium'] > bitrates['low']

        # Все битрейты должны быть положительными
        assert all(br > 0 for br in bitrates.values())

    def test_calculate_optimal_bitrates_4k(self):
        """Тест расчета битрейтов для 4K"""
        bitrates_4k = utils.calculate_optimal_bitrates(3840, 2160, fps=60.0)
        bitrates_hd = utils.calculate_optimal_bitrates(1920, 1080, fps=30.0)

        # 4K при 60fps должен требовать больше битрейта чем HD при 30fps
        assert bitrates_4k['high'] > bitrates_hd['high']

    @patch('hlsfield.utils.run')
    def test_create_test_video(self, mock_run, temp_dir):
        """Тест создания тестового видео"""
        output_path = temp_dir / 'test_video.mp4'

        # Мокаем успешное создание файла
        def mock_create(*args, **kwargs):
            output_path.write_bytes(b'generated test video' * 1000)
            return Mock(returncode=0)

        mock_run.side_effect = mock_create

        result = utils.create_test_video(output_path, duration=5)

        assert result == output_path
        assert output_path.exists()

        # Проверяем параметры команды
        call_args = mock_run.call_args[0][0]
        assert 'testsrc' in ' '.join(call_args)
        assert 'duration=5' in ' '.join(call_args)

    def test_estimate_transcoding_time(self, temp_dir):
        """Тест оценки времени транскодинга"""
        test_file = temp_dir / 'estimate.mp4'
        test_file.write_bytes(b'x' * 10000)

        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        ]

        with patch('hlsfield.utils.analyze_video_complexity') as mock_analyze:
            mock_analyze.return_value = {
                'duration': 120.0,
                'complexity': 'medium',
                'estimated_transcode_time': 1.5
            }

            estimate = utils.estimate_transcoding_time(test_file, ladder)

        assert 'estimated_seconds' in estimate
        assert estimate['estimated_seconds'] > 0
        assert 'confidence' in estimate
        assert 'factors' in estimate

    def test_get_video_info_quick(self, temp_dir):
        """Тест быстрого получения информации о видео"""
        test_file = temp_dir / 'quick.mp4'
        test_file.write_bytes(b'x' * 5000)

        with patch('hlsfield.utils.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps({
                    "format": {
                        "duration": "60.5",
                        "size": "5000",
                        "bit_rate": "2000000",
                        "format_name": "mp4"
                    }
                })
            )

            info = utils.get_video_info_quick(test_file)

        assert info['duration'] == 60.5
        assert info['size'] == 5000
        assert info['bitrate'] == 2000000
        assert info['format_name'] == 'mp4'

    def test_get_video_info_quick_error_handling(self, temp_dir):
        """Тест обработки ошибок при быстром анализе"""
        test_file = temp_dir / 'error.mp4'
        test_file.write_bytes(b'x' * 5000)

        with patch('hlsfield.utils.run') as mock_run:
            mock_run.side_effect = Exception("FFprobe failed")

            info = utils.get_video_info_quick(test_file)

        # Должны получить значения по умолчанию
        assert info['duration'] == 0
        assert info['size'] == 0
        assert info['format_name'] == 'unknown'
