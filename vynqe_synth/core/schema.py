"""Table contracts: columns, types, nullability, allowed values. The generator fails if output breaks them."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import pyarrow as pa


@dataclass(frozen=True)
class Col:
    name: str
    dtype: str            # string | int | float | bool | timestamp | json
    nullable: bool = False
    allowed: tuple | None = None
    desc: str = ""


@dataclass(frozen=True)
class TableSchema:
    name: str
    cols: tuple
    desc: str = ""
    hidden: bool = False

    @property
    def names(self):
        return [c.name for c in self.cols]

    def arrow(self) -> pa.Schema:
        return pa.schema([pa.field(c.name, PA[c.dtype], nullable=c.nullable) for c in self.cols])

    def to_json(self) -> dict:
        return {"table": self.name, "hidden": self.hidden, "description": self.desc,
                "columns": [{"name": c.name, "type": c.dtype, "nullable": c.nullable,
                             "allowed": list(c.allowed) if c.allowed else None, "description": c.desc}
                            for c in self.cols]}


PA = {"string": pa.string(), "int": pa.int64(), "float": pa.float64(), "bool": pa.bool_(),
      "timestamp": pa.timestamp("ms", tz="UTC"), "json": pa.string()}


def conform(schema: TableSchema, df: pd.DataFrame) -> pa.Table:
    """Validate a chunk against its contract and return an Arrow table. Raises ValueError on any breach."""
    missing = [c for c in schema.names if c not in df.columns]
    extra = [c for c in df.columns if c not in schema.names]
    if missing or extra:
        raise ValueError(f"{schema.name}: missing {missing} extra {extra}")
    df = df[schema.names]
    for c in schema.cols:
        s = df[c.name]
        if not c.nullable and s.isna().any():
            raise ValueError(f"{schema.name}.{c.name}: {int(s.isna().sum())} nulls in non-nullable column")
        if c.allowed is not None:
            bad = s.dropna()[~s.dropna().isin(c.allowed)]
            if len(bad):
                raise ValueError(f"{schema.name}.{c.name}: values outside allowed set: {sorted(set(bad))[:5]}")
    df = df.copy()
    for c in schema.cols:
        if c.dtype == "timestamp":
            df[c.name] = pd.to_datetime(df[c.name], utc=True)
        elif c.dtype == "int":
            df[c.name] = pd.array(df[c.name], dtype="Int64")
        elif c.dtype == "bool":
            df[c.name] = pd.array(df[c.name], dtype="boolean")
    return pa.Table.from_pandas(df, schema=schema.arrow(), preserve_index=False, safe=False)


def dump_schemas(schemas: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, s in schemas.items():
        (out_dir / f"{name}.json").write_text(json.dumps(s.to_json(), indent=1))
