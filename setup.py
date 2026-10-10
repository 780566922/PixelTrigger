"""
PixelTrigger — py2app 打包配置

用法：
    python3 setup.py py2app          # 生成 dist/PixelTrigger.app
    python3 setup.py py2app -A       # 生成 alias 免拷贝版（快速调试）

依赖：pip3 install py2app Pillow pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
"""

import sys
from setuptools import setup

APP = ['color_watcher.py']

VERSION = '1.2.2'

# pyobjc 框架以 .so 形式提供，必须显式纳入打包范围
PYOBJC_MODULES = [
    'objc',
    'Quartz',
    'ApplicationServices',
]

PIL_MODULES = [
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageGrab',
    'PIL._tkinter_finder',
]

TK_MODULES = [
    'tkinter',
    'tkinter.ttk',
    'tkinter.scrolledtext',
    'tkinter.constants',
    'tkinter.font',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.simpledialog',
]

DATA_FILES = [
    ('', ['donation.png']),
]

OPTIONS = {
    # 本应用不接受拖放文件，也不从命令行取参，关闭 argv 模拟可省掉不必要的开销
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'plist': {
        'CFBundleName': 'PixelTrigger',
        'CFBundleDisplayName': 'PixelTrigger',
        'CFBundleIdentifier': 'com.pixeltrigger.app',
        'CFBundleExecutable': 'PixelTrigger',
        'CFBundleIconFile': 'icon.icns',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'CFBundleGetInfoString': f'PixelTrigger {VERSION} · 像素触发器',
        'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True,
        # 保留为 False：应用有主窗口 Dock 图标，LSUIElement=True 会导致用户无法正常切换/退出
        'LSUIElement': False,
        'LSMinimumSystemVersion': '11.0',
        'NSAppleEventsUsageDescription': '需要控制鼠标滚轮与键盘按键以实现自动翻页触发',
        'NSAccessibilityUsageDescription': '需要辅助功能权限以模拟按键实现自动翻页',
        'NSScreenCaptureUsageDescription': '需要屏幕录制权限以识别指定区域的像素颜色',
    },
    'packages': PYOBJC_MODULES + ['PIL', 'tkinter'],
    'includes': PYOBJC_MODULES + PIL_MODULES + TK_MODULES + ['platform_backend'],
    'excludes': [
        #体积大且完全用不到的科学计算栈
        'numpy', 'scipy', 'pandas', 'matplotlib',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'setuptools', 'pip', 'wheel',
        'test', 'unittest', 'pydoc_data',
        'lib2to3', 'distutils',
    ],
    # 架构通过命令行指定，例如：python3 setup.py py2app --archs=arm64
    # 默认仅构建当前架构；如需 Intel 版用 --archs=x86_64 重新打包
}

setup(
    name='PixelTrigger',
    version=VERSION,
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app>=0.28.8'],
)