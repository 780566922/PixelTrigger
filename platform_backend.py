"""
PixelTrigger 平台适配层（macOS / Windows）

把两个平台在「系统级能力」上的差异全部收口到本模块，主程序
(color_watcher.py) 只调用这里暴露的统一接口，从而一份代码同时支持
macOS 与 Windows。

命名约定（沿用主程序既有风格）：
  - 键名沿用 X11 keysym：'Return' / 'Left' / 'a' / 'minus' / 'Next' ...
  - 修饰键名：'cmd' / 'shift' / 'ctrl' / 'opt'

平台差异一览：
  能力            macOS                          Windows
  ------------    ---------------------------    ----------------------------------
  截图            Quartz.CGWindowListCreateImage PIL.ImageGrab
  滚轮            CGEvent 像素级                  mouse_event(MOUSEEVENTF_WHEEL) 格级
  键盘            CGEvent + 虚拟键码              keybd_event + VK 码
  显示器枚举      CGGetActiveDisplayList          EnumDisplayMonitors
  系统深浅色      CFPreferences / defaults        winreg AppsUseLightTheme
  权限            屏幕录制 + 辅助功能（TCC）      无（恒为已授权）
  配置目录        ~/Library/Application Support   %APPDATA%
"""

import os
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

try:  # macOS 专有，Windows 上为 None
    import Quartz
except Exception:  # pragma: no cover - 仅在非 mac 平台触发
    Quartz = None


# ============================================================
# 配置目录 / 字体 / 光标
# ============================================================

def app_support_dir():
    """返回用户配置与资源目录（自动创建）。"""
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "PixelTrigger")
    else:
        path = os.path.expanduser("~/Library/Application Support/PixelTrigger")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


if IS_WIN:
    FONT_UI = "Microsoft YaHei UI"     # 微软雅黑，中文显示最佳
    FONT_MONO = "Consolas"
    HAND_CURSOR = "hand2"
else:
    FONT_UI = "Helvetica Neue"
    FONT_MONO = "Menlo"
    HAND_CURSOR = "pointinghand"


def permission_system_available():
    """是否存在「需要用户授权才能截图 / 模拟输入」的系统机制。

    仅 macOS 有（TCC：屏幕录制 + 辅助功能）。Windows 无此机制，
    主程序据此隐藏权限状态指示与相关引导。
    """
    return IS_MAC


# ============================================================
# 系统外观（浅色 / 深色）
# ============================================================

def get_system_theme():
    """返回 'light' 或 'dark'。读取失败一律按浅色处理。"""
    if IS_WIN:
        return _win_theme()
    return _mac_theme()


def _win_theme():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(val) != 0 else "dark"
    except Exception:
        return "light"


def _mac_theme():
    # 浅色模式下 AppleInterfaceStyle 这个 key 根本不存在，
    # CFPreferencesCopyAppValue 返回 None 即代表浅色。
    try:
        Quartz.CFPreferencesAppSynchronize("kCFPreferencesCurrentUser")
        val = Quartz.CFPreferencesCopyAppValue(
            "AppleInterfaceStyle", "kCFPreferencesCurrentUser")
        return "dark" if str(val).strip().lower() == "dark" else "light"
    except Exception:
        pass
    try:
        import subprocess
        res = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip().lower() == "dark":
            return "dark"
    except Exception:
        pass
    return "light"


# ============================================================
# 只读卷运行检测（仅 macOS 有意义）
# ============================================================

def is_readonly_volume_run():
    """是否从只读卷（DMG 挂载点 /Volumes/...）直接运行。

    macOS 的 TCC 授权按「完整路径 + 代码签名」匹配，从 DMG 直接运行会
    因挂载路径不稳定而拿不到稳定授权。Windows 无此问题，恒返回 False。
    """
    if IS_WIN:
        return False
    try:
        bundle = Quartz.CFBundleGetMainBundle()
        if bundle:
            url = Quartz.CFBundleCopyBundleURL(bundle)
            path = Quartz.CFURLCopyFileSystemPath(url, 0)
            if path:
                return str(path).startswith("/Volumes/")
    except Exception:
        pass
    try:
        exe = os.path.realpath(sys.executable)
    except Exception:
        exe = sys.executable
    return exe.startswith("/Volumes/")


# ============================================================
# 显示器枚举
# ============================================================

def list_displays():
    """返回 [(x, y, w, h), ...]，使用全局屏幕坐标系（主屏左上为原点）。

    用于框选覆盖层、取色器覆盖层、以及退出对话框的居中定位。
    """
    if IS_WIN:
        return _win_displays()
    return _mac_displays()


