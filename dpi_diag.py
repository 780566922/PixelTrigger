# -*- coding: utf-8 -*-
"""PixelTrigger DPI / 坐标诊断脚本（仅 Windows 有意义）。

用途：验证「框选区域 = 实际截图区域」所依赖的各坐标源是否一致。
在修复前的环境运行会看到 Tk 逻辑像素与 Pillow 物理像素不一致；
修复后（进程声明 Per-Monitor DPI Aware）所有坐标源应统一为物理像素。

用法：
    python dpi_diag.py            # 只读取并打印诊断信息
    python dpi_diag.py --grab     # 额外实测一次全虚拟屏截图尺寸

只读诊断，不修改任何配置；截图仅保留在内存中。
"""

import ctypes
import sys

IS_WIN = sys.platform.startswith("win")

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# GetAwarenessFromDpiAwarenessContext 返回的 DPI_AWARENESS 枚举
AWARENESS_NAMES = {
    0: "无效",
    1: "UNAWARE（DPI 虚拟化，逻辑像素）",
    2: "SYSTEM_AWARE（系统 DPI）",
    3: "PER_MONITOR_AWARE",
    4: "PER_MONITOR_AWARE_V2",
}


def section(title):
    print()
    print("=" * 62)
    print(title)
    print("=" * 62)


def main():
    if not IS_WIN:
        print("本脚本仅用于 Windows。")
        return 1

    user32 = ctypes.windll.user32
    grab_requested = "--grab" in sys.argv

    section("1) 进程 DPI 感知级别")
    # Win10 1607+ 的精确查询
    awareness = None
    try:
        GetThreadDpiAwarenessContext = user32.GetThreadDpiAwarenessContext
        GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        GetAwarenessFromDpiAwarenessContext = \
            user32.GetAwarenessFromDpiAwarenessContext
        GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
        awareness = GetAwarenessFromDpiAwarenessContext(
            GetThreadDpiAwarenessContext())
    except Exception:
        pass
    if awareness is not None and awareness != 0:
        print(f"  线程感知级别: {awareness} = "
              f"{AWARENESS_NAMES.get(awareness, '未知')}")
    else:
        print("  （Win10 1607 查询 API 不可用）")
    try:
        print(f"  IsProcessDPIAware: {bool(user32.IsProcessDPIAware())}")
    except Exception:
        pass

    section("2) 系统 / 主屏 DPI")
    scale = 1.0
    try:
        dpi = user32.GetDpiForSystem()
        scale = dpi / 96.0
        print(f"  GetDpiForSystem: {dpi} dpi  ->  缩放 {scale:.2f}x")
    except Exception:
        print("  GetDpiForSystem 不可用")
    try:
        hdc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        logpx = gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        user32.ReleaseDC(0, hdc)
        print(f"  GetDeviceCaps(LOGPIXELSX): {logpx} dpi  ->  缩放 "
              f"{logpx / 96.0:.2f}x")
    except Exception:
        pass

    section("3) Win32 虚拟屏 / 主屏尺寸（物理像素应为真实分辨率）")
    sm = {n: user32.GetSystemMetrics(n) for n in
          (0, 1, SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN,
           SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN)}
    print(f"  SM_CXSCREEN(主屏宽):   {sm[0]}")
    print(f"  SM_CYSCREEN(主屏高):   {sm[1]}")
    print(f"  虚拟屏: 起点({sm[SM_XVIRTUALSCREEN]}, "
          f"{sm[SM_YVIRTUALSCREEN]}) 尺寸 {sm[SM_CXVIRTUALSCREEN]}x"
          f"{sm[SM_CYVIRTUALSCREEN]}")

    section("4) 显示器枚举 EnumDisplayMonitors")

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    proc_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(RECT), ctypes.c_double)
    rects = []

    def _cb(hmon, hdc, lprc, data):
        r = lprc.contents
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(0, 0, proc_type(_cb), 0)
    for i, (x, y, w, h) in enumerate(rects, 1):
        print(f"  显示器 {i}: ({x}, {y}) {w}x{h}")

    section("5) Tk 视角的屏幕尺寸")
    tk_w = tk_h = None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        tk_w = root.winfo_screenwidth()
        tk_h = root.winfo_screenheight()
        root.destroy()
        print(f"  winfo_screenwidth/height: {tk_w}x{tk_h}")
        if abs(sm[0] - tk_w) > 1:
            print(f"  ⚠️ Tk 与 Win32 不一致（比值 {sm[0] / tk_w:.3f}）——"
                  f"进程未声明 DPI 感知，框选坐标将错位")
        else:
            print("  ✓ Tk 与 Win32 一致")
    except Exception as e:
        print(f"  Tk 不可用：{e}")

    if grab_requested:
        section("6) 实测截图尺寸")
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            print(f"  PIL.ImageGrab 全虚拟屏: {img.size[0]}x{img.size[1]}")
            expect = (sm[SM_CXVIRTUALSCREEN], sm[SM_CYVIRTUALSCREEN])
            if abs(img.size[0] - expect[0]) > 2:
                print(f"  ⚠️ 与 Win32 虚拟屏尺寸不一致（期望 {expect[0]}x"
                      f"{expect[1]}）——存在坐标系混用")
            else:
                print("  ✓ 与 Win32 虚拟屏尺寸一致")
        except Exception as e:
            print(f"  ImageGrab 失败：{e}")

    section("结论参考")
    print("  全部 ✓ ：框选坐标与截图坐标同属物理像素空间，监控区域准确。")
    print("  出现 ⚠️ ：进程处于 DPI 虚拟化空间，缩放屏幕上框选会偏移。")
    print("           请使用 v1.2.1 及以上版本的 PixelTrigger。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
