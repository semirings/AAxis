#!/usr/bin/env python3
from __future__ import annotations

from util_blender import ensure_collection

def setup_collections():
    # Root generated collections
    col_grid = ensure_collection("GEN_AA_GRID")
    col_overlay = ensure_collection("GEN_OVERLAY")
    col_debug = ensure_collection("GEN_DEBUG")

    # Overlay children
    col_cards = ensure_collection("GEN_OVERLAY_CARDS", parent=col_overlay)
    col_labels = ensure_collection("GEN_OVERLAY_LABELS", parent=col_overlay)

    return {
        "grid": col_grid,
        "overlay": col_overlay,
        "cards": col_cards,
        "labels": col_labels,
        "debug": col_debug,
    }
