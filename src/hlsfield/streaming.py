"""
Enhanced streaming server с поддержкой range requests,
защитой контента и оптимизацией доставки
"""

import os
import re
import hashlib
import time
from typing import Optional, Tuple
from pathlib import Path

from django.http import HttpResponse, StreamingHttpResponse, Http404
from django.views import View
from django.views.decorators.cache import cache_control
from django.utils.decorators import method_decorator
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin


class RangeFileWrapper:
    """
    Обертка для файлов с поддержкой HTTP Range requests.
    Позволяет эффективно стримить большие видео файлы.
    """

    def __init__(self, file, chunk_size=8192, offset=0, length=None):
        self.file = file
        self.chunk_size = chunk_size
        self.offset = offset
        self.length = length
        self.remaining = length
        self.file.seek(offset)

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining is None:
            # Читаем до конца файла
            data = self.file.read(self.chunk_size)
            if data:
                return data
            raise StopIteration
        else:
            # Читаем определенное количество байт
            if self.remaining <= 0:
                raise StopIteration

            chunk = min(self.chunk_size, self.remaining)
            data = self.file.read(chunk)

            if not data:
                raise StopIteration

            self.remaining -= len(data)
            return data


class SecureStreamingView(View):
    """
    Безопасная доставка HLS/DASH контента с поддержкой:
    - HTTP Range requests
    - Token-based authentication
    - Bandwidth throttling
    - Cache headers
    - CORS support
    """

    # Настройки безопасности
    ENABLE_TOKEN_AUTH = getattr(settings, 'HLSFIELD_SECURE_STREAMING', False)
    TOKEN_EXPIRY = getattr(settings, 'HLSFIELD_TOKEN_EXPIRY', 3600)  # 1 час
    ENABLE_BANDWIDTH_LIMIT = getattr(settings, 'HLSFIELD_BANDWIDTH_LIMIT', False)
    MAX_BANDWIDTH_MBPS = getattr(settings, 'HLSFIELD_MAX_BANDWIDTH_MBPS', 10)

    def get(self, request, *args, **kwargs):
        """Обработка GET запроса для стриминга"""

        file_path = self.get_file_path(request, *args, **kwargs)

        # Проверка безопасности
        if not self.check_access(request, file_path):
            return HttpResponse('Forbidden', status=403)

        # Проверка существования файла
        if not os.path.exists(file_path):
            raise Http404("File not found")

        # Определяем тип контента
        content_type = self.get_content_type(file_path)

        # Обработка Range requests
        range_header = request.META.get('HTTP_RANGE')

        if range_header:
            return self.serve_range_request(request, file_path, content_type)
        else:
            return self.serve_full_file(request, file_path, content_type)

    def get_file_path(self, request, *args, **kwargs) -> str:
        """Получает путь к файлу из запроса"""
        # Это нужно переопределить в наследниках
        video_id = kwargs.get('video_id')
        file_name = kwargs.get('file_name')

        # Базовая защита от path traversal
        if '..' in file_name or file_name.startswith('/'):
            raise Http404("Invalid file name")

        # Строим безопасный путь
        base_path = settings.MEDIA_ROOT
        return os.path.join(base_path, 'videos', video_id, file_name)

    def check_access(self, request, file_path: str) -> bool:
        """Проверяет права доступа к файлу"""

        if not self.ENABLE_TOKEN_AUTH:
            return True

        # Проверяем токен
        token = request.GET.get('token')
        if not token:
            return False

        # Валидируем токен
        return self.validate_token(token, file_path)

    def validate_token(self, token: str, file_path: str) -> bool:
        """Валидация токена доступа"""

        # Проверяем в кеше
        cache_key = f'stream_token:{token}'
        cached_data = cache.get(cache_key)

        if cached_data:
            # Токен валиден, проверяем соответствие файла
            return cached_data.get('file_path') == file_path

        # Генерируем ожидаемый токен
        expected_token = self.generate_token(file_path)

        if token == expected_token:
            # Сохраняем в кеш
            cache.set(cache_key, {
                'file_path': file_path,
                'created_at': time.time()
            }, self.TOKEN_EXPIRY)
            return True

        return False

    def generate_token(self, file_path: str) -> str:
        """Генерирует токен для файла"""
        secret = settings.SECRET_KEY
        timestamp = int(time.time() / self.TOKEN_EXPIRY)

        data = f"{file_path}:{timestamp}:{secret}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def get_content_type(self, file_path: str) -> str:
        """Определяет MIME type файла"""
        ext = Path(file_path).suffix.lower()

        mime_types = {
            '.m3u8': 'application/vnd.apple.mpegurl',
            '.mpd': 'application/dash+xml',
            '.ts': 'video/MP2T',
            '.m4s': 'video/iso.segment',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.jpg': 'image/jpeg',
            '.png': 'image/png',
            '.vtt': 'text/vtt',
        }

        return mime_types.get(ext, 'application/octet-stream')

    def parse_range_header(self, range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
        """Парсит Range header и возвращает (start, end)"""

        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not range_match:
            return None

        start = int(range_match.group(1))
        end = range_match.group(2)

        if end:
            end = int(end)
        else:
            end = file_size - 1

        # Валидация
        if start > end or start >= file_size:
            return None

        end = min(end, file_size - 1)

        return start, end

    def serve_range_request(self, request, file_path: str, content_type: str):
        """Обслуживает Range request"""

        file_size = os.path.getsize(file_path)
        range_header = request.META.get('HTTP_RANGE')

        # Парсим range
        byte_range = self.parse_range_header(range_header, file_size)

        if not byte_range:
            return HttpResponse('Invalid range', status=416)

        start, end = byte_range
        length = end - start + 1

        # Открываем файл
        file = open(file_path, 'rb')

        # Создаем wrapper с поддержкой throttling если нужно
        if self.ENABLE_BANDWIDTH_LIMIT:
            wrapper = ThrottledFileWrapper(
                file,
                offset=start,
                length=length,
                max_bandwidth_mbps=self.MAX_BANDWIDTH_MBPS
            )
        else:
            wrapper = RangeFileWrapper(file, offset=start, length=length)

        # Создаем response
        response = StreamingHttpResponse(
            wrapper,
            status=206,  # Partial Content
            content_type=content_type
        )

        # Добавляем заголовки
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Content-Length'] = str(length)
        response['Accept-Ranges'] = 'bytes'

        # Cache headers
        self.add_cache_headers(response, file_path)

        return response

    def serve_full_file(self, request, file_path: str, content_type: str):
        """Обслуживает полный файл"""

        file_size = os.path.getsize(file_path)

        # Для маленьких файлов (плейлисты, манифесты) отдаем целиком
        if file_size < 1024 * 1024:  # < 1MB
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type=content_type)
        else:
            # Для больших файлов используем streaming
            file = open(file_path, 'rb')

            if self.ENABLE_BANDWIDTH_LIMIT:
                wrapper = ThrottledFileWrapper(
                    file,
                    max_bandwidth_mbps=self.MAX_BANDWIDTH_MBPS
                )
            else:
                wrapper = RangeFileWrapper(file)

            response = StreamingHttpResponse(wrapper, content_type=content_type)

        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'

        # Cache headers
        self.add_cache_headers(response, file_path)

        return response

    def add_cache_headers(self, response, file_path: str):
        """Добавляет заголовки кеширования"""

        ext = Path(file_path).suffix.lower()

        # Различные стратегии кеширования для разных типов
        if ext in ['.ts', '.m4s', '.mp4']:
            # Сегменты видео - долгое кеширование
            response['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif ext in ['.m3u8', '.mpd']:
            # Плейлисты - короткое кеширование
            response['Cache-Control'] = 'public, max-age=60'
        else:
            # По умолчанию
            response['Cache-Control'] = 'public, max-age=3600'

        # ETag для проверки изменений
        mtime = os.path.getmtime(file_path)
        etag = f'"{hashlib.md5(f"{file_path}:{mtime}".encode()).hexdigest()}"'
        response['ETag'] = etag


class ThrottledFileWrapper(RangeFileWrapper):
    """
    File wrapper с ограничением пропускной способности.
    Полезно для тестирования адаптивного стриминга.
    """

    def __init__(self, file, max_bandwidth_mbps=10, **kwargs):
        super().__init__(file, **kwargs)
        self.max_bandwidth_mbps = max_bandwidth_mbps
        self.max_bytes_per_second = max_bandwidth_mbps * 1024 * 1024 / 8
        self.last_read_time = time.time()
        self.bytes_sent = 0

    def __next__(self):
        # Рассчитываем задержку для ограничения скорости
        current_time = time.time()
        elapsed = current_time - self.last_read_time

        if elapsed > 0 and self.bytes_sent > 0:
            current_rate = self.bytes_sent / elapsed

            if current_rate > self.max_bytes_per_second:
                # Нужна задержка
                sleep_time = (self.bytes_sent / self.max_bytes_per_second) - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        # Читаем следующий chunk
        data = super().__next__()

        self.bytes_sent += len(data)

        # Сбрасываем счетчик каждую секунду
        if current_time - self.last_read_time > 1:
            self.last_read_time = current_time
            self.bytes_sent = 0

        return data


class ProtectedHLSView(LoginRequiredMixin, SecureStreamingView):
    """
    Защищенный HLS streaming с авторизацией.
    Требует авторизованного пользователя.
    """

    def check_access(self, request, file_path: str) -> bool:
        """Дополнительная проверка прав пользователя"""

        if not super().check_access(request, file_path):
            return False

        # Проверяем права пользователя на конкретное видео
        video_id = self.kwargs.get('video_id')

        # Здесь можно добавить проверку прав на конкретное видео
        # Например, проверить подписку или покупку

        return self.user_has_access_to_video(request.user, video_id)

    def user_has_access_to_video(self, user, video_id: str) -> bool:
        """Проверяет доступ пользователя к видео"""

        # Пример: проверка через модель
        from django.apps import apps

        try:
            Video = apps.get_model('yourapp', 'Video')
            video = Video.objects.get(id=video_id)

            # Проверяем права
            if video.is_public:
                return True

            if video.owner == user:
                return True

            # Проверяем подписку/покупку
            if hasattr(user, 'purchases'):
                return user.purchases.filter(video=video).exists()

        except Exception:
            pass

        return False


# URL configuration
from django.urls import path

urlpatterns = [
    # Публичный стриминг
    path('stream/<str:video_id>/<path:file_name>/',
         SecureStreamingView.as_view(),
         name='stream_file'),

    # Защищенный стриминг
    path('protected/<str:video_id>/<path:file_name>/',
         ProtectedHLSView.as_view(),
         name='protected_stream'),
]


# Middleware для добавления CORS заголовков к streaming endpoints
class StreamingCORSMiddleware:
    """
    Middleware для добавления CORS заголовков к streaming запросам.
    Необходимо для кроссдоменного стриминга.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Добавляем CORS заголовки для streaming путей
        if request.path.startswith('/stream/') or request.path.startswith('/protected/'):
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Range, Accept-Encoding'
            response['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range'

        return response
