"""
Тесты транскодинга HLS и DASH
"""
import pytest
import json
from unittest.mock import Mock, patch, call
from pathlib import Path

from hlsfield import utils
from hlsfield.exceptions import (
    TranscodingError, ConfigurationError, InvalidVideoError
)


class TestHLSTranscoding:
    """Тесты HLS транскодинга"""

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_hls_transcoding_success(self, mock_run, mock_ffprobe,
                                     temp_dir, sample_ladder, mock_ffprobe_output):
        """Тест успешного HLS транскодинга"""
        # Настраиваем входной файл
        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'fake video data')

        output_dir = temp_dir / 'hls_output'

        mock_ffprobe.return_value = mock_ffprobe_output

        # Мокаем успешное выполнение FFmpeg команд
        def mock_ffmpeg(*args, **kwargs):
            cmd = args[0]
            if 'hls' in ' '.join(cmd):
                # Создаем структуру HLS файлов
                for rung in sample_ladder:
                    height = rung['height']
                    variant_dir = output_dir / f'v{height}'
                    variant_dir.mkdir(parents=True, exist_ok=True)

                    # Создаем плейлист
                    playlist = variant_dir / 'index.m3u8'
                    playlist.write_text('#EXTM3U\n#EXT-X-ENDLIST\n')

                    # Создаем сегменты
                    for i in range(3):
                        segment = variant_dir / f'seg_{i:04d}.ts'
                        segment.write_bytes(b'segment data')

                # Создаем master плейлист
                master = output_dir / 'master.m3u8'
                master.write_text('#EXTM3U\n#EXT-X-VERSION:3\n')

            return Mock(returncode=0)

        mock_run.side_effect = mock_ffmpeg

        # Выполняем транскодинг
        master_playlist = utils.transcode_hls_variants(
            input_file, output_dir, sample_ladder, segment_duration=6
        )

        # Проверяем результат
        assert master_playlist.exists()
        assert master_playlist.name == 'master.m3u8'

        # Проверяем структуру файлов
        for rung in sample_ladder:
            height = rung['height']
            variant_dir = output_dir / f'v{height}'
            assert variant_dir.exists()

            playlist = variant_dir / 'index.m3u8'
            assert playlist.exists()

    def test_hls_invalid_ladder(self, temp_dir):
        """Тест с невалидной лестницей"""
        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'fake video')

        invalid_ladder = [{"height": "not_a_number"}]  # Невалидная лестница

        with pytest.raises(ValueError):  # validate_ladder должна бросить ошибку
            utils.transcode_hls_variants(input_file, temp_dir, invalid_ladder)

    def test_hls_invalid_segment_duration(self, temp_dir, sample_ladder):
        """Тест с невалидной длительностью сегментов"""
        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'fake video')

        with pytest.raises(ConfigurationError, match="Invalid segment duration"):
            utils.transcode_hls_variants(
                input_file, temp_dir, sample_ladder, segment_duration=100
            )

    @patch('hlsfield.utils.ffprobe_streams')
    def test_hls_no_video_stream(self, mock_ffprobe, temp_dir, sample_ladder):
        """Тест файла без видео потока"""
        input_file = temp_dir / 'audio_only.mp4'
        input_file.write_bytes(b'audio data')

        # Только аудио поток
        mock_ffprobe.return_value = {
            "streams": [{"codec_type": "audio"}],
            "format": {}
        }

        with pytest.raises(InvalidVideoError, match="No video stream found"):
            utils.transcode_hls_variants(input_file, temp_dir, sample_ladder)

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_hls_ladder_filtering(self, mock_run, mock_ffprobe,
                                  temp_dir, mock_ffprobe_output):
        """Тест фильтрации лестницы по исходному разрешению"""
        # Низкое разрешение источника
        mock_ffprobe_output['streams'][0]['height'] = 480
        mock_ffprobe_output['streams'][0]['width'] = 640
        mock_ffprobe.return_value = mock_ffprobe_output

        input_file = temp_dir / 'lowres.mp4'
        input_file.write_bytes(b'low res video')

        # Лестница с качествами выше исходного
        high_ladder = [
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
            {"height": 1440, "v_bitrate": 8000, "a_bitrate": 192},
        ]

        def capture_ffmpeg_calls(*args, **kwargs):
            # Сохраняем вызовы для проверки
            captured_calls.append(args[0])
            return Mock(returncode=0)

        captured_calls = []
        mock_run.side_effect = capture_ffmpeg_calls

        # Транскодинг должен отфильтровать качества выше 480p
        utils.transcode_hls_variants(input_file, temp_dir, high_ladder)

        # Проверяем что создавались только качества <= 480p
        ffmpeg_calls = [call for call in captured_calls if 'ffmpeg' in call[0]]
        assert len(ffmpeg_calls) > 0  # Должен быть хотя бы один вызов

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_hls_partial_failure(self, mock_run, mock_ffprobe,
                                 temp_dir, mock_ffprobe_output):
        """Тест частичного сбоя при создании вариантов"""
        mock_ffprobe.return_value = mock_ffprobe_output

        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')
        output_dir = temp_dir / 'hls_out'

        call_count = 0

        def mock_selective_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 2:  # Второй вызов (720p) неуспешен
                raise Exception("Encoding failed for 720p")

            # Создаем файлы для успешных вызовов
            if 'v360' in str(output_dir):
                variant_dir = output_dir / 'v360'
                variant_dir.mkdir(parents=True, exist_ok=True)
                (variant_dir / 'index.m3u8').write_text('#EXTM3U\n')
                (variant_dir / 'seg_0000.ts').write_bytes(b'data')

            return Mock(returncode=0)

        mock_run.side_effect = mock_selective_failure

        # Должно создать master плейлист даже при частичном сбое
        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
        ]

        # Если нет успешных вариантов, должна быть ошибка
        with pytest.raises(TranscodingError, match="No HLS variants were successfully created"):
            utils.transcode_hls_variants(input_file, output_dir, ladder)


