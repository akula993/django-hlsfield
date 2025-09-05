"""
Django настройки для тестирования django-hlsfield
"""

import os
import tempfile

# Build paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Security
SECRET_KEY = 'test-secret-key-for-django-hlsfield-testing'
DEBUG = True
ALLOWED_HOSTS = ['*']

# Application definition - ДОБАВЛЕНО django.contrib.admin
INSTALLED_APPS = [
    'django.contrib.admin',  # ← ДОБАВЛЕНО
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
MEDIA_ROOT = tempfile.mkdtemp()

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = tempfile.mkdtemp()

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

# HLSField настройки
HLSFIELD_FFMPEG = 'ffmpeg'
HLSFIELD_FFPROBE = 'ffprobe'
HLSFIELD_SEGMENT_DURATION = 6
HLSFIELD_DEFAULT_LADDER = [
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
]

# Отключаем Celery для тестов
HLSFIELD_USE_CELERY = False

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'hlsfield': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}

# Временные файлы для тестов
HLSFIELD_TEMP_DIR = tempfile.mkdtemp()
HLSFIELD_KEEP_TEMP_FILES = False

# Уменьшаем ограничения для тестов
HLSFIELD_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
HLSFIELD_MAX_VIDEO_DURATION = 300  # 5 минут

# Django 5.0+ compatibility
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
