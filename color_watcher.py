import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageTk
import subprocess
import time
import os
import sys
import json
import math
import threading
import queue

# 平台适配层：截图 / 键鼠模拟 / 系统外观 / 权限 / 配置路径等系统级差异
# 全部收口在 platform_backend，本文件保持平台无关。
import platform_backend as pb

# ============================================================
APP_NAME = "PixelTrigger"
# 配置目录由平台层决定：macOS 用 ~/Library/Application Support，
# Windows 用 %APPDATA%。
APP_SUPPORT_DIR = pb.app_support_dir()

# 测试/自动化脚本通过设置 PIXELTRIGGER_CONFIG 指向临时路径，
# 避免污染用户真实配置（历史上已两次因测试 save_config 覆盖真实数据）。
CONFIG_FILE = os.environ.get(
    "PIXELTRIGGER_CONFIG",
    os.path.join(APP_SUPPORT_DIR, "config.json"),
)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)


def get_donation_path():
    """
    获取捐赠二维码图片路径，优先级：
    1. PyInstaller 打包后（Windows）：sys._MEIPASS/donation.png
    2. py2app 打包后（macOS .app 内 Resources/donation.png）
    3. 脚本同级目录 donation.png
    4. 用户配置目录下的 donation.png（兼容旧版）
    """
    candidates = []
    # PyInstaller 单文件模式：资源被解包到 sys._MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "donation.png"))
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


def get_app_icon_path():
    """Windows 下窗口 / 任务栏图标 icon.ico 的路径；macOS 返回 None
    （macOS 的图标由 .app 包内的 icns 提供，无需在此设置）。"""
    if not pb.IS_WIN:
        return None
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "icon.ico"))
    try:
        candidates.append(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
    except Exception:
        pass
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
    # 框选坐标所属空间标记：Windows 声明 Per-Monitor DPI Aware 后坐标
    # 为物理像素（"physical"）；缺失或为旧值表示 v1.2.0 之前的
    # 「DPI 虚拟化逻辑像素」坐标，加载时按缩放系数迁移。
    "coord_space": "",
}

PREVIEW_INTERVAL = 1.0
PREVIEW_HOLD_AFTER = 3.0
COUNTDOWN_TICK_MS = 100
PERM_CHECK_MS = 1000
# 主线程 UI 派发队列的轮询间隔（毫秒）。后台线程的 UI 更新经过
# 该队列收口到主线程，避免跨线程操作 Tk 导致崩溃。
UI_POLL_MS = 30

# 系统外观轮询间隔。macOS 没有公开的「外观变化」广播通知，
# 只能轮询 AppleInterfaceStyle；1 秒足以让肉眼感知为实时，
# 又不会因为频繁读preferences 造成可观的CPU 占用。
THEME_POLL_MS = 1000

# 日志区保留的最大行数，超出后丢弃最旧的。
LOG_MAX_LINES = 2000

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

MODIFIER_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R",
                    "Alt_L", "Alt_R", "Meta_L", "Meta_R",
                    "Super_L", "Super_R", "Command", "Caps_Lock"}
