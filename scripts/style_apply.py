#!/usr/bin/env python3
from __future__ import annotations

import bpy
from typing import Optional

from util_blender import ensure_material, ensure_font
from style_theme import Theme, DEFAULT_THEME


def _set_principled_rgba(mat: bpy.types.Material, rgba):
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = None
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bsdf = n
            break
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Alpha"].default_value = rgba[3]
    mat.blend_method = "BLEND" if rgba[3] < 1.0 else "OPAQUE"


def ensure_theme_materials(theme: Theme = DEFAULT_THEME) -> dict:
    mats = {}

    mats["GRID_INACTIVE"] = ensure_material("MAT_GRID_INACTIVE")
    _set_principled_rgba(mats["GRID_INACTIVE"], theme.grid_inactive)

    mats["GRID_ACTIVE"] = ensure_material("MAT_GRID_ACTIVE")
    _set_principled_rgba(mats["GRID_ACTIVE"], theme.grid_active)

    mats["CARD_BG"] = ensure_material("MAT_CARD_BG")
    _set_principled_rgba(mats["CARD_BG"], theme.card_bg)

    mats["CARD_TEXT"] = ensure_material("MAT_CARD_TEXT")
    _set_principled_rgba(mats["CARD_TEXT"], theme.card_text)

    return mats


def apply_fonts_to_text_objects(theme: Theme, root_collection_name: str) -> None:
    col = bpy.data.collections.get(root_collection_name)
    if col is None:
        return

    font_main = ensure_font(theme.font_main_path) if theme.font_main_path else None
    font_mono = ensure_font(theme.font_mono_path) if theme.font_mono_path else None

    for obj in col.all_objects:
        if obj.type != "FONT":
            continue
        # Heuristic: code cards contain "CODE" in name => mono
        if font_mono and "CODE" in obj.name:
            obj.data.font = font_mono
        elif font_main:
            obj.data.font = font_main


def apply_card_style(theme: Theme, cards_root: str = "GEN_OVERLAY_CARDS") -> None:
    mats = ensure_theme_materials(theme)
    col = bpy.data.collections.get(cards_root)
    if col is None:
        return

    for obj in col.all_objects:
        if obj.type == "MESH":
            # background plane
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mats["CARD_BG"])
            else:
                obj.data.materials[0] = mats["CARD_BG"]
        elif obj.type == "FONT":
            obj.data.size = theme.card_text_size
            # assign card text material (Font uses materials too)
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mats["CARD_TEXT"])
            else:
                obj.data.materials[0] = mats["CARD_TEXT"]


def apply_grid_style(theme: Theme, grid_obj_name: str = "AA_GRID__MESH") -> None:
    # For a GN-driven grid, style typically lives in node group materials.
    # Here we at least assign a base material to the underlying mesh as fallback.
    mats = ensure_theme_materials(theme)
    obj = bpy.data.objects.get(grid_obj_name)
    if obj and obj.type == "MESH":
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mats["GRID_INACTIVE"])
        else:
            obj.data.materials[0] = mats["GRID_INACTIVE"]


def apply_theme(theme: Theme = DEFAULT_THEME) -> None:
    # Cards
    apply_card_style(theme, "GEN_OVERLAY_CARDS")
    apply_card_style(theme, "GEN_OVERLAY_LABELS")
    apply_fonts_to_text_objects(theme, "GEN_OVERLAY")
    # Grid
    apply_grid_style(theme, "AA_GRID__MESH")
