from __future__ import annotations

import os
from pathlib import Path

try:
    from celery import shared_task
except Exception:
    def shared_task(*_a, **_kw):
        def deco(fn): return fn

        return deco

from django.apps import apps
from django.db import transaction
from . import utils, defaults


def _resolve_field(instance, field_name: str):
    field = instance._meta.get_field(field_name)
    file = getattr(instance, field_name)
    storage = file.storage
    name = file.name
    return field, file, storage, name


def _hls_out_base(name: str, subdir: str) -> str:
    base, _ext = os.path.splitext(name)
    return f"{base}/{subdir}/"


@shared_task
def build_hls_for_field(model_label: str, pk: int | str, field_name: str):
    build_hls_for_field_sync(model_label, pk, field_name)


def build_hls_for_field_sync(model_label: str, pk: int | str, field_name: str):
    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)
    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)
        local_hls_root = Path(td) / "hls_out";
        local_hls_root.mkdir(parents=True, exist_ok=True)
        master = utils.transcode_hls_variants(
            input_path=local_input,
            out_dir=local_hls_root,
            ladder=getattr(field, "ladder", defaults.DEFAULT_LADDER),
            segment_duration=getattr(field, "segment_duration", defaults.SEGMENT_DURATION),
        )
        base_key = _hls_out_base(name, getattr(field, "hls_base_subdir", defaults.HLS_SUBDIR))
        utils.save_tree_to_storage(local_hls_root, storage, base_key)
        master_key = base_key + master.name
    playlist_field = getattr(field, "hls_playlist_field", None)
    if playlist_field:
        setattr(instance, playlist_field, master_key)
    if hasattr(instance, "hls_built_at"):
        from django.utils import timezone
        instance.hls_built_at = timezone.now()
    with transaction.atomic():
        if playlist_field:
            fields = [playlist_field]
            if hasattr(instance, "hls_built_at"):
                fields.append("hls_built_at")
            instance.save(update_fields=fields)
        else:
            instance.save()

@shared_task
def build_dash_for_field(model_label: str, pk: int | str, field_name: str):
    build_dash_for_field_sync(model_label, pk, field_name)


def build_dash_for_field_sync(model_label: str, pk: int | str, field_name: str):
    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)
        local_dash_root = Path(td) / "dash_out"
        local_dash_root.mkdir(parents=True, exist_ok=True)

        manifest = utils.transcode_dash_variants(
            input_path=local_input,
            out_dir=local_dash_root,
            ladder=getattr(field, "ladder", defaults.DEFAULT_LADDER),
            segment_duration=getattr(field, "segment_duration", defaults.SEGMENT_DURATION),
        )

        base_key = _dash_out_base(name, getattr(field, "dash_base_subdir", "dash"))
        utils.save_tree_to_storage(local_dash_root, storage, base_key)
        manifest_key = base_key + manifest.name

    # Сохраняем путь к manifest.mpd
    manifest_field = getattr(field, "dash_manifest_field", None)
    if manifest_field:
        setattr(instance, manifest_field, manifest_key)

    if hasattr(instance, "dash_built_at"):
        from django.utils import timezone
        instance.dash_built_at = timezone.now()

    with transaction.atomic():
        if manifest_field:
            fields = [manifest_field]
            if hasattr(instance, "dash_built_at"):
                fields.append("dash_built_at")
            instance.save(update_fields=fields)
        else:
            instance.save()


@shared_task
def build_adaptive_for_field(model_label: str, pk: int | str, field_name: str):
    build_adaptive_for_field_sync(model_label, pk, field_name)


def build_adaptive_for_field_sync(model_label: str, pk: int | str, field_name: str):
    Model = apps.get_model(model_label)
    instance = Model.objects.get(pk=pk)
    field, file, storage, name = _resolve_field(instance, field_name)

    with utils.tempdir() as td:
        local_input = utils.pull_to_local(storage, name, td)
        local_adaptive_root = Path(td) / "adaptive_out"
        local_adaptive_root.mkdir(parents=True, exist_ok=True)

        results = utils.transcode_adaptive_variants(
            input_path=local_input,
            out_dir=local_adaptive_root,
            ladder=getattr(field, "ladder", defaults.DEFAULT_LADDER),
            segment_duration=getattr(field, "segment_duration", defaults.SEGMENT_DURATION),
        )

        base_key = _adaptive_out_base(name, getattr(field, "adaptive_base_subdir", "adaptive"))
        utils.save_tree_to_storage(local_adaptive_root, storage, base_key)

        hls_master_key = base_key + f"hls/{results['hls_master'].name}"
        dash_manifest_key = base_key + f"dash/{results['dash_manifest'].name}"

    # Сохраняем пути к обоим манифестам
    hls_field = getattr(field, "hls_playlist_field", None)
    dash_field = getattr(field, "dash_manifest_field", None)

    if hls_field:
        setattr(instance, hls_field, hls_master_key)
    if dash_field:
        setattr(instance, dash_field, dash_manifest_key)

    if hasattr(instance, "adaptive_built_at"):
        from django.utils import timezone
        instance.adaptive_built_at = timezone.now()

    with transaction.atomic():
        fields = []
        if hls_field: fields.append(hls_field)
        if dash_field: fields.append(dash_field)
        if hasattr(instance, "adaptive_built_at"): fields.append("adaptive_built_at")

        if fields:
            instance.save(update_fields=fields)
        else:
            instance.save()


def _dash_out_base(name: str, subdir: str) -> str:
    base, _ext = os.path.splitext(name)
    return f"{base}/{subdir}/"


def _adaptive_out_base(name: str, subdir: str) -> str:
    base, _ext = os.path.splitext(name)
    return f"{base}/{subdir}/"

