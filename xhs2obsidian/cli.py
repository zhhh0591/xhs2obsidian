"""命令行入口：python -m xhs2obsidian <命令>。"""
from __future__ import annotations

import argparse
import collections
import datetime
import os

from . import __version__, config, fetch, index, ocr, reader, transcribe
from .cache import FileCache
from .render import build_note, derive_title, has_prose, safe_name, update_note
from .topics import classify


def _media_texts(note, ocr_cache: FileCache, tr_cache: FileCache):
    o = [(i, (ocr_cache.get(p) or {}).get("text", "")) for i, p in note.images]
    t = [r for p in note.videos if (r := tr_cache.get(p))]
    return o, t


def cmd_scan(cfg, notes, unmatched, log):
    ocr_c = FileCache(os.path.join(cfg.cache, "ocr.json"), cfg.download_dir)
    tr_c = FileCache(os.path.join(cfg.cache, "transcripts.json"), cfg.download_dir)
    imgs = [p for n in notes.values() for _, p in n.images]
    vids = [p for n in notes.values() for p in n.videos]
    existing = index.existing_notes(cfg.notes_root)
    log(f"下载目录：{cfg.download_dir}")
    log(f"  笔记 {len(notes)} 篇（带 xsec_token 链接的 {sum(1 for n in notes.values() if 'xsec_token' in n.url)} 篇）")
    log(f"  图片 {len(imgs)} 张（已 OCR {sum(1 for p in imgs if ocr_c.get(p))}）")
    log(f"  视频 {len(vids)} 个（已转录 {sum(1 for p in vids if tr_c.get(p))}）")
    if unmatched:
        log(f"  ⚠ {len(unmatched)} 个媒体文件找不到对应的 md（XHS-Downloader 需开启 note_format = md）")
    log(f"Obsidian：{cfg.notes_root}")
    log(f"  已导入 {sum(1 for n in notes if n in existing)} 篇，待新建 {sum(1 for n in notes if n not in existing)} 篇")
    plan = collections.Counter(classify(n, cfg) for nid, n in notes.items() if nid not in existing)
    for t, k in sorted(plan.items()):
        log(f"    {t:24s} {k:3d}")


def cmd_build(cfg, notes, log):
    ocr_c = FileCache(os.path.join(cfg.cache, "ocr.json"), cfg.download_dir)
    tr_c = FileCache(os.path.join(cfg.cache, "transcripts.json"), cfg.download_dir)
    existing = index.existing_notes(cfg.notes_root)
    today = datetime.date.today().isoformat()
    stat = collections.Counter()

    for n in sorted(notes.values(), key=lambda n: n.pub):
        o, t = _media_texts(n, ocr_c, tr_c)
        label = (n.title or n.nid)[:28]
        if n.nid in existing:
            path = existing[n.nid]
            with open(path, encoding="utf-8") as f:
                old = f.read()
            new = update_note(old, o, t)
            if new != old:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
                stat["更新"] += 1
                log(f"  更新  {label}")
            else:
                stat["无变化"] += 1
            continue

        has_media_text = any(x.strip() for _, x in o) or any(r.get("text", "").strip() for r in t)
        if cfg.skip_empty and not has_prose(n) and not has_media_text:
            stat["跳过（无文字）"] += 1
            log(f"  跳过  {label}（没有文字正文，也没有 OCR / 转录文字）")
            continue

        topic = classify(n, cfg)
        folder = os.path.join(cfg.notes_root, topic)
        os.makedirs(folder, exist_ok=True)
        base =f"{safe_name(derive_title(n))} - {safe_name(n.author, 20)}"
        path = os.path.join(folder, base + ".md")
        if os.path.exists(path):
            path = os.path.join(folder, f"{base} {n.pub.split('_')[0] or n.nid}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_note(n, topic, o, t, cfg.scaffold, today))
        stat["新建"] += 1
        log(f"  新建  {label} → {topic}")

    log("完成：" + "，".join(f"{k} {v}" for k, v in stat.items()) if stat else "没有笔记可处理")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="xhs2obsidian",
        description="下载小红书作品，并整理成 Obsidian 笔记（含图片 OCR 和视频转录）。",
    )
    ap.add_argument("-c", "--config", default="config.toml", help="配置文件，默认 ./config.toml")
    ap.add_argument("--vault", help="临时改写配置里的 vault，比如先输出到一个空文件夹试跑")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="命令")

    def with_links(p):
        p.add_argument("links", nargs="*", help="作品链接或分享文案，可以写多个")
        p.add_argument("-f", "--file", help="从文本文件读取链接（一行一个，或直接粘贴分享文案）")
        return p

    with_links(sub.add_parser("run", help="一条命令跑完：下载 → OCR → 转录 → 写笔记 → 重建索引；不给链接就只处理已下载的"))
    with_links(sub.add_parser("fetch", help="只下载作品（调用自带的 XHS-Downloader）"))
    sub.add_parser("scan", help="只读取并统计，不写任何文件")
    sub.add_parser("ocr", help="对图片做 OCR（结果缓存，重跑只处理新图片）")
    sub.add_parser("transcribe", help="转录视频（结果缓存，重跑只处理新视频）")
    sub.add_parser("build", help="新建 / 更新 Obsidian 笔记")
    sub.add_parser("index", help="重建收藏地图和 README")
    args = ap.parse_args(argv)

    cfg = config.load(args.config, args.vault)
    log = print

    if args.cmd in ("run", "fetch"):
        text = fetch.collect_links(args.links, args.file)
        if text:
            fetch.run(cfg, text, log)
        elif args.cmd == "fetch":
            log("没有提供链接：xhs2obsidian fetch <链接…> 或 -f links.txt")
            return 1
        if args.cmd == "fetch":
            return 0

    if args.cmd == "index":
        index.rebuild(cfg, log)
        return 0

    notes, unmatched = reader.load(cfg.download_dir)
    if not notes:
        log(f"在 {cfg.download_dir} 里没找到任何笔记（需要 XHS-Downloader 导出的 *.md 或 ExploreData.db）")
        return 1

    if args.cmd == "scan":
        cmd_scan(cfg, notes, unmatched, log)
    if args.cmd in ("ocr", "run") and cfg.ocr_enabled:
        ocr.run(cfg, notes, log)
    if args.cmd in ("transcribe", "run") and cfg.tr_enabled:
        transcribe.run(cfg, notes, log)
    if args.cmd in ("build", "run"):
        cmd_build(cfg, notes, log)
    if args.cmd == "run":
        index.rebuild(cfg, log)
    return 0
