"""按关键词给笔记归主题（主题 = 子文件夹名）。"""
from __future__ import annotations

import re

from .render import all_tags


def _hits(keyword: str, text: str) -> bool:
    if re.fullmatch(r"[a-z0-9 .+#-]+", keyword):
        # 纯英文关键词按词边界匹配，避免 "ai" 命中 "said"
        return re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", text) is not None
    return keyword in text


def classify(note, cfg) -> str:
    """作品 ID 手动指定优先；否则标题命中 3 分、标签 2 分、正文 1 分，取最高分的主题。"""
    if note.nid in cfg.topic_overrides:
        return cfg.topic_overrides[note.nid]
    title = note.title.lower()
    tags = " ".join(all_tags(note)).lower()
    desc = note.desc.lower()
    best, best_score = cfg.topic_default, 0
    for topic, keywords in cfg.topic_keywords.items():
        score = 0
        for k in (k.lower() for k in keywords):
            score += 3 * _hits(k, title) + 2 * _hits(k, tags) + _hits(k, desc)
        if score > best_score:
            best, best_score = topic, score
    return best
