import os
import tempfile
import subprocess
from pathlib import Path


def create_test_video(duration=5, output_path=None):
    """
    Создает тестовое видео с помощью FFmpeg
    """
    if output_path is None:
        output_path = Path(tempfile.mktemp(suffix='.mp4'))

    # Команда для создания простого тестового видео
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', f'testsrc=duration={duration}:size=640x480:rate=30',
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-t', str(duration),
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Если FFmpeg недоступен, создаем минимальный валидный MP4
        return create_minimal_mp4(output_path)


def create_minimal_mp4(output_path):
    """
    Создает минимальный валидный MP4 файл
    """
    # Минимальный валидный MP4 заголовок + немного данных
    mp4_data = (
        b'\x00\x00\x00\x20ftypisom\x00\x00\x00\x01isomiso2avc1mp41'
        b'\x00\x00\x00\x00free'  # free atom
        b'\x00\x00\x02\x00mdat' + b'\x00' * 512  # mdat atom с данными
    )

    with open(output_path, 'wb') as f:
        f.write(mp4_data)

    return output_path


def get_test_video_content():
    """
    Возвращает содержимое тестового видеофайла
    """
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        video_path = create_minimal_mp4(Path(tmp.name))

        with open(video_path, 'rb') as f:
            content = f.read()

        os.unlink(video_path)
        return content
