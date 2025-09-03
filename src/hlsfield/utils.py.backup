"""
🛠️ Утилиты для работы с FFmpeg и видео обработкой

Этот модуль содержит все низкоуровневые функции для:
- Запуска FFmpeg команд
- Анализа видеофайлов через FFprobe
- Создания HLS и DASH стримов
- Извлечения превью кадров
- Работы с временными файлами и storage

Автор: akula993
Лицензия: MIT
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import defaults
from .exceptions import (
    FFmpegError,
    FFmpegNotFoundError,
    InvalidVideoError,
    StorageError,
    TimeoutError,
    TranscodingError,
    ConfigurationError
)

logger = logging.getLogger(__name__)


# ==============================================================================
# КОНТЕКСТНЫЕ МЕНЕДЖЕРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

@contextmanager
def tempdir(prefix: str = "hlsfield_"):
    """
    Контекстный менеджер для временных директорий.

    Args:
        prefix: Префикс для имени директории

    Yields:
        Path: Путь к временной директории
    """
    temp_base = defaults.TEMP_DIR or tempfile.gettempdir()
    temp_path = Path(tempfile.mkdtemp(prefix=prefix, dir=temp_base))

    try:
        logger.debug(f"Created temporary directory: {temp_path}")
        yield temp_path
    finally:
        try:
            if not defaults.KEEP_TEMP_FILES:
                shutil.rmtree(temp_path, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {temp_path}")
            else:
                logger.debug(f"Keeping temporary directory for debug: {temp_path}")
        except Exception as e:
            logger.warning(f"Could not clean up temporary directory {temp_path}: {e}")


def ensure_binary_available(binary_name: str, path: str) -> str:
    """
    Проверяет доступность бинарного файла.

    Args:
        binary_name: Имя бинарного файла для ошибок
        path: Путь к бинарному файлу

    Returns:
        str: Абсолютный путь к файлу

    Raises:
        FFmpegNotFoundError: Если файл не найден
    """
    # Проверяем абсолютный путь
    if os.path.isabs(path) and os.path.isfile(path) and os.access(path, os.X_OK):
        return path

    # Ищем в PATH
    full_path = shutil.which(path)
    if full_path:
        return full_path

    raise FFmpegNotFoundError(f"{binary_name} not found: {path}")


def get_file_info(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Получает базовую информацию о файле.

    Args:
        file_path: Путь к файлу

    Returns:
        dict: Информация о файле
    """
    path = Path(file_path)

    if not path.exists():
        raise InvalidVideoError(f"File does not exist: {path}")

    stat = path.stat()

    return {
        'size': stat.st_size,
        'mtime': stat.st_mtime,
        'extension': path.suffix.lower(),
        'name': path.name,
        'stem': path.stem,
    }


# ==============================================================================
# ВЫПОЛНЕНИЕ КОМАНД FFMPEG
# ==============================================================================

def run(cmd: List[str], timeout_sec: Optional[int] = None, log_output: bool = False) -> subprocess.CompletedProcess:
    """
    Выполняет команду с обработкой ошибок и таймаутами.

    Args:
        cmd: Список аргументов команды
        timeout_sec: Таймаут в секундах (None = использовать default)
        log_output: Логировать ли stdout/stderr

    Returns:
        CompletedProcess: Результат выполнения команды

    Raises:
        FFmpegNotFoundError: Если команда не найдена
        FFmpegError: Если команда завершилась с ошибкой
        TimeoutError: Если команда превысила таймаут
    """
    if not cmd:
        raise ValueError("Command cannot be empty")

    # Проверяем что команда существует
    binary_path = ensure_binary_available(cmd[0], cmd[0])
    cmd[0] = binary_path

    # Используем default таймаут если не указан
    if timeout_sec is None:
        timeout_sec = defaults.FFMPEG_TIMEOUT

    # Логируем команду
    cmd_str = ' '.join(cmd)
    logger.debug(f"Executing command: {cmd_str}")

    if defaults.SAVE_FFMPEG_LOGS:
        _save_command_to_log(cmd_str)

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False  # Не бросаем исключение на ненулевой код возврата
        )

        elapsed = time.time() - start_time
        logger.debug(f"Command completed in {elapsed:.2f}s with code {result.returncode}")

        # Логируем output если включено
        if log_output or defaults.VERBOSE_LOGGING:
            if result.stdout:
                logger.debug(f"STDOUT: {result.stdout}")
            if result.stderr:
                logger.debug(f"STDERR: {result.stderr}")

        # Проверяем код возврата
        if result.returncode != 0:
            _handle_ffmpeg_error(cmd, result.returncode, result.stdout, result.stderr)

        return result

    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout_sec}s: {cmd_str}")
        raise TimeoutError(f"Command timed out after {timeout_sec} seconds") from e

    except FileNotFoundError as e:
        raise FFmpegNotFoundError(cmd[0]) from e

    except Exception as e:
        logger.error(f"Unexpected error running command {cmd_str}: {e}")
        raise FFmpegError(cmd, -1, "", str(e)) from e


def _handle_ffmpeg_error(cmd: List[str], returncode: int, stdout: str, stderr: str):
    """Анализирует ошибки FFmpeg и бросает соответствующее исключение"""

    error_message = stderr.lower()

    # Анализируем типичные ошибки
    if "no such file or directory" in error_message:
        raise InvalidVideoError("Input file not found or inaccessible")

    if "invalid data found" in error_message or "moov atom not found" in error_message:
        raise InvalidVideoError("File is corrupted or not a valid video")

    if "permission denied" in error_message:
        raise StorageError("Permission denied accessing file")

    if "no space left" in error_message or "disk full" in error_message:
        raise StorageError("Insufficient disk space")

    if "unknown encoder" in error_message or "encoder not found" in error_message:
        raise ConfigurationError("Required encoder not available in FFmpeg")

    if "protocol not found" in error_message:
        raise ConfigurationError("Network protocol not supported")

    if "memory" in error_message and "allocate" in error_message:
        raise TranscodingError("Out of memory during transcoding")

    # Общая ошибка FFmpeg
    raise FFmpegError(cmd, returncode, stdout, stderr)


