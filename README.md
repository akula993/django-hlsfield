# django-hlsfield (черновик)

**Цель**: Сделать два поля для Django:

* `VideoField` — хранит оригинал, автоматически извлекает метаданные (длительность/размер кадра), делает превью-кадр.
* `HLSVideoField(VideoField)` — наследуется от `VideoField` и **автоматизирует** генерацию HLS (варианты качества,
  master.m3u8), чтобы фронтенд мог выбирать качество без дублирования полноразмерных файлов.

Особенности:

* ffmpeg/ffprobe через `subprocess`.
* Генерация превью-кадра (jpg/png) на указанной секунде.
* Хранение метаданных в полях модели (`DurationField`, `width`, `height`) + путь к `master.m3u8`.
* Построено под асинхронную обработку через Celery (тяжёлая перекодировка уходит в задачу). Есть синхронный «fallback»
  на случай отсутствия Celery.
* Работа с любым `Storage` (в т.ч. S3): все вычисления в temp-директории, потом — заливка артефактов в хранилище.

> **Требования**: установленный `ffmpeg`/`ffprobe` в PATH или указать пути в Django settings.

---

## Структура пакета

```
apps/
  hlsfield/
    __init__.py
    fields.py          # VideoField, HLSVideoField
    utils.py           # ffprobe/ffmpeg helpers, temp utils
    widgets.py         # Превью в админке
    tasks.py           # Celery задача: генерация HLS
    players/
      hls_player.html  # Пример шаблона с hls.js
```

---

## settings.py (пример)

```python
# Пути к бинарям (опционально)
HLSFIELD_FFPROBE = r"ffprobe"  # или полный путь
HLSFIELD_FFMPEG = r"ffmpeg"  # или полный путь

# Лестница качеств по умолчанию (h x video_bitrate_kbps)
HLSFIELD_DEFAULT_LADDER = [
    {"height": 240, "v_bitrate": 300, "a_bitrate": 64},
    {"height": 360, "v_bitrate": 800, "a_bitrate": 96},
    {"height": 480, "v_bitrate": 1200, "a_bitrate": 96},
    {"height": 720, "v_bitrate": 2500, "a_bitrate": 128},
    {"height": 1080, "v_bitrate": 4500, "a_bitrate": 160},
]

# HLS сегментация
HLSFIELD_SEGMENT_DURATION = 6  # секунд
```

## Заметки по продакшену

* **Кодеки**: для совместимости используем H.264/AAC. Если нужен HEVC/AV1 — добавьте флаги в
  `utils.transcode_hls_variants`.
* **S3/MinIO**: будет работать «из коробки», так как все артефакты сохраняются через `storage.save()`.
* **Без дублирования**: оригинал хранится один; фронтенд воспроизводит HLS, набор «кусков» на разных битрейтах — это не
  «полные копии», а сегменты для адаптивного стриминга.
* **Транскодирование в фоне**: используйте Celery + отдельный воркер. В админке/вью можно показать статус
  `hls_built_at`.
* **Очистка**: по сигналу `post_delete` модели удаляйте оригинал и директорию HLS-артефактов (реализуйте при
  необходимости).
* **Безопасность**: для приватного доступа отдавайте HLS через подписанные URL (S3, Nginx/X-Accel, CloudFront).

---

## TODO / Идеи

* Валидация MIME через `python-magic`.
* Генерация WebVTT-сабов для предпросмотра (sprite) и таймкодов.
* Генерация DASH (mpd) параллельно HLS.
* Пул воркеров ffmpeg, лимиты CPU/GPU.

````
# settings.py
HLSFIELD_DEFAULT_UPLOAD_TO = "hlsfield.upload_to.video_upload_to"
HLSFIELD_SIDECAR_LAYOUT = "nested"  # по умолчанию и так nested в моём примере



---

## Быстрый старт: Model + Admin + Views + URLs + Templates

Ниже — минимальный набор кода, чтобы **сразу загрузить видео** и посмотреть HLS в браузере без плясок с бубном.

> Предполагаем, что пакет `django-hlsfield` уже установлен, а в системе есть `ffmpeg/ffprobe` в PATH.

