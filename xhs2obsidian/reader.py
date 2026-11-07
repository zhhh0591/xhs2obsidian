"""读取 XHS-Downloader 的产物：*.md 导出、ExploreData.db、下载的图片和视频。

XHS-Downloader 设置里 note_format = "md" 时，每篇笔记会多一个 md 文件，
里面有作品 ID；同一篇的图片/视频与 md 共用文件名前缀（图片再加 _1、_2…）。
我们靠这个把媒体文件归到对应笔记。ExploreData.db（record_data = true 时生成）
多一个带 xsec_token 的原文链接，用来补全 md 里没有的 url。
"""
from __future__ import annotations

import glob
import os
import re
import sqlite3
from dataclasses import dataclass, field

IMAGE_EXT = (".jpeg", ".jpg", ".png", ".webp", ".heic", ".avif")
VIDEO_EXT = (".mp4", ".mov", ".m4v")


@dataclass
class Note:
    nid: str
    media: str = ""   # 视频 / 图文 / 图集
    title: str = ""
    desc: str = ""
    tags: str = ""    # 「作品标签」字段，空格分隔
    pub: str = ""     # 2026-07-25_12:06:26
    lik: str = ""
    fav: str = ""
    cmt: str = ""
    shr: str = ""
    author: str = ""
    aid: str = ""
    aurl: str = ""
    url: str = ""
    saved: str = ""   # 采集 / 保存时间
    images: list[tuple[int, str]] = field(default_factory=list)  # (序号, 路径)
    videos: list[str] = field(default_factory=list)


_MD_FIELDS = {
    "作品ID": "nid", "作品类型": "media", "发布时间": "pub", "作品标题": "title",
    "作品标签": "tags", "作品链接": "url",
    "点赞数量": "lik", "收藏数量": "fav", "评论数量": "cmt", "分享数量": "shr",
    "作者昵称": "author", "作者ID": "aid", "作者链接": "aurl",
}

_DB_COLS = {
    "作品ID": "nid", "作品类型": "media", "作品标题": "title", "作品描述": "desc",
    "作品标签": "tags", "发布时间": "pub", "收藏数量": "fav", "评论数量": "cmt",
    "分享数量": "shr", "点赞数量": "lik", "作者昵称": "author", "作者ID": "aid",
    "作者链接": "aurl", "作品链接": "url", "采集时间": "saved",
}


def parse_md(path: str) -> dict[str, str]:
    """解析 XHS-Downloader 导出的 md，逐字还原作品描述。"""
    with open(path, encoding="utf-8") as f:
        t = f.read()
    out: dict[str, str] = {}
    for label, key in _MD_FIELDS.items():
        # 有的行在 ** 前面还有个 emoji，比如 "- ❤️ **点赞数量**：311"
        m = re.search(r"^- (?:\S+ )?\*\*" + label + r"\*\*：`?(.*?)`?\s*$", t, re.M)
        if m:
            out[key] = m.group(1).strip()

    # 作品描述是一串 "  > 内容  " 行：去掉行首 "  > " 和导出器加的行尾两个空格
    m = re.search(r"^- \*\*作品描述\*\*：\n((?:  >.*\n?)*)", t, re.M)
    if m:
        lines = m.group(1).split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        lines = [re.sub(r"  $", "", re.sub(r"^  > ?", "", ln)) for ln in lines]
        out["desc"] = "\n".join(lines)

    m = re.search(r"保存时间：(.*?)\*", t)
    if m:
        out["saved"] = m.group(1).strip()
    return out


def read_db(path: str):
    """逐行读取 ExploreData.db 的 explore_data 表。"""
    con = sqlite3.connect(path)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(explore_data)")]
        use = [c for c in _DB_COLS if c in cols]
        if "作品ID" not in use:
            return
        for row in con.execute(f"SELECT {','.join(use)} FROM explore_data"):
            yield {_DB_COLS[c]: ("" if v is None else str(v)) for c, v in zip(use, row)}
    finally:
        con.close()


def _fill(note: Note, data: dict[str, str]) -> None:
    """只填空字段，先读到的来源优先。"""
    for k, v in data.items():
        if k != "nid" and v and not getattr(note, k):
            setattr(note, k, v)


def load(download_dir: str) -> tuple[dict[str, Note], list[str]]:
    """返回 ({作品ID: Note}, 无法归属的媒体文件列表)。"""
    notes: dict[str, Note] = {}
    stem2nid: dict[str, str] = {}
    dir2nids: dict[str, set[str]] = {}

    # glob 的 ** 不进隐藏目录，所以缓存目录 .xhs2obsidian 不会被扫到
    for path in sorted(glob.glob(os.path.join(download_dir, "**", "*.md"), recursive=True)):
        d = parse_md(path)
        nid = d.get("nid")
        if not nid:
            continue
        _fill(notes.setdefault(nid, Note(nid)), d)
        stem2nid[os.path.splitext(path)[0]] = nid
        dir2nids.setdefault(os.path.dirname(path), set()).add(nid)

    for db in sorted(glob.glob(os.path.join(download_dir, "**", "ExploreData.db"), recursive=True)):
        for d in read_db(db):
            if d.get("nid"):
                _fill(notes.setdefault(d["nid"], Note(d["nid"])), d)

    unmatched: list[str] = []
    for path in sorted(glob.glob(os.path.join(download_dir, "**", "*"), recursive=True)):
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXT + VIDEO_EXT:
            continue
        stem = os.path.splitext(path)[0]
        m = re.fullmatch(r"(.*)_(\d+)", stem)
        idx = int(m.group(2)) if m else 1
        nid = stem2nid.get(stem)
        if not nid and m:
            nid = stem2nid.get(m.group(1))
        folder = os.path.dirname(path)
        if not nid and os.path.normpath(folder) != os.path.normpath(download_dir):
            # folder_mode：一篇笔记一个子文件夹，文件夹里只有一个 md
            ids = dir2nids.get(folder, set())
            nid = next(iter(ids)) if len(ids) == 1 else None
        if not nid:
            unmatched.append(path)
            continue
        if ext in IMAGE_EXT:
            notes[nid].images.append((idx, path))
        else:
            notes[nid].videos.append(path)

    for n in notes.values():
        n.images.sort()
    return notes, unmatched
