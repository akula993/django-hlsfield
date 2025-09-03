import os
import sys

# Добавляем путь к src в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = 'test-secret-key-for-hlsfield'

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',  # Добавляем admin
    'django.contrib.auth',   # Добавляем auth (нужен для admin)
    'django.contrib.contenttypes',
    'django.contrib.sessions',  # Добавляем sessions (может понадобиться)
    'django.contrib.messages',  # Добавляем messages (может понадобиться)
    'hlsfield',
    'examples',  # Добавляем examples приложениеpython manage.py makemigrations examples

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

USE_TZ = True

# Настройки для тестов
HLSFIELD_FFMPEG = 'ffmpeg'
HLSFIELD_FFPROBE = 'ffprobe'
HLSFIELD_PROCESS_ON_SAVE = False
