"""Kali-inspired design system (colors, fonts, spacing) for the Windows GUI.

Same palette as the Linux build; only the font stack is tuned for fonts that
ship with Windows 11 (Cascadia / Consolas / Segoe UI).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # Surfaces
    bg: str = "#0B0E14"
    surface: str = "#11151C"
    surface_alt: str = "#161B22"
    border: str = "#1F2630"
    overlay: str = "#0A0D12"

    # Text
    text: str = "#C9D1D9"
    text_dim: str = "#8B949E"
    text_faint: str = "#5A6470"

    # Kali brand accents
    accent: str = "#367BF0"
    accent_hi: str = "#5B95F5"
    cyan: str = "#17B2C3"
    dragon: str = "#ED1C24"

    # Status
    ok: str = "#2ECC71"
    warn: str = "#F5A623"
    err: str = "#FF4D5A"
    idle: str = "#6E7681"


PALETTE = Palette()

# Font stack: prefer crisp monospace fonts shipped with Windows 11.
MONO = ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New", "monospace")
SANS = ("Segoe UI Variable", "Segoe UI", "Inter", "sans-serif")


def font(size: int = 11, *, bold: bool = False, mono: bool = True):
    family = MONO[0] if mono else SANS[0]
    return (family, size, "bold") if bold else (family, size)


SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
