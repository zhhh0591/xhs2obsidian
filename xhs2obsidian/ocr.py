"""用 macOS 自带的 Vision 框架做 OCR。完全离线，图片不会上传到任何地方。"""
from __future__ import annotations

import os

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
    for i, p in enumerate(todo, 1):
        try:
            text = recognize(p, cfg.ocr_languages)
            cache.put(p, text=text)
            log(f"  [{i}/{len(todo)}] {len(text):>5} 字  {os.path.basename(p)[:60]}")
        except RuntimeError as e:
            cache.put(p, text="", error=str(e))
            log(f"  [{i}/{len(todo)}] ✗ {e}  {os.path.basename(p)[:60]}")
        if i % 20 == 0:
            cache.save()
    cache.save()
    return cache
