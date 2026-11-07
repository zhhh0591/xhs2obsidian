"""读取 config.toml。"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field


def _path(s: str) -> str:
    return os.path.abspath(os.path.expanduser(s)) if s else ""


@dataclass
class Config:
    download_dir: str
    vault: str
    notes_dir: str = "10 Sources/小红书收藏"
    map_file: str = "50 Maps/小红书收藏地图.md"
    cache_dir: str = ""

    dl_cookie: str = ""
    dl_proxy: str = ""
    dl_name_format: str = "发布时间 作者昵称 作品标题"
    dl_image_format: str = "JPEG"
    dl_video_cover: bool = False
    dl_skip_downloaded: bool = True

    skip_empty: bool = True
    scaffold: bool = True

    ocr_enabled: bool = True
    ocr_languages: list[str] = field(default_factory=lambda: ["zh-Hans", "en-US"])

    tr_enabled: bool = True
    tr_model: str = "mlx-community/whisper-large-v3-turbo"
    tr_language: str = "zh"
    tr_prompt: str = ""

    topic_keywords: dict[str, list[str]] = field(default_factory=dict)
    topic_default: str = "99 未分类"
    topic_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def notes_root(self) -> str:
        return os.path.join(self.vault, self.notes_dir)

    @property
    def map_path(self) -> str:
        return os.path.join(self.vault, self.map_file) if self.map_file else ""

    @property
    def cache(self) -> str:
        return self.cache_dir or os.path.join(self.download_dir, ".xhs2obsidian")


def load(path: str, vault: str | None = None) -> Config:
    if not os.path.exists(path):
        raise SystemExit(f"找不到配置文件 {path}。先运行：cp config.example.toml config.toml，再按注释修改。")
    with open(path, "rb") as f:
        d = tomllib.load(f)

    p = d.get("paths", {})
    dl = d.get("download", {})
    b = d.get("build", {})
    o = d.get("ocr", {})
    t = d.get("transcribe", {})
    tp = d.get("topics", {})

    if not p.get("download_dir") or not (vault or p.get("vault")):
        raise SystemExit(f"{path}：[paths] 里必须填写 download_dir 和 vault")

    c = Config(download_dir=_path(p["download_dir"]), vault=_path(vault or p["vault"]))
    c.notes_dir = p.get("notes_dir", c.notes_dir)
    c.map_file = p.get("map_file", c.map_file)
    c.cache_dir = _path(p.get("cache_dir", ""))
    # Cookie 优先读环境变量，避免写进文件
    c.dl_cookie = os.environ.get("XHS_COOKIE") or dl.get("cookie", "")
    c.dl_proxy = dl.get("proxy", "")
    c.dl_name_format = dl.get("name_format", c.dl_name_format)
    c.dl_image_format = dl.get("image_format", c.dl_image_format)
    c.dl_video_cover = dl.get("video_cover", c.dl_video_cover)
    c.dl_skip_downloaded = dl.get("skip_downloaded", c.dl_skip_downloaded)
    c.skip_empty = b.get("skip_empty", c.skip_empty)
    c.scaffold = b.get("scaffold", c.scaffold)
    c.ocr_enabled = o.get("enabled", c.ocr_enabled)
    c.ocr_languages = o.get("languages", c.ocr_languages)
    c.tr_enabled = t.get("enabled", c.tr_enabled)
    c.tr_model = t.get("model", c.tr_model)
    c.tr_language = t.get("language", c.tr_language)
    c.tr_prompt = t.get("prompt", c.tr_prompt)
    c.topic_default = tp.get("default", c.topic_default)
    c.topic_keywords = dict(tp.get("keywords", {}))
    c.topic_overrides = dict(tp.get("overrides", {}))

    return c
