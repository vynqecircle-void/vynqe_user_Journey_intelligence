"""Config loader. Leaves are dicts that carry 'grade'; v(path) returns the leaf value."""
from __future__ import annotations
import json
from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class Cfg:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls, pack: str) -> "Cfg":
        with open(CONFIG_DIR / f"{pack}.yaml") as f:
            return cls(yaml.safe_load(f))

    def v(self, path: str):
        node = self.data
        for k in path.split("."):
            node = node[k]
        if isinstance(node, dict) and "grade" in node:
            return node["value"]
        return node

    def leaves(self):
        def walk(node, prefix):
            if isinstance(node, dict) and "grade" in node:
                yield prefix, node
            elif isinstance(node, dict):
                for k, val in node.items():
                    yield from walk(val, f"{prefix}.{k}" if prefix else k)
        yield from walk(self.data, "")

    def parameters_report(self) -> list[dict]:
        return [{"parameter": p, "value": json.dumps(n.get("value"), default=str)[:300],
                 "grade": n["grade"], "question": str(n.get("q", "")), "note": n.get("note", "")}
                for p, n in self.leaves()]


def load_preset(name: str, pack: str = "ecommerce") -> dict:
    with open(CONFIG_DIR / "presets.yaml") as f:
        presets = yaml.safe_load(f)
    if pack != "ecommerce":
        presets = presets[pack]
    if name not in presets:
        raise SystemExit(f"unknown preset {name}; choose from {list(presets)}")
    return presets[name]
