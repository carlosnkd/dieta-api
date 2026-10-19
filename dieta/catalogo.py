import json
from functools import lru_cache

from .config import DATA_DIR


@lru_cache
def plan() -> dict:
    return json.loads((DATA_DIR / "plan.json").read_text(encoding="utf-8"))


@lru_cache
def equivalencias() -> dict:
    return json.loads((DATA_DIR / "equivalencias.json").read_text(encoding="utf-8"))


def categorias() -> dict[str, dict]:
    return plan()["categorias"]


def metas() -> dict[str, float]:
    return {k: v["meta_diaria"] for k, v in categorias().items()}
