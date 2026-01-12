#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Optional


Color = Tuple[float, float, float, float]  # RGBA 0..1


@dataclass(frozen=True)
class Theme:
    # Fonts
    font_main_path: Optional[str] = None
    font_mono_path: Optional[str] = None

    # Base palette
    bg: Color = (0.06, 0.06, 0.07, 1.0)
    grid_inactive: Color = (0.25, 0.25, 0.27, 1.0)
    grid_active: Color = (0.15, 0.80, 0.90, 1.0)  # cyan-ish highlight
    grid_previous: Color = (0.12, 0.45, 0.50, 1.0)

    # Resource type accents (optional chips/labels)
    type_colors: Dict[str, Color] = None  # filled in __post_init__ below

    # Card styling
    card_bg: Color = (0.06, 0.06, 0.07, 0.75)
    card_text: Color = (0.95, 0.95, 0.96, 1.0)
    card_padding: float = 0.10
    card_text_size: float = 0.35  # Blender font size units vary by scene scale

    # Borders/rounding (implemented as bevel on plane mesh if you convert, or via shader)
    card_rounding: float = 0.02

    def __post_init__(self):
        if self.type_colors is None:
            object.__setattr__(self, "type_colors", {
                "Patient": (0.20, 0.55, 0.95, 1.0),
                "Encounter": (0.30, 0.85, 0.45, 1.0),
                "Observation": (0.95, 0.60, 0.20, 1.0),
                "Practitioner": (0.85, 0.30, 0.85, 1.0),
                "Specimen": (0.95, 0.90, 0.25, 1.0),
            })


DEFAULT_THEME = Theme()
