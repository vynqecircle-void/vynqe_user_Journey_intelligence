"""Chunked writers: Parquet always, CSV optional. Hidden tables go to a separate folder."""
from __future__ import annotations
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.csv as pacsv


class TableWriter:
    def __init__(self, root: Path, name: str, schema: pa.Schema, csv: bool = False):
        root.mkdir(parents=True, exist_ok=True)
        self.name, self.n = name, 0
        self.pq = pq.ParquetWriter(root / f"{name}.parquet", schema, compression="zstd")
        self.csv = pacsv.CSVWriter(root / f"{name}.csv", schema) if csv else None

    def write(self, tbl: pa.Table):
        self.pq.write_table(tbl)
        if self.csv:
            self.csv.write_table(tbl)
        self.n += tbl.num_rows

    def close(self):
        self.pq.close()
        if self.csv:
            self.csv.close()
