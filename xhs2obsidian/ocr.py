"""用 macOS 自带的 Vision 框架做 OCR。完全离线，图片不会上传到任何地方。"""
from __future__ import annotations

import os
import time

from .cache import FileCache


def recognize(path: str, languages: list[str]) -> str:
    """识别一张图片，返回按「自上而下、自左而右」排好的文本行。"""
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except ImportError as e:
        raise RuntimeError(
            "OCR 需要 macOS 和 pyobjc：pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
        ) from e

    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(path), None)
    if src is None:
        raise RuntimeError("无法读取图片")
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if img is None:
        raise RuntimeError("无法解码图片")

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(list(languages))
    req.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(str(err))

    lines = []
    for o in req.results() or []:
        cand = o.topCandidates_(1)
        if cand:
            bb = o.boundingBox()  # Vision 的坐标原点在左下角
            lines.append((-round(bb.origin.y, 3), bb.origin.x, cand[0].string()))
    lines.sort()
    return "\n".join(t for _, _, t in lines)


def run(cfg, notes, log=print) -> FileCache:
    cache = FileCache(os.path.join(cfg.cache, "ocr.json"), cfg.download_dir)
    todo = [p for n in notes.values() for _, p in n.images if cache.get(p) is None]
    total = sum(len(n.images) for n in notes.values())
    log(f"OCR：共 {total} 张图片，{total - len(todo)} 张已有缓存，{len(todo)} 张待识别")
    failed = 0
    for i, p in enumerate(todo, 1):
        for attempt in range(3):
            try:
                text = recognize(p, cfg.ocr_languages)
                break
            except RuntimeError as e:
                err = e
                time.sleep(1 + attempt)  # Vision 偶尔因神经网络引擎被占用而失败，稍等重试
        else:
            # 失败的不写缓存，下次运行会再试
            failed += 1
            log(f"  [{i}/{len(todo)}] ✗ {str(err)[:80]}  {os.path.basename(p)[:50]}")
            continue
        cache.put(p, text=text)
        log(f"  [{i}/{len(todo)}] {len(text):>5} 字  {os.path.basename(p)[:60]}")
        if i % 20 == 0:
            cache.save()
    cache.save()
    if failed:
        log(f"  {failed} 张识别失败，没有写入缓存，下次运行会重试（同时在跑转录等占用芯片的任务时更容易失败）")
    return cache
