#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from pathlib import Path

Color = Tuple[float, float, float, float]  # RGBA 0..1\

@staticmethod
def hex_to_rgba(hex_color: str, alpha: float = 1.0):
    """
    Convert a hex color (#RRGGBB or RRGGBB) to a Blender RGBA tuple (0–1 floats).
    """
    hex_color = hex_color.strip().lstrip("#")

    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")

    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    return (r, g, b, alpha)
@dataclass(frozen=True)
class Theme:
    # Fonts
    font_main_path: Optional[str] = str(
        Path("/Users/gcr/Vignettes/BlenderShared/Fonts/Graphik-Font-Family/GraphikRegular.otf")
    )
    font_mono_path: Optional[str] = str(
        Path("/Users/gcr/Vignettes/BlenderShared/Fonts/Roboto_Slab/static/RobotoSlab-Regular.ttf")
    )

    # Base palette

    bg: Color = hex_to_rgba("#4F5F77")
    fg: Color = hex_to_rgba("#FFFFFF")
    title: Color = hex_to_rgba("#DB3B26")
    grid_inactive: Color = hex_to_rgba("#6F6F6F")
    grid_active: Color = hex_to_rgba("#FFFFFF")  # cyan-ish highlight
    grid_previous: Color = (0.12, 0.45, 0.50, 1.0)

    # Resource type accents (optional chips/labels)
    type_colors: Dict[str, Color] = None  # filled in __post_init__ below

    # Card styling
    card_bg: Color = hex_to_rgba("#F4F0AC")
    card_text: Color = hex_to_rgba("#000000")
    card_padding: float = 0.10
    card_text_size: float = 0.35  # Blender font size units vary by scene scale

    # Borders/rounding (implemented as bevel on plane mesh if you convert, or via shader)
    card_rounding: float = 0.02

    def __post_init__(self):
        if self.type_colors is None:
            object.__setattr__(self, "type_colors", {
                "Patient": hex_to_rgba("#FAE232"),
                "Encounter": hex_to_rgba("#EF5FA7"),
                "Observation": hex_to_rgba("#FFFFFF"),
                "Practitioner": hex_to_rgba("#FF9301"),
                "Specimen": hex_to_rgba("#A9A9A9"),
            })

DEFAULT_THEME = Theme()
print("style_theme loaded, DEFAULT_THEME:", DEFAULT_THEME.bg)