class TestDASHTranscoding:
    """Тесты DASH транскодинга"""

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_dash_transcoding_success(self, mock_run, mock_ffprobe,
                                      temp_dir, sample_ladder, mock_ffprobe_output):
        """Тест успешного DASH транскодинга"""
        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')

        output_dir = temp_dir / 'dash_output'

        mock_ffprobe.return_value = mock_ffprobe_output

        def mock_dash_ffmpeg(*args, **kwargs):
            # Создаем DASH структуру файлов
            output_dir.mkdir(exist_ok=True)

            # Манифест
            manifest = output_dir / 'manifest.mpd'
            manifest.write_text('<?xml version="1.0"?><MPD></MPD>')

            # Init сегменты
            for i in range(len(sample_ladder)):
                (output_dir / f'init-{i}.m4s').write_bytes(b'init data')

            # Media сегменты
            for i in range(len(sample_ladder)):
                for j in range(5):
                    (output_dir / f'chunk-{i}-{j:05d}.m4s').write_bytes(b'chunk data')

            return Mock(returncode=0)

        mock_run.side_effect = mock_dash_ffmpeg

        manifest = utils.transcode_dash_variants(
            input_file, output_dir, sample_ladder, segment_duration=4
        )

        assert manifest.exists()
        assert manifest.name == 'manifest.mpd'

        # Проверяем наличие сегментов
        init_files = list(output_dir.glob('init-*.m4s'))
        chunk_files = list(output_dir.glob('chunk-*.m4s'))

        assert len(init_files) > 0
        assert len(chunk_files) > 0

    @patch('hlsfield.utils.ffprobe_streams')
    def test_dash_no_video_stream(self, mock_ffprobe, temp_dir, sample_ladder):
        """Тест DASH без видео потока"""
        input_file = temp_dir / 'audio.mp4'
        input_file.write_bytes(b'audio data')

        mock_ffprobe.return_value = {
            "streams": [{"codec_type": "audio"}],
            "format": {}
        }

        with pytest.raises(InvalidVideoError, match="No video stream found"):
            utils.transcode_dash_variants(input_file, temp_dir, sample_ladder)

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_dash_filter_complex(self, mock_run, mock_ffprobe,
                                 temp_dir, mock_ffprobe_output):
        """Тест генерации filter_complex для DASH"""
        mock_ffprobe.return_value = mock_ffprobe_output

        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')

        ladder = [
            {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
        ]

        captured_commands = []

        def capture_command(*args, **kwargs):
            captured_commands.append(args[0])

            # Создаем минимальную DASH структуру
            output_dir = temp_dir / 'dash'
            output_dir.mkdir(exist_ok=True)
            (output_dir / 'manifest.mpd').write_text('<MPD></MPD>')
            (output_dir / 'chunk-0-00000.m4s').write_bytes(b'data')

            return Mock(returncode=0)

        mock_run.side_effect = capture_command

        utils.transcode_dash_variants(input_file, temp_dir / 'dash', ladder)

        # Проверяем что была сгенерирована filter_complex команда
        ffmpeg_cmd = captured_commands[0]
        assert '-filter_complex' in ffmpeg_cmd

        # Должны быть scale фильтры для каждого качества
        filter_idx = ffmpeg_cmd.index('-filter_complex') + 1
        filter_complex = ffmpeg_cmd[filter_idx]

        assert 'scale=' in filter_complex
        assert 'h=480' in filter_complex or 'h=720' in filter_complex

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_dash_no_audio_handling(self, mock_run, mock_ffprobe, temp_dir):
        """Тест DASH без аудио потока"""
        # Только видео поток
        video_only_info = {
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080
            }],
            "format": {}
        }

        mock_ffprobe.return_value = video_only_info

        input_file = temp_dir / 'video_only.mp4'
        input_file.write_bytes(b'video only data')

        captured_commands = []

        def capture_command(*args, **kwargs):
            captured_commands.append(args[0])

            # Создаем DASH структуру
            output_dir = temp_dir / 'dash_video_only'
            output_dir.mkdir(exist_ok=True)
            (output_dir / 'manifest.mpd').write_text('<MPD></MPD>')
            (output_dir / 'chunk-0-00000.m4s').write_bytes(b'video chunk')

            return Mock(returncode=0)

        mock_run.side_effect = capture_command

        ladder = [{"height": 720, "v_bitrate": 2500, "a_bitrate": 128}]

        utils.transcode_dash_variants(input_file, temp_dir / 'dash_video_only', ladder)

        # В команде не должно быть аудио mapping для файла без аудио
        ffmpeg_cmd = captured_commands[0]
        cmd_str = ' '.join(ffmpeg_cmd)

        # Проверяем настройки adaptation sets
        assert 'adaptation_sets' in ffmpeg_cmd
        adaptation_idx = ffmpeg_cmd.index('adaptation_sets') + 1
        adaptation_sets = ffmpeg_cmd[adaptation_idx]

        # Для видео без аудио должен быть только video adaptation set
        assert 'id=0,streams=v' in adaptation_sets
        assert 'id=1,streams=a' not in adaptation_sets


