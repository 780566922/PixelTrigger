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
- 外观自动跟随：系统浅色/深色切换后 1 秒内自动换肤，无需重启

## 下载安装

1. 从 Releases 页面下载最新的 `PixelTrigger-1.0.0.dmg`（或 `PixelTrigger.app.zip`）
2. 打开 DMG，把 PixelTrigger 拖到「应用程序」文件夹；或解压 zip 后手动拖入
3. 第一次打开：右键点击 App，选择「打开」，弹窗里再点「打开」
4. 授权：
   - 首次点击「开始监控」或右上角权限红点时，应用会**主动弹出系统授权框**，
     点「允许」即可（屏幕录制 + 辅助功能各弹一次）；
   - 也可手动：系统设置 → 隐私与安全性 → 屏幕录制 / 辅助功能，勾选 PixelTrigger
5. 完全退出 App（Cmd+Q）再重新打开

> **关于「设置里没有 PixelTrigger 条目」**：macOS 的规则是——应用必须主动调用
> 权限请求 API，系统才会弹出授权框、并在设置里生成该应用的条目。本应用已支持：
> 点右上角红点或「开始监控」时会主动请求权限，弹框出现后设置里就会有条目了。
> 若仍未出现，先确认 App 已拖到「应用程序」目录（见下方提示），再点一次红点。

> 未做公证（notarization），首次打开需按上述步骤手动放行。若提示"无法验证开发者"，
> 可在终端执行 `xattr -cr /Applications/PixelTrigger.app` 后重试。

> **务必拖到「应用程序」后再运行**：从 DMG 磁盘映像（挂载卷 `/Volumes/...`）
> **直接双击运行**是权限红点不变绿的最常见原因。DMG 卷是只读的、挂载路径也不稳定
> （重复挂载会变成 `/Volumes/PixelTrigger 1` 等），系统无法给它稳定记录权限授权。
> 请把 App 拖到「应用程序」文件夹，再从那里打开。

> **更新应用后权限可能失效**：本应用使用 ad-hoc 签名（无开发者证书），每次更新后
> 二进制签名会变化，macOS 会把旧的辅助功能/屏幕录制授权视为「不再匹配」，
> 表现为系统设置里仍显示已勾选、但应用右上角红点不变绿。
> 解决办法：在系统设置里**取消勾选 → 重新勾选**一次即可（无需卸载）。

## 使用方法

1. 打开 PixelTrigger
2. 选择「色系匹配」或「精准容差」模式
3. 点击「点击框选屏幕区域」，框选监控区域
4. 选择触发方式（滚动翻页 / 触发按键）
5. 点击「开始监控」

- 日志区保留最近 2000 行，超出后自动丢弃最旧的，长时间运行不会持续吃内存

## 外观跟随系统

应用每1 秒读一次系统外观设置（`AppleInterfaceStyle`，走 CFPreferences进程内读取），
与当前主题不一致就换肤并重建界面。

换肤是重建整棵控件树，不是改颜色变量 —— Tk 的 `bg`/`fg` 在控件构造时就已固化，
事后改模块常量对已存在的控件无效。因此重建时会先把当前状态整体快照再还原，
以下内容跨切换完整保留：

- 所有输入框与下拉参数、色系/容差/精准RGB、按键组合
- 面板显隐（识别模式、触发方式、按键动作三组联动）
- 运行状态：监控是否在跑、开始/停止按钮可用性、状态灯颜色、冷却剩余
- 日志区全部历史、区域预览图

两点行为说明：

- 主题切换**不写入配置文件**，只影响显示；退出时「参数是否修改」的判定基线
  保持为启动时的快照，所以改过的参数该提示保存时依然会提示。
- 捐赠弹窗、按键捕获框、屏幕框选与取色器（全屏覆盖层）打开期间会**推迟**换肤，
  关闭后自动补上。这是为了避免重建界面打断正在进行的交互。

## 从源码运行

安装依赖：`pip3 install --user Pillow pyobjc-framework-Quartz`

运行：`python3 color_watcher.py`

## 自行打包为 .app

推荐使用仓库内置的一键打包脚本：

```bash
./build_app.sh# 生成 dist/PixelTrigger.app
./build_app.sh --dmg         # 同时生成 dist/PixelTrigger-1.0.0.dmg
```

脚本会自动完成：创建隔离的构建虚拟环境、安装依赖、应用 py2app 兼容补丁、
打包、补 stdlib 锚点、运行时自举验证、ad-hoc 签名。

> **不要用 `/usr/bin/python3` 打包。** CommandLineTools 自带的 Python 3.9 的
> Tcl/Tk 与 macOS 15.7 不兼容，py2app 探测 Tk 版本时会直接崩溃。脚本使用的是
> `python3.12`（Tk 9.0）。

### 手动打包

```bash
python3.12 -m venv .build/venv
.build/venv/bin/pip install py2app Pillow \
    pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
.build/venv/bin/python setup.py py2app
ln -sfn ../Resources/lib dist/PixelTrigger.app/Contents/MacOS/lib
codesign --force --deep --sign - dist/PixelTrigger.app
```

产物在 `dist/PixelTrigger.app`。

## 系统要求

- macOS 11 或更高
- 需要屏幕录制 + 辅助功能权限

## 支持

如果这个工具帮到了你，欢迎在 App 内点击右上角的爱心按钮扫码打赏。

## License

MIT
