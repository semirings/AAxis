#!/usr/bin/env python3
from __future__ import annotations

import bpy
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from util_blender import remove_collection_recursive


GEN_COLLECTIONS = [
    "GEN_AA_GRID",
    "GEN_OVERLAY",
    "GEN_DEBUG",
]


def clean_generated() -> None:
    for name in GEN_COLLECTIONS:
        col = bpy.data.collections.get(name)
        if col is not None:
            remove_collection_recursive(col)
print("All clean")