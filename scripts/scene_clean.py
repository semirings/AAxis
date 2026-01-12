#!/usr/bin/env python3
from __future__ import annotations

import bpy
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
