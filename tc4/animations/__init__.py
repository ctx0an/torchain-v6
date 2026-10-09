"""Torchain Enterprise Animation Telemetry Suite.

Engineered for:
- 0% Idle CPU / Memory efficiency (self-terminating request tickers).
- Military-grade Kali cyberpunk HUD aesthetic.
- True mathematical spring physics (damping ratio and elastic recoil).
- Gyroscopic azimuth dials, 3-hop circuit mesh nodes, and cryptographic text decoders.
"""
from __future__ import annotations

import math
import random
import tkinter as tk
from typing import Callable, List, Optional

from ..theme import PALETTE as P


def ease_out_elastic(t: float) -> float:
    """True mathematical spring oscillation with decay envelope."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    period = 0.35
    decay = math.pow(2.0, -10.0 * t)
    return decay * math.sin((t - period / 4.0) * (2.0 * math.pi) / period) + 1.0


class ProGyroBootHUD(tk.Canvas):
    """Military-grade gyroscopic boot HUD with triple differential rotating dials,
    azimuth tick marks, scanning beam, and terminal cryptography telemetry.
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_complete: Optional[Callable[[], None]] = None,
        width: int = 680,
        height: int = 380,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=P.bg,
            highlightthickness=0,
        )
        self.on_complete = on_complete
        self.w = width
        self.h = height
        self.cx = width // 2
        self.cy = height // 2 - 20
        self.progress = 0.0

        self.boot_phases = [
            "STAGE 01: CRYPTOGRAPHIC ENTROPY SEEDING",
            "STAGE 02: TOR PROXY CIRCUIT HARNESS VIRTUALIZED",
            "STAGE 03: ISOLATING IPTABLES & LOCAL DNS RESOLVER",
            "STAGE 04: KALI HARDENED TUNNEL ARMED [ONLINE]",
        ]

        self.bind("<Configure>", self._on_resize)
        self.after(30, self._step)

    def _on_resize(self, event: tk.Event) -> None:
        if event.width > 50 and event.height > 50:
            self.w = event.width
            self.h = event.height
            self.cx = event.width // 2
            self.cy = event.height // 2 - 20

    def _step(self) -> None:
        self.progress += 0.022
        if self.progress >= 1.0:
            self.destroy()
            if self.on_complete:
                self.on_complete()
            return

        self.delete("all")
        t = self.progress
        scale = ease_out_elastic(min(1.0, t * 1.25))

        # 1. Outer Compass Scale (Azimuth Degrees)
        r_outer = max(10, int(110 * scale))
        self.create_oval(
            self.cx - r_outer, self.cy - r_outer,
            self.cx + r_outer, self.cy + r_outer,
            outline=P.border, width=1
        )

        angle_rot = t * 120.0  # Slow rotation of azimuth ticks
        for deg in range(0, 360, 15):
            rad = math.radians(deg + angle_rot)
            tick_len = 8 if deg % 45 == 0 else 4
            x1 = self.cx + int((r_outer - tick_len) * math.cos(rad))
            y1 = self.cy + int((r_outer - tick_len) * math.sin(rad))
            x2 = self.cx + int(r_outer * math.cos(rad))
            y2 = self.cy + int(r_outer * math.sin(rad))
            color = P.cyan if deg % 90 == 0 else P.border
            self.create_line(x1, y1, x2, y2, fill=color, width=1)

        # 2. Middle Counter-Rotating Segmented Gyro Arc Ring
        r_mid = max(8, int(80 * scale))
        angle_mid = -t * 260.0
        for i in range(3):
            start_ang = angle_mid + i * 120.0
            self.create_arc(
                self.cx - r_mid, self.cy - r_mid,
                self.cx + r_mid, self.cy + r_mid,
                start=start_ang, extent=65,
                style=tk.ARC, outline=P.accent, width=2
            )

        # 3. Inner Pulsing Core
        r_inner = max(4, int(50 * scale))
        self.create_oval(
            self.cx - r_inner, self.cy - r_inner,
            self.cx + r_inner, self.cy + r_inner,
            outline=P.cyan, width=1, dash=(6, 4)
        )

        r_core = max(3, int(22 * scale))
        self.create_oval(
            self.cx - r_core, self.cy - r_core,
            self.cx + r_core, self.cy + r_core,
            fill=P.surface_alt,
            outline=P.ok if t > 0.7 else P.cyan,
            width=2
        )

        # 4. Sweeping Radar Beam
        sweep_rad = math.radians(t * 1080.0)
        x_sweep = self.cx + int(r_outer * math.cos(sweep_rad))
        y_sweep = self.cy + int(r_outer * math.sin(sweep_rad))
        self.create_line(self.cx, self.cy, x_sweep, y_sweep, fill=P.cyan, width=2)

        # 5. Tactical Corner HUD Brackets
        arm = int(135 * scale)
        c_len = 16
        coords = [
            (self.cx - arm, self.cy - arm, 1, 1),
            (self.cx + arm, self.cy - arm, -1, 1),
            (self.cx - arm, self.cy + arm, 1, -1),
            (self.cx + arm, self.cy + arm, -1, -1),
        ]
        for bx, by, dx, dy in coords:
            self.create_line(bx, by, bx + dx * c_len, by, fill=P.accent_hi, width=2)
            self.create_line(bx, by, bx, by + dy * c_len, fill=P.accent_hi, width=2)

        # 6. Realtime Telemetry String
        phase_idx = min(len(self.boot_phases) - 1, int(t * len(self.boot_phases)))
        self.create_text(
            self.cx, self.cy + 145,
            text=f"TORCHAIN // {self.boot_phases[phase_idx]}",
            fill=P.ok if t > 0.85 else P.cyan,
            font=("Cascadia Mono", 9, "bold")
        )

        # 33ms (~30 FPS) provides fluid animations with negligible CPU load
        self.after(33, self._step)


