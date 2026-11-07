"""OCR / 转录结果的 JSON 缓存：按「相对下载目录的路径 + 文件大小」记，重跑时跳过已处理的文件。"""
from __future__ import annotations

import json
import os


class FileCache:
    def __init__(self, path: str, base: str):
        self.path, self.base = path, base
        self.data: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _key(self, file: str) -> str:
        return os.path.relpath(file, self.base)

    def get(self, file: str) -> dict | None:
        rec = self.data.get(self._key(file))
        if rec and rec.get("size") == os.path.getsize(file):
            return rec
        return None

    def put(self, file: str, **rec) -> None:
        self.data[self._key(file)] = {"size": os.path.getsize(file), **rec}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
