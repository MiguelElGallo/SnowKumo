"""Shared helpers for the annual Snowflake Workspace notebook."""

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CELLS: list[dict] = []


def cell(source: str, name: str, language: str = "python") -> None:
    source = textwrap.dedent(source).strip() + "\n"
    metadata = {"name": name}
    kind = "markdown" if language == "markdown" else "code"
    if language == "sql":
        metadata.update(language="sql", resultVariableName=name)
        source = f"%%sql -r {name}\n" + source
    item = {
        "cell_type": kind,
        "id": f"hkn{len(CELLS):05d}",
        "metadata": metadata,
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        item.update(execution_count=None, outputs=[])
    CELLS.append(item)


PREFLIGHT = """
import importlib.metadata
import platform
import shutil
import sys
import torch
from snowflake.snowpark.context import get_active_session

session = get_active_session()
session.use_database("HELSINKI_WEATHER_LAB")
session.use_schema("KUMO")
print({"python": sys.version, "machine": platform.machine(),
       "torch": torch.__version__, "cuda": torch.version.cuda,
       "cuda_available": torch.cuda.is_available(),
       "scratch_free_gb": round(shutil.disk_usage("/tmp").free / 1e9, 2)})
assert sys.version_info[:2] == (3, 12), "Select GPU Container Runtime 2.9 / Python 3.12"
assert torch.cuda.is_available(), "GPU execution unavailable; do not continue to fit"
print(torch.cuda.get_device_name(0))
print("GPU memory GiB:", torch.cuda.get_device_properties(0).total_memory / 2**30)
"""


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