### 0) settings.py
```python
INSTALLED_APPS = [
    # ...
    "django.contrib.staticfiles",
    "hlsfield",   # наше приложение-пакет
    "video",      # ваше app с моделью Lecture
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# (опционально) указать явные пути к бинарям
HLSFIELD_FFPROBE = "ffprobe"
HLSFIELD_FFMPEG  = "ffmpeg"
````

### 1) models.py

```python
from django.db import models
from hlsfield.fields import HLSVideoField


class Lecture(models.Model):
    title = models.CharField(max_length=255)
    video = HLSVideoField(upload_to="videos/", hls_playlist_field="hls_master")
    hls_master = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.title
```

### 2) admin.py

```python
from django.contrib import admin
from .models import Lecture


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ("id", "title")
```

> Можно красиво врезать плеер и в админке, если захотите, через `hlsfield.widgets.AdminVideoWidget`.

### 3) views.py (в app `video`)

```python
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView
from django import forms
from .models import Lecture


class LectureForm(forms.ModelForm):
    class Meta:
        model = Lecture
        fields = ["title", "video"]


class LectureCreateView(CreateView):
    model = Lecture
    form_class = LectureForm
    template_name = "video/upload.html"

    def get_success_url(self):
        return reverse("video:detail", args=[self.object.pk])


class LectureDetailView(DetailView):
    model = Lecture
    template_name = "video/detail.html"


class LectureListView(ListView):
    model = Lecture
    template_name = "video/list.html"
    paginate_by = 20
```

### 4) urls.py (в app `video`)

```python
from django.urls import path
from .views import LectureCreateView, LectureDetailView, LectureListView

app_name = "video"

urlpatterns = [
    path("upload/", LectureCreateView.as_view(), name="upload"),
    path("<int:pk>/", LectureDetailView.as_view(), name="detail"),
    path("", LectureListView.as_view(), name="list"),
]
```

### 5) Корневой urls.py (проекта)

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("video.urls", namespace="video")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### 6) Шаблоны

Создайте папки:

```
video/templates/video/
```

**`video/templates/video/base.html`** (примитивный каркас)

```html
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{% block title %}Видео{% endblock %}</title>
    <style>body {
        font-family: system-ui, sans-serif;
        margin: 2rem auto;
        max-width: 960px
    }</style>
</head>
<body>
<nav><a href="{% url 'video:list' %}">Список</a> · <a href="{% url 'video:upload' %}">Загрузить</a></nav>
<hr/>
{% block content %}{% endblock %}
</body>
</html>
```

**`video/templates/video/upload.html`**

```html
{% extends "video/base.html" %}
{% block title %}Загрузка{% endblock %}
{% block content %}
<h1>Загрузить видео</h1>
<form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Сохранить</button>
</form>
<p>Совет: для проверки возьми небольшой файл (5–20 МБ), иначе без Celery запрос будет дольше.</p>
{% endblock %}
```

**`video/templates/video/detail.html`**

```html
{% extends "video/base.html" %}
{% block title %}{{ object.title }}{% endblock %}
{% block content %}
<h1>{{ object.title }}</h1>
{% if object.video.master_url %}
{% include "hlsfield/players/hls_player.html" with hls_url=object.video.master_url %}
{% else %}
<p>Видео ещё обрабатывается… Обновите страницу через минуту.</p>
{% endif %}
{% endblock %}
```

**`video/templates/video/list.html`**

```html
{% extends "video/base.html" %}
{% block title %}Список{% endblock %}
{% block content %}
<h1>Лекции</h1>
<ul>
    {% for obj in object_list %}
    <li><a href="{% url 'video:detail' obj.pk %}">{{ obj.title }}</a></li>
    {% empty %}
    <li>Пока пусто. <a href="{% url 'video:upload' %}">Загрузите первое видео</a>.</li>
    {% endfor %}
</ul>
{% endblock %}
```

### 7) Миграции и запуск

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # по желанию
python manage.py runserver
```

Затем открой:

* загрузка: `http://127.0.0.1:8000/upload/`
* список: `http://127.0.0.1:8000/`

> **Как это работает:** при сохранении `Lecture` поле `HLSVideoField` создаёт превью и метаданные; HLS-генерация
> запускается после `post_save` (когда объект уже имеет `pk`). Если Celery не установлен — выполняется синхронно, но уже *
*после** того, как объект записан в БД.
