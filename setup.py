from setuptools import setup

APP = ['color_watcher.py']
DATA_FILES = [
    ('', ['donation.png']),
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'packages': ['PIL', 'Quartz', 'objc', 'tkinter'],
    'includes': ['tkinter', 'tkinter.ttk', 'tkinter.scrolledtext',
                 'tkinter.constants', 'tkinter.font'],
    'excludes': ['PyQt5', 'PyQt6', 'matplotlib', 'numpy', 'scipy', 'pandas'],
    'plist': {
        'CFBundleName': 'PixelTrigger',
        'CFBundleDisplayName': 'PixelTrigger',
        'CFBundleIdentifier': 'com.pixeltrigger.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
        'NSAppleEventsUsageDescription': '需要控制滚轮与按键以实现自动触发',
        'NSCameraUsageDescription': '',
        'NSMicrophoneUsageDescription': '',
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
