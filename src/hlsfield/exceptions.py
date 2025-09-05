"""
🚨 Пользовательские исключения для django-hlsfield

Иерархия исключений для детального handling различных типов ошибок
при работе с видео обработкой, транскодингом и storage операциями.

Все исключения наследуют от HLSFieldError для удобного catch-all handling.

Автор: django-hlsfield team
Лицензия: MIT
"""

from typing import List, Optional, Any, Dict


# ==============================================================================
# БАЗОВОЕ ИСКЛЮЧЕНИЕ
# ==============================================================================


class HLSFieldError(Exception):
    """
    Базовое исключение для всех ошибок django-hlsfield.

    Используется как catch-all для всех ошибок пакета.
    Содержит дополнительную информацию для debugging и monitoring.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
    ):
        """
        Args:
            message: Основное сообщение об ошибке
            details: Дополнительная техническая информация
            suggestions: Список возможных решений проблемы
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.suggestions = suggestions or []

    def __str__(self) -> str:
        result = self.message

        if self.details:
            result += f" (Details: {self.details})"

        if self.suggestions:
            suggestions_str = "; ".join(self.suggestions)
            result += f" (Suggestions: {suggestions_str})"

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Возвращает структурированное представление ошибки"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "suggestions": self.suggestions,
        }


# ==============================================================================
# ОШИБКИ FFMPEG
# ==============================================================================


class FFmpegNotFoundError(HLSFieldError):
    """
    FFmpeg или FFprobe не найдены в системе.

    Критическая ошибка конфигурации - без FFmpeg пакет не может работать.
    """

    def __init__(self, binary_name: str = "ffmpeg"):
        self.binary_name = binary_name

        message = f"{binary_name} not found in system PATH"

        suggestions = [
            "Install FFmpeg: https://ffmpeg.org/download.html",
            f"Set HLSFIELD_FFMPEG and HLSFIELD_FFPROBE in Django settings",
            "Verify FFmpeg installation with: ffmpeg -version",
            "Check system PATH includes FFmpeg directory",
        ]

        details = {"binary_name": binary_name, "error_category": "system_configuration"}

        super().__init__(message, details, suggestions)


class FFmpegError(HLSFieldError):
    """
    Ошибка выполнения команды FFmpeg.

    Содержит детальную информацию о команде, коде возврата и output.
    """

    def __init__(self, command: List[str], returncode: int, stdout: str = "", stderr: str = ""):

        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

        command_str = " ".join(command)
        message = f"FFmpeg command failed with code {returncode}: {command_str}"

        details = {
            "command": command,
            "returncode": returncode,
            "stdout": stdout[:500],  # Ограничиваем для readability
            "stderr": stderr[:500],
            "error_category": "ffmpeg_execution",
        }

        suggestions = self._generate_suggestions()

        super().__init__(message, details, suggestions)

    def _generate_suggestions(self) -> List[str]:
        """Генерирует suggestions на основе stderr"""
        suggestions = []

        stderr_lower = self.stderr.lower()

        if "no such file" in stderr_lower:
            suggestions.extend(
                [
                    "Check input file path exists and is readable",
                    "Verify file permissions",
                    "Use absolute file path",
                ]
            )

        elif "invalid data found" in stderr_lower:
            suggestions.extend(
                [
                    "Input file may be corrupted",
                    "Try with a different video file",
                    "Check file was fully uploaded",
                ]
            )

        elif "permission denied" in stderr_lower:
            suggestions.extend(
                [
                    "Check file and directory permissions",
                    "Run with appropriate user privileges",
                    "Verify storage write permissions",
                ]
            )

        elif "no space left" in stderr_lower:
            suggestions.extend(
                [
                    "Free up disk space",
                    "Check temporary directory has sufficient space",
                    "Consider using different storage location",
                ]
            )

        elif "unknown encoder" in stderr_lower:
            suggestions.extend(
                [
                    "Check FFmpeg was compiled with required encoders",
                    "Install FFmpeg with libx264 support",
                    "Update FFmpeg to newer version",
                ]
            )

        if not suggestions:
            suggestions.append("Check FFmpeg documentation for this error")

        return suggestions