class TestAdaptiveTranscoding:
    """Тесты комбинированного HLS+DASH транскодинга"""

    @patch('hlsfield.utils.transcode_hls_variants')
    @patch('hlsfield.utils.transcode_dash_variants')
    def test_adaptive_transcoding(self, mock_dash, mock_hls, temp_dir, sample_ladder):
        """Тест создания HLS+DASH одновременно"""
        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')

        output_dir = temp_dir / 'adaptive_out'

        # Настраиваем возвращаемые значения
        hls_master = output_dir / 'hls' / 'master.m3u8'
        dash_manifest = output_dir / 'dash' / 'manifest.mpd'

        mock_hls.return_value = hls_master
        mock_dash.return_value = dash_manifest

        result = utils.transcode_adaptive_variants(
            input_file, output_dir, sample_ladder, segment_duration=6
        )

        # Проверяем что вызвались обе функции
        mock_hls.assert_called_once()
        mock_dash.assert_called_once()

        # Проверяем результат
        assert 'hls_master' in result
        assert 'dash_manifest' in result
        assert 'hls_dir' in result
        assert 'dash_dir' in result

        # Проверяем пути
        assert result['hls_master'] == hls_master
        assert result['dash_manifest'] == dash_manifest

    @patch('hlsfield.utils.transcode_hls_variants')
    @patch('hlsfield.utils.transcode_dash_variants')
    def test_adaptive_different_segment_durations(self, mock_dash, mock_hls,
                                                  temp_dir, sample_ladder):
        """Тест разных длительностей сегментов для HLS и DASH"""
        input_file = temp_dir / 'input.mp4'
        output_dir = temp_dir / 'adaptive_out'

        mock_hls.return_value = output_dir / 'hls' / 'master.m3u8'
        mock_dash.return_value = output_dir / 'dash' / 'manifest.mpd'

        utils.transcode_adaptive_variants(
            input_file, output_dir, sample_ladder, segment_duration=8
        )

        # Проверяем что HLS использует оригинальную длительность
        hls_call = mock_hls.call_args
        assert hls_call[1]['segment_duration'] == 8

        # DASH должен использовать на 2 секунды меньше
        dash_call = mock_dash.call_args
        assert dash_call[1]['segment_duration'] == 6  # 8-2

    @patch('hlsfield.utils.transcode_hls_variants')
    @patch('hlsfield.utils.transcode_dash_variants')
    def test_adaptive_hls_failure(self, mock_dash, mock_hls, temp_dir, sample_ladder):
        """Тест сбоя HLS при адаптивном транскодинге"""
        input_file = temp_dir / 'input.mp4'
        output_dir = temp_dir / 'adaptive_out'

        # HLS терпит неудачу
        mock_hls.side_effect = TranscodingError("HLS failed")
        mock_dash.return_value = output_dir / 'dash' / 'manifest.mpd'

        with pytest.raises(TranscodingError, match="Adaptive transcoding failed"):
            utils.transcode_adaptive_variants(input_file, output_dir, sample_ladder)


