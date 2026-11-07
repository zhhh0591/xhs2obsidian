"""调用仓库自带的 XHS-Downloader 下载作品：md 导出 + ExploreData.db + 图片/视频。

XHS-Downloader 源码放在仓库根目录的 XHS-Downloader/ 里（GPL-3.0，作者 JoeanAmier），
它的包名叫 source，所以这里把那个目录临时加进 sys.path 再导入。
"""
from __future__ import annotations

import asyncio
import os
import sys

VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "XHS-Downloader")


def _import_xhs():
    if not os.path.isdir(os.path.join(VENDOR, "source")):
        raise SystemExit(f"找不到 XHS-Downloader 源码：{VENDOR}")
    if VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)
    try:
        from source import XHS
    except ImportError as e:
        raise SystemExit(f"无法导入 XHS-Downloader（{e}）。先安装依赖：pip install -r requirements.txt") from e
    return XHS


def collect_links(links: list[str], file: str | None) -> str:
    """命令行里的链接 + 文件里的内容。分享文案、短链、作品链接、作者主页链接都可以，XHS-Downloader 自己会提取。"""
    text = " ".join(links)
    if file:
        with open(file, encoding="utf-8") as f:
            text += "\n" + f.read()
    return text.strip()


async def _run(cfg, text: str) -> list[dict]:
    XHS = _import_xhs()
    work_path, folder = os.path.split(cfg.download_dir.rstrip(os.sep))
    async with XHS(
        work_path=work_path,
        folder_name=folder,
        name_format=cfg.dl_name_format,
        cookie=cfg.dl_cookie,
        proxy=cfg.dl_proxy or None,
        image_format=cfg.dl_image_format,
        video_cover_download=cfg.dl_video_cover,
        # 下面几项是转换 Obsidian 笔记所依赖的，不开放修改
        note_format="md",        # 每篇导出一个 md，用来把图片/视频归到对应笔记
        record_data=True,        # 写 ExploreData.db，里面有带 xsec_token 的原文链接
        folder_mode=False,
        author_archive=False,
        download_record=True,    # 已下载过的作品自动跳过
        language="zh_CN",
    ) as xhs:
        return await xhs.extract(text, download=True)


def run(cfg, text: str, log=print) -> int:
    if not text:
        log("没有提供链接")
        return 0
    os.makedirs(cfg.download_dir, exist_ok=True)
    result = asyncio.run(_run(cfg, text))
    ok = [r for r in result if r]
    log(f"下载：处理了 {len(result)} 个链接，成功取到 {len(ok)} 篇作品数据 → {cfg.download_dir}")
    return len(ok)
