import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageTk
import Quartz
import subprocess
import time
import os
import sys
import json
import math
import threading

try:
    from ApplicationServices import AXIsProcessTrusted
    HAS_AX = True
except ImportError:
    AXIsProcessTrusted = None
    HAS_AX = False

# ============================================================
APP_NAME = "PixelTrigger"
APP_SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_FILE = os.path.join(APP_SUPPORT_DIR, "config.json")
os.makedirs(APP_SUPPORT_DIR, exist_ok=True)


def get_donation_path():
    """
    获取捐赠二维码图片路径，优先级：
    1. py2app 打包后 .app 内部 Resources/donation.png
    2. 脚本同级目录 donation.png
    3. 用户配置目录 ~/Library/Application Support/PixelTrigger/donation.png（兼容旧版）
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        # py2app：可执行文件在 Contents/MacOS/，资源在 Contents/Resources/
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.normpath(
            os.path.join(exe_dir, "..", "Resources", "donation.png")))
        candidates.append(os.path.normpath(
            os.path.join(exe_dir, "..", "Frameworks", "donation.png")))
        try:
            candidates.append(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "donation.png"))
        except Exception:
            pass
    else:
        try:
            candidates.append(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "donation.png"))
        except Exception:
            pass
    candidates.append(os.path.join(APP_SUPPORT_DIR, "donation.png"))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


DEFAULT_CONFIG = {
    "x": "1062", "y": "981", "w": "213", "h": "41",
    "br": "30", "bg": "20", "mb": "100", "mc": "5",
    "it": "0.08", "cd": "5", "sample_step": "1",
    "color_mode": "hue",
    "hue_r": "0", "hue_g": "122", "hue_b": "255", "hue_tol": "70",
    "precise_r": "0", "precise_g": "113", "precise_b": "202",
    "precise_tol": "30",
    "trigger_mode": "scroll", "scroll_dir": "up",
    "total_pixels": "325", "duration": "0.65",
    "key_combo": "Next", "key_action": "press",
    "key_repeat_count": "3", "key_repeat_interval": "0.5",
    "key_hold_duration": "1.0",
}

PREVIEW_INTERVAL = 1.0
PREVIEW_HOLD_AFTER = 3.0
COUNTDOWN_TICK_MS = 100
PERM_CHECK_MS = 1000

HUE_PRESETS = [
    ("赤", "#FF3B30", (255, 59, 48)),
    ("橙", "#FF9500", (255, 149, 0)),
    ("黄", "#FFCC00", (255, 204, 0)),
    ("绿", "#34C759", (52, 199, 89)),
    ("青", "#00C7BE", (0, 199, 190)),
    ("蓝", "#007AFF", (0, 122, 255)),
    ("紫", "#AF52DE", (175, 82, 222)),
]
HUE_DEFAULT_TOL = 70

KEYSYM_TO_MAC = {
    'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4,
    'i': 34, 'j': 38, 'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31, 'p': 35,
    'q': 12, 'r': 15, 's': 1, 't': 17, 'u': 32, 'v': 9, 'w': 13, 'x': 7,
    'y': 16, 'z': 6,
    '0': 29, '1': 18, '2': 19, '3': 20, '4': 21, '5': 23, '6': 22, '7': 26,
    '8': 28, '9': 25,
    'Return': 36, 'KP_Enter': 76, 'Tab': 48, 'space': 49, 'BackSpace': 51,
    'Escape': 53, 'Delete': 117,
    'Left': 123, 'Right': 124, 'Down': 125, 'Up': 126,
    'Home': 115, 'End': 119, 'Prior': 116, 'Next': 121,
    'F1': 122, 'F2': 120, 'F3': 99, 'F4': 118, 'F5': 96, 'F6': 97,
    'F7': 98, 'F8': 100, 'F9': 101, 'F10': 109, 'F11': 103, 'F12': 111,
    'minus': 27, 'equal': 24, 'bracketleft': 33, 'bracketright': 30,
    'backslash': 41, 'semicolon': 39, 'apostrophe': 43, 'grave': 50,
    'comma': 44, 'period': 47, 'slash': 42,
}
MODIFIER_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R",
                    "Alt_L", "Alt_R", "Meta_L", "Meta_R",
                    "Super_L", "Super_R", "Command", "Caps_Lock"}
DISPLAY_NAME = {"Return": "Return", "KP_Enter": "Enter", "space": "Space",
                "Tab": "Tab", "BackSpace": "Backspace", "Escape": "Esc",
                "Delete": "Delete", "Prior": "PageUp", "Next": "PageDown",
                "Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}
MOD_SYMBOL = {"cmd": "⌘", "shift": "⇧", "ctrl": "⌃", "opt": "⌥"}

C_WINDOW_BG = "#ECECEC"
C_CARD_BG = "#FFFFFF"
C_CARD_BORDER = "#E2E2E2"
C_TITLE = "#1D1D1F"
C_CARD_TITLE = "#6E6E73"
C_LABEL = "#3A3A3C"
C_SUBTEXT = "#8E8E93"
C_ACCENT = "#007AFF"
C_ACCENT_H = "#0058B8"
C_GREEN = "#34C759"
C_GREEN_H = "#28A745"
C_ORANGE = "#FF9500"
C_RED = "#FF3B30"
C_RED_H = "#DC2626"
C_HUE_BORDER = "#C7C7CC"
C_GRAY_BG = "#E5E5EA"
C_GRAY_BG_H = "#D1D1D6"
C_GRAY_DISABLED = "#D0D0D0"
C_GRAY_DISABLED_FG = "#A0A0A5"


class FancyButton:
    def __init__(self, parent, text, bg_normal, bg_hover,
                 bg_disabled, fg_normal, fg_disabled,
                 command, font_size=12, padx=18, pady=7):
        self.bg_normal = bg_normal
        self.bg_hover = bg_hover
        self.bg_disabled = bg_disabled
        self.fg_normal = fg_normal
        self.fg_disabled = fg_disabled
        self.command = command
        self.enabled = True
        self.label = tk.Label(
            parent, text=text, bg=bg_normal, fg=fg_normal,
            font=("Helvetica Neue", font_size, "bold"),
            padx=padx, pady=pady, cursor="pointinghand")
        self.label.bind("<Enter>", self._enter)
        self.label.bind("<Leave>", self._leave)
        self.label.bind("<Button-1>", self._click)

    def _enter(self, e):
        if self.enabled:
            self.label.configure(bg=self.bg_hover)

    def _leave(self, e):
        if self.enabled:
            self.label.configure(bg=self.bg_normal)

    def _click(self, e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.label.configure(bg=self.bg_normal, fg=self.fg_normal,
                                  cursor="pointinghand")
        else:
            self.label.configure(bg=self.bg_disabled, fg=self.fg_disabled,
                                  cursor="arrow")

    def pack(self, **kw):
        self.label.pack(**kw)

    def grid(self, **kw):
        self.label.grid(**kw)


def capture_region(x, y, w, h):
    rect = Quartz.CGRectMake(x, y, w, h)
    cg = Quartz.CGWindowListCreateImage(
        rect, Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
    if cg is None:
        return None
    width = Quartz.CGImageGetWidth(cg)
    height = Quartz.CGImageGetHeight(cg)
    bpr = Quartz.CGImageGetBytesPerRow(cg)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg))
    return Image.frombuffer("RGBA", (width, height), bytes(data),
                            "raw", "BGRA", bpr, 1).convert("RGB")


def pick_color_at(gx, gy):
    img = capture_region(gx, gy, 1, 1)
    return img.getpixel((0, 0)) if img else None


def smooth_scroll(total_pixels, duration, direction, stop_event):
    def ease(t):
        return 4*t*t*t if t < 0.5 else 1 - pow(-2*t + 2, 3) / 2
    sign = -1 if direction == "up" else 1
    fps = 120
    interval = 1.0 / fps
    total_frames = max(1, int(duration * fps))
    scrolled = 0
    for frame in range(1, total_frames + 1):
        if stop_event.is_set():
            return
        t = frame / total_frames
        target = int(total_pixels * ease(t) + 0.5)
        step = target - scrolled
        if step > 0:
            evt = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitPixel, 1, sign * step)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
            scrolled = target
        time.sleep(interval)
    if not stop_event.is_set():
        tail = total_pixels - scrolled
        if tail > 0:
            evt = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitPixel, 1, sign * tail)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)


def _combo_to_parts(combo):
    if not combo:
        return [], None
    parts = [p for p in combo.split("+") if p]
    if not parts:
        return [], None
    return parts[:-1], parts[-1]


def _mods_to_flags(mods):
    f = 0
    for m in mods:
        if m == "cmd": f |= Quartz.kCGEventFlagMaskCommand
        elif m == "shift": f |= Quartz.kCGEventFlagMaskShift
        elif m == "ctrl": f |= Quartz.kCGEventFlagMaskControl
        elif m == "opt": f |= Quartz.kCGEventFlagMaskAlternate
    return f


def send_key_combo(combo, action, count, interval, hold_duration, stop_event):
    mods, main = _combo_to_parts(combo)
    if main is None:
        return
    kc = KEYSYM_TO_MAC.get(main)
    if kc is None:
        return
    flags = _mods_to_flags(mods)

    def press_once():
        d = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
        Quartz.CGEventSetFlags(d, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, d)
        u = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
        Quartz.CGEventSetFlags(u, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, u)

    def hold_once(dur):
        d = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
        Quartz.CGEventSetFlags(d, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, d)
        end = time.time() + dur
        while time.time() < end:
            if stop_event.is_set(): break
            time.sleep(0.02)
        u = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
        Quartz.CGEventSetFlags(u, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, u)

    try:
        if action == "press":
            press_once()
        elif action == "repeat":
            for i in range(max(1, count)):
                if stop_event.is_set(): return
                press_once()
                if i < count - 1:
                    end = time.time() + interval
                    while time.time() < end:
                        if stop_event.is_set(): return
                        time.sleep(0.02)
        elif action == "hold":
            hold_once(max(0.05, hold_duration))
    except Exception:
        pass


def match_precise(r, g, b, r0, g0, b0, tol):
    return (abs(r - r0) <= tol and abs(g - g0) <= tol and abs(b - b0) <= tol)


def scan_region(img, matcher, mc, sample_step):
    w, h = img.size
    pixels = img.load()
    count = 0
    y = 0
    step = max(1, sample_step)
    while y < h:
        for x in range(w):
            r, g, b = pixels[x, y]
            if matcher(r, g, b):
                count += 1
                if count >= mc:
                    return count
        y += step
    return count


def format_key_display(combo):
    if not combo:
        return "（未设置）"
    parts = [p for p in combo.split("+") if p]
    if not parts:
        return "（未设置）"
    mods, main = parts[:-1], parts[-1]
    main_disp = DISPLAY_NAME.get(main)
    if main_disp is None:
        main_disp = main.upper() if len(main) == 1 else main
    if mods:
        return "".join(MOD_SYMBOL.get(m, m) for m in mods) + main_disp
    return main_disp


class ToolTip:
    def __init__(self, widget, text, delay=600):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip_window = None
        self.after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_leave, add="+")

    def _on_enter(self, e=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, e=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show(self):
        if self.tip_window:
            return
        try:
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        tw = tk.Toplevel(self.widget)
        tw.withdraw()
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(tw, text=self.text, bg="#F5F5F7", fg="#1D1D1F",
                 font=("Helvetica Neue", 11), justify="left", anchor="w",
                 padx=14, pady=10, wraplength=280,
                 highlightbackground="#C8C8CC",
                 highlightthickness=1).pack()
        tw.update_idletasks()
        tw.wm_geometry(f"+{x}+{y}")
        tw.deiconify()
        self.tip_window = tw

    def _hide(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None


class PixelTriggerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PixelTrigger")
        self.root.configure(bg=C_WINDOW_BG)
        self.root.resizable(True, True)
        self.root.minsize(1000, 650)

        self.running = False
        self.stop_event = threading.Event()
        self.worker = None
        self.preview_image = None
        self.scroll_stop_event = threading.Event()
        self.last_preview_time = 0
        self.preview_hold_until = 0

        self.cooldown_until = 0
        self.cooldown_start = 0
        self.current_cd = 0
        self.in_cooldown = False
        self.countdown_job = None

        self.has_screen = False
        self.has_ax = None
        self.perm_job = None

        self._close_dialog_open = False
        self._key_capture_open = False
        self._donation_window = None
        self._hue_borders = []
        self.key_combo_str = "Next"

        self.cfg_values = self.load_config()
        try:
            self.selected_hue = (
                int(float(self.cfg_values.get("hue_r", "0"))),
                int(float(self.cfg_values.get("hue_g", "122"))),
                int(float(self.cfg_values.get("hue_b", "255"))))
        except Exception:
            self.selected_hue = (0, 122, 255)
        try:
            self.hue_tol = int(float(self.cfg_values.get(
                "hue_tol", str(HUE_DEFAULT_TOL))))
        except Exception:
            self.hue_tol = HUE_DEFAULT_TOL
        self.key_combo_str = self.cfg_values.get("key_combo", "Next")

        self.live = {}
        self._build_ui()
        self._update_live()

        self._initial_snapshot = self._snapshot_all()

        self._tick_permissions()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(10, self._fit_and_center)

    def _fit_and_center(self):
        try:
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            req_w = self.root.winfo_reqwidth()
            req_h = self.root.winfo_reqheight()
            min_w, min_h = 1000, 650
            max_w, max_h = sw - 60, sh - 100
            w = max(min_w, min(max_w, req_w))
            h = max(min_h, min(max_h, req_h))
            x = max(20, (sw - w) // 2)
            y = max(30, (sh - h) // 2 - 20)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def load_config(self):
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    saved = json.load(f)
                for k in cfg:
                    if k in saved:
                        cfg[k] = str(saved[k])
            except Exception:
                pass
        return cfg

    def save_config(self):
        try:
            data = {k: v.get() for k, v in self.vars.items()}
            data.update({
                "color_mode": self.color_mode.get(),
                "trigger_mode": self.trigger_mode.get(),
                "scroll_dir": self.scroll_dir.get(),
                "key_action": self.key_action.get(),
                "key_combo": self.key_combo_str,
                "hue_r": str(self.selected_hue[0]),
                "hue_g": str(self.selected_hue[1]),
                "hue_b": str(self.selected_hue[2]),
                "hue_tol": str(self.hue_tol),
            })
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self.log_msg(f"⚠️ 配置保存失败：{e}")
            return False

    def _snapshot_all(self):
        snap = {}
        try:
            for k, v in self.vars.items():
                try:
                    snap[f"var_{k}"] = str(v.get())
                except Exception:
                    pass
            snap["color_mode"] = self.color_mode.get()
            snap["trigger_mode"] = self.trigger_mode.get()
            snap["scroll_dir"] = self.scroll_dir.get()
            snap["key_action"] = self.key_action.get()
            snap["key_combo"] = self.key_combo_str
            snap["hue"] = tuple(self.selected_hue)
            snap["hue_tol"] = int(self.hue_tol)
        except Exception:
            pass
        return snap

    def _has_changes(self):
        try:
            current = self._snapshot_all()
            return current != self._initial_snapshot
        except Exception:
            return True

    def _make_card(self, parent, title):
        outer = tk.Frame(parent, bg=C_WINDOW_BG)
        card = tk.Frame(outer, bg=C_CARD_BG,
                        highlightbackground=C_CARD_BORDER,
                        highlightthickness=1)
        card.pack(fill="both", expand=True)
        hdr = tk.Frame(card, bg=C_CARD_BG)
        hdr.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(hdr, text=title, bg=C_CARD_BG, fg=C_CARD_TITLE,
                 font=("Helvetica Neue", 10, "bold"),
                 anchor="w").pack(fill="x")
        body = tk.Frame(card, bg=C_CARD_BG)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 10))
        return outer, body

    def _make_field(self, parent, label, key, default="", width=6):
        f = tk.Frame(parent, bg=C_CARD_BG)
        tk.Label(f, text=label, bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 10), anchor="w").pack(fill="x")
        v = tk.StringVar(value=self.cfg_values.get(key, default))
        self.vars[key] = v
        e = ttk.Entry(f, textvariable=v, width=width, font=("Menlo", 11))
        e.pack(fill="x", pady=(2, 0), ipady=1)
        return f, e

    def _build_ui(self):
        self.vars = {}
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=0)
        self.root.rowconfigure(3, weight=0)
        self.root.columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_main()
        self._build_params_bar()
        self._build_log_area()

    def _build_topbar(self):
        top = tk.Frame(self.root, bg=C_WINDOW_BG)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        left = tk.Frame(top, bg=C_WINDOW_BG)
        left.pack(side="left")
        tk.Label(left, text="🎯  PixelTrigger", bg=C_WINDOW_BG, fg=C_TITLE,
                 font=("Helvetica Neue", 18, "bold")).pack(side="left")
        tk.Label(left, text="  像素触发器",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 11)).pack(side="left", pady=(6, 0))

        right = tk.Frame(top, bg=C_WINDOW_BG)
        right.pack(side="right")

        perm_area = tk.Frame(right, bg=C_WINDOW_BG)
        perm_area.pack(side="right")

        def mk_perm(text):
            f = tk.Frame(perm_area, bg=C_WINDOW_BG, cursor="hand2")
            dot = tk.Label(f, text="●", bg=C_WINDOW_BG,
                           font=("Helvetica Neue", 11), fg="#B0B0B0")
            dot.pack(side="left", padx=(0, 4))
            lbl = tk.Label(f, text=text, bg=C_WINDOW_BG, fg=C_LABEL,
                           font=("Helvetica Neue", 11))
            lbl.pack(side="left")
            return f, dot, lbl

        self.screen_perm_frame, self.screen_perm_dot, self.screen_perm_lbl = mk_perm("屏幕录制")
        self.ax_perm_frame, self.ax_perm_dot, self.ax_perm_lbl = mk_perm("辅助功能")
        self.ax_perm_frame.pack(side="left", padx=(16, 0))
        self.screen_perm_frame.pack(side="left")

        for w in (self.screen_perm_frame, self.screen_perm_dot, self.screen_perm_lbl):
            w.bind("<Button-1>", lambda e: self.open_screen_settings())
        for w in (self.ax_perm_frame, self.ax_perm_dot, self.ax_perm_lbl):
            w.bind("<Button-1>", lambda e: self.open_ax_settings())

        tk.Frame(right, bg="#C7C7CC", width=1, height=24).pack(
            side="right", padx=(16, 0), pady=6)

        buttons_area = tk.Frame(right, bg=C_WINDOW_BG)
        buttons_area.pack(side="right", padx=(0, 16))

        self.start_btn = FancyButton(
            buttons_area, "▶   开始监控",
            bg_normal=C_GREEN, bg_hover=C_GREEN_H,
            bg_disabled=C_GRAY_DISABLED, fg_normal="#FFFFFF",
            fg_disabled=C_GRAY_DISABLED_FG,
            command=self.start)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = FancyButton(
            buttons_area, "■   停止",
            bg_normal=C_RED, bg_hover=C_RED_H,
            bg_disabled=C_GRAY_DISABLED, fg_normal="#FFFFFF",
            fg_disabled=C_GRAY_DISABLED_FG,
            command=self.stop)
        self.stop_btn.pack(side="left")
        self.stop_btn.set_enabled(False)

        donate_btn = tk.Label(
            right, text="❤", bg=C_WINDOW_BG, fg=C_RED,
            font=("Helvetica Neue", 18), cursor="pointinghand",
            padx=6, pady=2)
        donate_btn.pack(side="right", padx=(0, 16))
        donate_btn.bind("<Button-1>", lambda e: self.open_donation())
        donate_btn.bind("<Enter>", lambda e: donate_btn.configure(fg=C_RED_H))
        donate_btn.bind("<Leave>", lambda e: donate_btn.configure(fg=C_RED))

    # ============================================================
    # 捐赠弹窗（图片打包进程序，尺寸更大更清晰）
    # ============================================================
    def open_donation(self):
        if self._donation_window is not None:
            try:
                self._donation_window.lift()
                self._donation_window.focus_force()
            except Exception:
                pass
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("支持 PixelTrigger")
        dlg.configure(bg=C_WINDOW_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        def close_donation():
            self._donation_window = None
            try:
                dlg.destroy()
            except Exception:
                pass

        dlg.protocol("WM_DELETE_WINDOW", close_donation)

        tk.Label(dlg, text="❤️  感谢您的支持",
                 bg=C_WINDOW_BG, fg=C_TITLE,
                 font=("Helvetica Neue", 16, "bold")).pack(pady=(22, 4))
        tk.Label(dlg, text="如果您觉得 PixelTrigger 有帮助，欢迎扫码打赏",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 11)).pack(pady=(0, 14))

        img_frame = tk.Frame(dlg, bg=C_CARD_BG,
                             highlightbackground=C_CARD_BORDER,
                             highlightthickness=1)
        img_frame.pack(padx=28, pady=(0, 14))

        img_path = get_donation_path()
        shown = False
        if img_path:
            try:
                pil_img = Image.open(img_path)
                # ★ 放大到 480 以内，尽量保留二维码细节
                pil_img.thumbnail((480, 480), Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil_img)
                img_label = tk.Label(img_frame, image=photo, bg=C_CARD_BG)
                img_label.image = photo
                img_label.pack(padx=10, pady=10)
                shown = True
            except Exception:
                shown = False
        if not shown:
            tk.Label(img_frame, text="（未找到捐赠二维码）",
                     bg=C_CARD_BG, fg=C_SUBTEXT,
                     font=("Helvetica Neue", 11),
                     width=32, height=10,
                     justify="center").pack(padx=10, pady=10)

        btns = tk.Frame(dlg, bg=C_WINDOW_BG)
        btns.pack(pady=(0, 18))

        close_btn = tk.Label(btns, text="关闭", bg=C_ACCENT, fg="#FFFFFF",
                              font=("Helvetica Neue", 11, "bold"),
                              padx=20, pady=6, cursor="pointinghand")
        close_btn.bind("<Enter>", lambda e: close_btn.configure(bg=C_ACCENT_H))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=C_ACCENT))
        close_btn.bind("<Button-1>", lambda e: close_donation())
        close_btn.pack()

        dlg.update_idletasks()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        dx = rx + (rw - dw) // 2
        dy = ry + (rh - dh) // 2
        dlg.geometry(f"+{dx}+{dy}")

        self._donation_window = dlg

    def _build_main(self):
        body = tk.Frame(self.root, bg=C_WINDOW_BG)
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        body.columnconfigure(0, weight=30, minsize=280)
        body.columnconfigure(1, weight=70, minsize=560)

        col_l = tk.Frame(body, bg=C_WINDOW_BG)
        col_l.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        col_m = tk.Frame(body, bg=C_WINDOW_BG)
        col_m.grid(row=0, column=1, sticky="nsew")

        self._build_left(col_l)
        self._build_middle(col_m)

    def _build_left(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=0)

        outer, b = self._make_card(parent, "状态")
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        st = tk.Frame(b, bg=C_CARD_BG)
        st.pack(fill="x")
        self.status_dot = tk.Label(st, text="●", bg=C_CARD_BG,
                                     font=("Helvetica Neue", 20),
                                     fg="#B0B0B0")
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_var = tk.StringVar(value="未运行")
        self.status_label = tk.Label(st, textvariable=self.status_var,
                                       bg=C_CARD_BG, fg="#8E8E93",
                                       font=("Helvetica Neue", 22, "bold"),
                                       anchor="w")
        self.status_label.pack(side="left")
        self.match_var = tk.StringVar(value="匹配像素：—")
        tk.Label(b, textvariable=self.match_var, bg=C_CARD_BG,
                 fg=C_SUBTEXT, font=("Menlo", 10),
                 anchor="w").pack(fill="x", pady=(6, 0))

        outer, b = self._make_card(parent, "监控区域")
        outer.grid(row=1, column=0, sticky="ew")
        r = tk.Frame(b, bg=C_CARD_BG)
        r.pack(fill="x")
        for i, (lbl, key) in enumerate([("X", "x"), ("Y", "y")]):
            f, _ = self._make_field(r, lbl, key)
            f.pack(side="left", padx=(0 if i == 0 else 10, 0))
        r = tk.Frame(b, bg=C_CARD_BG)
        r.pack(fill="x", pady=(8, 0))
        for i, (lbl, key) in enumerate([("宽 W", "w"), ("高 H", "h")]):
            f, _ = self._make_field(r, lbl, key)
            f.pack(side="left", padx=(0 if i == 0 else 10, 0))
        ttk.Button(b, text="📐  点击框选屏幕区域",
                    command=self.select_region).pack(
                        fill="x", pady=(10, 0), ipady=3)

    def _build_middle(self, parent):
        parent.columnconfigure(0, weight=1)

        outer, b = self._make_card(parent, "识别模式")
        outer.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.color_mode = tk.StringVar(
            value=self.cfg_values.get("color_mode", "hue"))
        mr = tk.Frame(b, bg=C_CARD_BG)
        mr.pack(fill="x")
        tk.Radiobutton(mr, text="色系匹配（默认）",
                        variable=self.color_mode, value="hue",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 11),
                        command=self._on_mode_change).pack(side="left", padx=(0, 16))
        tk.Radiobutton(mr, text="精准容差",
                        variable=self.color_mode, value="precise",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 11),
                        command=self._on_mode_change).pack(side="left")

        self.hue_panel = tk.Frame(b, bg=C_CARD_BG)
        sw = tk.Frame(self.hue_panel, bg=C_CARD_BG)
        sw.pack(fill="x", pady=(8, 0))
        for idx, (name, hexc, rgb) in enumerate(HUE_PRESETS):
            border = tk.Frame(sw, bg=C_CARD_BG,
                              highlightbackground=C_HUE_BORDER,
                              highlightthickness=2)
            border.pack(side="left", padx=3)
            lbl = tk.Label(border, text="", bg=hexc,
                           width=3, height=1, cursor="hand2")
            lbl.pack(padx=2, pady=2)
            lbl.bind("<Button-1>", lambda e, i=idx: self._select_hue(i))
            self._hue_borders.append(border)
        self._refresh_hue_borders()

        self.precise_panel = tk.Frame(b, bg=C_CARD_BG)
        pr1 = tk.Frame(self.precise_panel, bg=C_CARD_BG)
        pr1.pack(fill="x", pady=(8, 6))
        ttk.Button(pr1, text="💧  屏幕取色",
                    command=self.start_eyedrop).pack(side="left", ipady=1)
        self.base_color_box = tk.Label(pr1, text="  ", bg="#0000c9",
                                        width=4, height=1,
                                        highlightbackground=C_HUE_BORDER,
                                        highlightthickness=1)
        self.base_color_box.pack(side="left", padx=(10, 6), ipady=5)
        self.base_rgb_var = tk.StringVar(
            value=f"R{self.cfg_values.get('precise_r','0')} "
                  f"G{self.cfg_values.get('precise_g','113')} "
                  f"B{self.cfg_values.get('precise_b','202')}")
        tk.Label(pr1, textvariable=self.base_rgb_var,
                 bg=C_CARD_BG, fg=C_TITLE,
                 font=("Menlo", 10)).pack(side="left")
        pr2 = tk.Frame(self.precise_panel, bg=C_CARD_BG)
        pr2.pack(fill="x")
        tk.Label(pr2, text="容差", bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 10)).pack(side="left", padx=(0, 6))
        tol_init = int(float(self.cfg_values.get("precise_tol", "30")))
        self.tol_var = tk.IntVar(value=tol_init)
        self.vars["precise_tol"] = self.tol_var
        ttk.Scale(pr2, from_=0, to=120, orient="horizontal",
                   variable=self.tol_var, length=200).pack(side="left", padx=(0, 8))
        self.tol_label = tk.Label(pr2, text=str(tol_init),
                                    bg=C_CARD_BG, fg=C_TITLE,
                                    font=("Menlo", 11, "bold"),
                                    width=4, anchor="e")
        self.tol_label.pack(side="left")
        tk.Label(pr2, text="(0-120)", bg=C_CARD_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 9)).pack(side="left", padx=(4, 0))

        def _on_tol(*a):
            try:
                v = int(self.tol_var.get())
                self.tol_label.configure(text=str(v))
            except Exception:
                pass
        self.tol_var.trace_add("write", _on_tol)
        for k in ("precise_r", "precise_g", "precise_b"):
            self.vars[k] = tk.StringVar(value=self.cfg_values.get(k, ""))
        self._on_mode_change()

        outer, b = self._make_card(parent, "冷却时间（触发后暂停检测）")
        outer.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        cdr = tk.Frame(b, bg=C_CARD_BG)
        cdr.pack(fill="x")
        v_cd = tk.StringVar(value=self.cfg_values.get("cd", "5"))
        self.vars["cd"] = v_cd
        ttk.Spinbox(cdr, textvariable=v_cd, from_=0, to=1000,
                     increment=0.5, width=5, font=("Menlo", 11),
                     justify="center").pack(side="left", ipady=1)
        tk.Label(cdr, text="秒", bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 11)).pack(side="left", padx=(4, 12))
        for secs in (2, 4, 6, 8, 10):
            ttk.Button(cdr, text=f"{secs}s", width=3,
                        command=lambda s=secs: v_cd.set(str(s))
                        ).pack(side="left", padx=2)

        outer = tk.Frame(parent, bg=C_WINDOW_BG)
        outer.grid(row=2, column=0, sticky="ew")
        outer.columnconfigure(0, weight=40, minsize=240)
        outer.columnconfigure(1, weight=60, minsize=280)

        self._build_trigger_card(outer)
        self._build_preview_card(outer)

    def _build_trigger_card(self, parent):
        outer, b = self._make_card(parent, "触发方式")
        outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.trigger_mode = tk.StringVar(
            value=self.cfg_values.get("trigger_mode", "scroll"))
        tm = tk.Frame(b, bg=C_CARD_BG)
        tm.pack(fill="x")
        tk.Radiobutton(tm, text="滚动翻页", variable=self.trigger_mode,
                        value="scroll", bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 11),
                        command=self._on_trigger_mode_change).pack(side="left", padx=(0, 14))
        tk.Radiobutton(tm, text="触发按键", variable=self.trigger_mode,
                        value="key", bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 11),
                        command=self._on_trigger_mode_change).pack(side="left")

        self.scroll_panel = tk.Frame(b, bg=C_CARD_BG)
        sr = tk.Frame(self.scroll_panel, bg=C_CARD_BG)
        sr.pack(fill="x", pady=(8, 4))
        tk.Label(sr, text="方向", bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 10)).pack(side="left", padx=(0, 6))
        self.scroll_dir = tk.StringVar(
            value=self.cfg_values.get("scroll_dir", "up"))
        tk.Radiobutton(sr, text="向上", variable=self.scroll_dir, value="up",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 10)).pack(side="left", padx=(0, 10))
        tk.Radiobutton(sr, text="向下", variable=self.scroll_dir, value="down",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=("Helvetica Neue", 10)).pack(side="left")
        sr2 = tk.Frame(self.scroll_panel, bg=C_CARD_BG)
        sr2.pack(fill="x")
        f1, e1 = self._make_field(sr2, "总距离", "total_pixels", width=5)
        f1.pack(side="left")
        ToolTip(e1, "一次翻页的跨度。\n调大：翻得更远。\n调小：翻得更近。")
        f2, e2 = self._make_field(sr2, "总时长", "duration", width=5)
        f2.pack(side="left", padx=(8, 0))
        ToolTip(e2, "完成一次滚动所用的时间。\n调大：更慢更悠长。\n调小：更快更干脆。")

        self.key_panel = tk.Frame(b, bg=C_CARD_BG)
        kr1 = tk.Frame(self.key_panel, bg=C_CARD_BG)
        kr1.pack(fill="x", pady=(8, 4))
        tk.Label(kr1, text="按键", bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 10)).pack(side="left", padx=(0, 6))
        self.key_display_var = tk.StringVar(
            value=format_key_display(self.key_combo_str))
        tk.Label(kr1, textvariable=self.key_display_var,
                 bg="#F5F5F7", fg=C_TITLE,
                 font=("Menlo", 11, "bold"),
                 padx=10, pady=4,
                 highlightbackground=C_HUE_BORDER,
                 highlightthickness=1).pack(side="left", padx=(0, 6))
        ttk.Button(kr1, text="设置", command=self.open_key_capture,
                    width=4).pack(side="left")

        kr2 = tk.Frame(self.key_panel, bg=C_CARD_BG)
        kr2.pack(fill="x", pady=(0, 4))
        tk.Label(kr2, text="动作", bg=C_CARD_BG, fg=C_LABEL,
                 font=("Helvetica Neue", 10)).pack(side="left", padx=(0, 6))
        self.key_action = tk.StringVar(
            value=self.cfg_values.get("key_action", "press"))
        for txt, val in [("按一下", "press"), ("连按", "repeat"), ("按住", "hold")]:
            tk.Radiobutton(kr2, text=txt, variable=self.key_action, value=val,
                            bg=C_CARD_BG, fg=C_TITLE,
                            activebackground=C_CARD_BG,
                            font=("Helvetica Neue", 10),
                            command=self._on_key_action_change
                            ).pack(side="left", padx=(0, 10))

        self.repeat_panel = tk.Frame(self.key_panel, bg=C_CARD_BG)
        rp = tk.Frame(self.repeat_panel, bg=C_CARD_BG)
        rp.pack(fill="x")
        fr1, _ = self._make_field(rp, "次数", "key_repeat_count", width=4)
        fr1.pack(side="left")
        fr2, _ = self._make_field(rp, "间隔(s)", "key_repeat_interval", width=4)
        fr2.pack(side="left", padx=(8, 0))

        self.hold_panel = tk.Frame(self.key_panel, bg=C_CARD_BG)
        hp = tk.Frame(self.hold_panel, bg=C_CARD_BG)
        hp.pack(fill="x")
        fh, _ = self._make_field(hp, "按住时长(s)", "key_hold_duration", width=4)
        fh.pack(side="left")
        self._on_trigger_mode_change()

    def _build_preview_card(self, parent):
        outer, b = self._make_card(parent, "监控区域预览")
        outer.grid(row=0, column=1, sticky="nsew")

        preview_box = tk.Frame(b, bg="#F5F5F7",
                               highlightbackground="#E2E2E2",
                               highlightthickness=1,
                               width=1, height=1)
        preview_box.pack(fill="both", expand=True)
        preview_box.pack_propagate(False)

        self.preview_label = tk.Label(preview_box, text="（未运行）",
                                       bg="#F5F5F7", fg=C_SUBTEXT,
                                       font=("Helvetica Neue", 11))
        self.preview_label.pack(fill="both", expand=True)

    def _build_params_bar(self):
        params_row = tk.Frame(self.root, bg=C_WINDOW_BG)
        params_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        outer, b = self._make_card(params_row, "检测参数")
        outer.pack(fill="x")

        r = tk.Frame(b, bg=C_CARD_BG)
        r.pack(fill="x")
        fields = [("蓝>红+", "br", "30"), ("蓝>绿+", "bg", "20"),
                  ("最低亮度", "mb", "100"), ("最少像素", "mc", "5"),
                  ("检测间隔", "it", "0.08"), ("采样步长", "sample_step", "1")]
        for i, (lbl, key, dft) in enumerate(fields):
            f, _ = self._make_field(r, lbl, key, default=dft, width=6)
            f.pack(side="left", padx=(0 if i == 0 else 14, 0))

    def _build_log_area(self):
        log_row = tk.Frame(self.root, bg=C_WINDOW_BG)
        log_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))

        card = tk.Frame(log_row, bg=C_CARD_BG,
                        highlightbackground=C_CARD_BORDER,
                        highlightthickness=1)
        card.pack(fill="both", expand=True)

        hdr = tk.Frame(card, bg=C_CARD_BG)
        hdr.pack(fill="x", padx=12, pady=(6, 0))
        tk.Label(hdr, text="日志", bg=C_CARD_BG, fg=C_CARD_TITLE,
                 font=("Helvetica Neue", 10, "bold"),
                 anchor="w").pack(side="left")

        log_inner = tk.Frame(card, bg=C_CARD_BG)
        log_inner.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        self.log = scrolledtext.ScrolledText(
            log_inner, state="disabled", wrap="word",
            width=1, height=8,
            font=("Menlo", 10),
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#E2E2E2",
            bg="#FFFFFF")
        self.log.pack(fill="both", expand=True)

    def _on_mode_change(self):
        if self.color_mode.get() == "hue":
            self.precise_panel.pack_forget()
            self.hue_panel.pack(fill="x", pady=(2, 0))
            self._refresh_hue_borders()
        else:
            self.hue_panel.pack_forget()
            self.precise_panel.pack(fill="x", pady=(2, 0))
            self._update_base_color_swatch()
        self._update_live()

    def _on_trigger_mode_change(self):
        if self.trigger_mode.get() == "scroll":
            self.key_panel.pack_forget()
            self.scroll_panel.pack(fill="x", pady=(4, 0))
        else:
            self.scroll_panel.pack_forget()
            self.key_panel.pack(fill="x", pady=(4, 0))
            self._on_key_action_change()
        self._update_live()

    def _on_key_action_change(self):
        a = self.key_action.get()
        if a == "repeat":
            self.hold_panel.pack_forget()
            self.repeat_panel.pack(fill="x", pady=(0, 0))
        elif a == "hold":
            self.repeat_panel.pack_forget()
            self.hold_panel.pack(fill="x", pady=(0, 0))
        else:
            self.repeat_panel.pack_forget()
            self.hold_panel.pack_forget()
        self._update_live()

    def _select_hue(self, idx):
        name, hexc, rgb = HUE_PRESETS[idx]
        self.selected_hue = rgb
        self.hue_tol = HUE_DEFAULT_TOL
        self._refresh_hue_borders()
        self.log_msg(f"🎨 选择色系：{name}  RGB{rgb}")
        self._update_live()

    def _refresh_hue_borders(self):
        for i, b in enumerate(self._hue_borders):
            _, _, rgb = HUE_PRESETS[i]
            if rgb == self.selected_hue:
                b.configure(highlightbackground=C_ACCENT, highlightthickness=3)
            else:
                b.configure(highlightbackground=C_HUE_BORDER, highlightthickness=2)

    def _update_base_color_swatch(self):
        try:
            r = max(0, min(255, int(float(self.vars["precise_r"].get()))))
            g = max(0, min(255, int(float(self.vars["precise_g"].get()))))
            b = max(0, min(255, int(float(self.vars["precise_b"].get()))))
            self.base_color_box.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
            self.base_rgb_var.set(f"R{r} G{g} B{b}")
        except Exception:
            pass

    def _update_live(self, *args):
        try:
            live = {}
            for k in ("x", "y", "w", "h", "mc", "it", "cd", "sample_step",
                       "total_pixels", "duration", "br", "bg", "mb",
                       "precise_r", "precise_g", "precise_b",
                       "key_repeat_count", "key_repeat_interval",
                       "key_hold_duration"):
                if k in self.vars:
                    live[k] = self.vars[k].get()
            try:
                live["precise_tol"] = str(int(self.tol_var.get()))
            except Exception:
                live["precise_tol"] = "30"
            live["color_mode"] = self.color_mode.get()
            live["trigger_mode"] = self.trigger_mode.get()
            live["scroll_dir"] = self.scroll_dir.get()
            live["key_action"] = self.key_action.get()
            live["key_combo"] = self.key_combo_str
            live["selected_hue"] = self.selected_hue
            live["hue_tol"] = self.hue_tol
            self.live = live
        except Exception:
            pass
        self._maybe_adjust_cooldown()

    def _maybe_adjust_cooldown(self):
        if not self.running or not self.in_cooldown:
            return
        try:
            new_cd = float(self.vars["cd"].get())
        except Exception:
            return
        if abs(new_cd - self.current_cd) < 0.001:
            return
        self.current_cd = new_cd
        elapsed = time.time() - self.cooldown_start
        if elapsed >= new_cd:
            self.in_cooldown = False
            self.cooldown_until = 0
            self.root.after(0, self._on_cooldown_end)
        else:
            self.cooldown_until = self.cooldown_start + new_cd

    def open_key_capture(self):
        if self._key_capture_open:
            return
        self._key_capture_open = True
        dlg = tk.Toplevel(self.root)
        dlg.title("请输入按键")
        dlg.configure(bg=C_WINDOW_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        w, h = 420, 210
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(dlg, text="请按下一个键作为触发按键",
                 bg=C_WINDOW_BG, fg=C_TITLE,
                 font=("Helvetica Neue", 14, "bold")).pack(pady=(24, 4))
        tk.Label(dlg, text="支持字母、数字、方向键、F1-F12、以及 ⌘/⇧/⌃/⌥ 组合键",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 10)).pack(pady=(0, 12))

        status_var = tk.StringVar(value="⌨️  等待按键…")
        status_label = tk.Label(dlg, textvariable=status_var,
                                 bg="#F5F5F7", fg=C_ACCENT,
                                 font=("Menlo", 16, "bold"),
                                 padx=18, pady=12,
                                 highlightbackground=C_HUE_BORDER,
                                 highlightthickness=1)
        status_label.pack(pady=(0, 6))

        tk.Label(dlg, text="按 ESC 取消", bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 10)).pack(pady=(0, 12))

        state = {"done": False}

        def close(delay=0):
            if state["done"]:
                return
            state["done"] = True
            def _do():
                try:
                    dlg.unbind_all("<KeyPress>")
                except Exception:
                    pass
                self._key_capture_open = False
                try:
                    dlg.destroy()
                except Exception:
                    pass
            if delay > 0:
                dlg.after(delay, _do)
            else:
                _do()

        def on_key(event):
            if state["done"]:
                return
            keysym = event.keysym
            flags = event.state

            if keysym in MODIFIER_KEYSYMS:
                mods = []
                if flags & 0x0010: mods.append("cmd")
                if flags & 0x0008: mods.append("opt")
                if flags & 0x0004: mods.append("ctrl")
                if flags & 0x0001: mods.append("shift")
                if mods:
                    s = "".join(MOD_SYMBOL.get(m, m) for m in mods)
                    status_var.set(f"{s}  …  再按一个键")
                    status_label.configure(fg=C_ACCENT)
                return

            main = keysym.lower() if len(keysym) == 1 and keysym.isalpha() else keysym
            mods = []
            if flags & 0x0010: mods.append("cmd")
            if flags & 0x0008: mods.append("opt")
            if flags & 0x0004: mods.append("ctrl")
            if flags & 0x0001: mods.append("shift")

            if main == "Escape" and not mods:
                status_var.set("已取消")
                status_label.configure(fg=C_SUBTEXT)
                close(150)
                return

            if main not in KEYSYM_TO_MAC:
                status_var.set(f"❌  不支持的按键：{keysym}")
                status_label.configure(fg=C_RED)
                dlg.after(1000, lambda: (status_var.set("⌨️  等待按键…"),
                                          status_label.configure(fg=C_ACCENT)))
                return

            combo = "+".join(mods + [main]) if mods else main
            self.key_combo_str = combo
            disp = format_key_display(combo)
            self.key_display_var.set(disp)
            self._update_live()
            self.log_msg(f"⌨️  设置触发按键：{disp}")
            status_var.set(f"✅  已捕获：{disp}")
            status_label.configure(fg=C_GREEN)
            close(500)

        dlg.protocol("WM_DELETE_WINDOW", lambda: close(0))
        dlg.bind("<KeyPress>", on_key)
        dlg.focus_force()

    def start_eyedrop(self):
        state = {"done": False, "gx": 0, "gy": 0}
        try:
            err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        except Exception:
            return
        if not ids:
            return
        screens = []
        for did in ids:
            r = Quartz.CGDisplayBounds(did)
            screens.append((int(r.origin.x), int(r.origin.y),
                            int(r.size.width), int(r.size.height)))
        overlays = []

        def destroy_all():
            for o in overlays:
                try:
                    o.destroy()
                except Exception:
                    pass
            try:
                self.root.unbind_all("<Escape>")
            except Exception:
                pass

        self.root.bind_all("<Escape>", lambda e: destroy_all())

        def pick():
            gx, gy = state["gx"], state["gy"]
            destroy_all()
            def _do():
                col = pick_color_at(gx, gy)
                if col:
                    r, g, b = col
                    self.vars["precise_r"].set(str(r))
                    self.vars["precise_g"].set(str(g))
                    self.vars["precise_b"].set(str(b))
                    self._update_base_color_swatch()
                    self._update_live()
                    self.log_msg(f"💧 拾取颜色 R{r} G{g} B{b}")
                else:
                    self.log_msg("⚠️ 取色失败")
            self.root.after(180, _do)

        for (sx, sy, sw, sh) in screens:
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.configure(bg="black")
            try:
                ov.attributes("-alpha", 0.20)
            except Exception:
                pass
            ov.geometry(f"{sw}x{sh}+{sx}+{sy}")
            c = tk.Canvas(ov, bg="black", highlightthickness=0,
                          cursor="crosshair", width=sw, height=sh)
            c.pack(fill="both", expand=True)
            ch = c.create_line(0, 0, 0, 0, fill="#ff3b30", width=1)
            cv = c.create_line(0, 0, 0, 0, fill="#ff3b30", width=1)
            ring = c.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)

            def motion(canvas=c, ch_=ch, cv_=cv, ring_=ring, w_=sw, h_=sh):
                def _m(e):
                    canvas.coords(ch_, 0, e.y, w_, e.y)
                    canvas.coords(cv_, e.x, 0, e.x, h_)
                    canvas.coords(ring_, e.x-12, e.y-12, e.x+12, e.y+12)
                return _m

            def click(ox=sx, oy=sy):
                def _c(e):
                    if state["done"]:
                        return
                    state["done"] = True
                    state["gx"], state["gy"] = e.x + ox, e.y + oy
                    pick()
                return _c

            c.bind("<Motion>", motion())
            c.bind("<ButtonPress-1>", click())
            ov.update_idletasks()
            ov.lift()
            overlays.append(ov)
        if overlays:
            self.root.wait_window(overlays[0])
        try:
            self.root.unbind_all("<Escape>")
        except Exception:
            pass

    def _check_screen_perm(self):
        try:
            return bool(Quartz.CGPreflightScreenCaptureAccess())
        except Exception:
            return False

    def _check_ax_perm(self):
        if not HAS_AX or AXIsProcessTrusted is None:
            return None
        try:
            return bool(AXIsProcessTrusted())
        except Exception:
            return None

    def _tick_permissions(self):
        self.has_screen = self._check_screen_perm()
        self.has_ax = self._check_ax_perm()
        if self.has_screen:
            self.screen_perm_dot.configure(fg=C_GREEN)
        else:
            self.screen_perm_dot.configure(fg=C_RED)
        if self.has_ax is True:
            self.ax_perm_dot.configure(fg=C_GREEN)
        elif self.has_ax is False:
            self.ax_perm_dot.configure(fg=C_RED)
        else:
            self.ax_perm_dot.configure(fg="#B0B0B0")
        self.perm_job = self.root.after(PERM_CHECK_MS, self._tick_permissions)

    def open_screen_settings(self):
        if self.has_screen:
            return
        try:
            subprocess.run(["open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
                check=False)
        except Exception:
            pass

    def open_ax_settings(self):
        if self.has_ax is True:
            return
        try:
            subprocess.run(["open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
                check=False)
        except Exception:
            pass

    def select_region(self):
        result = {"x": None, "y": None, "w": None, "h": None}
        try:
            err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        except Exception as e:
            self.log_msg(f"⚠️ 无法获取显示器列表: {e}")
            return
        if not ids:
            return
        screens = []
        for did in ids:
            r = Quartz.CGDisplayBounds(did)
            screens.append((int(r.origin.x), int(r.origin.y),
                            int(r.size.width), int(r.size.height)))
        overlays, canvas_info = [], []
        st = {"down": False, "dx": 0, "dy": 0, "fx": None, "fy": None, "moved": False}

        def cross(gx, gy):
            for c, s in canvas_info:
                sx, sy, sw, sh = s
                lx, ly = gx - sx, gy - sy
                if 0 <= lx < sw and 0 <= ly < sh:
                    c.coords(c._ch, 0, ly, sw, ly)
                    c.itemconfig(c._ch, state="normal")
                    c.coords(c._cv, lx, 0, lx, sh)
                    c.itemconfig(c._cv, state="normal")
                else:
                    c.itemconfig(c._ch, state="hidden")
                    c.itemconfig(c._cv, state="hidden")

        def rect(g1, g2, g3, g4):
            x1, y1 = min(g1, g3), min(g2, g4)
            x2, y2 = max(g1, g3), max(g2, g4)
            for c, s in canvas_info:
                sx, sy, sw, sh = s
                cx1, cy1 = x1 - sx, y1 - sy
                cx2, cy2 = x2 - sx, y2 - sy
                if cx2 > 0 and cy2 > 0 and cx1 < sw and cy1 < sh:
                    c.coords(c._r, max(0, cx1), max(0, cy1),
                              min(sw, cx2), min(sh, cy2))
                    c.itemconfig(c._r, state="normal")
                else:
                    c.itemconfig(c._r, state="hidden")

        def dot(gx, gy):
            for c, s in canvas_info:
                sx, sy, sw, sh = s
                lx, ly = gx - sx, gy - sy
                if 0 <= lx < sw and 0 <= ly < sh:
                    c.coords(c._d, lx-5, ly-5, lx+5, ly+5)
                    c.itemconfig(c._d, state="normal")
                else:
                    c.itemconfig(c._d, state="hidden")

        def destroy():
            for o in overlays:
                try:
                    o.destroy()
                except Exception:
                    pass
            try:
                self.root.unbind_all("<Escape>")
            except Exception:
                pass

        self.root.bind_all("<Escape>", lambda e: destroy())

        def make(screen):
            sx, sy, sw, sh = screen
            def motion(e):
                gx, gy = e.x + sx, e.y + sy
                cross(gx, gy)
                if st["down"] and abs(gx-st["dx"]) + abs(gy-st["dy"]) > 6:
                    st["moved"] = True
                if st["down"] and st["moved"]:
                    rect(st["dx"], st["dy"], gx, gy)
                elif st["fx"] is not None and not st["down"]:
                    rect(st["fx"], st["fy"], gx, gy)
            def press(e):
                gx, gy = e.x + sx, e.y + sy
                st["down"] = True
                st["dx"], st["dy"] = gx, gy
                st["moved"] = False
                if st["fx"] is not None:
                    st["dx"], st["dy"] = st["fx"], st["fy"]
                cross(gx, gy)
            def release(e):
                if not st["down"]:
                    return
                gx, gy = e.x + sx, e.y + sy
                if st["moved"]:
                    x1, y1 = min(st["dx"], gx), min(st["dy"], gy)
                    x2, y2 = max(st["dx"], gx), max(st["dy"], gy)
                    if x2-x1 > 3 and y2-y1 > 3:
                        result.update(dict(x=x1, y=y1, w=x2-x1, h=y2-y1))
                        destroy()
                        return
                else:
                    if st["fx"] is None:
                        st["fx"], st["fy"] = gx, gy
                        dot(gx, gy)
                    else:
                        x1, y1 = min(st["fx"], gx), min(st["fy"], gy)
                        x2, y2 = max(st["fx"], gx), max(st["fy"], gy)
                        if x2-x1 > 3 and y2-y1 > 3:
                            result.update(dict(x=x1, y=y1, w=x2-x1, h=y2-y1))
                            destroy()
                            return
                        else:
                            st["fx"], st["fy"] = gx, gy
                            dot(gx, gy)
                st["down"], st["moved"] = False, False
            return motion, press, release

        first = True
        for (sx, sy, sw, sh) in screens:
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.configure(bg="black")
            try:
                ov.attributes("-alpha", 0.45)
            except Exception:
                pass
            ov.geometry(f"{sw}x{sh}+{sx}+{sy}")
            c = tk.Canvas(ov, bg="black", highlightthickness=0,
                          cursor="crosshair", width=sw, height=sh)
            c.pack(fill="both", expand=True)
            if first:
                c.create_text(sw//2, 50,
                    text="按住拖拽，或点击两次（左上角 → 右下角）   按 ESC 取消",
                    fill="white", font=("Helvetica Neue", 18, "bold"))
                first = False
            c._ch = c.create_line(0,0,0,0, fill="#ff3b30", width=1, state="hidden")
            c._cv = c.create_line(0,0,0,0, fill="#ff3b30", width=1, state="hidden")
            c._r = c.create_rectangle(0,0,0,0, outline="#ffee00", width=3, state="hidden")
            c._d = c.create_oval(0,0,0,0, outline="#00e5ff", width=2, state="hidden")
            m, p, r = make((sx, sy, sw, sh))
            c.bind("<Motion>", m)
            c.bind("<ButtonPress-1>", p)
            c.bind("<ButtonRelease-1>", r)
            ov.update_idletasks()
            ov.lift()
            overlays.append(ov)
            canvas_info.append((c, (sx, sy, sw, sh)))
        if overlays:
            self.root.wait_window(overlays[0])
        if result["x"] is not None:
            self.vars["x"].set(str(result["x"]))
            self.vars["y"].set(str(result["y"]))
            self.vars["w"].set(str(result["w"]))
            self.vars["h"].set(str(result["h"]))
            self._update_live()
            self.log_msg(f"✅ 已获取区域: X={result['x']}, Y={result['y']}, "
                         f"宽={result['w']}, 高={result['h']}")
            if not self.running:
                self.take_snapshot(result["x"], result["y"],
                                   result["w"], result["h"])
        else:
            self.log_msg("⏱ 已取消框选")

    def take_snapshot(self, x, y, w, h):
        try:
            img = capture_region(x, y, w, h)
            if img is None:
                self.log_msg("⚠️ 快照失败：截图返回空")
                return
            self.update_preview(img)
            self.log_msg("📷 已显示框选区域快照")
        except Exception as e:
            self.log_msg(f"⚠️ 快照失败：{e}")

    def update_preview(self, img):
        try:
            try:
                aw = self.preview_label.winfo_width()
                ah = self.preview_label.winfo_height()
                if aw < 50 or ah < 50:
                    aw, ah = 360, 200
            except Exception:
                aw, ah = 360, 200

            w, h = img.size
            scale = min(aw / w, ah / h)
            if scale < 0.2: scale = 0.2
            if scale > 4.0: scale = 4.0
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            self.preview_image = ImageTk.PhotoImage(
                img.resize((nw, nh), Image.NEAREST))
            self.preview_label.configure(image=self.preview_image, text="")
        except Exception as e:
            self.log_msg(f"预览更新失败：{e}")

    def start(self):
        if self.running:
            return
        self._update_live()
        self.running = True
        self.stop_event.clear()
        self.last_preview_time = 0
        self.preview_hold_until = 0
        self.cooldown_until = 0
        self.cooldown_start = 0
        self.current_cd = 0
        self.in_cooldown = False

        self.start_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
        self.status_var.set("运行中")
        self.status_label.configure(fg=C_GREEN)
        self.status_dot.configure(fg=C_GREEN)

        self.log_msg("▶ 开始监控（所有参数实时生效）")
        self._stop_countdown_ticker()
        self._start_countdown_ticker()
        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.scroll_stop_event.set()
        self._stop_countdown_ticker()
        self.cooldown_until = 0
        self.in_cooldown = False

        self.start_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.status_var.set("未运行")
        self.status_label.configure(fg="#8E8E93")
        self.status_dot.configure(fg="#B0B0B0")
        self.match_var.set("匹配像素：—")
        self.log_msg("■ 已停止")

    def _start_countdown_ticker(self):
        if not self.running:
            self.countdown_job = None
            return
        if self.cooldown_until > 0:
            remaining = self.cooldown_until - time.time()
            if remaining > 0:
                secs = math.ceil(remaining)
                self.status_var.set(f"冷却中 {secs} 秒")
                self.status_label.configure(fg=C_ORANGE)
                self.status_dot.configure(fg=C_ORANGE)
            else:
                self.cooldown_until = 0
                self.in_cooldown = False
                self._on_cooldown_end()
        self.countdown_job = self.root.after(
            COUNTDOWN_TICK_MS, self._start_countdown_ticker)

    def _stop_countdown_ticker(self):
        if self.countdown_job:
            try:
                self.root.after_cancel(self.countdown_job)
            except Exception:
                pass
            self.countdown_job = None

    def _on_enter_cooldown(self, cd):
        if not self.running:
            return
        c = int(cd) if cd == int(cd) else cd
        self.status_var.set(f"冷却中 {math.ceil(cd)} 秒")
        self.status_label.configure(fg=C_ORANGE)
        self.status_dot.configure(fg=C_ORANGE)
        self.log_msg(f"进入冷却：{c} 秒（期间暂停截图）")

    def _on_cooldown_end(self):
        if not self.running:
            return
        self.status_var.set("运行中")
        self.status_label.configure(fg=C_GREEN)
        self.status_dot.configure(fg=C_GREEN)
        self.log_msg("🔵 冷却结束，继续监控")

    def log_msg(self, msg):
        def _do():
            self.log.configure(state="normal")
            ts = time.strftime("%H:%M:%S")
            self.log.insert("end", f"[{ts}] {msg}\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def loop(self):
        while self.running and not self.stop_event.is_set():
            if self.in_cooldown:
                if time.time() < self.cooldown_until:
                    self.stop_event.wait(0.05)
                    continue
                else:
                    self.in_cooldown = False
                    self.cooldown_until = 0
                    self.root.after(0, self._on_cooldown_end)

            t0 = time.time()
            live = dict(self.live)
            try:
                x = int(live["x"]); y = int(live["y"])
                w = max(1, int(live["w"])); h = max(1, int(live["h"]))
            except Exception:
                self.stop_event.wait(0.5)
                continue

            mode = live.get("color_mode", "hue")
            if mode == "hue":
                r0, g0, b0 = live.get("selected_hue", (0, 122, 255))
                tol = int(live.get("hue_tol", 70))
            else:
                try:
                    r0 = int(live["precise_r"]); g0 = int(live["precise_g"])
                    b0 = int(live["precise_b"])
                    tol = int(live.get("precise_tol", "30"))
                except Exception:
                    r0, g0, b0, tol = 0, 122, 255, 70

            try:
                mc = int(live.get("mc", "5"))
                it = float(live.get("it", "0.08"))
                step = max(1, int(live.get("sample_step", "1")))
            except Exception:
                mc, it, step = 5, 0.08, 1

            try:
                img = capture_region(x, y, w, h)
            except Exception as e:
                self.log_msg(f"截图出错：{e}")
                self.stop_event.wait(1)
                continue
            if img is None:
                self.stop_event.wait(0.2)
                continue

            now = time.time()
            if now >= self.preview_hold_until and \
               now - self.last_preview_time >= PREVIEW_INTERVAL:
                self.last_preview_time = now
                self.root.after(0, self.update_preview, img)

            def matcher(r, g, b, _r0=r0, _g0=g0, _b0=b0, _t=tol):
                return match_precise(r, g, b, _r0, _g0, _b0, _t)
            try:
                count = scan_region(img, matcher, mc, step)
            except Exception as e:
                self.log_msg(f"扫描出错：{e}")
                count = 0

            frame_ms = int((time.time() - t0) * 1000)
            if self.running:
                self.root.after(0, self._set_match_text,
                                 f"匹配像素：{count}（帧耗时 {frame_ms} ms）")

            if count >= mc:
                self.last_preview_time = now
                self.preview_hold_until = now + PREVIEW_HOLD_AFTER
                self.root.after(0, self.update_preview, img)

                tm = live.get("trigger_mode", "scroll")
                if tm == "scroll":
                    direction = live.get("scroll_dir", "up")
                    try:
                        tp = int(live.get("total_pixels", "325"))
                        dur = float(live.get("duration", "0.65"))
                    except Exception:
                        tp, dur = 325, 0.65
                    self.log_msg(f"✅ 检测到蓝线（{count} 像素），触发"
                                 f"{'向上' if direction=='up' else '向下'}滚动")
                    self.scroll_stop_event.clear()
                    threading.Thread(
                        target=smooth_scroll,
                        args=(tp, dur, direction, self.scroll_stop_event),
                        daemon=True).start()
                else:
                    combo = live.get("key_combo", "")
                    action = live.get("key_action", "press")
                    try:
                        rc = int(live.get("key_repeat_count", "3"))
                        ri = float(live.get("key_repeat_interval", "0.5"))
                        hd = float(live.get("key_hold_duration", "1.0"))
                    except Exception:
                        rc, ri, hd = 3, 0.5, 1.0
                    disp = format_key_display(combo)
                    self.log_msg(f"✅ 检测到蓝线（{count} 像素），触发按键 {disp}"
                                 f"（{action}）")
                    threading.Thread(
                        target=send_key_combo,
                        args=(combo, action, rc, ri, hd, self.stop_event),
                        daemon=True).start()

                try:
                    cd = float(live.get("cd", "5"))
                except Exception:
                    cd = 5
                if cd > 0:
                    self.cooldown_start = time.time()
                    self.cooldown_until = self.cooldown_start + cd
                    self.current_cd = cd
                    self.in_cooldown = True
                    self.root.after(0, self._on_enter_cooldown, cd)

            self.stop_event.wait(it)

    def _set_match_text(self, text):
        if self.running:
            self.match_var.set(text)

    def on_close(self):
        if self._close_dialog_open:
            return
        self._close_dialog_open = True
        if self.running:
            self.stop()

        if not self._has_changes():
            self._quit()
            return

        self.root.update_idletasks()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dw, dh = 440, 220
        dx = rx + (rw - dw) // 2
        dy = ry + (rh - dh) // 2
        try:
            err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
            screens = []
            for did in ids:
                r = Quartz.CGDisplayBounds(did)
                screens.append((int(r.origin.x), int(r.origin.y),
                                int(r.size.width), int(r.size.height)))
            cx, cy = rx + rw // 2, ry + rh // 2
            target = None
            for (sx, sy, sw, sh) in screens:
                if sx <= cx < sx + sw and sy <= cy < sy + sh:
                    target = (sx, sy, sw, sh)
                    break
            if target is None and screens:
                target = screens[0]
            if target:
                sx, sy, sw, sh = target
                dx = max(sx + 20, min(dx, sx + sw - dw - 20))
                dy = max(sy + 20, min(dy, sy + sh - dh - 20))
        except Exception:
            pass
        dlg = tk.Toplevel(self.root)
        dlg.title("退出 PixelTrigger")
        dlg.configure(bg=C_WINDOW_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry(f"{dw}x{dh}+{dx}+{dy}")
        tk.Label(dlg, text="检测到参数已修改",
                 bg=C_WINDOW_BG, fg=C_TITLE,
                 font=("Helvetica Neue", 14, "bold")).pack(pady=(24, 4))
        tk.Label(dlg,
                 text="是否保存本次修改的参数到配置文件？\n"
                      "选择「不保存」则保留原配置。",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=("Helvetica Neue", 11),
                 justify="center").pack(pady=(0, 18))
        btns = tk.Frame(dlg, bg=C_WINDOW_BG)
        btns.pack()

        def _reset():
            self._close_dialog_open = False

        def do_save():
            self.save_config()
            _reset()
            dlg.destroy()
            self._quit()

        def do_no_save():
            _reset()
            dlg.destroy()
            self._quit()

        def do_cancel():
            _reset()
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", do_cancel)

        FancyButton(btns, "保存并退出",
                    bg_normal=C_ACCENT, bg_hover=C_ACCENT_H,
                    bg_disabled=C_GRAY_DISABLED, fg_normal="#FFFFFF",
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_save, font_size=11).pack(side="left", padx=4)
        FancyButton(btns, "不保存直接退出",
                    bg_normal="#6E6E73", bg_hover="#5A5A5E",
                    bg_disabled=C_GRAY_DISABLED, fg_normal="#FFFFFF",
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_no_save, font_size=11).pack(side="left", padx=4)
        FancyButton(btns, "取消退出",
                    bg_normal=C_GRAY_BG, bg_hover=C_GRAY_BG_H,
                    bg_disabled=C_GRAY_DISABLED, fg_normal=C_TITLE,
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_cancel, font_size=11).pack(side="left", padx=4)

    def _quit(self):
        if self.perm_job:
            try:
                self.root.after_cancel(self.perm_job)
            except Exception:
                pass
            self.perm_job = None
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass
    app = PixelTriggerApp(root)
    root.mainloop()