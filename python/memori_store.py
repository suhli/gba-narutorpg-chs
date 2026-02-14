#!/usr/bin/env python3
"""
Memori 术语记忆库：用于翻译时检索与写入日文→中文术语，保证全局一致。
与 translate.instruction.md 中约定的工具语义一致：
- search(query) -> {hits: [{jp, zh, note}]}
- upsert(jp, zh, note) -> ok
"""

import json
import re
from pathlib import Path
from typing import Any


class MemoriStore:
    """基于 JSON 文件的 Memori 实现，支持 search 与 upsert。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: list[dict[str, str]] = []  # [{jp, zh, note}, ...]
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = data.get("terms", [])
                if not isinstance(self._records, list):
                    self._records = []
            except (json.JSONDecodeError, IOError):
                self._records = []
        else:
            self._records = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"terms": self._records}, f, ensure_ascii=False, indent=2)

    def search(self, query: str) -> dict[str, Any]:
        """
        检索术语：按日文或备注模糊匹配。
        query 可以是片段日文或中文，返回包含该关键词的条目。
        """
        query = (query or "").strip()
        hits = []
        if not query:
            return {"hits": []}
        q_lower = query.lower()
        for r in self._records:
            jp = (r.get("jp") or "").strip()
            zh = (r.get("zh") or "").strip()
            note = (r.get("note") or "").strip()
            if (
                q_lower in jp.lower()
                or q_lower in zh.lower()
                or q_lower in note.lower()
                or (query in jp or query in zh)
            ):
                hits.append({"jp": jp, "zh": zh, "note": note})
        return {"hits": hits}

    def search_for_texts(self, texts: list[str]) -> dict[str, Any]:
        """对多条原文做检索，合并去重后返回所有相关术语（用于注入 prompt）。"""
        seen: set[tuple[str, str, str]] = set()
        hits: list[dict[str, str]] = []
        for t in texts:
            t = (t or "").strip()
            if not t:
                continue
            # 用整句和可能的片段（去掉空格）检索
            for part in re.split(r"[\s　]+", t):
                if len(part) < 2:
                    continue
                for h in self.search(part).get("hits", []):
                    key = (h.get("jp", ""), h.get("zh", ""), h.get("note", ""))
                    if key not in seen:
                        seen.add(key)
                        hits.append(h)
        return {"hits": hits}

    def upsert(self, jp: str, zh: str, note: str = "") -> str:
        """写入或更新一条术语；若 jp 已存在则更新，否则追加。返回 "ok"。"""
        jp = (jp or "").strip()
        zh = (zh or "").strip()
        note = (note or "").strip()
        if not jp:
            return "ok"
        for r in self._records:
            if (r.get("jp") or "").strip() == jp:
                r["zh"] = zh
                r["note"] = note
                self._save()
                return "ok"
        self._records.append({"jp": jp, "zh": zh, "note": note})
        self._save()
        return "ok"
