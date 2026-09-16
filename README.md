# PixelTrigger

> 像素触发器 · 蓝线识别自动翻页

一个 macOS 应用，通过识别屏幕上指定区域的像素颜色变化，自动触发滚动或按键操作。典型用途是乐谱软件（如 MuseScore）的自动翻页：检测到播放光标经过指定区域后，自动向上/向下滚动页面。

## 功能

- 像素颜色识别：支持 7 种预设色系 + 精准容差模式
- 两种触发方式：滚动翻页、按键触发
- 智能冷却：触发后自动暂停检测
- 实时预览：实时显示监控区域截图
- 参数实时生效：运行中修改参数立即生效
- 内存截图：无磁盘 I/O，帧耗时 10~50ms
- 多屏支持：主屏/副屏都能框选监控区域

## 下载安装

1. 从 Releases 页面下载最新的 PixelTrigger.app.zip
2. 解压后把 PixelTrigger.app 拖到「应用程序」文件夹
3. 第一次打开：右键点击 App，选择「打开」，弹窗里再点「打开」
4. 授权：
   - 系统设置 → 隐私与安全性 → 屏幕录制：勾选 PixelTrigger
   - 系统设置 → 隐私与安全性 → 辅助功能：勾选 PixelTrigger
5. 完全退出 App（Cmd+Q）再重新打开

## 使用方法

1. 打开 PixelTrigger
2. 选择「色系匹配」或「精准容差」模式
3. 点击「点击框选屏幕区域」，框选监控区域
4. 选择触发方式（滚动翻页 / 触发按键）
5. 点击「开始监控」

## 从源码运行

安装依赖：`pip3 install --user Pillow pyobjc-framework-Quartz`

运行：`python3 color_watcher.py`

## 自行打包为 .app

安装 py2app：`pip3 install --user py2app`

打包：`cd color_watcher && python3 setup.py py2app`

打包产物在 `dist/PixelTrigger.app`。

## 系统要求

- macOS 11 或更高
- 需要屏幕录制 + 辅助功能权限

## 支持

如果这个工具帮到了你，欢迎在 App 内点击右上角的爱心按钮扫码打赏。

## License

MIT