class FFmpegTimeoutError(FFmpegError):
    """FFmpeg команда превысила таймаут"""

    def __init__(self, command: List[str], timeout_seconds: int):
        self.timeout_seconds = timeout_seconds

        message = f"FFmpeg command timed out after {timeout_seconds} seconds"

        super().__init__(command, -1, "", f"Timeout after {timeout_seconds}s")

        self.suggestions = [
            f"Increase timeout (current: {timeout_seconds}s)",
            "Check if input video is very long or high resolution",
            "Consider using faster FFmpeg preset",
            "Monitor system resources during transcoding",
        ]


# ==============================================================================
# ОШИБКИ ВИДЕОФАЙЛОВ
# ==============================================================================


class InvalidVideoError(HLSFieldError):
    """
    Недопустимый, поврежденный или неподдерживаемый видеофайл.
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        file_info: Optional[Dict[str, Any]] = None,
    ):

        self.file_path = file_path
        self.file_info = file_info or {}

        details = {
            "file_path": file_path,
            "file_info": file_info,
            "error_category": "video_validation",
        }

        suggestions = [
            "Try with a different video file",
            "Check file was fully uploaded and not truncated",
            "Verify file format is supported (MP4, AVI, MOV, etc.)",
            "Use FFmpeg to validate file: ffprobe your_file.mp4",
        ]

        super().__init__(message, details, suggestions)


class UnsupportedFormatError(InvalidVideoError):
    """Неподдерживаемый формат видеофайла"""

    def __init__(self, format_name: str, file_path: Optional[str] = None):
        self.format_name = format_name

        message = f"Unsupported video format: {format_name}"

        file_info = {"detected_format": format_name}

        super().__init__(message, file_path, file_info)

        self.suggestions = [
            "Convert video to supported format (MP4, MOV, AVI)",
            "Use FFmpeg to convert: ffmpeg -i input.{format_name} output.mp4",
            "Check HLSFIELD_ALLOWED_EXTENSIONS setting",
            f"Current format '{format_name}' not in allowed list",
        ]


class VideoTooLargeError(InvalidVideoError):
    """Видеофайл превышает максимальный размер"""

    def __init__(self, file_size: int, max_size: int, file_path: Optional[str] = None):
        self.file_size = file_size
        self.max_size = max_size

        size_mb = file_size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)

        message = f"Video file too large: {size_mb:.1f}MB (max: {max_mb:.1f}MB)"

        file_info = {
            "size_bytes": file_size,
            "size_mb": size_mb,
            "max_size_bytes": max_size,
            "max_size_mb": max_mb,
        }

        super().__init__(message, file_path, file_info)

        self.suggestions = [
            f"Compress video to under {max_mb:.0f}MB",
            "Reduce video bitrate or resolution",
            "Split video into smaller segments",
            "Increase HLSFIELD_MAX_FILE_SIZE setting if needed",
        ]


class VideoTooShortError(InvalidVideoError):
    """Видео слишком короткое для обработки"""

    def __init__(self, duration: float, min_duration: float = 1.0):
        self.duration = duration
        self.min_duration = min_duration

        message = f"Video too short: {duration:.1f}s (minimum: {min_duration:.1f}s)"

        file_info = {"duration_seconds": duration, "min_duration_seconds": min_duration}

        super().__init__(message, None, file_info)


# ==============================================================================
# ОШИБКИ ТРАНСКОДИНГА
# ==============================================================================


class TranscodingError(HLSFieldError):
    """
    Общие ошибки процесса транскодинга видео.
    """

    def __init__(
        self, message: str, stage: Optional[str] = None, original_error: Optional[Exception] = None
    ):

        self.stage = stage
        self.original_error = original_error

        details = {
            "transcoding_stage": stage,
            "original_error": str(original_error) if original_error else None,
            "error_category": "transcoding",
        }

        suggestions = [
            "Check system has sufficient CPU and memory",
            "Verify temporary storage has enough space",
            "Try with a simpler quality ladder",
            "Check FFmpeg logs for detailed error info",
        ]

        if stage:
            suggestions.insert(0, f"Error occurred during {stage} stage")

        super().__init__(message, details, suggestions)


class HLSTranscodingError(TranscodingError):
    """Ошибки при создании HLS стрима"""

    def __init__(
        self, message: str, variant_height: Optional[int] = None, segments_created: int = 0
    ):

        self.variant_height = variant_height
        self.segments_created = segments_created

        details = {
            "variant_height": variant_height,
            "segments_created": segments_created,
            "transcoding_type": "HLS",
        }

        suggestions = [
            "Check HLS segment duration is reasonable (2-10 seconds)",
            "Verify output directory is writable",
            "Try with fewer quality variants",
            "Check source video is not corrupted",
        ]

        if variant_height:
            suggestions.insert(0, f"Error creating {variant_height}p HLS variant")

        super().__init__(message, "HLS_transcoding", None)
        self.details.update(details)


class DASHTranscodingError(TranscodingError):
    """Ошибки при создании DASH стрима"""

    def __init__(self, message: str, representations_created: int = 0):
        self.representations_created = representations_created

        details = {"representations_created": representations_created, "transcoding_type": "DASH"}

        suggestions = [
            "Check DASH segment settings are valid",
            "Verify manifest template configuration",
            "Try shorter segment duration (2-4 seconds)",
            "Check FFmpeg DASH support is available",
        ]

        super().__init__(message, "DASH_transcoding", None)
        self.details.update(details)


# ==============================================================================
# ОШИБКИ STORAGE
# ==============================================================================


class StorageError(HLSFieldError):
    """
    Ошибки при работе с файловым хранилищем.
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        file_path: Optional[str] = None,
        storage_backend: Optional[str] = None,
    ):

        self.operation = operation
        self.file_path = file_path
        self.storage_backend = storage_backend

        details = {
            "operation": operation,
            "file_path": file_path,
            "storage_backend": storage_backend,
            "error_category": "storage",
        }

        suggestions = [
            "Check file and directory permissions",
            "Verify storage backend configuration",
            "Ensure sufficient storage space available",
        ]

        if operation == "upload":
            suggestions.extend(
                [
                    "Check network connectivity for cloud storage",
                    "Verify authentication credentials",
                    "Try uploading smaller test file",
                ]
            )
        elif operation == "download":
            suggestions.extend(
                [
                    "Verify file exists in storage",
                    "Check read permissions",
                    "Confirm storage backend is accessible",
                ]
            )

        super().__init__(message, details, suggestions)


