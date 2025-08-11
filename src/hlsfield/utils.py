import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

from . import defaults


@contextmanager
def tempdir(prefix: str = "hlsfield_"):
    d = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT: {cp.stdout}\nSTDERR: {cp.stderr}")
    return cp


def ffprobe_streams(input_path: str | os.PathLike) -> Dict[str, Any]:
    cmd = [defaults.FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(input_path)]
    cp = run(cmd)
    return json.loads(cp.stdout)


def pick_video_audio_streams(info: Dict[str, Any]):
    v = a = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s
        if s.get("codec_type") == "audio" and a is None:
            a = s
    return v, a


def extract_preview(input_path: Path, out_image: Path, at_sec: float = 3.0):
    cmd = [defaults.FFMPEG, "-y", "-ss", str(at_sec), "-i", str(input_path), "-frames:v", "1", "-q:v", "2",
           str(out_image)]
    run(cmd)


def transcode_hls_variants(input_path: Path, out_dir: Path, ladder: List[dict], segment_duration: int = 6):
    out_dir.mkdir(parents=True, exist_ok=True)

    # detect presence of audio
    info = ffprobe_streams(input_path)
    _v, a = pick_video_audio_streams(info)
    has_audio = a is not None

    variant_infos = []
    for rung in ladder:
        h = int(rung["height"])
        vkbps = int(rung["v_bitrate"])
        akbps = int(rung["a_bitrate"])
        var_dir = out_dir / f"v{h}"
        var_dir.mkdir(exist_ok=True)
        playlist = var_dir / "index.m3u8"

        # scale by height, keep AR; then pad to even dims (libx264 requires even)
        vf = f"scale=w=-2:h={h}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2"

        cmd = [
            defaults.FFMPEG, "-y",
            "-i", str(input_path),
            "-map", "0:v:0",
            "-vf", vf,
            "-c:v", "h264", "-profile:v", "main", "-preset", "veryfast",
            "-b:v", f"{vkbps}k", "-maxrate", f"{int(vkbps * 1.07)}k", "-bufsize", f"{vkbps * 2}k",
            "-pix_fmt", "yuv420p",
            "-f", "hls",
            "-hls_time", str(segment_duration),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(var_dir / "seg_%04d.ts"),
        ]

        if has_audio:
            cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", f"{akbps}k", "-ac", "2", "-ar", "48000"]
        else:
            cmd += ["-an"]

        cmd.append(str(playlist))
        run(cmd)

        approx_w = int((h * 16 / 9) // 2 * 2)
        variant_infos.append({
            "height": h,
            "bandwidth": (vkbps + (akbps if has_audio else 0)) * 1000,
            "playlist": playlist.name,
            "dir": var_dir.name,
            "resolution": f"{approx_w}x{h}",
        })

    master = out_dir / "master.m3u8"
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for vi in sorted(variant_infos, key=lambda x: x["height"]):
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={vi['bandwidth']},RESOLUTION={vi['resolution']}")
        lines.append(f"{vi['dir']}/{vi['playlist']}")
    master.write_text("\n".join(lines), encoding="utf-8")
    return master


def save_tree_to_storage(local_root: Path, storage, base_path: str) -> list[str]:
    saved_paths: list[str] = []
    for root, _dirs, files in os.walk(local_root):
        for fname in files:
            abs_path = Path(root) / fname
            rel = str(abs_path.relative_to(local_root)).replace("\\", "/")
            key = f"{base_path.rstrip('/')}/{rel}"
            with abs_path.open("rb") as fh:
                storage.save(key, fh)
            saved_paths.append(key)
    return saved_paths


def pull_to_local(storage, name: str, dst_dir: Path) -> Path:
    try:
        p = Path(storage.path(name))
        if p.exists():
            return p
    except Exception:
        pass
    dst = dst_dir / Path(name).name
    with storage.open(name, "rb") as src, dst.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dst


def transcode_dash_variants(input_path: Path, out_dir: Path, ladder: List[dict], segment_duration: int = 4):
    """Создает DASH адаптивный стрим с multiple bitrates"""
    out_dir.mkdir(parents=True, exist_ok=True)

    # detect audio
    info = ffprobe_streams(input_path)
    _v, a = pick_video_audio_streams(info)
    has_audio = a is not None

    # Собираем все варианты в одной команде ffmpeg для DASH
    cmd = [defaults.FFMPEG, "-y", "-i", str(input_path)]

    map_args = []
    filter_complex_parts = []
    output_args = []

    # Создаем фильтры для каждого разрешения
    for i, rung in enumerate(ladder):
        h = int(rung["height"])
        vkbps = int(rung["v_bitrate"])

        # Фильтр масштабирования с выравниванием по четным пикселям
        vf = f"scale=w=-2:h={h}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        filter_complex_parts.append(f"[0:v]{vf}[v{i}]")

        map_args.extend(["-map", f"[v{i}]"])
        output_args.extend([
            f"-c:v:{i}", "libx264",
            f"-preset:v:{i}", "veryfast",
            f"-profile:v:{i}", "main",
            f"-b:v:{i}", f"{vkbps}k",
            f"-maxrate:v:{i}", f"{int(vkbps * 1.07)}k",
            f"-bufsize:v:{i}", f"{vkbps * 2}k",
            f"-pix_fmt:v:{i}", "yuv420p"
        ])

    # Добавляем аудио если есть
    if has_audio:
        for i, rung in enumerate(ladder):
            akbps = int(rung["a_bitrate"])
            map_args.extend(["-map", "0:a:0"])
            output_args.extend([
                f"-c:a:{i}", "aac",
                f"-b:a:{i}", f"{akbps}k",
                f"-ac:a:{i}", "2",
                f"-ar:a:{i}", "48000"
            ])

    if filter_complex_parts:
        cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])

    cmd.extend(map_args)
    cmd.extend(output_args)

    # DASH-специфичные параметры
    cmd.extend([
        "-f", "dash",
        "-seg_duration", str(segment_duration),
        "-use_template", "1",
        "-use_timeline", "1",
        "-init_seg_name", "init-$RepresentationID$.$ext$",
        "-media_seg_name", "chunk-$RepresentationID$-$Number%05d$.$ext$",
        str(out_dir / "manifest.mpd")
    ])

    run(cmd)
    return out_dir / "manifest.mpd"


def transcode_adaptive_variants(input_path: Path, out_dir: Path, ladder: List[dict], segment_duration: int = 6):
    """Создает и HLS и DASH одновременно, с общими сегментами где возможно"""
    hls_dir = out_dir / "hls"
    dash_dir = out_dir / "dash"

    # Сначала создаем HLS
    hls_master = transcode_hls_variants(input_path, hls_dir, ladder, segment_duration)

    # Затем DASH
    dash_manifest = transcode_dash_variants(input_path, dash_dir, ladder, segment_duration)

    return {
        "hls_master": hls_master,
        "dash_manifest": dash_manifest,
        "hls_dir": hls_dir,
        "dash_dir": dash_dir
    }