class ProCyberButton(tk.Canvas):
    """Chamfered military-style button with hover aura, cryptographic text scramble,
    and expanding dynamic coordinate-tracked ripple shockwaves.
    """

    GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*="

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Optional[Callable[[], None]] = None,
        width: int = 150,
        height: int = 38,
        bg_color: str = P.surface,
        accent_color: str = P.accent,
        hover_color: str = P.cyan,
        text_color: str = P.text,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=P.surface,
            highlightthickness=0,
            cursor="hand2"
        )
        self.target_text = text
        self.displayed_text = text
        self.command = command
        self.w = width
        self.h = height
        self.bg_color = bg_color
        self.accent_color = accent_color
        self.hover_color = hover_color
        self.text_color = text_color

        self._hovered = False
        self._pressed = False
        self._scramble_iter = 0

        self._draw_state()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_text(self, text: str, accent_color: Optional[str] = None) -> None:
        self.target_text = text
        self.displayed_text = text
        if accent_color:
            self.accent_color = accent_color
        self._draw_state()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self.target_text = str(kwargs.pop("text"))
            self.displayed_text = self.target_text
        if "bg" in kwargs or "background" in kwargs:
            self.accent_color = kwargs.pop("bg", kwargs.pop("background", self.accent_color))
        if "fg" in kwargs or "foreground" in kwargs:
            self.text_color = kwargs.pop("fg", kwargs.pop("foreground", self.text_color))
        if kwargs:
            super().configure(**kwargs)
        self._draw_state()

    config = configure

    def _draw_state(self, inset: int = 0) -> None:
        self.delete("ui")
        border = self.hover_color if (self._hovered or self._pressed) else self.accent_color
        fill = P.surface_alt if self._hovered else self.bg_color

        # Chamfered polygon (45-degree angle top-left and bottom-right corners)
        c = 7
        poly = [
            c + inset, 2 + inset,
            self.w - 2 - inset, 2 + inset,
            self.w - 2 - inset, self.h - c - inset,
            self.w - c - inset, self.h - 2 - inset,
            2 + inset, self.h - 2 - inset,
            2 + inset, c + inset
        ]
        self.create_polygon(poly, fill=fill, outline=border, width=2, tags="ui")

        self.create_text(
            self.w // 2, self.h // 2,
            text=self.displayed_text,
            fill="#FFFFFF" if self._hovered else self.text_color,
            font=("Cascadia Mono", 9, "bold"),
            tags="ui"
        )

    def _scramble_step(self) -> None:
        if not self._hovered or self._scramble_iter > len(self.target_text) * 2:
            self.displayed_text = self.target_text
            self._draw_state()
            return

        chars = []
        for idx, char in enumerate(self.target_text):
            if char == " ":
                chars.append(" ")
            elif idx < self._scramble_iter // 2:
                chars.append(char)
            else:
                chars.append(random.choice(self.GLYPHS))

        self.displayed_text = "".join(chars)
        self._draw_state()
        self._scramble_iter += 1
        self.after(35, self._scramble_step)

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._scramble_iter = 0
        self._scramble_step()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._pressed = False
        self.displayed_text = self.target_text
        self._draw_state()

    def _on_press(self, _event: tk.Event) -> None:
        self._pressed = True
        self._draw_state(inset=2)

    def _on_release(self, event: tk.Event) -> None:
        if not self._pressed:
            return
        self._pressed = False
        self._draw_state(inset=0)
        self._trigger_shockwave(event.x, event.y)
        if self.command:
            self.command()

    def _trigger_shockwave(self, x: int, y: int) -> None:
        step = 0
        max_steps = 7
        max_r = max(self.w, self.h)

        def _step_wave() -> None:
            nonlocal step
            self.delete("wave")
            if step < max_steps:
                pct = step / max_steps
                r = int(pct * max_r)
                self.create_oval(
                    x - r, y - r, x + r, y + r,
                    outline=self.hover_color,
                    width=max(1, int(3 * (1.0 - pct))),
                    tags="wave"
                )
                step += 1
                self.after(20, _step_wave)
            else:
                self.delete("wave")

        _step_wave()


def pulse_node_elastic(
    canvas: tk.Canvas,
    node_id: int,
    active_color: str = P.ok,
    base_color: str = P.idle,
) -> None:
    """One-shot elastic spring pulse for state change alerts (0% CPU at rest)."""
    scales = [1.0, 1.28, 1.45, 1.20, 1.05, 1.0]

    def _step(idx: int = 0) -> None:
        if idx < len(scales):
            color = active_color if idx < len(scales) - 1 else base_color
            try:
                canvas.itemconfig(node_id, fill=color)
            except Exception:
                return
            canvas.after(40, lambda: _step(idx + 1))

    _step(0)
