"""视频转录：先抽出 16kHz 单声道音轨，再用 mlx-whisper 在本机（Apple Silicon）转写。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import wave

from .cache import FileCache

# 完整版：权重 1.6GB，运行时约占 3.5GB 内存
FULL_MODEL = "mlx-community/whisper-large-v3-turbo"
# 4-bit 量化版：权重 464MB，运行时约占 1.2GB 内存；中文实测与完整版字符相似度约 97%
LIGHT_MODEL = "mlx-community/whisper-large-v3-turbo-q4"
FULL_MODEL_MIN_RAM_GB = 16


def physical_ram_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (ValueError, OSError, AttributeError):
        return 0.0


def resolve_model(name: str, ram_gb: float | None = None) -> str:
    """model = "auto"（或留空）时按内存选：16GB 及以上用完整版，否则用量化版，避免 8GB 的 Mac 大量换页卡死。"""
    if name and name.lower() != "auto":
        return name
    ram_gb = physical_ram_gb() if ram_gb is None else ram_gb
    return FULL_MODEL if ram_gb >= FULL_MODEL_MIN_RAM_GB else LIGHT_MODEL


def _limit_mlx_cache(limit_mb: int = 256) -> None:
    """MLX 默认会留着用完的显存不还，转长视频时进程能涨到好几 GB。
    限制在 256MB：4 分钟视频的内存峰值从 2.5GB 降到 1.6GB，结果完全相同，内存紧张时还更快。"""
    import mlx.core as mx

    setter = getattr(mx, "set_cache_limit", None) or getattr(getattr(mx, "metal", None), "set_cache_limit", None)
    if setter:
        setter(limit_mb * 1024**2)


def extract_audio(video: str, wav: str) -> None:
    if shutil.which("afconvert"):  # macOS 自带
        cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", video, wav]
    elif shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", video,
               "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav]
    else:
        raise RuntimeError("需要 afconvert（macOS 自带）或 ffmpeg 来提取音轨")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError(f"提取音轨失败（视频可能没有声音）：{(r.stderr or r.stdout).strip()[:200]}")


def load_wav(path: str):
    """用标准库读 16bit 单声道 WAV，转成 whisper 要的 float32 数组（不依赖 ffmpeg）。"""
    import numpy as np

    with wave.open(path) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise RuntimeError("需要 16bit 单声道 WAV")
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        idx = np.linspace(0, len(a) - 1, int(len(a) * 16000 / sr))
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a, len(a) / 16000


def transcribe(video: str, cfg) -> dict:
    try:
        import mlx_whisper
    except ImportError as e:
        raise RuntimeError("视频转录需要 Apple Silicon 和 mlx-whisper：pip install mlx-whisper numpy") from e

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "audio.wav")
        extract_audio(video, wav)
        audio, seconds = load_wav(wav)
    _limit_mlx_cache()
    model = resolve_model(cfg.tr_model)
    r = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        language=cfg.tr_language or None,
        initial_prompt=cfg.tr_prompt or None,
        verbose=None,
    )
    s = int(round(seconds))
    return {
        "text": r["text"].strip(),
        "model": model.rsplit("/", 1)[-1],
        "duration": f"{s // 60}分{s % 60}秒",
    }


def run(cfg, notes, log=print) -> FileCache:
    cache = FileCache(os.path.join(cfg.cache, "transcripts.json"), cfg.download_dir)
    todo = [p for n in notes.values() for p in n.videos if cache.get(p) is None]
    total = sum(len(n.videos) for n in notes.values())
    log(f"转录：共 {total} 个视频，{total - len(todo)} 个已有缓存，{len(todo)} 个待转录")
    if todo:
        model = resolve_model(cfg.tr_model)
        why = ""
        if not cfg.tr_model or cfg.tr_model.lower() == "auto":
            why = f"（本机内存 {physical_ram_gb():.0f}GB，自动选择）"
        log(f"  模型 {model}{why}；首次运行会自动下载")
    for i, p in enumerate(todo, 1):
        t0 = time.time()
        try:
            rec = transcribe(p, cfg)
            cache.put(p, **rec)
            log(f"  [{i}/{len(todo)}] {rec['duration']:>8} → {len(rec['text']):>5} 字"
                f"（{time.time() - t0:.0f}s）  {os.path.basename(p)[:50]}")
        except RuntimeError as e:
            # 失败的不写缓存，下次运行会再试
            log(f"  [{i}/{len(todo)}] ✗ {e}  {os.path.basename(p)[:50]}")
            continue
        cache.save()
    return cache