class S3StorageError(StorageError):
    """Специфичные ошибки AWS S3 storage"""

    def __init__(
        self,
        message: str,
        bucket: Optional[str] = None,
        key: Optional[str] = None,
        aws_error_code: Optional[str] = None,
    ):

        self.bucket = bucket
        self.key = key
        self.aws_error_code = aws_error_code

        details = {
            "bucket": bucket,
            "key": key,
            "aws_error_code": aws_error_code,
            "storage_type": "S3",
        }

        suggestions = [
            "Check AWS credentials (ACCESS_KEY_ID, SECRET_ACCESS_KEY)",
            "Verify S3 bucket exists and is accessible",
            "Check S3 bucket permissions and policies",
            "Confirm AWS region is correct",
        ]

        if aws_error_code == "NoSuchBucket":
            suggestions.insert(0, f"S3 bucket '{bucket}' does not exist")
        elif aws_error_code == "AccessDenied":
            suggestions.insert(0, "S3 access denied - check IAM permissions")
        elif aws_error_code == "NoSuchKey":
            suggestions.insert(0, f"S3 object '{key}' not found")

        super().__init__(message, None, key, "S3")
        self.details.update(details)


# ==============================================================================
# ОШИБКИ КОНФИГУРАЦИИ
# ==============================================================================


class ConfigurationError(HLSFieldError):
    """
    Ошибки конфигурации django-hlsfield.
    """

    def __init__(
        self,
        message: str,
        setting_name: Optional[str] = None,
        current_value: Optional[Any] = None,
        expected_type: Optional[str] = None,
    ):

        self.setting_name = setting_name
        self.current_value = current_value
        self.expected_type = expected_type

        details = {
            "setting_name": setting_name,
            "current_value": current_value,
            "expected_type": expected_type,
            "error_category": "configuration",
        }

        suggestions = [
            "Check Django settings.py configuration",
            "Verify HLSFIELD_* settings are correct",
            "Run: python manage.py hlsfield_health_check",
            "Review django-hlsfield documentation",
        ]

        if setting_name:
            suggestions.insert(0, f"Fix {setting_name} setting in Django configuration")

        super().__init__(message, details, suggestions)


