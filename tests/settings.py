"""
Django настройки для тестирования django-hlsfield
"""

import os
import tempfile

# Build paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Security
SECRET_KEY = 'test-secret-key-for-django-hlsfield-testing-very-long-and-secure'
DEBUG = True
ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'hlsfield',
    'tests',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tests.urls'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = tempfile.mkdtemp(prefix='hlsfield_test_media_')

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = tempfile.mkdtemp(prefix='hlsfield_test_static_')

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# HLSField настройки для тестов
HLSFIELD_FFMPEG = 'ffmpeg'
HLSFIELD_FFPROBE = 'ffprobe'
HLSFIELD_SEGMENT_DURATION = 6
HLSFIELD_DEFAULT_LADDER = [
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
]

# Отключаем Celery для тестов
HLSFIELD_USE_CELERY = False

# Упрощенные настройки для тестов
HLSFIELD_PROCESS_ON_SAVE = True
HLSFIELD_CREATE_PREVIEW = True
HLSFIELD_EXTRACT_METADATA = True
HLSFIELD_USE_DEFAULT_UPLOAD_TO = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'ERROR',  # Только ошибки в тестах
        },
    },
    'loggers': {
        'hlsfield': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'ERROR',
    },
}

# Временные файлы для тестов
HLSFIELD_TEMP_DIR = tempfile.mkdtemp(prefix='hlsfield_test_temp_')
HLSFIELD_KEEP_TEMP_FILES = False

# Уменьшаем ограничения для тестов
HLSFIELD_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
HLSFIELD_MAX_VIDEO_DURATION = 300  # 5 минут
HLSFIELD_MIN_FILE_SIZE = 100  # 100 байт для тестов

# Django настройки
USE_TZ = True
USE_I18N = True
USE_L10N = True
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Отключаем миграции для ускорения тестов
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

# Только для тестов - отключаем миграции
MIGRATION_MODULES = DisableMigrations()

# Кеширование отключено для тестов
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Email backend для тестов
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Отключаем проверки системы для ускорения тестов
SILENCED_SYSTEM_CHECKS = [
    'hlsfield.E001',  # FFmpeg not found
    'hlsfield.E002',  # FFprobe not found
]

# Специальные настройки для тестирования ошибок
HLSFIELD_TEST_MODE = True
HLSFIELD_VERBOSE_LOGGING = False

# Password validation отключена для тестов
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'

# HLSFIELD специфичные настройки для тестов
HLSFIELD_ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.txt']  # Добавляем .txt для тестов
HLSFIELD_ALLOWED_MIME_TYPES = [
    'video/mp4',
    'video/avi',
    'video/mov',
    'video/wmv',
    'video/flv',
    'video/webm',
    'video/x-msvideo',
    'video/quicktime',
    'text/plain',  # Для тестов
]

# Настройки для storage тестов
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Отключаем аналитику и уведомления для тестов
HLSFIELD_ENABLE_ANALYTICS = False
HLSFIELD_SEND_NOTIFICATIONS = False
HLSFIELD_SEARCH_INTEGRATION = False
HLSFIELD_CDN_INTEGRATION = False
HLSFIELD_ENABLE_WEBHOOKS = False