def _save_command_to_log(cmd_str: str):
    """Сохраняет команду в лог-файл для отладки"""

    try:
        log_dir = Path(defaults.FFMPEG_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"ffmpeg_{int(time.time())}.log"

        with log_file.open('w') as f:
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Command: {cmd_str}\n\n")

    except Exception as e:
        logger.warning(f"Could not save FFmpeg command to log: {e}")


# ==============================================================================
# АНАЛИЗ ВИДЕОФАЙЛОВ ЧЕРЕЗ FFPROBE
# ==============================================================================

def ffprobe_streams(input_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Анализирует видеофайл и возвращает информацию о потоках.

    Args:
        input_path: Путь к видеофайлу

    Returns:
        dict: Информация о потоках и формате

    Raises:
        InvalidVideoError: Если файл не является видео или поврежден
        FFmpegNotFoundError: Если ffprobe не найден
    """
    cmd = [
        defaults.FFPROBE,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path)
    ]

    try:
        result = run(cmd, timeout_sec=30)  # Короткий таймаут для анализа

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ffprobe output: {result.stdout}")
            raise InvalidVideoError("FFprobe returned invalid JSON") from e

        # Проверяем что получили валидные данные
        if 'streams' not in data:
            raise InvalidVideoError("No streams found in video file")

        return data

    except FFmpegError as e:
        # Анализируем ошибку ffprobe более детально
        if "Invalid data found" in str(e):
            raise InvalidVideoError("File is not a valid video or is corrupted") from e
        elif "No such file" in str(e):
            raise InvalidVideoError(f"Video file not found: {input_path}") from e
        else:
            raise InvalidVideoError(f"Cannot analyze video file: {e}") from e


def pick_video_audio_streams(info: Dict[str, Any]) -> tuple[Optional[Dict], Optional[Dict]]:
    """
    Выбирает основные видео и аудио потоки из информации ffprobe.

    Args:
        info: Результат ffprobe_streams()

    Returns:
        tuple: (video_stream, audio_stream) или (None, None) если не найдены
    """
    video_stream = None
    audio_stream = None

    streams = info.get("streams", [])

    # Ищем потоки в порядке приоритета
    for stream in streams:
        codec_type = stream.get("codec_type")

        # Берем первый найденный видео поток
        if codec_type == "video" and video_stream is None:
            video_stream = stream

        # Берем первый найденный аудио поток
        if codec_type == "audio" and audio_stream is None:
            audio_stream = stream

    return video_stream, audio_stream


def analyze_video_complexity(input_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Анализирует сложность видео для определения оптимальных параметров кодирования.

    Args:
        input_path: Путь к видеофайлу

    Returns:
        dict: Анализ сложности видео
    """
    try:
        info = ffprobe_streams(input_path)
        video_stream, audio_stream = pick_video_audio_streams(info)

        analysis = {
            'has_video': video_stream is not None,
            'has_audio': audio_stream is not None,
            'complexity': 'medium',  # default
            'recommended_preset': 'veryfast',
            'estimated_transcode_time': 1.0,  # множитель от длительности
        }

        if video_stream:
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            # Оцениваем сложность по разрешению
            pixels = width * height

            if pixels > 1920 * 1080:  # > FullHD
                analysis['complexity'] = 'high'
                analysis['recommended_preset'] = 'fast'
                analysis['estimated_transcode_time'] = 2.0
            elif pixels < 640 * 480:  # < VGA
                analysis['complexity'] = 'low'
                analysis['recommended_preset'] = 'medium'
                analysis['estimated_transcode_time'] = 0.5

            # Анализируем битрейт если доступен
            if 'bit_rate' in video_stream:
                bitrate = int(video_stream['bit_rate'])
                if bitrate > 10_000_000:  # > 10 Mbps
                    analysis['complexity'] = 'high'
                    analysis['estimated_transcode_time'] *= 1.5

        # Учитываем длительность
        if format_info := info.get('format'):
            try:
                duration = float(format_info.get('duration', 0))
                analysis['duration'] = duration

                # Для очень длинных видео увеличиваем время
                if duration > 3600:  # > 1 час
                    analysis['estimated_transcode_time'] *= 1.2

            except (ValueError, TypeError):
                pass

        return analysis

    except Exception as e:
        logger.warning(f"Could not analyze video complexity: {e}")
        return {
            'has_video': True,
            'has_audio': True,
            'complexity': 'medium',
            'recommended_preset': 'veryfast',
            'estimated_transcode_time': 1.0,
        }


# ==============================================================================
# ИЗВЛЕЧЕНИЕ ПРЕВЬЮ КАДРОВ
# ==============================================================================

def extract_preview(input_path: Path, out_image: Path, at_sec: float = 3.0,
                    width: Optional[int] = None, height: Optional[int] = None) -> Path:
    """
    Извлекает превью кадр из видео с retry логикой.

    Args:
        input_path: Путь к исходному видео
        out_image: Путь для сохранения превью
        at_sec: Время извлечения кадра в секундах
        width: Ширина превью (None = оригинальная)
        height: Высота превью (None = оригинальная)

    Returns:
        Path: Путь к созданному превью

    Raises:
        TranscodingError: Если не удалось создать превью
    """
    max_attempts = 3
    attempt_times = [at_sec, 1.0, 0.0]  # Пробуем разное время

    for attempt in range(max_attempts):
        try:
            seek_time = attempt_times[attempt] if attempt < len(attempt_times) else attempt

            cmd = [
                defaults.FFMPEG, "-y",
                "-ss", str(seek_time),
                "-i", str(input_path),
                "-frames:v", "1",
                "-q:v", "2",  # Высокое качество JPEG
                "-f", "image2"
            ]

            # Добавляем масштабирование если нужно
            if width or height:
                if width and height:
                    scale = f"scale={width}:{height}"
                elif width:
                    scale = f"scale={width}:-1"  # Сохраняем соотношение сторон
                else:
                    scale = f"scale=-1:{height}"

                cmd.extend(["-vf", scale])

            cmd.append(str(out_image))

            run(cmd, timeout_sec=60)

            # Проверяем что файл создан и не пустой
            if out_image.exists() and out_image.stat().st_size > 100:
                logger.debug(f"Preview extracted at {seek_time}s on attempt {attempt + 1}")
                return out_image
            else:
                logger.warning(f"Preview file too small on attempt {attempt + 1}")

        except Exception as e:
            logger.warning(f"Preview extraction attempt {attempt + 1} failed: {e}")

            # Очищаем неудачный файл
            if out_image.exists():
                try:
                    out_image.unlink()
                except:
                    pass

    raise TranscodingError(f"Failed to extract preview after {max_attempts} attempts")


def create_preview_sprites(input_path: Path, out_dir: Path,
                           interval: int = 10, sprite_cols: int = 10) -> Dict[str, Any]:
    """
    Создает спрайт превью для timeline navigation.

    Args:
        input_path: Путь к видео
        out_dir: Директория для сохранения спрайтов
        interval: Интервал между кадрами в секундах
        sprite_cols: Количество колонок в спрайте

    Returns:
        dict: Информация о созданных спрайтах
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Получаем длительность видео
    info = ffprobe_streams(input_path)
    duration = 0

    if format_info := info.get('format'):
        try:
            duration = float(format_info.get('duration', 0))
        except (ValueError, TypeError):
            pass

    if duration <= 0:
        raise TranscodingError("Cannot determine video duration for sprites")

    # Рассчитываем параметры спрайтов
    total_thumbs = int(duration // interval)
    sprite_rows = (total_thumbs + sprite_cols - 1) // sprite_cols

    sprites_info = {
        'interval': interval,
        'total_thumbs': total_thumbs,
        'sprite_cols': sprite_cols,
        'sprite_rows': sprite_rows,
        'sprites': []
    }

    # Создаем отдельные кадры
    thumbs_dir = out_dir / "thumbs"
    thumbs_dir.mkdir(exist_ok=True)

    cmd = [
        defaults.FFMPEG, "-y",
        "-i", str(input_path),
        "-vf", f"fps=1/{interval},scale=160:90",  # Маленькие превью
        "-q:v", "5",
        str(thumbs_dir / "thumb_%04d.jpg")
    ]

    run(cmd, timeout_sec=int(duration * 0.1) + 60)

    # Объединяем в спрайты
    thumb_files = sorted(thumbs_dir.glob("thumb_*.jpg"))

    for sprite_idx in range(sprite_rows):
        start_idx = sprite_idx * sprite_cols
        end_idx = min(start_idx + sprite_cols, len(thumb_files))

        if start_idx >= len(thumb_files):
            break

        sprite_thumbs = thumb_files[start_idx:end_idx]
        sprite_file = out_dir / f"sprite_{sprite_idx:04d}.jpg"

        # Создаем горизонтальный спрайт
        _create_sprite_from_thumbs(sprite_thumbs, sprite_file, sprite_cols, 1)

        sprites_info['sprites'].append({
            'file': sprite_file.name,
            'start_time': start_idx * interval,
            'end_time': (end_idx - 1) * interval,
            'thumbs_count': len(sprite_thumbs)
        })

    # Очищаем временные файлы
    shutil.rmtree(thumbs_dir, ignore_errors=True)

    return sprites_info


def _create_sprite_from_thumbs(thumb_files: List[Path], output: Path,
                               cols: int, rows: int):
    """Создает спрайт из отдельных превью изображений"""

    if not thumb_files:
        return

    # Используем ImageMagick если доступен, иначе FFmpeg
    if shutil.which('montage'):
        cmd = [
            'montage',
            *[str(f) for f in thumb_files],
            '-tile', f'{cols}x{rows}',
            '-geometry', '+0+0',
            str(output)
        ]
    else:
        # Fallback на FFmpeg (более сложная команда)
        inputs = []
        for f in thumb_files:
            inputs.extend(['-i', str(f)])

        filter_complex = f"hstack=inputs={len(thumb_files)}"

        cmd = [
            defaults.FFMPEG, "-y",
            *inputs,
            '-filter_complex', filter_complex,
            str(output)
        ]

    run(cmd, timeout_sec=60)


# ==============================================================================
# HLS ТРАНСКОДИНГ
# ==============================================================================

def transcode_hls_variants(input_path: Path, out_dir: Path,
                           ladder: List[Dict], segment_duration: int = 6) -> Path:
    """
    Создает HLS адаптивный стрим с несколькими качествами.

    Args:
        input_path: Путь к исходному видео
        out_dir: Директория для сохранения HLS файлов
        ladder: Лестница качеств
        segment_duration: Длительность сегментов в секундах

    Returns:
        Path: Путь к master.m3u8 плейлисту

    Raises:
        TranscodingError: При ошибках транскодинга
    """
    try:
        # Валидируем параметры
        from .fields import validate_ladder
        validate_ladder(ladder)

        if not (2 <= segment_duration <= 60):
            raise ConfigurationError(f"Invalid segment duration: {segment_duration}")

        # Создаем выходную директорию
        out_dir.mkdir(parents=True, exist_ok=True)

        # Анализируем исходное видео
        logger.info(f"Analyzing input video: {input_path}")
        info = ffprobe_streams(input_path)
        video_stream, audio_stream = pick_video_audio_streams(info)

        if not video_stream:
            raise InvalidVideoError("No video stream found in input file")

        has_audio = audio_stream is not None
        source_height = int(video_stream.get('height', 0))
        source_width = int(video_stream.get('width', 0))

        # Фильтруем лестницу - убираем качества выше исходного
        filtered_ladder = _filter_ladder_by_source(ladder, source_height)

        logger.info(f"Transcoding {len(filtered_ladder)} HLS variants for {source_width}x{source_height} video")

        # Создаем каждый вариант качества
        variant_infos = []
        failed_variants = []

        for rung in filtered_ladder:
            try:
                variant_info = _create_hls_variant(
                    input_path, out_dir, rung, segment_duration, has_audio
                )
                variant_infos.append(variant_info)

                logger.info(f"Created HLS variant: {variant_info['height']}p "
                            f"({variant_info['segments_count']} segments)")

            except Exception as e:
                logger.error(f"Failed to create {rung['height']}p HLS variant: {e}")
                failed_variants.append((rung['height'], str(e)))
                continue

        if not variant_infos:
            raise TranscodingError("No HLS variants were successfully created")

        if failed_variants:
            logger.warning(f"Some HLS variants failed: {failed_variants}")

        # Создаем master плейлист
        master_playlist = _create_hls_master_playlist(out_dir, variant_infos)

        logger.info(f"HLS master playlist created: {master_playlist} "
                    f"({len(variant_infos)} variants)")

        return master_playlist

    except Exception as e:
        logger.error(f"HLS transcoding failed: {e}")
        if isinstance(e, (TranscodingError, ConfigurationError, InvalidVideoError)):
            raise
        raise TranscodingError(f"HLS transcoding failed: {e}") from e


def _filter_ladder_by_source(ladder: List[Dict], source_height: int) -> List[Dict]:
    """Фильтрует лестницу качеств по исходному разрешению"""

    # Убираем качества выше исходного (с небольшим запасом)
    filtered = [r for r in ladder if r['height'] <= source_height * 1.1]

    # Если все качества больше источника - оставляем самое маленькое
    if not filtered:
        filtered = [min(ladder, key=lambda x: x['height'])]
        logger.warning(f"All ladder heights exceed source {source_height}p, using lowest")

    # Сортируем по возрастанию
    return sorted(filtered, key=lambda x: x['height'])


def _create_hls_variant(input_path: Path, out_dir: Path, rung: Dict,
                        segment_duration: int, has_audio: bool) -> Dict:
    """Создает один вариант качества HLS"""

    height = int(rung["height"])
    v_bitrate = int(rung["v_bitrate"])
    a_bitrate = int(rung["a_bitrate"]) if has_audio else 0

    # Создаем директорию для этого качества
    variant_dir = out_dir / f"v{height}"
    variant_dir.mkdir(exist_ok=True)

    playlist_file = variant_dir / "index.m3u8"

    # Строим команду FFmpeg
    cmd = [
        defaults.FFMPEG, "-y",
        "-i", str(input_path),
        "-map", "0:v:0",  # Видео поток
    ]

    # Видео фильтры и кодирование
    vf_parts = []

    # Масштабирование с сохранением соотношения сторон
    vf_parts.append(f"scale=w=-2:h={height}:force_original_aspect_ratio=decrease")

    # Padding до четных размеров (требование H.264)
    vf_parts.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")

    cmd.extend([
        "-vf", ",".join(vf_parts),
        "-c:v", "libx264",
        "-profile:v", defaults.H264_PROFILE,
        "-preset", defaults.FFMPEG_PRESET,
        "-b:v", f"{v_bitrate}k",
        "-maxrate", f"{int(v_bitrate * 1.07)}k",  # +7% burst
        "-bufsize", f"{v_bitrate * 2}k",
        "-pix_fmt", defaults.PIXEL_FORMAT,
        "-g", str(segment_duration * 30),  # GOP = segment * fps
        "-keyint_min", str(segment_duration * 30),
        "-sc_threshold", "0",  # Отключаем автоматические keyframes
    ])

    # Аудио кодирование
    if has_audio and a_bitrate > 0:
        cmd.extend([
            "-map", "0:a:0",
            "-c:a", defaults.AUDIO_CODEC,
            "-b:a", f"{a_bitrate}k",
            "-ac", str(defaults.AUDIO_CHANNELS),
            "-ar", str(defaults.AUDIO_SAMPLE_RATE),
        ])
    else:
        cmd.append("-an")  # Без аудио

    # HLS специфичные параметры
    cmd.extend([
        "-f", "hls",
        "-hls_time", str(segment_duration),
        "-hls_playlist_type", "vod",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", str(variant_dir / "seg_%04d.ts"),
        "-hls_flags", "single_file+independent_segments",
        str(playlist_file)
    ])

    # Оцениваем время выполнения
    complexity = analyze_video_complexity(input_path)
    estimated_time = int(complexity['estimated_transcode_time'] *
                         complexity.get('duration', 300))  # default 5 min
    timeout_sec = max(300, estimated_time * 2)  # минимум 5 минут

    # Выполняем транскодинг
    run(cmd, timeout_sec=timeout_sec)

    # Проверяем результат
    if not playlist_file.exists():
        raise TranscodingError(f"HLS playlist not created: {playlist_file}")

    segment_files = list(variant_dir.glob("seg_*.ts"))
    if not segment_files:
        raise TranscodingError(f"No HLS segments created in {variant_dir}")

    # Рассчитываем приблизительную ширину для master плейлиста
    approx_width = int((height * 16 / 9) // 2 * 2)  # 16:9 aspect ratio, четная ширина

    return {
        "height": height,
        "width": approx_width,
        "bandwidth": (v_bitrate + a_bitrate) * 1000,  # в bps
        "playlist": playlist_file.name,
        "dir": variant_dir.name,
        "resolution": f"{approx_width}x{height}",
        "segments_count": len(segment_files),
        "video_bitrate": v_bitrate,
        "audio_bitrate": a_bitrate,
    }


def _create_hls_master_playlist(out_dir: Path, variants: List[Dict]) -> Path:
    """Создает master.m3u8 плейлист"""

    master_file = out_dir / "master.m3u8"

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3"
    ]

    # Сортируем варианты по качеству (по возрастанию)
    sorted_variants = sorted(variants, key=lambda x: x["height"])

    for variant in sorted_variants:
        # EXT-X-STREAM-INF line
        stream_inf = f"#EXT-X-STREAM-INF:BANDWIDTH={variant['bandwidth']}"
        stream_inf += f",RESOLUTION={variant['resolution']}"

        # Добавляем кодеки для лучшей совместимости
        codecs = "avc1.42E01E"  # H.264 Baseline Profile
        if variant['audio_bitrate'] > 0:
            codecs += ",mp4a.40.2"  # AAC-LC
        stream_inf += f",CODECS=\"{codecs}\""

        lines.append(stream_inf)
        lines.append(f"{variant['dir']}/{variant['playlist']}")

    # Записываем файл
    master_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return master_file


# ==============================================================================
# DASH ТРАНСКОДИНГ
# ==============================================================================

def transcode_dash_variants(input_path: Path, out_dir: Path,
                            ladder: List[Dict], segment_duration: int = 4) -> Path:
    """
    Создает DASH адаптивный стрим.

    Args:
        input_path: Путь к исходному видео
        out_dir: Директория для DASH файлов
        ladder: Лестница качеств
        segment_duration: Длительность сегментов

    Returns:
        Path: Путь к manifest.mpd
    """
    try:
        from .fields import validate_ladder
        validate_ladder(ladder)

        out_dir.mkdir(parents=True, exist_ok=True)

        # Анализируем исходное видео
        info = ffprobe_streams(input_path)
        video_stream, audio_stream = pick_video_audio_streams(info)

        if not video_stream:
            raise InvalidVideoError("No video stream found")

        has_audio = audio_stream is not None
        source_height = int(video_stream.get('height', 0))

        # Фильтруем лестницу
        filtered_ladder = _filter_ladder_by_source(ladder, source_height)

        logger.info(f"Creating DASH with {len(filtered_ladder)} representations")

        # Создаем команду FFmpeg для DASH
        cmd = [
            defaults.FFMPEG, "-y",
            "-i", str(input_path)
        ]

        # Добавляем видео представления
        video_maps = []
        filter_complex_parts = []

        for i, rung in enumerate(filtered_ladder):
            height = int(rung["height"])
            v_bitrate = int(rung["v_bitrate"])

            # Фильтр масштабирования
            scale_filter = f"scale=w=-2:h={height}:force_original_aspect_ratio=decrease"
            pad_filter = "pad=ceil(iw/2)*2:ceil(ih/2)*2"

            filter_complex_parts.append(f"[0:v]{scale_filter},{pad_filter}[v{i}]")

            # Добавляем map для этого представления
            video_maps.extend(["-map", f"[v{i}]"])

            # Настройки кодирования для этого представления
            cmd.extend([
                f"-c:v:{i}", "libx264",
                f"-preset:v:{i}", defaults.FFMPEG_PRESET,
                f"-profile:v:{i}", defaults.H264_PROFILE,
                f"-b:v:{i}", f"{v_bitrate}k",
                f"-maxrate:v:{i}", f"{int(v_bitrate * 1.07)}k",
                f"-bufsize:v:{i}", f"{v_bitrate * 2}k",
                f"-pix_fmt:v:{i}", defaults.PIXEL_FORMAT,
            ])

        # Добавляем аудио представления если есть аудио
        if has_audio:
            for i, rung in enumerate(filtered_ladder):
                a_bitrate = int(rung["a_bitrate"])
                if a_bitrate > 0:
                    video_maps.extend(["-map", "0:a:0"])
                    cmd.extend([
                        f"-c:a:{i}", defaults.AUDIO_CODEC,
                        f"-b:a:{i}", f"{a_bitrate}k",
                        f"-ac:a:{i}", str(defaults.AUDIO_CHANNELS),
                        f"-ar:a:{i}", str(defaults.AUDIO_SAMPLE_RATE),
                    ])

        # Filter complex
        if filter_complex_parts:
            cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])

        # Добавляем все maps
        cmd.extend(video_maps)

        # DASH специфичные параметры
        manifest_file = out_dir / "manifest.mpd"

        cmd.extend([
            "-f", "dash",
            "-seg_duration", str(segment_duration),
            "-use_template", "1" if defaults._get_setting("HLSFIELD_DASH_USE_TEMPLATE", True) else "0",
            "-use_timeline", "1" if defaults._get_setting("HLSFIELD_DASH_USE_TIMELINE", True) else "0",
            "-init_seg_name", "init-$RepresentationID$.$ext$",
            "-media_seg_name", "chunk-$RepresentationID$-$Number%05d$.$ext$",
            "-adaptation_sets", "id=0,streams=v id=1,streams=a" if has_audio else "id=0,streams=v",
            str(manifest_file)
        ])

        # Выполняем транскодинг
        complexity = analyze_video_complexity(input_path)
        estimated_time = int(complexity['estimated_transcode_time'] *
                             complexity.get('duration', 300))
        timeout_sec = max(600, estimated_time * 2)  # DASH обычно дольше HLS

        run(cmd, timeout_sec=timeout_sec)

        # Проверяем результат
        if not manifest_file.exists():
            raise TranscodingError("DASH manifest not created")

        # Проверяем что созданы сегменты
        segment_files = list(out_dir.glob("chunk-*.m4s"))
        if not segment_files:
            raise TranscodingError("No DASH segments created")

        logger.info(f"DASH manifest created: {manifest_file} "
                    f"({len(segment_files)} segments)")

        return manifest_file

    except Exception as e:
        logger.error(f"DASH transcoding failed: {e}")
        if isinstance(e, (TranscodingError, ConfigurationError, InvalidVideoError)):
            raise
        raise TranscodingError(f"DASH transcoding failed: {e}") from e


# ==============================================================================
# КОМБИНИРОВАННЫЙ HLS + DASH ТРАНСКОДИНГ
# ==============================================================================

def transcode_adaptive_variants(input_path: Path, out_dir: Path,
                                ladder: List[Dict], segment_duration: int = 6) -> Dict[str, Path]:
    """
    Создает одновременно HLS и DASH стримы из одного источника.

    Args:
        input_path: Исходное видео
        out_dir: Базовая директория для вывода
        ladder: Лестница качеств
        segment_duration: Длительность сегментов

    Returns:
        dict: Пути к созданным манифестам
    """
    try:
        out_dir.mkdir(parents=True, exist_ok=True)

        hls_dir = out_dir / "hls"
        dash_dir = out_dir / "dash"

        logger.info(f"Starting adaptive transcoding (HLS + DASH) for {input_path.name}")

        # Создаем HLS
        logger.info("Creating HLS stream...")
        hls_master = transcode_hls_variants(input_path, hls_dir, ladder, segment_duration)

        # Создаем DASH (с немного меньшими сегментами для лучшей адаптации)
        logger.info("Creating DASH stream...")
        dash_segment_duration = max(2, segment_duration - 2)  # На 2 секунды меньше
        dash_manifest = transcode_dash_variants(input_path, dash_dir, ladder, dash_segment_duration)

        logger.info("Adaptive transcoding completed successfully")

        return {
            "hls_master": hls_master,
            "dash_manifest": dash_manifest,
            "hls_dir": hls_dir,
            "dash_dir": dash_dir,
        }

    except Exception as e:
        logger.error(f"Adaptive transcoding failed: {e}")
        if isinstance(e, (TranscodingError, ConfigurationError, InvalidVideoError)):
            raise
        raise TranscodingError(f"Adaptive transcoding failed: {e}") from e


# ==============================================================================
# РАБОТА СО STORAGE
# ==============================================================================

def pull_to_local(storage, name: str, dst_dir: Path) -> Path:
    """
    Загружает файл из storage в локальную временную директорию.

    Args:
        storage: Django storage backend
        name: Имя файла в storage
        dst_dir: Локальная директория назначения

    Returns:
        Path: Путь к локальному файлу

    Raises:
        StorageError: При ошибках загрузки
    """
    try:
        # Сначала пробуем получить прямой путь (для локального storage)
        try:
            direct_path = Path(storage.path(name))
            if direct_path.exists() and direct_path.is_file():
                logger.debug(f"Using direct file access: {direct_path}")
                return direct_path
        except (AttributeError, NotImplementedError):
            # Storage не поддерживает прямые пути
            pass

        # Копируем через storage API
        dst = dst_dir / Path(name).name

        logger.debug(f"Downloading {name} to {dst}")

        file_info = get_file_info_from_storage(storage, name)
        total_size = file_info.get('size', 0)

        with storage.open(name, "rb") as src:
            with dst.open("wb") as out:
                copied = 0
                chunk_size = min(defaults.IO_BUFFER_SIZE, 1024 * 1024)  # 1MB max
                last_log_time = time.time()

                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break

                    out.write(chunk)
                    copied += len(chunk)

                    # Логируем прогресс для больших файлов
                    now = time.time()
                    if total_size > 50 * 1024 * 1024 and now - last_log_time > 5:  # > 50MB, каждые 5 сек
                        progress = (copied / total_size * 100) if total_size > 0 else 0
                        logger.info(f"Download progress: {progress:.1f}% ({copied / (1024 * 1024):.1f}MB)")
                        last_log_time = now

        # Проверяем что файл загружен полностью
        if not dst.exists():
            raise StorageError(f"Downloaded file does not exist: {dst}")

        actual_size = dst.stat().st_size
        if actual_size == 0:
            raise StorageError(f"Downloaded file is empty: {dst}")

        if total_size > 0 and abs(actual_size - total_size) > 1024:  # допустимая погрешность 1KB
            logger.warning(f"Size mismatch: expected {total_size}, got {actual_size}")

        logger.debug(f"Successfully downloaded {actual_size} bytes")
        return dst

    except Exception as e:
        logger.error(f"Error pulling file {name}: {e}")

        # Очищаем частично скачанный файл
        if 'dst' in locals() and dst.exists():
            try:
                dst.unlink()
            except:
                pass

        if isinstance(e, StorageError):
            raise
        raise StorageError(f"Cannot download file {name}: {e}") from e


def get_file_info_from_storage(storage, name: str) -> Dict[str, Any]:
    """Получает информацию о файле из storage"""

    info = {'name': name}

    try:
        if hasattr(storage, 'size'):
            info['size'] = storage.size(name)
    except:
        pass

    try:
        if hasattr(storage, 'get_modified_time'):
            info['modified'] = storage.get_modified_time(name)
    except:
        pass

    try:
        if hasattr(storage, 'url'):
            info['url'] = storage.url(name)
    except:
        pass

    return info


def save_tree_to_storage(local_root: Path, storage, base_path: str) -> List[str]:
    """
    Рекурсивно сохраняет дерево файлов в storage.

    Args:
        local_root: Корневая директория с файлами
        storage: Django storage backend
        base_path: Базовый путь в storage

    Returns:
        list: Список сохраненных путей

    Raises:
        StorageError: При ошибках сохранения
    """
    saved_paths = []

    try:
        for root, dirs, files in os.walk(local_root):
            for filename in files:
                local_file_path = Path(root) / filename

                # Вычисляем относительный путь
                rel_path = local_file_path.relative_to(local_root)
                storage_key = f"{base_path.rstrip('/')}/{str(rel_path).replace(os.sep, '/')}"

                logger.debug(f"Saving {local_file_path} -> {storage_key}")

                # Открываем и сохраняем файл
                try:
                    with local_file_path.open("rb") as fh:
                        saved_name = storage.save(storage_key, fh)
                        saved_paths.append(saved_name)

                except Exception as e:
                    logger.error(f"Failed to save {storage_key}: {e}")
                    raise StorageError(f"Cannot save file {storage_key}: {e}") from e

        logger.info(f"Saved {len(saved_paths)} files to storage under {base_path}")
        return saved_paths

    except Exception as e:
        logger.error(f"Error saving file tree: {e}")
        if isinstance(e, StorageError):
            raise
        raise StorageError(f"Cannot save file tree: {e}") from e


def cleanup_storage_path(storage, path: str, max_attempts: int = 3) -> bool:
    """
    Безопасно удаляет файлы из storage с retry логикой.

    Args:
        storage: Django storage backend
        path: Путь для удаления
        max_attempts: Количество попыток

    Returns:
        bool: True если успешно удалено
    """
    for attempt in range(max_attempts):
        try:
            if storage.exists(path):
                storage.delete(path)
                logger.debug(f"Deleted from storage: {path}")
            return True

        except Exception as e:
            if attempt == max_attempts - 1:
                logger.warning(f"Failed to delete {path} after {max_attempts} attempts: {e}")
                return False

            # Exponential backoff
            time.sleep(0.1 * (2 ** attempt))

    return False


# ==============================================================================
# УТИЛИТЫ ДЛЯ ВАЛИДАЦИИ
# ==============================================================================

def validate_video_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Выполняет комплексную валидацию видеофайла.

    Args:
        file_path: Путь к видеофайлу

    Returns:
        dict: Результат валидации

    Raises:
        InvalidVideoError: Если файл не прошел валидацию
    """
    path = Path(file_path)

    validation = {
        'valid': False,
        'issues': [],
        'warnings': [],
        'info': {}
    }

    # Проверяем существование файла
    if not path.exists():
        validation['issues'].append("File does not exist")
        return validation

    # Проверяем размер файла
    size = path.stat().st_size
    validation['info']['size'] = size

    if size < defaults.MIN_FILE_SIZE:
        validation['issues'].append(f"File too small: {size} bytes")

    if size > defaults.MAX_FILE_SIZE:
        validation['issues'].append(f"File too large: {size} bytes")

    # Проверяем расширение
    ext = path.suffix.lower()
    validation['info']['extension'] = ext

    if ext not in defaults.ALLOWED_EXTENSIONS:
        validation['issues'].append(f"Unsupported extension: {ext}")

    # Анализируем через FFprobe
    try:
        info = ffprobe_streams(path)
        video_stream, audio_stream = pick_video_audio_streams(info)

        validation['info']['has_video'] = video_stream is not None
        validation['info']['has_audio'] = audio_stream is not None

        if video_stream:
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            validation['info']['width'] = width
            validation['info']['height'] = height
            validation['info']['codec'] = video_stream.get('codec_name', 'unknown')

            # Проверяем разрешение
            if height < defaults.MIN_VIDEO_HEIGHT:
                validation['issues'].append(f"Height too small: {height}p")

            if height > defaults.MAX_VIDEO_HEIGHT:
                validation['issues'].append(f"Height too large: {height}p")

            # Предупреждения о нестандартных параметрах
            if width % 2 != 0 or height % 2 != 0:
                validation['warnings'].append("Odd dimensions may cause encoding issues")

        else:
            validation['issues'].append("No video stream found")

        # Проверяем длительность
        if format_info := info.get('format'):
            try:
                duration = float(format_info.get('duration', 0))
                validation['info']['duration'] = duration

                if duration > defaults.MAX_VIDEO_DURATION:
                    validation['issues'].append(f"Video too long: {duration}s")

            except (ValueError, TypeError):
                validation['warnings'].append("Could not determine video duration")

    except Exception as e:
        validation['issues'].append(f"Cannot analyze video: {e}")

    # Определяем общий результат
    validation['valid'] = len(validation['issues']) == 0

    return validation


def estimate_transcoding_time(file_path: Union[str, Path], ladder: List[Dict]) -> Dict[str, Any]:
    """
    Оценивает время транскодинга для видеофайла.

    Args:
        file_path: Путь к видеофайлу
        ladder: Лестница качеств

    Returns:
        dict: Оценка времени транскодинга
    """
    try:
        complexity = analyze_video_complexity(file_path)
        duration = complexity.get('duration', 0)

        if duration <= 0:
            return {'estimated_seconds': 0, 'confidence': 'low'}

        # Базовое время на основе сложности
        base_multiplier = complexity.get('estimated_transcode_time', 1.0)

        # Корректируем на количество качеств
        quality_multiplier = len(ladder) * 0.3 + 0.7  # от 1.0 до ~2.2

        # Корректируем на разрешения в лестнице
        resolution_factor = 1.0
        total_pixels = sum(r['height'] * r['height'] * 16 // 9 for r in ladder)  # приблизительно
        avg_pixels = total_pixels / len(ladder)

        if avg_pixels > 1920 * 1080:
            resolution_factor = 1.5
        elif avg_pixels < 640 * 480:
            resolution_factor = 0.7

        # Итоговая оценка
        estimated = duration * base_multiplier * quality_multiplier * resolution_factor

        # Добавляем запас
        estimated = int(estimated * 1.2)

        # Определяем уверенность в оценке
        confidence = 'high'
        if complexity.get('complexity') == 'high':
            confidence = 'medium'
            estimated = int(estimated * 1.3)

        return {
            'estimated_seconds': estimated,
            'confidence': confidence,
            'factors': {
                'duration': duration,
                'complexity': complexity.get('complexity', 'medium'),
                'qualities_count': len(ladder),
                'resolution_factor': resolution_factor,
            }
        }

    except Exception as e:
        logger.warning(f"Could not estimate transcoding time: {e}")
        return {
            'estimated_seconds': 300,  # 5 минут по умолчанию
            'confidence': 'low',
            'error': str(e)
        }


# ==============================================================================
# ДОПОЛНИТЕЛЬНЫЕ УТИЛИТЫ
# ==============================================================================

def get_video_info_quick(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Быстро получает основную информацию о видео без детального анализа.

    Args:
        file_path: Путь к видеофайлу

    Returns:
        dict: Основная информация о видео
    """
    try:
        # Используем только show_format для скорости
        cmd = [
            defaults.FFPROBE,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            str(file_path)
        ]

        result = run(cmd, timeout_sec=15)
        data = json.loads(result.stdout)

        format_info = data.get('format', {})

        return {
            'duration': float(format_info.get('duration', 0)),
            'size': int(format_info.get('size', 0)),
            'bitrate': int(format_info.get('bit_rate', 0)),
            'format_name': format_info.get('format_name', 'unknown'),
            'nb_streams': int(format_info.get('nb_streams', 0)),
        }

    except Exception as e:
        logger.warning(f"Quick video info failed: {e}")
        return {
            'duration': 0,
            'size': 0,
            'bitrate': 0,
            'format_name': 'unknown',
            'nb_streams': 0,
        }


def calculate_optimal_bitrates(width: int, height: int, fps: float = 30.0) -> Dict[str, int]:
    """
    Рассчитывает оптимальные битрейты для заданного разрешения.

    Args:
        width: Ширина видео
        height: Высота видео
        fps: Частота кадров

    Returns:
        dict: Рекомендованные битрейты
    """
    pixels = width * height
    fps_factor = fps / 30.0  # Нормализация относительно 30fps

    # Базовые битрейты на пиксель (в bps)
    base_bpp = {
        'low': 0.05,  # Низкое качество
        'medium': 0.08,  # Среднее качество
        'high': 0.12,  # Высокое качество
        'max': 0.16  # Максимальное качество
    }

    bitrates = {}

    for quality, bpp in base_bpp.items():
        # Базовый битрейт
        base_bitrate = pixels * bpp * fps_factor

        # Корректировки для разных разрешений
        if height >= 2160:  # 4K
            base_bitrate *= 0.8  # 4K более эффективно сжимается
        elif height <= 480:  # SD
            base_bitrate *= 1.2  # SD менее эффективно

        # Округляем до разумных значений
        bitrates[quality] = int(base_bitrate / 1000) * 1000  # Округление до килобит

    return bitrates


def create_test_video(output_path: Path, duration: int = 10,
                      width: int = 640, height: int = 480) -> Path:
    """
    Создает тестовое видео для разработки и тестирования.

    Args:
        output_path: Путь для сохранения
        duration: Длительность в секундах
        width: Ширина
        height: Высота

    Returns:
        Path: Путь к созданному файлу
    """
    cmd = [
        defaults.FFMPEG, "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
        "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "64k",
        "-t", str(duration),
        str(output_path)
    ]

    run(cmd, timeout_sec=duration + 30)

    if not output_path.exists():
        raise TranscodingError(f"Test video not created: {output_path}")

    logger.info(f"Test video created: {output_path} ({duration}s, {width}x{height})")
    return output_path


# ==============================================================================
# ЭКСПОРТ ФУНКЦИЙ
# ==============================================================================

__all__ = [
    # Контекстные менеджеры
    'tempdir',

    # Выполнение команд
    'run',
    'ensure_binary_available',

    # Анализ видео
    'ffprobe_streams',
    'pick_video_audio_streams',
    'analyze_video_complexity',
    'validate_video_file',
    'estimate_transcoding_time',
    'get_video_info_quick',

    # Превью
    'extract_preview',
    'create_preview_sprites',

    # Транскодинг
    'transcode_hls_variants',
    'transcode_dash_variants',
    'transcode_adaptive_variants',

    # Storage
    'pull_to_local',
    'save_tree_to_storage',
    'cleanup_storage_path',
    'get_file_info_from_storage',

    # Утилиты
    'get_file_info',
    'calculate_optimal_bitrates',
    'create_test_video',
]