class InvalidLadderError(ConfigurationError):
    """Некорректная конфигурация лестницы качеств"""

    def __init__(
        self, message: str, ladder: Optional[List[Dict]] = None, rung_index: Optional[int] = None
    ):

        self.ladder = ladder
        self.rung_index = rung_index

        details = {
            "ladder_length": len(ladder) if ladder else 0,
            "invalid_rung_index": rung_index,
            "setting_type": "quality_ladder",
        }

        suggestions = [
            "Check ladder format: [{'height': 720, 'v_bitrate': 2500, 'a_bitrate': 128}, ...]",
            "Verify all ladder rungs have required fields",
            "Ensure bitrates and heights are positive integers",
            "Remove duplicate height values from ladder",
        ]

        if rung_index is not None:
            suggestions.insert(0, f"Fix ladder rung at index {rung_index}")

        super().__init__(message, "ladder", ladder, "List[Dict]")
        self.details.update(details)


# ==============================================================================
# ОШИБКИ CELERY/ЗАДАЧ
# ==============================================================================


class TaskError(HLSFieldError):
    """
    Ошибки выполнения фоновых задач.
    """

    def __init__(
        self,
        message: str,
        task_name: Optional[str] = None,
        task_id: Optional[str] = None,
        retry_count: int = 0,
    ):

        self.task_name = task_name
        self.task_id = task_id
        self.retry_count = retry_count

        details = {
            "task_name": task_name,
            "task_id": task_id,
            "retry_count": retry_count,
            "error_category": "task_execution",
        }

        suggestions = [
            "Check Celery worker is running",
            "Verify Redis/broker connectivity",
            "Monitor system resources (CPU, memory, disk)",
            "Check task logs for detailed errors",
        ]

        if retry_count > 0:
            suggestions.insert(0, f"Task failed after {retry_count} retries")

        super().__init__(message, details, suggestions)


class CeleryNotAvailableError(TaskError):
    """Celery не доступен, fallback на синхронную обработку"""

    def __init__(self):
        message = "Celery not available, falling back to synchronous processing"

        suggestions = [
            "Install Celery: pip install celery",
            "Configure Celery in Django settings",
            "Start Celery worker: celery -A myproject worker",
            "Synchronous processing will continue but may be slow",
        ]

        details = {"fallback_mode": "synchronous"}

        super().__init__(message, None, None, 0)
        self.details.update(details)


# ==============================================================================
# ОШИБКИ ВАЛИДАЦИИ
# ==============================================================================


