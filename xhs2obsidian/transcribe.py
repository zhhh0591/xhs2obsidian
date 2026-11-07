"""视频转录：先抽出 16kHz 单声道音轨，再用 mlx-whisper 在本机（Apple Silicon）转写。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import wave

from .cache import FileCache


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
    r = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=cfg.tr_model,
        language=cfg.tr_language or None,
        initial_prompt=cfg.tr_prompt or None,
        verbose=None,
    )
    s = int(round(seconds))
    return {
        "text": r["text"].strip(),
        "model": cfg.tr_model.rsplit("/", 1)[-1],
        "duration": f"{s // 60}分{s % 60}秒",
    }


def run(cfg, notes, log=print) -> FileCache:
    cache = FileCache(os.path.join(cfg.cache, "transcripts.json"), cfg.download_dir)
    todo = [p for n in notes.values() for p in n.videos if cache.get(p) is None]
    total = sum(len(n.videos) for n in notes.values())
    log(f"转录：共 {total} 个视频，{total - len(todo)} 个已有缓存，{len(todo)} 个待转录")
    if todo:
        log(f"  模型 {cfg.tr_model}（首次运行会自动下载，large-v3-turbo 约 1.6GB）")
    for i, p in enumerate(todo, 1):
        t0 = time.time()
        try:
            rec = transcribe(p, cfg)
            cache.put(p, **rec)
            log(f"  [{i}/{len(todo)}] {rec['duration']:>8} → {len(rec['text']):>5} 字"
                f"（{time.time() - t0:.0f}s）  {os.path.basename(p)[:50]}")
        except RuntimeError as e:
            cache.put(p, text="", error=str(e))
            log(f"  [{i}/{len(todo)}] ✗ {e}  {os.path.basename(p)[:50]}")
        cache.save()
    return cache
