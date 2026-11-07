"""从库里实际存在的笔记重建「收藏地图」和文件夹 README。不改任何笔记。"""
from __future__ import annotations

import collections
import datetime
import glob
import os
import re

from . import REPO_URL
from .render import topic_label


def read_frontmatter(path: str) -> dict[str, str] | None:
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m:
        return None
    d = {}
    for line in m.group(1).split("\n"):
        if line.startswith(" ") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        d[k.strip()] = v.strip().strip('"')
    return d


def existing_notes(root: str) -> dict[str, str]:
    """{作品ID: 笔记路径}，用来判断哪篇已经导入过（不管你把它挪到了哪个子文件夹）。"""
    out = {}
    for f in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        if os.path.basename(f) == "README.md":
            continue
        fm = read_frontmatter(f)
        if fm and fm.get("note-id"):
            out[fm["note-id"]] = f
    return out


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _cell(s: str) -> str:
    return (s or "").replace("|", "｜").replace("\n", " ")


def rebuild(cfg, log=print) -> None:
    root, today = cfg.notes_root, datetime.date.today().isoformat()
    rel = cfg.notes_dir.strip("/")
    items = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(root, "*", "*.md"))):
        if os.path.basename(f) == "README.md":
            continue
        fm = read_frontmatter(f)
        if not fm or fm.get("platform") != "小红书":
            continue
        items[os.path.basename(os.path.dirname(f))].append(dict(
            name=os.path.splitext(os.path.basename(f))[0],
            title=fm.get("title", ""), author=fm.get("author", ""),
            media=fm.get("media", ""), pub=fm.get("published", ""),
            lik=_int(fm.get("likes")), fav=_int(fm.get("collects")),
            ocr=_int(fm.get("ocr-images")), tr=fm.get("transcript") == "true",
        ))

    topics = sorted(items)
    total = sum(len(v) for v in items.values())
    n_ocr = sum(1 for v in items.values() for i in v if i["ocr"])
    n_tr = sum(1 for v in items.values() for i in v if i["tr"])
    n_any = sum(1 for v in items.values() for i in v if i["ocr"] or i["tr"])

    def link(t, i):
        return f"[[{rel}/{t}/{i['name']}\\|{_cell(i['title'])}]]"

    if cfg.map_path:
        L = ["---", "type: source-map", "status: active", f"updated: {today}",
             "tags:", "  - source/xiaohongshu", "---", "",
             "# 小红书收藏地图", "",
             f"共 **{total} 篇**小红书收藏，由 xhs2obsidian 从 XHS-Downloader 的导出结构化导入。", "",
             f"- 存放位置：`{rel}/<主题>`",
             "- 原文**逐字保留**在每篇笔记的「原文」代码块中，未做任何改写或摘要",
             "- 话题标签保留在 frontmatter 的 `xhs-tags` 属性（作品标签字段 ∪ 正文内联标签）",
             f"- 其中 **{n_ocr} 篇**含图片 OCR 文字、**{n_tr} 篇**含视频转录文字，图片和视频本体没有放进库里",
             "", "## 主题分布", "", "| 主题 | 篇数 | 含提取文字 |", "|---|---:|---:|"]
        for t in topics:
            k = sum(1 for i in items[t] if i["ocr"] or i["tr"])
            L.append(f"| [[#{t}]] | {len(items[t])} | {k} |")
        L += [f"| **合计** | **{total}** | **{n_any}** |", ""]

        L += ["## 收藏最多的 15 篇", "", "| 笔记 | 作者 | ⭐ 收藏 | ❤️ 点赞 | 主题 |", "|---|---|---:|---:|---|"]
        top = sorted(((i, t) for t in topics for i in items[t]), key=lambda x: -x[0]["fav"])[:15]
        for i, t in top:
            L.append(f"| {link(t, i)} | {_cell(i['author'])} | {i['fav']} | {i['lik']} | {topic_label(t)} |")
        L.append("")

        for t in topics:
            v = sorted(items[t], key=lambda x: (-x["fav"], x["pub"]))
            L += [f"## {t}", "", f"共 {len(v)} 篇。", "",
                  "| 笔记 | 作者 | 类型 | 提取文字 | 发布 | ❤️ | ⭐ |", "|---|---|---|---|---|---:|---:|"]
            for i in v:
                mark = " ".join(x for x in (f"🖼️{i['ocr']}" if i["ocr"] else "",
                                            "🎙️" if i["tr"] else "") if x) or "—"
                L.append(f"| {link(t, i)} | {_cell(i['author'])} | {i['media']} | {mark} "
                         f"| {i['pub']} | {i['lik']} | {i['fav']} |")
            L += ["", "🖼️N = 从 N 张图片 OCR 出文字；🎙️ = 有视频转录。", ""]

        os.makedirs(os.path.dirname(cfg.map_path), exist_ok=True)
        with open(cfg.map_path, "w", encoding="utf-8") as f:
            f.write("\n".join(L))
        log(f"索引地图 → {os.path.relpath(cfg.map_path, cfg.vault)}")

    map_link = (f"索引见 [[{os.path.splitext(cfg.map_file)[0]}|小红书收藏地图]]。"
                if cfg.map_path else "")
    readme = f"""---
type: source-index
status: active
updated: {today}
tags:
  - source/xiaohongshu
---

# 小红书收藏

从小红书导出的收藏，共 **{total} 篇**。{map_link}

这些笔记由 [xhs2obsidian]({REPO_URL}) 生成：数据来自 XHS-Downloader 的导出，
**笔记里只存文字，图片和视频本体留在下载目录，没有放进库里。**

## 笔记里的三种文字，性质不同

| 小节 | 来源 | 可靠性 |
|---|---|---|
| 原文 | 作者写的作品描述，逐字保留 | 保留采集文本；观点与事实未经核实 |
| 图片文字（OCR 提取） | macOS Vision 从图片里识别 | **可能有错字漏字** |
| 视频转录 | Whisper 语音识别 | **可能有听错漏句** |

后两种是机器提取的，不是作者原话，引用前请对照原文链接核实。
其中 **{n_ocr} 篇**有图片文字、**{n_tr} 篇**有视频转录。

## 字段约定

| 字段 | 含义 |
|---|---|
| `platform` | 固定为「小红书」 |
| `media` | 视频 / 图文 / 图集 |
| `topic` | 主题，与所在子文件夹一致 |
| `url` | 原文链接；带 `xsec_token` 的可直接打开，否则可能需要登录 |
| `note-id` | 小红书作品 ID，重复运行时靠它识别同一篇 |
| `likes` / `collects` / `comments` / `shares` | 采集时的互动数据；未公开时为空 |
| `ocr-images` | 从几张图片里提取到了文字 |
| `transcript` | 有视频转录则为 true |
| `xhs-tags` | 原始话题标签，取「作品标签字段 ∪ 正文内联标签」的并集 |

## 重新运行时会改什么

再次运行 xhs2obsidian 时，已经存在的笔记只会更新「图片文字」「视频转录」两个小节，
你写在「我的理解」等小节里的内容和你手动挪过的文件夹都会保留。
"""
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"README → {os.path.relpath(os.path.join(root, 'README.md'), cfg.vault)}（共 {total} 篇）")