def _mac_displays():
    out = []
    try:
        err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        for did in ids or []:
            r = Quartz.CGDisplayBounds(did)
            out.append((int(r.origin.x), int(r.origin.y),
                        int(r.size.width), int(r.size.height)))
    except Exception:
        pass
    return out


def _win_displays():
    out = []
    try:
        import ctypes
        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(RECT), ctypes.c_double)

        def _cb(hmon, hdc, lprc, data):
            r = lprc.contents
            out.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1

        user32.EnumDisplayMonitors(0, 0, proc_type(_cb), 0)
    except Exception:
        pass
    return out


# ============================================================
# 屏幕截图
# ============================================================

def grab_region(x, y, w, h):
    """截取屏幕指定矩形区域，返回 PIL.Image(RGB)；失败返回 None。"""
    try:
        x, y, w, h = int(x), int(y), int(w), int(h)
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    if IS_WIN:
        return _win_grab(x, y, w, h)
    return _mac_grab(x, y, w, h)


def _win_grab(x, y, w, h):
    try:
        from PIL import ImageGrab
        # all_screens=True 使用虚拟桌面坐标（与 list_displays 一致），
        # 可正确截取副屏；要求 Pillow >= 8.2。
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        return img.convert("RGB")
    except Exception:
        return None


def _mac_grab(x, y, w, h):
    from PIL import Image
    try:
        rect = Quartz.CGRectMake(x, y, w, h)
        cg = Quartz.CGWindowListCreateImage(
            rect, Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
        if cg is None:
            return None
        width = Quartz.CGImageGetWidth(cg)
        height = Quartz.CGImageGetHeight(cg)
        bpr = Quartz.CGImageGetBytesPerRow(cg)
        # 关键：先把 CGImage 的像素数据完整拷贝到 Python bytes，之后
        # CGImage/CFData 交给 pyobjc 引用计数自动释放。
        # 不能手动 CGImageRelease(cg)：pyobjc 托管对象在 Python 侧
        # __del__ 里还会再 release 一次，手动释放会导致双重释放，在打包
        # 环境（冻结 pyobjc + macOS 15）下直接 SIGSEGV。
        data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg))
        buf = bytes(data)
        del data
        return Image.frombuffer("RGBA", (width, height), buf,
                                "raw", "BGRA", bpr, 1).convert("RGB")
    except Exception:
        return None


# ============================================================
# 滚轮
# ============================================================

# macOS 是像素级滚动；Windows 的 mouse_event 只能按「格」(WHEEL_DELTA=120)。
# 用累积器把连续的像素量换算成整格，避免小步长被取整丢光。
_WIN_PIXELS_PER_CLICK = 100.0
_win_scroll_accum = 0.0


def post_scroll(pixels):
    """发送一次滚轮事件。pixels 为像素量，正值表示向上滚动（内容下移）。"""
    global _win_scroll_accum
    try:
        pixels = float(pixels)
    except Exception:
        return
    if not IS_WIN:
        try:
            evt = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitPixel, 1, int(pixels))
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        except Exception:
            pass
        return

    _win_scroll_accum += pixels
    clicks = int(_win_scroll_accum / _WIN_PIXELS_PER_CLICK)
    if clicks == 0:
        return
    _win_scroll_accum -= clicks * _WIN_PIXELS_PER_CLICK
    try:
        import ctypes
        MOUSEEVENTF_WHEEL = 0x0800
        ctypes.windll.user32.mouse_event(
            MOUSEEVENTF_WHEEL, 0, 0, int(clicks * 120), 0)
    except Exception:
        pass


# ============================================================
# 键盘
# ============================================================

# 主键名 -> macOS 虚拟键码
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

# 主键名 -> Windows 虚拟键码(VK)
KEYSYM_TO_VK = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
    'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C,
    'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52,
    's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
    'y': 0x59, 'z': 0x5A,
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
    '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    'Return': 0x0D, 'KP_Enter': 0x0D, 'Tab': 0x09, 'space': 0x20,
    'BackSpace': 0x08, 'Escape': 0x1B, 'Delete': 0x2E,
    'Left': 0x25, 'Right': 0x27, 'Down': 0x28, 'Up': 0x26,
    'Home': 0x24, 'End': 0x23, 'Prior': 0x21, 'Next': 0x22,
    'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74, 'F6': 0x75,
    'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
    'minus': 0xBD, 'equal': 0xBB, 'bracketleft': 0xDB, 'bracketright': 0xDD,
    'backslash': 0xDC, 'semicolon': 0xBA, 'apostrophe': 0xDE, 'grave': 0xC0,
    'comma': 0xBC, 'period': 0xBE, 'slash': 0xBF,
}