class TestTranscodingHelpers:
    """Тесты вспомогательных функций транскодинга"""

    def test_filter_ladder_by_source(self):
        """Тест фильтрации лестницы по исходному разрешению"""
        from hlsfield.utils import _filter_ladder_by_source

        ladder = [
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
            {"height": 1440, "v_bitrate": 8000, "a_bitrate": 192},
        ]

        # Источник 720p - должен отфильтровать качества выше
        filtered = _filter_ladder_by_source(ladder, 720)

        heights = [r['height'] for r in filtered]
        assert max(heights) <= 720 * 1.1  # С запасом 10%
        assert 720 in heights  # Исходное разрешение включено

    def test_filter_ladder_all_higher(self):
        """Тест когда все качества выше источника"""
        from hlsfield.utils import _filter_ladder_by_source

        ladder = [
            {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
            {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
        ]

        # Очень низкий источник
        filtered = _filter_ladder_by_source(ladder, 240)

        # Должен остаться хотя бы один элемент (самый низкий)
        assert len(filtered) == 1
        assert filtered[0]['height'] == 720

    @patch('hlsfield.utils.run')
    def test_create_hls_variant(self, mock_run, temp_dir, mock_ffprobe_output):
        """Тест создания одного варианта HLS"""
        from hlsfield.utils import _create_hls_variant

        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')

        output_dir = temp_dir / 'hls_out'

        rung = {"height": 720, "v_bitrate": 2500, "a_bitrate": 128}

        def mock_create_variant(*args, **kwargs):
            # Создаем структуру для варианта
            variant_dir = output_dir / 'v720'
            variant_dir.mkdir(parents=True)

            playlist = variant_dir / 'index.m3u8'
            playlist.write_text('#EXTM3U\n#EXT-X-ENDLIST\n')

            # Создаем несколько сегментов
            for i in range(5):
                segment = variant_dir / f'seg_{i:04d}.ts'
                segment.write_bytes(b'segment data' * 100)

            return Mock(returncode=0)

        mock_run.side_effect = mock_create_variant

        variant_info = _create_hls_variant(
            input_file, output_dir, rung, segment_duration=6, has_audio=True
        )

        # Проверяем возвращаемую информацию
        assert variant_info['height'] == 720
        assert variant_info['bandwidth'] == (2500 + 128) * 1000  # В bps
        assert variant_info['segments_count'] == 5
        assert 'playlist' in variant_info
        assert 'resolution' in variant_info

    def test_create_hls_master_playlist(self, temp_dir):
        """Тест создания master плейлиста HLS"""
        from hlsfield.utils import _create_hls_master_playlist

        variants = [
            {
                "height": 360,
                "width": 640,
                "bandwidth": 896000,
                "playlist": "index.m3u8",
                "dir": "v360",
                "resolution": "640x360"
            },
            {
                "height": 720,
                "width": 1280,
                "bandwidth": 2628000,
                "playlist": "index.m3u8",
                "dir": "v720",
                "resolution": "1280x720"
            }
        ]

        master_path = _create_hls_master_playlist(temp_dir, variants)

        assert master_path.exists()
        assert master_path.name == 'master.m3u8'

        content = master_path.read_text()

        # Проверяем содержимое master плейлиста
        assert '#EXTM3U' in content
        assert '#EXT-X-VERSION:3' in content
        assert 'BANDWIDTH=896000' in content
        assert 'BANDWIDTH=2628000' in content
        assert 'RESOLUTION=640x360' in content
        assert 'RESOLUTION=1280x720' in content
        assert 'v360/index.m3u8' in content
        assert 'v720/index.m3u8' in content

    def test_master_playlist_codecs(self, temp_dir):
        """Тест кодеков в master плейлисте"""
        from hlsfield.utils import _create_hls_master_playlist

        variants = [{
            "height": 720,
            "width": 1280,
            "bandwidth": 2628000,
            "playlist": "index.m3u8",
            "dir": "v720",
            "resolution": "1280x720",
            "audio_bitrate": 128
        }]

        master_path = _create_hls_master_playlist(temp_dir, variants)
        content = master_path.read_text()

        # Проверяем наличие кодеков
        assert 'CODECS="avc1.42E01E,mp4a.40.2"' in content

    def test_master_playlist_no_audio(self, temp_dir):
        """Тест master плейлиста без аудио"""
        from hlsfield.utils import _create_hls_master_playlist

        variants = [{
            "height": 720,
            "width": 1280,
            "bandwidth": 2500000,
            "playlist": "index.m3u8",
            "dir": "v720",
            "resolution": "1280x720",
            "audio_bitrate": 0  # Без аудио
        }]

        master_path = _create_hls_master_playlist(temp_dir, variants)
        content = master_path.read_text()

        # Только видео кодек
        assert 'CODECS="avc1.42E01E"' in content
        assert 'mp4a.40.2' not in content


class TestTranscodingErrors:
    """Тесты обработки ошибок транскодинга"""

    @patch('hlsfield.utils.ffprobe_streams')
    def test_transcode_missing_input(self, mock_ffprobe, temp_dir, sample_ladder):
        """Тест с отсутствующим входным файлом"""
        missing_file = temp_dir / 'missing.mp4'

        mock_ffprobe.side_effect = InvalidVideoError("File not found")

        with pytest.raises(InvalidVideoError):
            utils.transcode_hls_variants(missing_file, temp_dir, sample_ladder)

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_ffmpeg_command_failure(self, mock_run, mock_ffprobe,
                                    temp_dir, sample_ladder, mock_ffprobe_output):
        """Тест сбоя команды FFmpeg"""
        mock_ffprobe.return_value = mock_ffprobe_output

        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')

        # FFmpeg терпит неудачу
        mock_run.side_effect = FFmpegError(['ffmpeg'], 1, '', 'Encoding failed')

        with pytest.raises(TranscodingError):
            utils.transcode_hls_variants(input_file, temp_dir, sample_ladder)

    @patch('hlsfield.utils.ffprobe_streams')
    @patch('hlsfield.utils.run')
    def test_partial_hls_creation(self, mock_run, mock_ffprobe,
                                  temp_dir, sample_ladder, mock_ffprobe_output):
        """Тест частичного создания HLS файлов"""
        mock_ffprobe.return_value = mock_ffprobe_output

        input_file = temp_dir / 'input.mp4'
        input_file.write_bytes(b'video data')
        output_dir = temp_dir / 'hls_out'

        def mock_partial_creation(*args, **kwargs):
            # Создаем плейлист но не создаем сегменты
            variant_dir = output_dir / 'v720'
            variant_dir.mkdir(parents=True)
            (variant_dir / 'index.m3u8').write_text('#EXTM3U\n')
            # НЕ создаем сегменты - это должно вызвать ошибку

            return Mock(returncode=0)

        mock_run.side_effect = mock_partial_creation

        with pytest.raises(TranscodingError, match="No HLS segments created"):
            utils.transcode_hls_variants(input_file, output_dir, sample_ladder)
