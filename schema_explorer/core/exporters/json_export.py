# -*- coding: utf-8 -*-
"""Plain JSON export of the graph contract (PLAN.md, section 11)."""
from __future__ import annotations

import json


def to_json(graph: dict, *, indent: int | None = 2) -> str:
    """Serialize ``graph`` deterministically (sorted keys, stable indent)
    so exports can be diffed in review or CI (PLAN.md, section 20, "CI mode")."""
    return json.dumps(graph, indent=indent, sort_keys=True, default=str, ensure_ascii=False)