# 修饰键 -> 平台键码
_MAC_MOD_KEYCODES = {"cmd": 55, "shift": 56, "opt": 58, "ctrl": 59}
_WIN_MOD_VKS = {"cmd": 0x5B, "shift": 0x10, "opt": 0x12, "ctrl": 0x11}

# Windows 上这些键是「扩展键」，keybd_event 必须带 KEYEVENTF_EXTENDEDKEY，
# 否则方向键 / PgUp / PgDn / 小键盘等会被当成主键盘区同名键。
_WIN_EXTENDED_VKS = {
    0x25, 0x26, 0x27, 0x28,          # 方向键
    0x24, 0x23, 0x21, 0x22,          # Home / End / PageUp / PageDown
    0x2D, 0x2E,                      # Insert / Delete
    0x5B, 0x5C,                      # Win / Menu
}


def is_supported_key(name):
    """判断主键名是否能被当前平台发送。"""
    table = KEYSYM_TO_VK if IS_WIN else KEYSYM_TO_MAC
    return name in table


def key_event(name, is_down):
    """发送一次按键按下 / 抬起事件。

    name 既可以是主键名（'Return'），也可以是修饰键名（'cmd'）。
    """
    if IS_WIN:
        vk = KEYSYM_TO_VK.get(name) or _WIN_MOD_VKS.get(name)
        if vk is None:
            return
        _win_keybd(vk, is_down)
    else:
        kc = KEYSYM_TO_MAC.get(name)
        if kc is None:
            kc = _MAC_MOD_KEYCODES.get(name)
        if kc is None:
            return
        try:
            evt = Quartz.CGEventCreateKeyboardEvent(None, kc, bool(is_down))
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        except Exception:
            pass


def _win_keybd(vk, is_down):
    try:
        import ctypes
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        flags = 0 if is_down else KEYEVENTF_KEYUP
        if vk in _WIN_EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        ctypes.windll.user32.keybd_event(vk, 0, flags, 0)
    except Exception:
        pass


# ============================================================
# 按键捕获（对话框里解析 event.state 的修饰键位）
# ============================================================

if IS_WIN:
    # Tk 在 Windows 上：Shift=0x1, Control=0x4, Alt=0x20000；
    # 没有独立的 Win 键位（设为 0 表示捕获不到）。
    MOD_MASKS = {"shift": 0x0001, "ctrl": 0x0004, "opt": 0x20000, "cmd": 0x0000}
    MOD_SYMBOL = {"cmd": "Win", "shift": "Shift", "ctrl": "Ctrl", "opt": "Alt"}
else:
    MOD_MASKS = {"cmd": 0x0010, "opt": 0x0008, "ctrl": 0x0004, "shift": 0x0001}
    MOD_SYMBOL = {"cmd": "⌘", "shift": "⇧", "ctrl": "⌃", "opt": "⌥"}


def decode_mods(state):
    """把 Tk 事件的 state 解析成修饰键名列表（顺序固定，便于去重）。"""
    out = []
    for name in ("cmd", "opt", "ctrl", "shift"):
        mask = MOD_MASKS.get(name, 0)
        if mask and (state & mask):
            out.append(name)
    return out


# ============================================================
# 权限（仅 macOS 有实际语义）
# ============================================================

def check_screen_perm():
    """屏幕录制权限是否已授予。Windows 恒为 True。"""
    if IS_WIN:
        return True
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def check_ax_perm():
    """辅助功能权限状态：True/False，无法判定时 None。Windows 恒为 True。"""
    if IS_WIN:
        return True
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def request_screen_perm():
    """主动请求屏幕录制权限（触发系统授权弹窗）。Windows 无操作。"""
    if IS_WIN:
        return True
    try:
        return bool(Quartz.CGRequestScreenCaptureAccess())
    except Exception:
        return False


def request_ax_perm():
    """主动请求辅助功能权限（触发系统授权弹窗）。Windows 无操作。"""
    if IS_WIN:
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        return bool(AXIsProcessTrustedWithOptions(
            {"AXTrustedCheckOptionPrompt": True}))
    except Exception:
        return check_ax_perm()


def open_screen_settings_page():
    """打开系统的屏幕录制权限设置页。Windows 无操作。"""
    if IS_WIN:
        return
    try:
        import subprocess
        subprocess.run(["open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
            check=False)
    except Exception:
        pass


def open_ax_settings_page():
    """打开系统的辅助功能权限设置页。Windows 无操作。"""
    if IS_WIN:
        return
    try:
        import subprocess
        subprocess.run(["open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            check=False)
    except Exception:
        pass
