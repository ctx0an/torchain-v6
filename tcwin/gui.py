"""torchain desktop dashboard - Kali-themed, enterprise-grade, lightweight.

Performance principles (this is why it sips RAM/CPU):
- NO animation loop. The UI is fully event-driven.
- A single status poller runs every 2s and only updates label text when a
  value actually changed (no widget churn, no canvas redraws).
- Long/blocking work (start/stop/leaktest) runs on worker threads and posts
  results back to the Tk main loop via a thread-safe queue.
- The logs view only tails the file while it is the active view.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from . import LOG_FILE, __version__
from . import config as config_mod
from . import engine
from .errors import TorChainError
from .theme import PALETTE as P
from .theme import SPACE, font

REPO_URL = "https://github.com/ctx0an/torchain"
CREDIT = "by ctx0an · Claude Opus 4.8"


class TorChainGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config_mod.load()
        self._events: queue.Queue = queue.Queue()
        self._last_status: engine.Status | None = None
        self._busy = False
        self._active_view = "dashboard"
        self._log_pos = 0

        # Title is intentionally just the app name, nothing else.
        self.root.title("torchain")
        self.root.configure(bg=P.bg)
        self.root.geometry("1024x640")
        self.root.minsize(880, 560)
        # Unique generated app icon (no binary assets shipped).
        try:
            from . import icon
            self._icon = icon.tk_photo(64)
            self.root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None

        self._init_style()
        self._build_layout()
        self._show_view("dashboard")

        # Start light pollers.
        self.root.after(200, self._drain_events)
        self.root.after(400, self._poll_status)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------
    def _init_style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TFrame", background=P.bg)
        st.configure("Card.TFrame", background=P.surface)
        st.configure("Treeview",
                     background=P.surface, fieldbackground=P.surface,
                     foreground=P.text, borderwidth=0, font=font(10), rowheight=24)
        st.configure("Treeview.Heading", background=P.surface_alt,
                     foreground=P.cyan, font=font(10, bold=True), borderwidth=0)
        st.map("Treeview", background=[("selected", P.accent)],
               foreground=[("selected", "#ffffff")])
        st.configure("Vertical.TScrollbar", background=P.surface_alt,
                     troughcolor=P.overlay, borderwidth=0, arrowcolor=P.text_dim)
        st.configure("Horizontal.TScrollbar", background=P.surface_alt,
                     troughcolor=P.overlay, borderwidth=0, arrowcolor=P.text_dim)
        st.configure("Kali.Horizontal.TProgressbar", background=P.accent,
                     troughcolor=P.surface_alt, borderwidth=0)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # Top bar
        top = tk.Frame(self.root, bg=P.overlay, height=52)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="torchain", bg=P.overlay, fg=P.text,
                 font=font(16, bold=True)).pack(side="left", padx=SPACE["lg"])
        self.status_pill = tk.Label(top, text="●  CHECKING", bg=P.overlay,
                                    fg=P.idle, font=font(11, bold=True))
        self.status_pill.pack(side="right", padx=SPACE["lg"])

        # Body: sidebar + content
        body = tk.Frame(self.root, bg=P.bg)
        body.pack(side="top", fill="both", expand=True)

        self.sidebar = tk.Frame(body, bg=P.overlay, width=190)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = tk.Frame(body, bg=P.bg)
        self.content.pack(side="left", fill="both", expand=True)

        self._nav_buttons = {}
        for key, label in (("dashboard", "▣  Dashboard"),
                           ("circuits", "⦿  Circuits"),
                           ("bridges", "⇄  Bridges"),
                           ("leaktest", "✓  Leak Test"),
                           ("settings", "⚙  Settings"),
                           ("advanced", "⚡  Advanced"),
                           ("logs", "≡  Logs")):
            b = tk.Label(self.sidebar, text=label, bg=P.overlay, fg=P.text_dim,
                         font=font(11), anchor="w", padx=SPACE["lg"], pady=SPACE["md"])
            b.pack(fill="x")
            b.bind("<Button-1>", lambda e, k=key: self._show_view(k))
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=P.text))
            b.bind("<Leave>", lambda e, w=b, k=key: w.configure(
                fg=P.accent if k == self._active_view else P.text_dim))
            self._nav_buttons[key] = b

        # Sidebar footer: star button + credit + version (always visible).
        footer = tk.Frame(self.sidebar, bg=P.overlay)
        footer.pack(side="bottom", fill="x", pady=SPACE["md"])

        star = tk.Label(footer, text="★  Star on GitHub", bg=P.overlay,
                        fg=P.warn, font=font(10, bold=True), cursor="hand2",
                        anchor="w", padx=SPACE["lg"], pady=SPACE["sm"])
        star.pack(fill="x")
        star.bind("<Button-1>", lambda e: self._open_repo())
        star.bind("<Enter>", lambda e: star.configure(fg=P.accent_hi))
        star.bind("<Leave>", lambda e: star.configure(fg=P.warn))

        tk.Label(footer, text=CREDIT, bg=P.overlay, fg=P.text_dim,
                 font=font(9), anchor="w", padx=SPACE["lg"]).pack(fill="x")
        tk.Label(footer, text=f"v{__version__}", bg=P.overlay, fg=P.text_faint,
                 font=font(9), anchor="w", padx=SPACE["lg"]).pack(fill="x")

        # Build all views once; show/hide on demand (cheap, avoids rebuilds).
        self.views = {}
        self._build_dashboard()
        self._build_circuits()
        self._build_leaktest()
        self._build_settings()
        self._build_bridges()
        self._build_advanced()
        self._build_logs()

    def _card(self, parent, title=None):
        card = tk.Frame(parent, bg=P.surface, highlightbackground=P.border,
                        highlightthickness=1)
        if title:
            tk.Label(card, text=title, bg=P.surface, fg=P.cyan,
                     font=font(10, bold=True)).pack(anchor="w", padx=SPACE["md"],
                                                    pady=(SPACE["sm"], 0))
        return card

    def _btn(self, parent, text, command, kind="primary"):
        colors = {"primary": (P.accent, "#ffffff"), "danger": (P.dragon, "#ffffff"),
                  "ghost": (P.surface_alt, P.text)}
        bg, fg = colors.get(kind, colors["primary"])
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=font(11, bold=True),
                     padx=SPACE["lg"], pady=SPACE["sm"], cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.configure(bg=P.accent_hi if kind == "primary" else bg))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        return b

    def _open_repo(self):
        """Open the project repository in the user's browser."""
        import webbrowser
        try:
            webbrowser.open(REPO_URL)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def _build_dashboard(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["dashboard"] = v

        hero = self._card(v)
        hero.pack(fill="x", padx=SPACE["lg"], pady=SPACE["lg"])
        self.big_status = tk.Label(hero, text="INACTIVE", bg=P.surface, fg=P.idle,
                                   font=font(28, bold=True))
        self.big_status.pack(anchor="w", padx=SPACE["lg"], pady=(SPACE["lg"], 0))
        self.sub_status = tk.Label(hero, text="All traffic is using your real connection.",
                                   bg=P.surface, fg=P.text_dim, font=font(11))
        self.sub_status.pack(anchor="w", padx=SPACE["lg"])

        self.boot_bar = ttk.Progressbar(hero, style="Kali.Horizontal.TProgressbar",
                                        maximum=100, length=300)
        self.boot_bar.pack(anchor="w", padx=SPACE["lg"], pady=SPACE["sm"])

        row = tk.Frame(hero, bg=P.surface)
        row.pack(anchor="w", padx=SPACE["lg"], pady=SPACE["lg"])
        self.connect_btn = self._btn(row, "CONNECT", self._toggle_connection)
        self.connect_btn.pack(side="left")
        self.rotate_btn = self._btn(row, "NEW IDENTITY", self._do_rotate, kind="ghost")
        self.rotate_btn.pack(side="left", padx=SPACE["sm"])
        self.panic_btn = self._btn(row, "PANIC", self._do_panic, kind="danger")
        self.panic_btn.pack(side="left")
        self.pandora_btn = self._btn(row, "PANDORA", self._do_pandora, kind="danger")
        self.pandora_btn.pack(side="left", padx=SPACE["sm"])

        # Stat tiles
        tiles = tk.Frame(v, bg=P.bg)
        tiles.pack(fill="x", padx=SPACE["lg"])
        self.tile_vals = {}
        for key, label in (("pid", "TOR PID"), ("boot", "BOOTSTRAP"),
                           ("fw", "FIREWALL")):
            t = self._card(tiles)
            t.pack(side="left", fill="both", expand=True, padx=(0, SPACE["sm"]))
            val = tk.Label(t, text="—", bg=P.surface, fg=P.text, font=font(18, bold=True))
            val.pack(anchor="w", padx=SPACE["md"], pady=(SPACE["md"], 0))
            tk.Label(t, text=label, bg=P.surface, fg=P.text_faint,
                     font=font(9)).pack(anchor="w", padx=SPACE["md"], pady=(0, SPACE["md"]))
            self.tile_vals[key] = val

    def _build_circuits(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["circuits"] = v
        bar = tk.Frame(v, bg=P.bg)
        bar.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        tk.Label(bar, text="Active Circuits", bg=P.bg, fg=P.text,
                 font=font(14, bold=True)).pack(side="left")
        self._btn(bar, "REFRESH", self._refresh_circuits, kind="ghost").pack(side="right")
        self.circ_tree = self._make_tree(v, ("id", "status", "hops", "path"),
                                         ("ID", "STATUS", "#", "PATH (IP · nickname · country)"),
                                         (60, 120, 40, 560))

    def _build_leaktest(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["leaktest"] = v
        bar = tk.Frame(v, bg=P.bg)
        bar.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        tk.Label(bar, text="Leak Test Suite", bg=P.bg, fg=P.text,
                 font=font(14, bold=True)).pack(side="left")
        self._btn(bar, "RUN FULL", lambda: self._run_leaktest(False)).pack(side="right")
        self._btn(bar, "RUN QUICK", lambda: self._run_leaktest(True),
                  kind="ghost").pack(side="right", padx=SPACE["sm"])
        self.leak_tree = self._make_tree(v, ("status", "test", "detail"),
                                         ("STATUS", "TEST", "DETAIL"), (90, 200, 480))
        for tag, col in (("pass", P.ok), ("fail", P.err), ("warn", P.warn), ("info", P.cyan)):
            self.leak_tree.tag_configure(tag, foreground=col)

    def _build_settings(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["settings"] = v
        card = self._card(v, "Configuration")
        card.pack(fill="x", padx=SPACE["lg"], pady=(SPACE["md"], SPACE["xs"]))
        inner = tk.Frame(card, bg=P.surface)
        inner.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])

        self.var_country = tk.StringVar(value=self.cfg.exit_country)
        self.var_ipv6 = tk.BooleanVar(value=self.cfg.block_ipv6)
        self.var_bridges = tk.BooleanVar(value=self.cfg.use_bridges)
        self.var_mac = tk.BooleanVar(value=self.cfg.spoof_mac)
        self.var_host = tk.BooleanVar(value=self.cfg.spoof_hostname)
        self.var_watchdog = tk.BooleanVar(value=self.cfg.watchdog_enabled)
        self.var_boot = tk.BooleanVar(value=self.cfg.start_on_boot)
        self.var_rotate = tk.StringVar(value=str(self.cfg.auto_rotate_minutes))

        self._field(inner, "Exit country (2-letter, blank = any)", self.var_country)
        self._field(inner, "Auto identity rotation (minutes, 0 = off)", self.var_rotate)

        # 2-column checkbuttons layout to prevent vertical truncation/clipping
        cb_frame = tk.Frame(inner, bg=P.surface)
        cb_frame.pack(fill="x", pady=SPACE["xs"])

        cb_left = tk.Frame(cb_frame, bg=P.surface)
        cb_left.pack(side="left", fill="both", expand=True)

        cb_right = tk.Frame(cb_frame, bg=P.surface)
        cb_right.pack(side="left", fill="both", expand=True)

        self._check(cb_left, "Block IPv6 (recommended)", self.var_ipv6)
        self._check(cb_left, "Spoof MAC address on connect", self.var_mac)
        self._check(cb_left, "Self-healing watchdog", self.var_watchdog)

        self._check(cb_right, "Use bridges (circumvention)", self.var_bridges)
        self._check(cb_right, "Spoof hostname on connect", self.var_host)
        self._check(cb_right, "Start torchain on boot", self.var_boot)

        self._btn(inner, "SAVE SETTINGS", self._save_settings).pack(anchor="w",
                                                                    pady=SPACE["md"])

        # --- Network recovery -----------------------------------------
        rec = self._card(v, "Network Recovery")
        rec.pack(fill="x", padx=SPACE["lg"], pady=(0, SPACE["md"]))
        rinner = tk.Frame(rec, bg=P.surface)
        rinner.pack(fill="x", padx=SPACE["md"], pady=SPACE["md"])
        tk.Label(rinner,
                 text=("Stuck offline after stopping torchain? Restore normal "
                       "networking: clears torchain firewall rules, fixes DNS, "
                       "and restarts your network services."),
                 bg=P.surface, fg=P.text_dim, font=font(10), justify="left",
                 wraplength=720, anchor="w").pack(fill="x")
        self.repair_status = tk.Label(rinner, text="", bg=P.surface,
                                      fg=P.text_dim, font=font(10), anchor="w",
                                      justify="left", wraplength=720)
        self.repair_status.pack(fill="x", pady=SPACE["xs"])
        rrow = tk.Frame(rinner, bg=P.surface)
        rrow.pack(fill="x", pady=SPACE["xs"])
        self._btn(rrow, "REPAIR INTERNET",
                  lambda: self._repair_to(self.repair_status)).pack(side="left")
        self._btn(rrow, "PANDORA (WIPE + SCRUB)", self._do_pandora,
                  kind="danger").pack(side="left", padx=SPACE["sm"])

    def _build_bridges(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["bridges"] = v
        from . import bridges as bridges_mod
        bar = tk.Frame(v, bg=P.bg)
        bar.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        tk.Label(bar, text="Bridges & Pluggable Transports", bg=P.bg, fg=P.text,
                 font=font(14, bold=True)).pack(side="left")
        card = self._card(v, "Transport")
        card.pack(fill="x", padx=SPACE["lg"])
        inner = tk.Frame(card, bg=P.surface)
        inner.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        self.var_bridge_type = tk.StringVar(value=self.cfg.bridge_type)
        row = tk.Frame(inner, bg=P.surface)
        row.pack(fill="x", pady=SPACE["xs"])
        tk.Label(row, text="Bridge type", bg=P.surface, fg=P.text_dim,
                 font=font(10), width=38, anchor="w").pack(side="left")
        ttk.OptionMenu(row, self.var_bridge_type, self.cfg.bridge_type,
                       *bridges_mod.BRIDGE_TYPES).pack(side="left")
        self._btn(row, "SAVE TYPE", self._save_bridge_type, kind="ghost").pack(side="left", padx=SPACE["sm"])
        tk.Label(inner, text="Add a custom bridge line (e.g. 'obfs4 1.2.3.4:443 <FP> cert=... iat-mode=0')",
                 bg=P.surface, fg=P.text_faint, font=font(9), anchor="w").pack(fill="x", pady=(SPACE["sm"], 0))
        self.bridge_entry = tk.Entry(inner, bg=P.overlay, fg=P.text,
                                     insertbackground=P.text, relief="flat", font=font(10))
        self.bridge_entry.pack(fill="x", pady=SPACE["xs"])
        brow = tk.Frame(inner, bg=P.surface)
        brow.pack(fill="x", pady=SPACE["xs"])
        self._btn(brow, "ADD BRIDGE", self._add_bridge).pack(side="left")
        self._btn(brow, "REMOVE SELECTED", self._remove_bridge, kind="ghost").pack(side="left", padx=SPACE["sm"])
        self._btn(brow, "CLEAR ALL", self._clear_bridges, kind="danger").pack(side="left")
        self._btn(brow, "TEST", self._test_bridges, kind="ghost").pack(side="left", padx=SPACE["sm"])
        self._btn(brow, "FETCH FROM TOR PROJECT", self._fetch_bridges, kind="ghost").pack(side="left", padx=SPACE["sm"])
        self.bridge_tree = self._make_tree(v, ("line",), ("CUSTOM BRIDGE LINE",), (760,))

    def _build_advanced(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["advanced"] = v
        bar = tk.Frame(v, bg=P.bg)
        bar.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        tk.Label(bar, text="Advanced", bg=P.bg, fg=P.text,
                 font=font(14, bold=True)).pack(side="left")
        card = self._card(v, "Automation & Maintenance")
        card.pack(fill="x", padx=SPACE["lg"])
        inner = tk.Frame(card, bg=P.surface)
        inner.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        self.adv_status = tk.Label(inner, text="", bg=P.surface, fg=P.text_dim,
                                   font=font(10), anchor="w", justify="left", wraplength=720)
        self.adv_status.pack(fill="x", pady=SPACE["xs"])
        r1 = tk.Frame(inner, bg=P.surface); r1.pack(fill="x", pady=SPACE["xs"])
        self._btn(r1, "ENABLE START ON BOOT", lambda: self._adv(self._enable_boot)).pack(side="left")
        self._btn(r1, "DISABLE BOOT", lambda: self._adv(self._disable_boot), kind="ghost").pack(side="left", padx=SPACE["sm"])
        r2 = tk.Frame(inner, bg=P.surface); r2.pack(fill="x", pady=SPACE["xs"])
        self._btn(r2, "START WATCHDOG", lambda: self._adv(self._start_wd)).pack(side="left")
        self._btn(r2, "STOP WATCHDOG", lambda: self._adv(self._stop_wd), kind="ghost").pack(side="left", padx=SPACE["sm"])
        r3 = tk.Frame(inner, bg=P.surface); r3.pack(fill="x", pady=SPACE["xs"])
        self._btn(r3, "SCAN FOR OLD VERSIONS", lambda: self._adv(self._scan_old), kind="ghost").pack(side="left")
        r4 = tk.Frame(inner, bg=P.surface); r4.pack(fill="x", pady=SPACE["xs"])
        self._btn(r4, "REPAIR INTERNET", lambda: self._repair_to(self.adv_status)).pack(side="left")
        self._btn(r4, "PANDORA (WIPE + SCRUB)", self._do_pandora, kind="danger").pack(side="left", padx=SPACE["sm"])

    # -- bridge handlers --
    def _save_bridge_type(self):
        from . import bridges as b
        try:
            self.cfg = b.set_type(self.var_bridge_type.get(), self.cfg)
            self.sub_status.configure(text="Bridge type saved.", fg=P.ok)
        except TorChainError as exc:
            self._notify(exc)

    def _add_bridge(self):
        from . import bridges as b
        line = self.bridge_entry.get().strip()
        if not line:
            return
        try:
            self.cfg = b.add(line, self.cfg)
            self.bridge_entry.delete(0, "end")
            self._refresh_bridges()
        except TorChainError as exc:
            self._notify(exc)

    def _remove_bridge(self):
        from . import bridges as b
        sel = self.bridge_tree.selection()
        if not sel:
            return
        line = self.bridge_tree.item(sel[0])["values"][0]
        try:
            self.cfg = b.remove(str(line), self.cfg)
            self._refresh_bridges()
        except TorChainError as exc:
            self._notify(exc)

    def _clear_bridges(self):
        from . import bridges as b
        self.cfg = b.clear(self.cfg)
        self._refresh_bridges()

    def _test_bridges(self):
        from . import bridges as b
        if getattr(self, "_testing_bridges", False):
            return
        self._testing_bridges = True
        def _work():
            try:
                results = b.test_bridges(cfg=self.cfg)
                alive = sum(1 for _, ok, _ in results if ok)
                lines = [f"{'✓' if ok else '✗'} {info}" for _, ok, info in results]
                report = f"{alive}/{len(results)} bridges reachable\n" + "\n".join(lines)
                self.root.after(0, lambda: self._test_bridges_done(report))
            except TorChainError as exc:
                err_msg = str(exc)
                self.root.after(0, lambda: self._test_bridges_done(err_msg))
        self._notify("Testing bridges...")
        threading.Thread(target=_work, daemon=True).start()

    def _test_bridges_done(self, report):
        self._testing_bridges = False
        self._notify(report)

    def _fetch_bridges(self):
        from . import bridges as b
        if getattr(self, "_fetching_bridges", False):
            return
        self._fetching_bridges = True
        def _work():
            try:
                new_cfg = b.append_fetched(cfg=self.cfg)
                self.root.after(0, lambda: self._fetch_done(new_cfg))
            except TorChainError as exc:
                err_val = exc
                self.root.after(0, lambda: self._fetch_failed(err_val))
        self._notify("Fetching bridges from Tor Project...")
        threading.Thread(target=_work, daemon=True).start()

    def _fetch_done(self, new_cfg):
        self._fetching_bridges = False
        self.cfg = new_cfg
        self._refresh_bridges()
        self.sub_status.configure(text="Bridges fetched from Tor Project.", fg=P.ok)

    def _fetch_failed(self, exc):
        self._fetching_bridges = False
        self._notify(exc)

    def _refresh_bridges(self):
        self.bridge_tree.delete(*self.bridge_tree.get_children())
        for ln in self.cfg.custom_bridges:
            self.bridge_tree.insert("", "end", values=(ln,))

    # -- advanced handlers --
    def _adv(self, fn):
        self._run_worker(fn, lambda r: self.adv_status.configure(text=r or "Done.", fg=P.ok))

    def _enable_boot(self):
        from . import boot
        return "Start on boot enabled via " + boot.enable()

    def _disable_boot(self):
        from . import boot
        boot.disable()
        return "Start on boot disabled."

    def _start_wd(self):
        from . import watchdog
        return "Watchdog started." if watchdog.start_daemon() else "Watchdog failed to start."

    def _stop_wd(self):
        from . import watchdog
        watchdog.stop_daemon()
        return "Watchdog stopped."

    def _scan_old(self):
        from . import migrate
        rows = migrate.scan()
        return "   ".join(f"[{sev}] {msg}" for sev, msg in rows) or "No issues detected."

    def _refresh_advanced(self):
        self.adv_status.configure(text="Detecting environment...", fg=P.text_dim)
        def detect_env():
            from . import platform as plat, watchdog
            wd = "running" if watchdog.is_running() else "stopped"
            desc = plat.describe()
            return f"Environment: {desc}\nWatchdog: {wd}"

        def show_env(text):
            self.adv_status.configure(text=text, fg=P.text_dim)

        self._run_worker(detect_env, show_env)

    def _build_logs(self):
        v = tk.Frame(self.content, bg=P.bg)
        self.views["logs"] = v
        wrap = tk.Frame(v, bg=P.overlay)
        wrap.pack(fill="both", expand=True, padx=SPACE["lg"], pady=SPACE["lg"])
        vsb = ttk.Scrollbar(wrap, orient="vertical")
        hsb = ttk.Scrollbar(wrap, orient="horizontal")
        self.log_text = tk.Text(wrap, bg=P.overlay, fg=P.text, wrap="none",
                                bd=0, highlightthickness=0, font=font(10),
                                yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.log_text.yview)
        hsb.config(command=self.log_text.xview)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _make_tree(self, parent, cols, headings, widths):
        wrap = tk.Frame(parent, bg=P.surface)
        wrap.pack(fill="both", expand=True, padx=SPACE["lg"], pady=(0, SPACE["lg"]))
        vsb = ttk.Scrollbar(wrap, orient="vertical")
        hsb = ttk.Scrollbar(wrap, orient="horizontal")
        tree = ttk.Treeview(wrap, columns=cols, show="headings",
                            yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        for c, h, w in zip(cols, headings, widths):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _field(self, parent, label, var):
        row = tk.Frame(parent, bg=P.surface)
        row.pack(fill="x", pady=SPACE["xs"])
        tk.Label(row, text=label, bg=P.surface, fg=P.text_dim,
                 font=font(10), width=38, anchor="w").pack(side="left")
        e = tk.Entry(row, textvariable=var, bg=P.overlay, fg=P.text,
                     insertbackground=P.text, relief="flat", font=font(10))
        e.pack(side="left", fill="x", expand=True)

    def _check(self, parent, label, var):
        cb = tk.Checkbutton(parent, text=label, variable=var, bg=P.surface,
                            fg=P.text, selectcolor=P.overlay, activebackground=P.surface,
                            activeforeground=P.text, font=font(10), anchor="w")
        cb.pack(fill="x", pady=SPACE["xs"])

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------
    def _show_view(self, key):
        for v in self.views.values():
            v.pack_forget()
        self.views[key].pack(fill="both", expand=True)
        self._active_view = key
        for k, b in self._nav_buttons.items():
            b.configure(fg=P.accent if k == key else P.text_dim)
        if key == "circuits":
            self._refresh_circuits()
        elif key == "bridges":
            self._refresh_bridges()
        elif key == "advanced":
            self._refresh_advanced()
        elif key == "logs":
            self._refresh_logs(full=True)

    # ------------------------------------------------------------------
    # Worker plumbing
    # ------------------------------------------------------------------
    def _run_worker(self, fn, on_done=None):
        if self._busy:
            return
        self._busy = True

        def task():
            try:
                result = fn()
                self._events.put(("done", on_done, result, None))
            except Exception as exc:  # noqa: BLE001
                self._events.put(("done", on_done, None, exc))

        threading.Thread(target=task, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                kind, cb, result, err = self._events.get_nowait()
                if kind == "progress":
                    self.boot_bar["value"] = result
                    continue
                self._busy = False
                if err is not None:
                    self.connect_btn.configure(text="CONNECT")
                    self._notify(err)
                elif cb:
                    cb(result)
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def _notify(self, exc):
        msg = exc.render() if isinstance(exc, TorChainError) else str(exc)
        self.sub_status.configure(text=msg, fg=P.err)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _toggle_connection(self):
        st = self._last_status
        if st and st.active:
            if self._elevate(["stop"], "Disconnect"):
                self.connect_btn.configure(text="DISCONNECTING…")
                self.sub_status.configure(
                    text="Restoring normal networking…", fg=P.text_dim)
        else:
            if self._elevate(["start"], "Connect"):
                self.connect_btn.configure(text="CONNECTING…")
                self.sub_status.configure(
                    text="Bootstrapping tor… (this can take ~30s)", fg=P.text_dim)

    def _do_rotate(self):
        self._run_worker(engine.newnym, lambda r: self.sub_status.configure(
            text="New identity requested.", fg=P.ok))

    def _confirm(self, title: str, body: str) -> bool:
        """Modal confirmation dialog shown before a privileged action.

        On Windows the real credential prompt is the UAC consent dialog that
        appears when the elevated helper launches; this only confirms intent.
        Returns True if the user clicks CONFIRM.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Confirm")
        dlg.configure(bg=P.surface)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text=title, bg=P.surface, fg=P.text,
                 font=font(12, bold=True)).pack(anchor="w", padx=SPACE["lg"],
                                                pady=(SPACE["lg"], 0))
        tk.Label(dlg, text=body, bg=P.surface, fg=P.text_dim, font=font(10),
                 justify="left", wraplength=380).pack(
                     anchor="w", padx=SPACE["lg"], pady=(SPACE["sm"], 0))
        result = {"ok": False}

        def confirm():
            result["ok"] = True
            dlg.destroy()

        brow = tk.Frame(dlg, bg=P.surface)
        brow.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        self._btn(brow, "CONFIRM", confirm, kind="danger").pack(side="left")
        self._btn(brow, "CANCEL", dlg.destroy, kind="ghost").pack(
            side="left", padx=SPACE["sm"])
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.wait_window()
        return result["ok"]

    def _elevate(self, cli_args, label: str) -> bool:
        """Run a privileged torchain CLI action via a UAC-elevated process.

        This is the Windows analogue of the sudo-password gate: Windows shows
        its secure consent / password prompt when the elevated helper starts.
        The GUI itself stays unprivileged. Returns True if the elevated helper
        was launched.
        """
        import subprocess
        import sys
        from .sysutil import elevate, is_admin, NO_WINDOW
        try:
            if is_admin():
                if getattr(sys, 'frozen', False):
                    subprocess.Popen(
                        [sys.argv[0], *cli_args],
                        creationflags=NO_WINDOW)
                else:
                    subprocess.Popen(
                        [sys.executable or "python", "-m", "tcwin", *cli_args],
                        creationflags=NO_WINDOW)
                return True
            ok = elevate(list(cli_args))
            if not ok:
                self.sub_status.configure(
                    text=f"{label}: elevation was cancelled.", fg=P.err)
            return ok
        except Exception as exc:  # noqa: BLE001
            self._notify(exc)
            return False

    def _do_panic(self):
        if not self._confirm(
                "Engage PANIC kill-switch",
                "This immediately blocks ALL network traffic and stops tor. "
                "Windows will ask for administrator confirmation."):
            return
        if self._elevate(["panic"], "PANIC"):
            self.sub_status.configure(
                text="PANIC requested - all traffic will be blocked.", fg=P.warn)
            self.root.after(1500, lambda: self._run_worker(engine.status, self._apply_status))

    def _do_pandora(self):
        if not self._confirm(
                "Detonate PANDORA (wipe + memory scrub)",
                "This engages the kill-switch, securely wipes torchain state, "
                "and scrubs memory. Windows will ask for administrator "
                "confirmation. This cannot be undone."):
            return
        if self._elevate(["pandora", "--yes"], "PANDORA"):
            self.sub_status.configure(
                text="PANDORA detonated - state wiped, memory scrubbed. Use "
                     "Repair Internet to restore networking.", fg=P.warn)
            self.root.after(1500, lambda: self._run_worker(engine.status, self._apply_status))

    def _repair_to(self, label):
        if self._elevate(["repair"], "Repair Internet"):
            label.configure(
                text="Repairing internet… (see Logs for details)", fg=P.text_dim)

    def _refresh_circuits(self):
        def load():
            try:
                from .torctl import ControlClient
                with ControlClient(timeout=5) as c:
                    return c.circuit_details()
            except Exception:
                return None
        def show(circuits):
            self.circ_tree.delete(*self.circ_tree.get_children())
            if circuits is None:
                self.circ_tree.insert("", "end", values=("—", "OFFLINE", "", "tor is not running"))
                return
            for circ in circuits or []:
                hops = circ.get("hops", [])
                path_parts = []
                for h in hops:
                    ip = h.get("ip", "?")
                    nick = h.get("nickname", "?")[:15]
                    cc = h.get("country", "??")
                    path_parts.append(f"{ip} ({nick}, {cc})")
                path_str = " → ".join(path_parts) if path_parts else "—"
                n_hops = len(hops)
                self.circ_tree.insert("", "end",
                    values=(circ["id"], circ["status"], n_hops, path_str))
            if not self.circ_tree.get_children():
                self.circ_tree.insert("", "end", values=("—", "IDLE", "", "no active circuits yet"))
        self._run_worker(load, show)

    def _run_leaktest(self, quick):
        from . import leaktest
        self.leak_tree.delete(*self.leak_tree.get_children())
        self._run_worker(lambda: list(leaktest.run_all(quick=quick)), self._show_leak)

    def _show_leak(self, results):
        for r in results or []:
            self.leak_tree.insert("", "end", values=(r.status.upper(), r.name, r.detail),
                                  tags=(r.status,))

    def _save_settings(self):
        self.cfg.exit_country = self.var_country.get().strip()
        self.cfg.block_ipv6 = self.var_ipv6.get()
        self.cfg.use_bridges = self.var_bridges.get()
        self.cfg.spoof_mac = self.var_mac.get()
        self.cfg.spoof_hostname = self.var_host.get()
        self.cfg.watchdog_enabled = self.var_watchdog.get()
        want_boot = self.var_boot.get()
        try:
            self.cfg.auto_rotate_minutes = int(self.var_rotate.get() or 0)
        except ValueError:
            self.cfg.auto_rotate_minutes = 0
        try:
            config_mod.save(self.cfg)
            if want_boot != self.cfg.start_on_boot:
                from . import boot
                boot.enable() if want_boot else boot.disable()
                self.cfg.start_on_boot = want_boot
            self.sub_status.configure(text="Settings saved.", fg=P.ok)
        except TorChainError as exc:
            self._notify(exc)

    # ------------------------------------------------------------------
    # Status polling (cheap)
    # ------------------------------------------------------------------
    def _poll_status(self):
        if not self._busy:
            self._run_worker(engine.status, self._apply_status)
        self.root.after(2000, self._poll_status)

    def _apply_status(self, st):
        if st is None:
            return
        prev = self._last_status
        self._last_status = st
        # Only touch widgets when something changed.
        if not prev or prev.active != st.active:
            if st.active:
                self.big_status.configure(text="PROTECTED", fg=P.ok)
                self.sub_status.configure(text="All traffic is routed through the Tor network.",
                                          fg=P.text_dim)
                self.status_pill.configure(text="●  PROTECTED", fg=P.ok)
                self.connect_btn.configure(text="DISCONNECT", bg=P.dragon)
            else:
                self.big_status.configure(text="INACTIVE", fg=P.idle)
                self.sub_status.configure(text="All traffic is using your real connection.",
                                          fg=P.text_dim)
                self.status_pill.configure(text="●  INACTIVE", fg=P.idle)
                self.connect_btn.configure(text="CONNECT", bg=P.accent)
        if not prev or prev.bootstrap != st.bootstrap:
            self.boot_bar["value"] = st.bootstrap
            self.tile_vals["boot"].configure(text=f"{st.bootstrap}%")
        if not prev or prev.pid != st.pid:
            self.tile_vals["pid"].configure(text=str(st.pid) if st.pid else "—")
        if not prev or prev.firewall_up != st.firewall_up:
            self.tile_vals["fw"].configure(
                text="ON" if st.firewall_up else "OFF",
                fg=P.ok if st.firewall_up else P.idle)
        if self._active_view == "logs":
            self._refresh_logs()

    # ------------------------------------------------------------------
    # Logs tailing
    # ------------------------------------------------------------------
    def _refresh_logs(self, full=False):
        try:
            if full:
                self._log_pos = 0
            if not os.path.exists(LOG_FILE):
                return
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_pos)
                chunk = fh.read()
                self._log_pos = fh.tell()
            if chunk:
                self.log_text.configure(state="normal")
                if full:
                    self.log_text.delete("1.0", "end")
                self.log_text.insert("end", chunk)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except OSError:
            pass


def launch() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise TorChainError(
            f"cannot open the GUI: {exc}",
            hint="Run inside a Windows desktop session.",
        )
    TorChainGUI(root)
    root.mainloop()
    return 0
