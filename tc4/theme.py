"""Kali Linux inspired design system (colors, fonts, spacing).

A single source of truth so the GUI looks consistent and enterprise-grade.
Palette mirrors the modern Kali dark theme: near-black panels, signature
Kali blue accents, dragon-red for danger, and crisp cyan/green status hues.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # Surfaces
    bg: str = "#0B0E14"          # app background (deep slate-black)
    surface: str = "#11151C"     # cards / panels
    surface_alt: str = "#161B22" # raised elements, table rows
    border: str = "#1F2630"      # hairline borders
    overlay: str = "#0A0D12"     # console / terminal bg

    # Text
    text: str = "#C9D1D9"        # primary text
    text_dim: str = "#8B949E"    # secondary text
    text_faint: str = "#5A6470"  # disabled / hints

    # Kali brand accents
    accent: str = "#367BF0"      # Kali blue (primary action)
    accent_hi: str = "#5B95F5"   # hover/brighter blue
    cyan: str = "#17B2C3"        # info / links
    dragon: str = "#ED1C24"      # Kali dragon red (danger)

    # Status
    ok: str = "#2ECC71"          # connected / pass
    warn: str = "#F5A623"        # warning
    err: str = "#FF4D5A"         # error / fail
    idle: str = "#6E7681"        # disconnected / neutral


PALETTE = Palette()

# Font stack: prefer crisp monospace fonts shipped with Kali.
MONO = ("JetBrains Mono", "Hack", "DejaVu Sans Mono", "monospace")
SANS = ("Inter", "Cantarell", "DejaVu Sans", "sans-serif")


_cached_mono = None
_cached_sans = None


def _find_first_available(families_list: tuple[str, ...]) -> str:
    try:
        import tkinter as tk
        import tkinter.font as tkfont
        if tk._default_root is not None:
            available = {f.lower() for f in tkfont.families()}
            for f in families_list:
                if f.lower() in available or f in ("monospace", "sans-serif"):
                    return f
    except Exception:
        pass
    return families_list[0]


def font(size: int = 11, *, bold: bool = False, mono: bool = True):
    global _cached_mono, _cached_sans
    if mono:
        if _cached_mono is None:
            _cached_mono = _find_first_available(MONO)
        family = _cached_mono
    else:
        if _cached_sans is None:
            _cached_sans = _find_first_available(SANS)
        family = _cached_sans
    return (family, size, "bold") if bold else (family, size)


# 8pt spacing scale keeps layouts tidy and consistent.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
