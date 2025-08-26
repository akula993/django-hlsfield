"""
Интеграционные тесты с реальным ffmpeg
"""

import pytest
import subprocess
from pathlib import Path
from hlsfield.utils import ffprobe_streams, transcode_hls_variants


@pytest.mark.integration
class TestFFmpegIntegration:
    """Интеграционные тесты с реальным ffmpeg"""

    def test_ffmpeg_available(self):
        """Проверка что ffmpeg доступен"""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                    capture_output=True, timeout=10)
            assert result.returncode == 0
        except FileNotFoundError:
            pytest.skip("ffmpeg not found in PATH")

    def test_ffprobe_available(self):
        """Проверка что ffprobe доступен"""
        try:
            result = subprocess.run(['ffprobe', '-version'],
                                    capture_output=True, timeout=10)
            assert result.returncode == 0
        except FileNotFoundError:
            pytest.skip("ffprobe not found in PATH")

    @pytest.mark.slow
    def test_create_test_video(self, tmp_path):
        """Создание тестового видео через ffmpeg"""
        video_path = tmp_path / "test_video.mp4"

        # Создаем простое тестовое видео: цветной экран 5 секунд
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi',
            '-i', 'testsrc=duration=5:size=320x240:rate=30',
            '-f', 'lavfi',
            '-i', 'sine=frequency=1000:duration=5',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-t', '5',
            str(video_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            assert result.returncode == 0
            assert video_path.exists()
            assert video_path.stat().st_size > 1000  # Файл не пустой
        except FileNotFoundError:
            pytest.skip("ffmpeg not available for integration tests")

        return video_path

    @pytest.mark.slow
    def test_ffprobe_real_video(self, tmp_path):
        """Тест ffprobe с реальным видео"""
        video_path = self.test_create_test_video(tmp_path)

        info = ffprobe_streams(video_path)

        # Проверяем что получили корректную информацию
        assert 'streams' in info
        assert 'format' in info
        assert len(info['streams']) >= 1  # Минимум видео поток

        # Проверяем видео поток
        video_stream = next((s for s in info['streams']
                             if s.get('codec_type') == 'video'), None)
        assert video_stream is not None
        assert video_stream['width'] == 320
        assert video_stream['height'] == 240

    @pytest.mark.slow
    def test_hls_transcoding_integration(self, tmp_path):
        """Интеграционный тест HLS транскодинга"""

        # Создаем тестовое видео
        input_video = self.test_create_test_video(tmp_path)

        # Настраиваем HLS транскодинг
        output_dir = tmp_path / "hls_output"
        output_dir.mkdir()

        ladder = [
            {"height": 240, "v_bitrate": 400, "a_bitrate": 64},
            {"height": 360, "v_bitrate": 800, "a_bitrate": 96}
        ]

        # Запускаем транскодинг
        master_playlist = transcode_hls_variants(
            input_path=input_video,
            out_dir=output_dir,
            ladder=ladder,
            segment_duration=2
        )

        # Проверяем результат
        assert master_playlist.exists()
        assert master_playlist.name == "master.m3u8"

        # Проверяем что созданы директории качеств
        assert (output_dir / "v240").exists()
        assert (output_dir / "v360").exists()

        # Проверяем плейлисты качеств
        assert (output_dir / "v240" / "index.m3u8").exists()
        assert (output_dir / "v360" / "index.m3u8").exists()

        # Проверяем что созданы TS сегменты
        ts_files_240 = list((output_dir / "v240").glob("*.ts"))
        ts_files_360 = list((output_dir / "v360").glob("*.ts"))

        assert len(ts_files_240) > 0
        assert len(ts_files_360) > 0

        # Проверяем содержимое master плейлиста
        master_content = master_playlist.read_text()
        assert "#EXTM3U" in master_content
        assert "v240/index.m3u8" in master_content
        assert "v360/index.m3u8" in master_content
        assert "BANDWIDTH=" in master_content