DISPLAY_NAME = {"Return": "Return", "KP_Enter": "Enter", "space": "Space",
                "Tab": "Tab", "BackSpace": "Backspace", "Escape": "Esc",
                "Delete": "Delete", "Prior": "PageUp", "Next": "PageDown",
                "Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}
# 修饰键符号由平台层提供（macOS: ⌘⇧⌃⌥，Windows: Win/Shift/Ctrl/Alt）
MOD_SYMBOL = pb.MOD_SYMBOL

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
C_ON_ACCENT = "#FFFFFF"
# 亮色按钮（绿/红系）上的文字色。白色文字在亮绿底(#30D158)上对比度仅
# 2.02，远低于 WCAG AA 的 4.5；改用近黑可达 8.32。这是亮底必配深字的
# 通用规律，故与 C_ON_ACCENT（深色底上的白字）分开定义。
C_ON_LIGHT_BTN = "#0B3D1E"
# 红底按钮专用前景：白字在 #FF3B30 上仅 3.55，深字可达 4.74
C_ON_RED_BTN = "#1D1D1F"
C_ON_RED_BTN_H = "#1D1D1F"
C_ON_LIGHT_BTN_H = "#0B3D1E"
#蓝底按钮专用前景：亮蓝底需深字，深蓝底用白字
C_ON_ACCENT_BTN = "#FFFFFF"
C_ON_ACCENT_BTN_H = "#FFFFFF"
C_NEUTRAL_BTN = "#6E6E73"
C_NEUTRAL_BTN_H = "#5A5A5E"
C_ENTRY_BG = "#FFFFFF"
C_PREVIEW_BG = "#F5F5F7"
# 屏幕取色覆盖层的标记色（叠在任意截图上，必须高对比）
C_MARK_RED = "#FF3B30"
C_MARK_ON_RED = "#FFFFFF"
C_MARK_YELLOW = "#FFCC00"
C_MARK_CYAN = "#00C7BE"


# ============================================================
# 主题：跟随系统浅色 / 深色外观
# ============================================================
# Tkinter 没有原生主题支持，控件配色全部由本文件显式指定，因此需要
# 自行读取系统外观并切换调色板。系统深色时 defaults 返回 "Dark"，
# 浅色（或未设置）时该键不存在，命令返回非 0。
THEME_LIGHT = "light"
THEME_DARK = "dark"

LIGHT_PALETTE = {
    "window_bg": "#ECECEC",
    "card_bg": "#FFFFFF",
    "card_border": "#E2E2E2",
    "title": "#1D1D1F",
    "card_title": "#6E6E73",
    "label": "#3A3A3C",
    "subtext": "#66666A",
    "accent": "#0062CC",
    "accent_h": "#0052A8",
    "green": "#34C759",
    "green_h": "#1B7F35",
    "orange": "#FF9500",
    "red": "#FF3B30",
    "red_h": "#B31D1D",
    "hue_border": "#C7C7CC",
    "gray_bg": "#E5E5EA",
    "gray_bg_h": "#D1D1D6",
    "gray_disabled": "#D0D0D0",
    "gray_disabled_fg": "#48484A",
    "on_accent": "#FFFFFF",
    #浅色主题下绿底 #34C759 配白字仅 2.55，同样需深字
    "on_light_btn": "#0B3D1E",
    "on_light_btn_h": "#FFFFFF",
    "on_red_btn": "#1D1D1F",
    "on_red_btn_h": "#FFFFFF",
    "on_accent_btn": "#FFFFFF",
    "on_accent_btn_h": "#FFFFFF",
    "neutral_btn": "#6E6E73",
    "neutral_btn_h": "#5A5A5E",
    "entry_bg": "#FFFFFF",
    "preview_bg": "#F5F5F7",
    "mark_red": "#FF3B30",
    "mark_on_red": "#FFFFFF",
    "mark_yellow": "#FFCC00",
    "mark_cyan": "#00C7BE",
}

# 深色下调色板遵循 Apple HIG 语义色：背景用 elevation 层级区分，
# 文字用 label 层级（primary / secondary / tertiary）。
DARK_PALETTE = {
    "window_bg": "#1E1E20",
    "card_bg": "#2C2C2E",
    "card_border": "#3A3A3C",
    "title": "#F5F5F7",
    "card_title": "#AEAEB2",
    "label": "#E5E5EA",
    "subtext": "#98989D",
    "accent": "#0A84FF",
    "accent_h": "#409CFF",
    "green": "#30D158",
    "green_h": "#3DD964",
    "orange": "#FF9F0A",
    "red": "#FF453A",
    "red_h": "#FF6961",
    "hue_border": "#48484A",
    "gray_bg": "#3A3A3C",
    "gray_bg_h": "#48484A",
    "gray_disabled": "#3A3A3C",
    "gray_disabled_fg": "#AEAEB2",
    # 深色底上用近黑文字，浅色底上用白色文字，保证对比度
    "on_accent": "#FFFFFF",
    # 亮蓝底 #0A84FF 配白字仅 3.65，改深字达 4.51
    "on_accent_btn": "#0B1F3D",
    "on_accent_btn_h": "#0B1F3D",
    # 暗色下绿底 #30D158 亮度更高，深字可达 8.32:1
    "on_light_btn": "#0B3D1E",
    "on_light_btn_h": "#0B3D1E",
    "on_red_btn": "#3D0A06",
    "on_red_btn_h": "#3D0A06",
    "neutral_btn": "#5A5A5E",
    "neutral_btn_h": "#6E6E73",
    "entry_bg": "#1C1C1E",
    "preview_bg": "#141416",
    # 覆盖层标记在深色截图上需要更亮的描边
    "mark_red": "#FF453A",
    "mark_on_red": "#FFFFFF",
    "mark_yellow": "#FFD60A",
    "mark_cyan": "#64D2FF",
}

CURRENT_THEME = THEME_LIGHT


def detect_system_theme():
    """
    读取系统外观，返回 THEME_LIGHT / THEME_DARK。

    读取方式委托平台层（platform_backend.get_system_theme）：
      - macOS：CFPreferences 进程内读取，失败退回 `defaults read`
      - Windows：注册表 AppsUseLightTheme
    读不到一律按浅色处理。
    """
    return THEME_DARK if pb.get_system_theme() == "dark" else THEME_LIGHT


def detect_running_from_dmg():
    """
    检测当前是否从只读卷（macOS 的 DMG 挂载点 /Volumes/...）直接运行。

    macOS 的 TCC 授权按「完整路径 + 代码签名」匹配，从 DMG 直接运行会因
    挂载路径不稳定（/Volumes/PixelTrigger 1、2 …）而无法获得稳定授权，
    需引导用户拖到「应用程序」目录再运行。Windows 无此机制，恒为 False。
    实现委托平台层。
    """
    return pb.is_readonly_volume_run()


def apply_theme(theme):
    """把调色板写入模块级常量，供所有控件读取。"""
    global CURRENT_THEME
    pal = DARK_PALETTE if theme == THEME_DARK else LIGHT_PALETTE
    CURRENT_THEME = theme
    globals().update({
        "C_WINDOW_BG": pal["window_bg"],
        "C_CARD_BG": pal["card_bg"],
        "C_CARD_BORDER": pal["card_border"],
        "C_TITLE": pal["title"],
        "C_CARD_TITLE": pal["card_title"],
        "C_LABEL": pal["label"],
        "C_SUBTEXT": pal["subtext"],
        "C_ACCENT": pal["accent"],
        "C_ACCENT_H": pal["accent_h"],
        "C_GREEN": pal["green"],
        "C_GREEN_H": pal["green_h"],
        "C_ORANGE": pal["orange"],
        "C_RED": pal["red"],
        "C_RED_H": pal["red_h"],
        "C_HUE_BORDER": pal["hue_border"],
        "C_GRAY_BG": pal["gray_bg"],
        "C_GRAY_BG_H": pal["gray_bg_h"],
        "C_GRAY_DISABLED": pal["gray_disabled"],
        "C_GRAY_DISABLED_FG": pal["gray_disabled_fg"],
        "C_ON_ACCENT": pal["on_accent"],
        "C_ON_LIGHT_BTN": pal["on_light_btn"],
        "C_ON_RED_BTN": pal["on_red_btn"],
        "C_ON_RED_BTN_H": pal["on_red_btn_h"],
        "C_ON_LIGHT_BTN_H": pal["on_light_btn_h"],
        "C_ON_ACCENT_BTN": pal["on_accent_btn"],
        "C_ON_ACCENT_BTN_H": pal["on_accent_btn_h"],
        "C_NEUTRAL_BTN": pal["neutral_btn"],
        "C_NEUTRAL_BTN_H": pal["neutral_btn_h"],
        "C_ENTRY_BG": pal["entry_bg"],
        "C_PREVIEW_BG": pal["preview_bg"],
        "C_MARK_RED": pal["mark_red"],
        "C_MARK_ON_RED": pal["mark_on_red"],
        "C_MARK_YELLOW": pal["mark_yellow"],
        "C_MARK_CYAN": pal["mark_cyan"],
    })
    return pal


class FancyButton:
    def __init__(self, parent, text, bg_normal, bg_hover,
                 bg_disabled, fg_normal, fg_disabled,
                 command, font_size=12, padx=18, pady=7,
                 fg_hover=None):
        self.bg_normal = bg_normal
        self.bg_hover = bg_hover
        self.bg_disabled = bg_disabled
        self.fg_normal = fg_normal
        self.fg_disabled = fg_disabled
        # hover 底色亮度可能与常态不同（如亮蓝 -> 更浅蓝），允许单独指定
        # 文字色，否则 hover 时对比度会失配
        self.fg_hover = fg_hover or fg_normal
        self.command = command
        self.enabled = True
        self.label = tk.Label(
            parent, text=text, bg=bg_normal, fg=fg_normal,
            font=(pb.FONT_UI, font_size, "bold"),
            padx=padx, pady=pady, cursor=pb.HAND_CURSOR)
        self.label.bind("<Enter>", self._enter)
        self.label.bind("<Leave>", self._leave)
        self.label.bind("<Button-1>", self._click)

    def _enter(self, e):
        if self.enabled:
            self.label.configure(bg=self.bg_hover, fg=self.fg_hover)

    def _leave(self, e):
        if self.enabled:
            self.label.configure(bg=self.bg_normal, fg=self.fg_normal)

    def _click(self, e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.label.configure(bg=self.bg_normal, fg=self.fg_normal,
                                  cursor=pb.HAND_CURSOR)
        else:
            self.label.configure(bg=self.bg_disabled, fg=self.fg_disabled,
                                  cursor="arrow")

    def pack(self, **kw):
        self.label.pack(**kw)

    def grid(self, **kw):
        self.label.grid(**kw)


def capture_region(x, y, w, h):
    """截取屏幕矩形区域，返回 PIL.Image(RGB)；失败返回 None。

    macOS 走 Quartz，Windows 走 GDI（ctypes），差异已由平台层封装。
    """
    return pb.grab_region(x, y, w, h)


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
            pb.post_scroll(sign * step)
            scrolled = target
        time.sleep(interval)
    if not stop_event.is_set():
        tail = total_pixels - scrolled
        if tail > 0:
            pb.post_scroll(sign * tail)


def _combo_to_parts(combo):
    if not combo:
        return [], None
    parts = [p for p in combo.split("+") if p]
    if not parts:
        return [], None
    return parts[:-1], parts[-1]


def send_key_combo(combo, action, count, interval, hold_duration, stop_event):
    """发送按键组合。

    修饰键改为显式的「按下 → 主键 → 抬起」事件序列，使 macOS 与
    Windows 行为一致（底层实现由平台层 platform_backend.key_event 提供）。
    """
    mods, main = _combo_to_parts(combo)
    if main is None:
        return
    if not pb.is_supported_key(main):
        return

    def _down_mods():
        for m in mods:
            pb.key_event(m, True)

    def _up_mods():
        for m in reversed(mods):
            pb.key_event(m, False)

    def press_once():
        _down_mods()
        pb.key_event(main, True)
        pb.key_event(main, False)
        _up_mods()

    def hold_once(dur):
        _down_mods()
        pb.key_event(main, True)
        end = time.time() + dur
        while time.time() < end:
            if stop_event.is_set():
                break
            time.sleep(0.02)
        pb.key_event(main, False)
        _up_mods()

    try:
        if action == "press":
            press_once()
        elif action == "repeat":
            for i in range(max(1, count)):
                if stop_event.is_set():
                    return
                press_once()
                if i < count - 1:
                    end = time.time() + interval
                    while time.time() < end:
                        if stop_event.is_set():
                            return
                        time.sleep(0.02)
        elif action == "hold":
            hold_once(max(0.05, hold_duration))
    except Exception:
        pass


def match_precise(r, g, b, r0, g0, b0, tol):
    return (abs(r - r0) <= tol and abs(g - g0) <= tol and abs(b - b0) <= tol)


def scan_region(img, matcher, mc, sample_step, target=None):
    w, h = img.size
    step = max(1, sample_step)
    count = 0
    # 热路径优化：当提供 target=(r0,g0,b0,tol) 时（loop 中的唯一用法），
    # 直接将 RGB 数据读入内存视图逐行扫描，避免每像素一次 img.load()
    # 字典查找与 matcher 函数调用开销。否则回退到通用逐像素 matcher。
    if target is not None:
        r0, g0, b0, tol = target
        try:
            raw = img.tobytes("raw", "RGB")
        except Exception:
            raw = None
        if raw is not None:
            view = memoryview(raw)
            row_bytes = w * 3
            y = 0
            while y < h:
                row = view[y * row_bytes:(y + 1) * row_bytes]
                i = 0
                while i < row_bytes:
                    r = row[i]
                    g = row[i + 1]
                    b = row[i + 2]
                    if (r - r0 if r >= r0 else r0 - r) <= tol and \
                       (g - g0 if g >= g0 else g0 - g) <= tol and \
                       (b - b0 if b >= b0 else b0 - b) <= tol:
                        count += 1
                        if count >= mc:
                            return count
                    i += 3
                y += step
            return count
    # 通用回退路径
    pixels = img.load()
    y = 0
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
        tk.Label(tw, text=self.text, bg=C_PREVIEW_BG, fg=C_TITLE,
                 font=(pb.FONT_UI, 11), justify="left", anchor="w",
                 padx=14, pady=10, wraplength=280,
                 highlightbackground=C_HUE_BORDER,
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
        # 记录上一次权限状态，用于检测「授权状态变化」并提示用户
        self._last_screen_perm = None
        self._last_ax_perm = None
        self._perm_notified = {"screen": False, "ax": False}

        self.theme_job = None
        # 主题重建期间挂起一切对外交互，避免在半成品UI 上操作
        self._rebuilding = False
        # 全屏覆盖层（框选 / 取色器）是否正在显示
        self._overlay_open = False
        # 记录已经打进日志的主题切换，避免同一次切换刷屏
        self._last_logged_theme = CURRENT_THEME

        self._close_dialog_open = False
        self._key_capture_open = False
        # ============================================================
        # 线程安全的 UI 派发队列
        #
        # 后台监控线程（loop / smooth_scroll / send_key_combo）绝不能
        # 直接调用 Tk 的 after / configure / set 等方法。Tk（Tcl）解释器
        # 非线程安全：后台线程与主线程事件循环并发操作 Tcl 解释器，会在
        # 主线程销毁控件树（关闭窗口、主题重建）时访问到已释放的 Tcl
        # 命令对象，表现为 Tcl_EvalObjv 里访问非法地址(如 0x23)而 SIGSEGV。
        #
        # 方案：后台线程只把「要执行的 UI 动作」塞进线程安全队列，由
        # 主线程用一个 after 轮询器统一取出并执行。这样所有 Tk 调用都
        # 只发生在主线程，从根本上消除竞态。
        # ============================================================
        self._ui_queue = queue.Queue()
        self._closing = False
        self._ui_poll_job = None
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
        self._tick_theme()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(10, self._fit_and_center)

        # 启动时若检测到从 DMG 卷运行，弹窗强提示——这是权限红点的最常见根因。
        # 用户从 DMG 直接双击运行，挂载路径不稳定（重复挂载变 /Volumes/xxx 1），
        # 且系统拒绝给只读卷程序写 TCC 记录，导致授权永远不生效。
        if detect_running_from_dmg():
            self.root.after(600, self._warn_running_from_dmg)

        # 启动 UI 派发队列轮询器：主线程周期性取出后台线程塞入的
        # UI 动作并执行。轮询间隔短，保证预览刷新、日志、倒计时等
        # 反馈的实时性。
        self._ui_poll_job = self.root.after(UI_POLL_MS, self._drain_ui_queue)

    def _post_ui(self, fn, *args):
        """线程安全地把一个 UI 动作交给主线程执行。

        后台线程只能通过本方法间接更新界面；主线程也可直接调用。
        """
        if self._closing:
            return
        try:
            self._ui_queue.put_nowait((fn, args))
        except Exception:
            pass

    def _drain_ui_queue(self):
        """主线程轮询器：取出队列里所有待执行的 UI 动作并执行。"""
        if self._closing:
            return
        # 一次性取完当前积压的动作，避免高频刷新时队列越积越深。
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    # 单个动作失败不应拖垮整个队列（例如目标 widget
                    # 已销毁，触发 TclError）。
                    pass
        except queue.Empty:
            pass
        self._ui_poll_job = self.root.after(UI_POLL_MS, self._drain_ui_queue)

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

    def _warn_running_from_dmg(self):
        """从 DMG 卷运行时的启动强提示，引导用户正确安装。"""
        try:
            messagebox.showwarning(
                "请先安装到「应用程序」",
                "检测到 PixelTrigger 正从 DMG 磁盘映像直接运行。\n\n"
                "这种方式无法稳定获得「辅助功能」和「屏幕录制」权限，"
                "会导致权限圆点一直显示红色。\n\n"
                "请把 PixelTrigger 拖到「应用程序」文件夹，\n"
                "然后从应用程序里打开，再在系统设置中重新勾选权限。",
                parent=self.root)
        except Exception:
            pass

    # 数值类配置字段（用于类型校验，避免外部篡改导致异常）
    _NUMERIC_KEYS = {
        "x", "y", "w", "h", "br", "bg", "mb", "mc", "it", "cd",
        "sample_step", "hue_r", "hue_g", "hue_b", "hue_tol",
        "precise_r", "precise_g", "precise_b", "precise_tol",
        "total_pixels", "duration", "key_repeat_count",
        "key_repeat_interval", "key_hold_duration",
    }

    def load_config(self):
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    saved = json.load(f)
                if not isinstance(saved, dict):
                    return cfg
                for k in cfg:
                    if k not in saved:
                        continue
                    val = saved[k]
                    if k in self._NUMERIC_KEYS:
                        try:
                            # 数值字段校验：仅接受可解析为数字的标量
                            cfg[k] = str(float(val))
                        except (TypeError, ValueError):
                            # 非法值（数组/对象/非数字）回退到默认值
                            continue
                    else:
                        cfg[k] = str(val)
            except Exception:
                pass
        # Windows 坐标空间迁移：v1.2.0 及更早版本的框选坐标记录在
        # 「DPI 虚拟化逻辑像素」空间；启用 Per-Monitor DPI Aware 后为
        # 物理像素。检测到旧格式时按系统 DPI 缩放系数一次性换算。
        if pb.IS_WIN and cfg.get("coord_space") != "physical":
            s = pb.win_display_scale()
            if abs(s - 1.0) > 1e-6:
                for k in ("x", "y", "w", "h"):
                    try:
                        cfg[k] = str(int(round(float(cfg[k]) * s)))
                    except Exception:
                        pass
            # 标记已迁移并立即回写磁盘，防止下次启动对坐标重复放大
            cfg["coord_space"] = "physical"
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(cfg, f, indent=2)
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
                # Windows 框选坐标空间标记（物理像素），供版本升级迁移
                "coord_space": "physical" if pb.IS_WIN else "points",
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
                 font=(pb.FONT_UI, 10, "bold"),
                 anchor="w").pack(fill="x")
        body = tk.Frame(card, bg=C_CARD_BG)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 10))
        return outer, body

    def _make_field(self, parent, label, key, default="", width=6):
        f = tk.Frame(parent, bg=C_CARD_BG)
        tk.Label(f, text=label, bg=C_CARD_BG, fg=C_LABEL,
                 font=(pb.FONT_UI, 10), anchor="w").pack(fill="x")
        v = tk.StringVar(value=self.cfg_values.get(key, default))
        self.vars[key] = v
        e = ttk.Entry(f, textvariable=v, width=width, font=(pb.FONT_MONO, 11))
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
                 font=(pb.FONT_UI, 18, "bold")).pack(side="left")
        tk.Label(left, text="  像素触发器",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 11)).pack(side="left", pady=(6, 0))

        right = tk.Frame(top, bg=C_WINDOW_BG)
        right.pack(side="right")

        perm_area = tk.Frame(right, bg=C_WINDOW_BG)
        perm_area.pack(side="right")

        # 权限指示仅在存在「需要用户授权」机制的平台上显示（macOS）。
        # Windows 截图与模拟输入无需授权，隐藏该区域避免误导。
        self.screen_perm_frame = self.screen_perm_dot = self.screen_perm_lbl = None
        self.ax_perm_frame = self.ax_perm_dot = self.ax_perm_lbl = None
        if pb.permission_system_available():
            def mk_perm(text):
                f = tk.Frame(perm_area, bg=C_WINDOW_BG, cursor=pb.HAND_CURSOR)
                dot = tk.Label(f, text="●", bg=C_WINDOW_BG,
                               font=(pb.FONT_UI, 11), fg=C_GRAY_DISABLED_FG)
                dot.pack(side="left", padx=(0, 4))
                lbl = tk.Label(f, text=text, bg=C_WINDOW_BG, fg=C_LABEL,
                               font=(pb.FONT_UI, 11))
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

        tk.Frame(right, bg=C_HUE_BORDER, width=1, height=24).pack(
            side="right", padx=(16, 0), pady=6)

        buttons_area = tk.Frame(right, bg=C_WINDOW_BG)
        buttons_area.pack(side="right", padx=(0, 16))

        self.start_btn = FancyButton(
            buttons_area, "▶   开始监控",
            bg_normal=C_GREEN, bg_hover=C_GREEN_H,
            bg_disabled=C_GRAY_DISABLED,
            fg_normal=C_ON_LIGHT_BTN, fg_hover=C_ON_LIGHT_BTN_H,
            fg_disabled=C_GRAY_DISABLED_FG,
            command=self.start)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = FancyButton(
            buttons_area, "■   停止",
            bg_normal=C_RED, bg_hover=C_RED_H,
            bg_disabled=C_GRAY_DISABLED,
            fg_normal=C_ON_RED_BTN, fg_hover=C_ON_RED_BTN_H,
            fg_disabled=C_GRAY_DISABLED_FG,
            command=self.stop)
        self.stop_btn.pack(side="left")
        self.stop_btn.set_enabled(False)

        donate_btn = tk.Label(
            right, text="❤", bg=C_WINDOW_BG, fg=C_RED,
            font=(pb.FONT_UI, 18), cursor=pb.HAND_CURSOR,
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
                 font=(pb.FONT_UI, 16, "bold")).pack(pady=(22, 4))
        tk.Label(dlg, text="如果您觉得 PixelTrigger 有帮助，欢迎扫码打赏",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 11)).pack(pady=(0, 14))

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
                     font=(pb.FONT_UI, 11),
                     width=32, height=10,
                     justify="center").pack(padx=10, pady=10)

        btns = tk.Frame(dlg, bg=C_WINDOW_BG)
        btns.pack(pady=(0, 18))

        close_btn = tk.Label(btns, text="关闭", bg=C_ACCENT, fg=C_ON_ACCENT_BTN,
                             font=(pb.FONT_UI, 11, "bold"),
                             padx=20, pady=6, cursor=pb.HAND_CURSOR)
        close_btn.bind("<Enter>", lambda e: close_btn.configure(
            bg=C_ACCENT_H, fg=C_ON_ACCENT_BTN_H))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(
            bg=C_ACCENT, fg=C_ON_ACCENT_BTN))
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
                                     font=(pb.FONT_UI, 20),
                                     fg=C_GRAY_DISABLED_FG)
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_var = tk.StringVar(value="未运行")
        self.status_label = tk.Label(st, textvariable=self.status_var,
                                       bg=C_CARD_BG, fg=C_SUBTEXT,
                                       font=(pb.FONT_UI, 22, "bold"),
                                       anchor="w")
        self.status_label.pack(side="left")
        self.match_var = tk.StringVar(value="匹配像素：—")
        tk.Label(b, textvariable=self.match_var, bg=C_CARD_BG,
                 fg=C_SUBTEXT, font=(pb.FONT_MONO, 10),
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
                        font=(pb.FONT_UI, 11),
                        command=self._on_mode_change).pack(side="left", padx=(0, 16))
        tk.Radiobutton(mr, text="精准容差",
                        variable=self.color_mode, value="precise",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=(pb.FONT_UI, 11),
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
        self.base_color_box = tk.Label(pr1, text="  ", bg=C_ENTRY_BG,
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
                 font=(pb.FONT_MONO, 10)).pack(side="left")
        pr2 = tk.Frame(self.precise_panel, bg=C_CARD_BG)
        pr2.pack(fill="x")
        tk.Label(pr2, text="容差", bg=C_CARD_BG, fg=C_LABEL,
                 font=(pb.FONT_UI, 10)).pack(side="left", padx=(0, 6))
        tol_init = int(float(self.cfg_values.get("precise_tol", "30")))
        self.tol_var = tk.IntVar(value=tol_init)
        self.vars["precise_tol"] = self.tol_var
        ttk.Scale(pr2, from_=0, to=120, orient="horizontal",
                   variable=self.tol_var, length=200).pack(side="left", padx=(0, 8))
        self.tol_label = tk.Label(pr2, text=str(tol_init),
                                    bg=C_CARD_BG, fg=C_TITLE,
                                    font=(pb.FONT_MONO, 11, "bold"),
                                    width=4, anchor="e")
        self.tol_label.pack(side="left")
        tk.Label(pr2, text="(0-120)", bg=C_CARD_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 9)).pack(side="left", padx=(4, 0))

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
                     increment=0.5, width=5, font=(pb.FONT_MONO, 11),
                     justify="center").pack(side="left", ipady=1)
        tk.Label(cdr, text="秒", bg=C_CARD_BG, fg=C_LABEL,
                 font=(pb.FONT_UI, 11)).pack(side="left", padx=(4, 12))
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
                        font=(pb.FONT_UI, 11),
                        command=self._on_trigger_mode_change).pack(side="left", padx=(0, 14))
        tk.Radiobutton(tm, text="触发按键", variable=self.trigger_mode,
                        value="key", bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=(pb.FONT_UI, 11),
                        command=self._on_trigger_mode_change).pack(side="left")

        self.scroll_panel = tk.Frame(b, bg=C_CARD_BG)
        sr = tk.Frame(self.scroll_panel, bg=C_CARD_BG)
        sr.pack(fill="x", pady=(8, 4))
        tk.Label(sr, text="方向", bg=C_CARD_BG, fg=C_LABEL,
                 font=(pb.FONT_UI, 10)).pack(side="left", padx=(0, 6))
        self.scroll_dir = tk.StringVar(
            value=self.cfg_values.get("scroll_dir", "up"))
        tk.Radiobutton(sr, text="向上", variable=self.scroll_dir, value="up",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=(pb.FONT_UI, 10)).pack(side="left", padx=(0, 10))
        tk.Radiobutton(sr, text="向下", variable=self.scroll_dir, value="down",
                        bg=C_CARD_BG, fg=C_TITLE,
                        activebackground=C_CARD_BG,
                        font=(pb.FONT_UI, 10)).pack(side="left")
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
                 font=(pb.FONT_UI, 10)).pack(side="left", padx=(0, 6))
        self.key_display_var = tk.StringVar(
            value=format_key_display(self.key_combo_str))
        tk.Label(kr1, textvariable=self.key_display_var,
                 bg=C_PREVIEW_BG, fg=C_TITLE,
                 font=(pb.FONT_MONO, 11, "bold"),
                 padx=10, pady=4,
                 highlightbackground=C_HUE_BORDER,
                 highlightthickness=1).pack(side="left", padx=(0, 6))
        ttk.Button(kr1, text="设置", command=self.open_key_capture,
                    width=4).pack(side="left")

        kr2 = tk.Frame(self.key_panel, bg=C_CARD_BG)
        kr2.pack(fill="x", pady=(0, 4))
        tk.Label(kr2, text="动作", bg=C_CARD_BG, fg=C_LABEL,
                 font=(pb.FONT_UI, 10)).pack(side="left", padx=(0, 6))
        self.key_action = tk.StringVar(
            value=self.cfg_values.get("key_action", "press"))
        for txt, val in [("按一下", "press"), ("连按", "repeat"), ("按住", "hold")]:
            tk.Radiobutton(kr2, text=txt, variable=self.key_action, value=val,
                            bg=C_CARD_BG, fg=C_TITLE,
                            activebackground=C_CARD_BG,
                            font=(pb.FONT_UI, 10),
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

        preview_box = tk.Frame(b, bg=C_PREVIEW_BG,
                               highlightbackground=C_CARD_BORDER,
                               highlightthickness=1,
                               width=1, height=1)
        preview_box.pack(fill="both", expand=True)
        preview_box.pack_propagate(False)

        self.preview_label = tk.Label(preview_box, text="（未运行）",
                                       bg=C_PREVIEW_BG, fg=C_SUBTEXT,
                                       font=(pb.FONT_UI, 11))
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
                 font=(pb.FONT_UI, 10, "bold"),
                 anchor="w").pack(side="left")

        log_inner = tk.Frame(card, bg=C_CARD_BG)
        log_inner.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        self.log = scrolledtext.ScrolledText(
            log_inner, state="disabled", wrap="word",
            width=1, height=8,
            font=(pb.FONT_MONO, 10),
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=C_CARD_BORDER,
            # 必须显式给 fg：ScrolledText 默认取 systemTextColor，
            # 它跟随「系统」外观而非本应用调色板。深色系统下配深色底
            # 尚可读，但一旦系统外观与应用主题不同步就会撞色。
            bg=C_ENTRY_BG, fg=C_SUBTEXT,
            insertbackground=C_SUBTEXT,
            selectbackground=C_ACCENT, selectforeground=C_ON_ACCENT_BTN)
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
        # cd 为 0 或负值时视为「无冷却」，交给 loop 线程裁决退出，
        # 这里不做任何状态写入，避免与 loop 线程的时钟打架。
        if new_cd < 0.001:
            return
        if abs(new_cd - self.current_cd) < 0.001:
            return
        # 用户冷却期间改了 cd：仅更新「冷却结束时间点」，让 loop
        # 线程按新的时长继续倒计时，而不在主线程裁决结束/清标志。
        self.current_cd = new_cd
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
                 font=(pb.FONT_UI, 14, "bold")).pack(pady=(24, 4))
        tk.Label(dlg, text="支持字母、数字、方向键、F1-F12、以及 ⌘/⇧/⌃/⌥ 组合键",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 10)).pack(pady=(0, 12))

        status_var = tk.StringVar(value="⌨️  等待按键…")
        status_label = tk.Label(dlg, textvariable=status_var,
                                 bg=C_PREVIEW_BG, fg=C_ACCENT,
                                 font=(pb.FONT_MONO, 16, "bold"),
                                 padx=18, pady=12,
                                 highlightbackground=C_HUE_BORDER,
                                 highlightthickness=1)
        status_label.pack(pady=(0, 6))

        tk.Label(dlg, text="按 ESC 取消", bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 10)).pack(pady=(0, 12))

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
            # 修饰键位掩码随平台不同，统一交给平台层解析
            mods = pb.decode_mods(flags)

            if keysym in MODIFIER_KEYSYMS:
                if mods:
                    s = "".join(MOD_SYMBOL.get(m, m) for m in mods)
                    status_var.set(f"{s}  …  再按一个键")
                    status_label.configure(fg=C_ACCENT)
                return

            main = keysym.lower() if len(keysym) == 1 and keysym.isalpha() else keysym

            if main == "Escape" and not mods:
                status_var.set("已取消")
                status_label.configure(fg=C_SUBTEXT)
                close(150)
                return

            if not pb.is_supported_key(main):
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
        screens = pb.list_displays()
        if not screens:
            return
        overlays = []

        def destroy_all():
            self._overlay_open = False
            for o in overlays:
                try:
                    o.destroy()
                except Exception:
                    pass
            try:
                self.root.unbind_all("<Escape>")
            except Exception:
                pass

        self._overlay_open = True
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
            ch = c.create_line(0, 0, 0, 0, fill=C_MARK_RED, width=1)
            cv = c.create_line(0, 0, 0, 0, fill=C_MARK_RED, width=1)
            ring = c.create_oval(0, 0, 0, 0, outline=C_MARK_ON_RED, width=2)

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
        return pb.check_screen_perm()

    def _check_ax_perm(self):
        return pb.check_ax_perm()

    def _request_screen_perm(self):
        """
        主动请求屏幕录制权限，触发系统授权弹窗。

        macOS 必须调用 CGRequestScreenCaptureAccess() 才会弹出授权框；
        只做检测（CGPreflightScreenCaptureAccess）永远不会弹窗，设置里
        也就永远没有条目。Windows 无此机制，平台层直接返回 True。
        """
        return pb.request_screen_perm()

    def _request_ax_perm(self):
        """
        主动请求辅助功能权限，触发系统授权弹窗。

        macOS 用 AXIsProcessTrustedWithOptions + kAXTrustedCheckOptionPrompt
        强制弹窗。Windows 无此机制，平台层直接返回 True。
        """
        return pb.request_ax_perm()

    def _tick_permissions(self):
        self._tick_permissions_once()
        self.perm_job = self.root.after(PERM_CHECK_MS, self._tick_permissions)

    # ============================================================
    # 系统外观（浅色/ 深色）监听
    #
    # 难点：所有颜色在控件构造时就被写死进bg/fg，事后改模块常量对
    # 已存在的控件无效。因此切换主题只能销毁并重建整棵界面树，
    # 同时把用户当前的输入、运行状态、日志、预览图原样搬回去。
    # ============================================================
    def _theme_busy(self):
        """
        主题重建期间不能有模态/ 覆盖层窗口存在。

        框选、取色器都是全屏透明覆盖层并带wait_window 阻塞，
        捐赠窗与按键捕获窗则grab_set 了输入；此时重建主界面会
        打断它们，因此一律推迟到它们关闭后再切。
        """
        return bool(self._donation_window is not None
                    or self._key_capture_open
                    or self._close_dialog_open
                    or getattr(self, "_overlay_open", False))

    def _tick_theme(self):
        if self._rebuilding:
            self.theme_job = self.root.after(THEME_POLL_MS, self._tick_theme)
            return
        try:
            now = detect_system_theme()
            if now != CURRENT_THEME:
                if not self._theme_busy():
                    self._rebuild_for_theme(now)
                # 忙碌时静默跳过：下一次轮询会重新比对，
                # 覆盖层一关就会自动补上切换。
        except Exception:
            pass
        self.theme_job = self.root.after(THEME_POLL_MS, self._tick_theme)

    def _capture_ui_state(self):
        """把界面上的动态状态抽成可序列化的 dict，供重建后还原。"""
        state = {}
        try:
            for k, v in self.vars.items():
                try:
                    state["var:" + k] = str(v.get())
                except Exception:
                    pass
            state["color_mode"] = self.color_mode.get()
            state["trigger_mode"] = self.trigger_mode.get()
            state["scroll_dir"] = self.scroll_dir.get()
            state["key_action"] = self.key_action.get()
            state["key_combo"] = self.key_combo_str
            state["hue"] = tuple(self.selected_hue)
            state["hue_tol"] = int(self.hue_tol)
        except Exception:
            pass
        # 运行期状态：重建后要继续跑，而不是变回"未运行"
        state["running"] = self.running
        state["status"] = self.status_var.get()
        state["match"] = self.match_var.get()
        state["in_cooldown"] = self.in_cooldown
        try:
            state["log"] = self.log.get("1.0", "end-1c")
        except Exception:
            state["log"] = ""
        return state

    def _restore_ui_state(self, state):
        """把 _capture_ui_state 抓到的状态写回新建的控件。"""
        try:
            for k, v in self.vars.items():
                key = "var:" + k
                if key in state:
                    try:
                        v.set(state[key])
                    except Exception:
                        pass
            self.color_mode.set(state.get("color_mode", "hue"))
            self.trigger_mode.set(state.get("trigger_mode", "scroll"))
            self.scroll_dir.set(state.get("scroll_dir", "up"))
            self.key_action.set(state.get("key_action", "press"))
            self.key_combo_str = state.get("key_combo", "Next")
            h = state.get("hue")
            if h:
                self.selected_hue = tuple(h)
            self.hue_tol = int(state.get("hue_tol", HUE_DEFAULT_TOL))
        except Exception:
            pass

        # 面板显隐要按还原后的模式重新计算一次
        try:
            self._on_mode_change()
            self._on_trigger_mode_change()
            self._refresh_hue_borders()
        except Exception:
            pass

        # 日志
        try:
            text = state.get("log", "")
            if text:
                self.log.configure(state="normal")
                self.log.insert("1.0", text)
                self.log.see("end")
                self.log.configure(state="disabled")
        except Exception:
            pass

        # 运行状态：按钮可用性与状态灯颜色要一并还原，
        # 否则会出现「日志说在跑但停止按钮是灰的」这种不一致。
        try:
            self.match_var.set(state.get("match", "匹配像素：—"))
            self.status_var.set(state.get("status", "未运行"))
            if state.get("running"):
                self.start_btn.set_enabled(False)
                self.stop_btn.set_enabled(True)
                fg = C_ORANGE if state.get("in_cooldown") else C_GREEN
                self.status_label.configure(fg=fg)
                self.status_dot.configure(fg=fg)
            else:
                self.start_btn.set_enabled(True)
                self.stop_btn.set_enabled(False)
                self.status_label.configure(fg=C_SUBTEXT)
                self.status_dot.configure(fg=C_GRAY_DISABLED_FG)
        except Exception:
            pass

        try:
            self._update_live()
        except Exception:
            pass

        # 冷却标记必须在 _update_live 之后回写：_update_live 会触发
        # _maybe_adjust_cooldown，若 cd 被改过，它可能把冷却判定为已结束
        # 并顺手清掉 in_cooldown。回写顺序放在后面，状态才与界面一致。
        if state.get("in_cooldown"):
            self.in_cooldown = True

    def _rebuild_for_theme(self, theme):
        """
        切换调色板并重建界面。

        顺序很关键：必须先把状态抓下来（此时控件还活着的旧配色），
        再销毁重建，最后还原；顺序颠倒会丢参数。
        """
        state = self._capture_ui_state()
        # 快照基线要跟着一起重置：重建后的控件集合与初始时不同，
        # 若沿用旧基线会把「主题切换」误判成「用户改了参数」，
        # 退出时凭空弹出保存对话框。
        self._rebuilding = True
        try:
            # 预热预览图引用，避免销毁父widget 时被GC 连带回收
            old_preview = self.preview_image
            apply_theme(theme)
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            # _build_ui 会重置 vars 与 _hue_borders，先清干净
            self.vars = {}
            self._hue_borders = []
            self.preview_image = None
            self.root.configure(bg=C_WINDOW_BG)
            self._build_ui()
            self._restore_ui_state(state)
            # 预览图在新label 上重新贴一次
            if old_preview is not None:
                try:
                    self.preview_image = old_preview
                    self.preview_label.configure(image=old_preview, text="")
                except Exception:
                    self.preview_image = None
        finally:
            self._rebuilding = False

        # 权限圆点由 _tick_permissions 下一轮刷新，这里主动同步一次，
        # 免得重建后有最长 1 秒显示成默认灰色
        try:
            self._tick_permissions_once()
        except Exception:
            pass
        # 注意：刻意不重置 _initial_snapshot。它记录的是「启动时读到的配置」，
        # 是退出时判断是否要提示保存的唯一依据。若在这里用重建后的控件
        # 重新取一次基线，用户改过的参数会被当成没改过，退出时静默丢配置。

        if theme != self._last_logged_theme:
            self._last_logged_theme = theme
            name = "深色" if theme == THEME_DARK else "浅色"
            self.log_msg(f"🎨 已跟随系统切换到{name}外观")

    def _tick_permissions_once(self):
        """只刷新权限圆点颜色，不重新排定轮询。"""
        self.has_screen = self._check_screen_perm()
        self.has_ax = self._check_ax_perm()
        # 无授权机制的平台（Windows）不创建权限控件，直接跳过 UI 刷新。
        if self.screen_perm_dot is None or self.ax_perm_dot is None:
            return
        if self.has_screen:
            self.screen_perm_dot.configure(fg=C_GREEN)
        else:
            self.screen_perm_dot.configure(fg=C_RED)
        if self.has_ax is True:
            self.ax_perm_dot.configure(fg=C_GREEN)
        elif self.has_ax is False:
            self.ax_perm_dot.configure(fg=C_RED)
        else:
            self.ax_perm_dot.configure(fg=C_GRAY_DISABLED_FG)

        # 权限状态发生变化时主动提示，而不是让用户对着红点猜。
        # 关键场景：ad-hoc 签名 + 重新打包 → CDHash 变化 → TCC 里旧的
        # 授权记录匹配不上，AXIsProcessTrusted 返回 False，但系统设置里
        # 仍显示「已勾选」。此时只提示「重新勾选一次」即可恢复。
        self._maybe_notify_perm_change()

    def _maybe_notify_perm_change(self):
        """权限状态变化时向用户提示，并给出针对性引导。"""
        # 首次进入时仅记录基线，不提示
        if self._last_screen_perm is None:
            self._last_screen_perm = self.has_screen
            self._last_ax_perm = self.has_ax
            return

        # 屏幕录制：从无到有
        if self.has_screen and not self._last_screen_perm \
                and not self._perm_notified["screen"]:
            self._perm_notified["screen"] = True
            self.log_msg("🟢 屏幕录制权限已生效")

        # 辅助功能：从无到有
        if self.has_ax is True and self._last_ax_perm is not True \
                and not self._perm_notified["ax"]:
            self._perm_notified["ax"] = True
            self.log_msg("🟢 辅助功能权限已生效")

        # 辅助功能：一直拿不到，但系统里可能已勾选（CDHash 不匹配的典型）
        if self.has_ax is False and not self._perm_notified["ax"]:
            # 仅提示一次，避免刷屏
            self._perm_notified["ax"] = True
            if detect_running_from_dmg():
                self.log_msg(
                    "🔴 辅助功能权限未生效：检测到正从 DMG 磁盘映像直接运行，"
                    "这种运行方式无法稳定获得系统授权。请把 PixelTrigger 拖到"
                    "「应用程序」目录后，从那里打开，再重新勾选权限。")
            else:
                self.log_msg(
                    "🔴 辅助功能权限未生效：若系统设置里已勾选，请取消勾选后"
                    "重新勾选一次（应用更新后签名变化会导致旧授权失效）")

        self._last_screen_perm = self.has_screen
        self._last_ax_perm = self.has_ax

    def open_screen_settings(self):
        if self.has_screen:
            return
        # 先主动请求权限触发系统弹窗——这样「屏幕录制」里才会出现本应用条目。
        # 请求后无论用户是否同意，再打开设置页让用户能直接勾选/添加。
        try:
            self._request_screen_perm()
        except Exception:
            pass
        pb.open_screen_settings_page()

    def open_ax_settings(self):
        if self.has_ax is True:
            return
        # 同上：先请求权限触发弹窗，再打开设置页。
        try:
            self._request_ax_perm()
        except Exception:
            pass
        pb.open_ax_settings_page()

    def select_region(self):
        result = {"x": None, "y": None, "w": None, "h": None}
        screens = pb.list_displays()
        if not screens:
            self.log_msg("⚠️ 无法获取显示器列表")
            return
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
            self._overlay_open = False
            for o in overlays:
                try:
                    o.destroy()
                except Exception:
                    pass
            try:
                self.root.unbind_all("<Escape>")
            except Exception:
                pass

        self._overlay_open = True
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
                    fill="white", font=(pb.FONT_UI, 18, "bold"))
                first = False
            c._ch = c.create_line(0,0,0,0, fill=C_MARK_RED, width=1, state="hidden")
            c._cv = c.create_line(0,0,0,0, fill=C_MARK_RED, width=1, state="hidden")
            c._r = c.create_rectangle(0,0,0,0, outline=C_MARK_YELLOW, width=3, state="hidden")
            c._d = c.create_oval(0,0,0,0, outline=C_MARK_CYAN, width=2, state="hidden")
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
        # 启动前主动检查权限，缺失时给出明确指引，而不是让用户
        # 进入运行态后才发现截图/按键一直不生效。
        self._tick_permissions_once()
        if not self.has_screen:
            # 主动请求屏幕录制权限，触发系统授权弹窗。
            # 之前只做检测不请求，导致系统设置里永远没有本应用条目。
            self.log_msg("🔴 尚未授予「屏幕录制」权限。正在请求系统授权…")
            try:
                granted = self._request_screen_perm()
            except Exception:
                granted = False
            if granted:
                self.has_screen = True
                self.log_msg("🟢 屏幕录制权限已生效")
            else:
                self.log_msg("🔴 请在弹出的系统授权框中允许，或点击右上角红点授权。")
                return
        if self.has_ax is False:
            # 主动请求辅助功能权限，触发系统授权弹窗（仅提示不阻断）。
            self.log_msg("🔴 尚未授予「辅助功能」权限，正在请求系统授权…")
            try:
                self._request_ax_perm()
            except Exception:
                pass
            if self._check_ax_perm() is True:
                self.has_ax = True
                self.log_msg("🟢 辅助功能权限已生效")
            else:
                self.log_msg("🔴 辅助功能权限仍缺失，按键/滚动触发将无法生效。")
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
        self.status_label.configure(fg=C_SUBTEXT)
        self.status_dot.configure(fg=C_GRAY_DISABLED_FG)
        self.match_var.set("匹配像素：—")
        self.log_msg("■ 已停止")

    def _start_countdown_ticker(self):
        if not self.running:
            self.countdown_job = None
            return
        # 倒计时显示只负责「读」冷却剩余时间并刷新状态栏文字，
        # 绝不裁决冷却是否结束。结束裁决权唯一地属于 loop 线程
        # （它是唯一推进 in_cooldown / cooldown_until 的时钟），
        # 否则两个时钟互相清状态会造成「一直显示冷却中 1 秒」。
        if self.cooldown_until > 0:
            remaining = self.cooldown_until - time.time()
            if remaining > 0:
                secs = max(1, math.ceil(remaining))
                self.status_var.set(f"冷却中 {secs} 秒")
                self.status_label.configure(fg=C_ORANGE)
                self.status_dot.configure(fg=C_ORANGE)
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
            # 裁掉超出上限的历史，避免长时间运行后 ScrolledText
            # 无限膨胀（异常分支每秒可写一条，跑一整天就是几万行）。
            # 只在超量时动手，平时零开销。
            # end-1c 指向末尾换行符之前，index 返回的是「末行行号」，
            # 故实际行数 = 该值；再减 1 是为了让删除区间正好留上限行。
            nlines = int(self.log.index("end-1c").split(".")[0])
            if nlines > LOG_MAX_LINES:
                self.log.delete("1.0", f"{nlines - LOG_MAX_LINES + 1}.0")
            self.log.see("end")
            self.log.configure(state="disabled")
        # 统一走线程安全队列：log_msg 可能被主线程（start/stop）与
        # 后台线程（loop）同时调用，都必须收口到主线程执行。
        self._post_ui(_do)

    def loop(self):
        while self.running and not self.stop_event.is_set():
            if self.in_cooldown:
                if time.time() < self.cooldown_until:
                    self.stop_event.wait(0.05)
                    continue
                else:
                    self.in_cooldown = False
                    self.cooldown_until = 0
                    self._post_ui(self._on_cooldown_end)

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
                self._post_ui(self.update_preview, img)

            def matcher(r, g, b, _r0=r0, _g0=g0, _b0=b0, _t=tol):
                return match_precise(r, g, b, _r0, _g0, _b0, _t)
            try:
                count = scan_region(img, matcher, mc, step, target=(r0, g0, b0, tol))
            except Exception as e:
                self.log_msg(f"扫描出错：{e}")
                count = 0

            frame_ms = int((time.time() - t0) * 1000)
            if self.running:
                self._post_ui(self._set_match_text,
                               f"匹配像素：{count}（帧耗时 {frame_ms} ms）")

            if count >= mc:
                self.last_preview_time = now
                self.preview_hold_until = now + PREVIEW_HOLD_AFTER
                self._post_ui(self.update_preview, img)

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
                    self._post_ui(self._on_enter_cooldown, cd)

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
            screens = pb.list_displays()
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
                 font=(pb.FONT_UI, 14, "bold")).pack(pady=(24, 4))
        tk.Label(dlg,
                 text="是否保存本次修改的参数到配置文件？\n"
                      "选择「不保存」则保留原配置。",
                 bg=C_WINDOW_BG, fg=C_SUBTEXT,
                 font=(pb.FONT_UI, 11),
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
                    bg_disabled=C_GRAY_DISABLED,
                    fg_normal=C_ON_ACCENT_BTN, fg_hover=C_ON_ACCENT_BTN_H,
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_save, font_size=11).pack(side="left", padx=4)
        FancyButton(btns, "不保存直接退出",
                    bg_normal=C_NEUTRAL_BTN, bg_hover=C_NEUTRAL_BTN_H,
                    bg_disabled=C_GRAY_DISABLED, fg_normal=C_ON_ACCENT,
                    fg_hover=C_ON_ACCENT,
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_no_save, font_size=11).pack(side="left", padx=4)
        FancyButton(btns, "取消退出",
                    bg_normal=C_GRAY_BG, bg_hover=C_GRAY_BG_H,
                    bg_disabled=C_GRAY_DISABLED, fg_normal=C_TITLE,
                    fg_hover=C_TITLE,
                    fg_disabled=C_GRAY_DISABLED_FG,
                    command=do_cancel, font_size=11).pack(side="left", padx=4)

    def _quit(self):
        # 置关闭标志：后台线程再往队列塞 UI 动作会被直接丢弃，
        # 轮询器也立即停止，杜绝销毁后再访问 Tk 对象导致的崩溃。
        self._closing = True
        if self._ui_poll_job:
            try:
                self.root.after_cancel(self._ui_poll_job)
            except Exception:
                pass
            self._ui_poll_job = None
        if self.perm_job:
            try:
                self.root.after_cancel(self.perm_job)
            except Exception:
                pass
            self.perm_job = None
        if self.theme_job:
            try:
                self.root.after_cancel(self.theme_job)
            except Exception:
                pass
            self.theme_job = None
        self.root.destroy()


if __name__ == "__main__":
    # 主题必须在任何控件创建前应用：控件构造时会把当前的 C_* 常量
    # 直接写入bg/fg，之后再改常量不会生效。
    apply_theme(detect_system_theme())

    root = tk.Tk()
    # 登记 Tk 视角的屏幕尺寸，供 Windows 侧自校准坐标空间
    # （platform_backend.set_ui_screen_size；其他平台为空操作）。
    try:
        pb.set_ui_screen_size(root.winfo_screenwidth(),
                              root.winfo_screenheight())
    except Exception:
        pass
    try:
        # Windows 进程已声明 Per-Monitor DPI Aware，DWM 不再做位图放大，
        # 字号按系统 DPI 同比例补偿（96dpi 时即原值 1.2），视觉大小与
        # 旧版一致且文字更清晰。macOS 维持 1.2（win_display_scale 恒 1）。
        root.tk.call("tk", "scaling", 1.2 * pb.win_display_scale())
    except Exception:
        pass
    # Windows 下设置窗口 / 任务栏图标（macOS 由 .app 的 icns 承担）
    try:
        _icon = get_app_icon_path()
        if _icon:
            root.iconbitmap(_icon)
    except Exception:
        pass
    app = PixelTriggerApp(root)
    root.mainloop()