class ValidationError(HLSFieldError):
    """
    Ошибки валидации входных данных.
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        validation_errors: Optional[List[str]] = None,
    ):

        self.field_name = field_name
        self.validation_errors = validation_errors or []

        details = {
            "field_name": field_name,
            "validation_errors": validation_errors,
            "error_category": "validation",
        }

        suggestions = []
        if validation_errors:
            suggestions.extend(validation_errors)

        suggestions.append("Check input data format and constraints")

        super().__init__(message, details, suggestions)


# ==============================================================================
# NETWORK И TIMEOUT ОШИБКИ
# ==============================================================================


class TimeoutError(HLSFieldError):
    """Операция превысила таймаут"""

    def __init__(self, message: str, timeout_seconds: int, operation: Optional[str] = None):

        self.timeout_seconds = timeout_seconds
        self.operation = operation

        details = {
            "timeout_seconds": timeout_seconds,
            "operation": operation,
            "error_category": "timeout",
        }

        suggestions = [
            f"Increase timeout (current: {timeout_seconds}s)",
            "Check if operation is appropriate for timeout duration",
            "Monitor system performance during operation",
        ]

        if operation:
            suggestions.insert(0, f"Timeout during {operation}")

        super().__init__(message, details, suggestions)


class NetworkError(HLSFieldError):
    """Сетевые ошибки при работе с удаленными ресурсами"""

    def __init__(self, message: str, url: Optional[str] = None, status_code: Optional[int] = None):
        self.url = url
        self.status_code = status_code

        details = {"url": url, "status_code": status_code, "error_category": "network"}

        suggestions = [
            "Check network connectivity",
            "Verify URL is accessible",
            "Check firewall and proxy settings",
        ]

        if status_code:
            if status_code == 404:
                suggestions.insert(0, "Resource not found (404)")
            elif status_code == 403:
                suggestions.insert(0, "Access forbidden (403) - check permissions")
            elif status_code >= 500:
                suggestions.insert(0, f"Server error ({status_code}) - try again later")

        super().__init__(message, details, suggestions)


# ==============================================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ С ИСКЛЮЧЕНИЯМИ
# ==============================================================================


def categorize_exception(error: Exception) -> Dict[str, Any]:
    """
    Анализирует исключение и возвращает структурированную информацию.

    Args:
        error: Исключение для анализа

    Returns:
        dict: Категоризированная информация об ошибке
    """

    if isinstance(error, HLSFieldError):
        return error.to_dict()

    # Для стандартных исключений Python
    error_info = {
        "error_type": error.__class__.__name__,
        "message": str(error),
        "details": {},
        "suggestions": [],
    }

    # Специальная обработка для некоторых стандартных исключений
    if isinstance(error, FileNotFoundError):
        error_info["details"]["error_category"] = "file_system"
        error_info["suggestions"] = [
            "Check file path exists",
            "Verify file permissions",
            "Ensure file was not moved or deleted",
        ]

    elif isinstance(error, PermissionError):
        error_info["details"]["error_category"] = "permissions"
        error_info["suggestions"] = [
            "Check file and directory permissions",
            "Run with appropriate user privileges",
            "Verify write access to destination",
        ]

    elif isinstance(error, OSError):
        error_info["details"]["error_category"] = "system"
        error_info["suggestions"] = [
            "Check system resources (disk space, memory)",
            "Verify system configuration",
            "Check for hardware issues",
        ]

    return error_info


def format_exception_for_user(error: Exception) -> str:
    """
    Форматирует исключение для показа пользователю (без технических деталей).

    Args:
        error: Исключение для форматирования

    Returns:
        str: Пользовательское сообщение об ошибке
    """

    if isinstance(error, HLSFieldError):
        message = error.message

        if error.suggestions:
            # Берем только первые 2 suggestion для краткости
            suggestions = error.suggestions[:2]
            message += f"\n\nПопробуйте: {'; '.join(suggestions)}"

        return message

    # Для стандартных исключений
    error_messages = {
        FileNotFoundError: "Файл не найден. Проверьте путь к файлу.",
        PermissionError: "Недостаточно прав доступа. Проверьте разрешения.",
        OSError: "Системная ошибка. Проверьте ресурсы системы.",
        ValueError: "Некорректное значение. Проверьте входные данные.",
        TypeError: "Неправильный тип данных. Проверьте формат данных.",
    }

    return error_messages.get(type(error), f"Произошла ошибка: {str(error)}")


def is_retryable_error(error: Exception) -> bool:
    """
    Определяет можно ли повторить операцию после данной ошибки.

    Args:
        error: Исключение для анализа

    Returns:
        bool: True если ошибка временная и можно повторить
    """

    # Ошибки которые НЕ стоит повторять
    non_retryable = (
        FFmpegNotFoundError,
        InvalidVideoError,
        UnsupportedFormatError,
        VideoTooLargeError,
        ConfigurationError,
        ValidationError,
    )

    if isinstance(error, non_retryable):
        return False

    # Ошибки которые можно повторить
    retryable = (NetworkError, TimeoutError, StorageError, TaskError)

    if isinstance(error, retryable):
        return True

    # Для HLSFieldError проверяем категорию
    if isinstance(error, HLSFieldError):
        error_category = error.details.get("error_category")

        non_retryable_categories = ["video_validation", "configuration", "system_configuration"]

        return error_category not in non_retryable_categories

    # Стандартные исключения Python
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True

    if isinstance(error, (ValueError, TypeError, FileNotFoundError)):
        return False

    # По умолчанию не повторяем
    return False


# ==============================================================================
# ЭКСПОРТ ИСКЛЮЧЕНИЙ
# ==============================================================================

__all__ = [
    # Базовые
    "HLSFieldError",
    # FFmpeg
    "FFmpegNotFoundError",
    "FFmpegError",
    "FFmpegTimeoutError",
    # Видео
    "InvalidVideoError",
    "UnsupportedFormatError",
    "VideoTooLargeError",
    "VideoTooShortError",
    # Транскодинг
    "TranscodingError",
    "HLSTranscodingError",
    "DASHTranscodingError",
    # Storage
    "StorageError",
    "S3StorageError",
    # Конфигурация
    "ConfigurationError",
    "InvalidLadderError",
    # Задачи
    "TaskError",
    "CeleryNotAvailableError",
    # Валидация
    "ValidationError",
    # Network
    "TimeoutError",
    "NetworkError",
    # Утилиты
    "categorize_exception",
    "format_exception_for_user",
    "is_retryable_error",
]
