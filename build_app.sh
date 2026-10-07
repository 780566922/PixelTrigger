#!/usr/bin/env bash
#
# PixelTrigger 一键打包脚本
#
# 用法：
#   ./build_app.sh              # 完整打包 -> dist/PixelTrigger.app
#   ./build_app.sh --dmg        # 打包并额外生成 DMG 安装镜像
#
# 背景说明
# --------
# 本机可用的 Python 有两个问题，必须规避后才能用 py2app 打包：
#
#   1. /usr/bin/python3（CommandLineTools 3.9）的 Tcl/Tk 组件与 macOS 15.7
#      不兼容，import _tkinter 后调用 create() 会直接 SIGABRT
#      （报 "macOS 15 (1507) or later required"），py2app 的 tkinter recipe
#      探测 Tk 版本时必然崩溃。
#
#   2. uv / python-build-standalone 版Python 是静态链接构建，仅 _tkinter
#      保留为动态模块，且 stdlib 位于编译期前缀 /install。py2app 打包后
#      解释器找不到 lib/pythonX.Y 锚点，无法完成自举。
#
# 因此本脚本使用 uv 管理的 Python 3.12（Tk 9.0 可用），并在打包后
# 补上 Contents/MacOS/lib 符号链接，使解释器能定位到 Resources/lib 下的 stdlib。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${PROJECT_DIR}/.build"
VENV_DIR="${BUILD_DIR}/venv"
APP_NAME="PixelTrigger"
MAKE_DMG=0

[[ "${1:-}" == "--dmg" ]] && MAKE_DMG=1

# uv 管理的 Python（Tk 9.0，py2app 可用）
UV_PYTHON="/Users/youwei/.local/bin/python3.12"
[[ -x "${UV_PYTHON}" ]] || UV_PYTHON="$(command -v python3.12)"

if [[ -z "${UV_PYTHON}" || ! -x "${UV_PYTHON}" ]]; then
  echo "错误：找不到可用的 python3.12" >&2
  exit 1
fi

echo "==> 使用 Python: ${UV_PYTHON} ($(${UV_PYTHON} -V 2>&1))"

# ---------------------------------------------------------------- venv
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "==> 创建构建虚拟环境"
  "${UV_PYTHON}" -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip -q
fi

echo "==> 安装打包依赖"
"${VENV_DIR}/bin/python" -m pip install -q \
  py2app Pillow pyobjc-framework-Quartz pyobjc-framework-ApplicationServices

# ------------------------------------------------------- py2app 兼容补丁
# uv 版 Python 把 zlib 静态链接进解释器（无 __file__），而 py2app 硬编码要
# 拷贝该文件；tkinter recipe 又用 sys.prefix（venv 路径）而非 base_prefix
# 查找 Tcl/Tk，导致两者都找不到。以下补丁让 recipe 兼容静态链接发行版。
echo "==> 应用 py2app 兼容补丁"
"${VENV_DIR}/bin/python" - <<'PYEOF'
import re, pathlib, sysconfig

sp = pathlib.Path(sysconfig.get_paths()["purelib"])

# --- 补丁 1：build_app.py 跳过无 __file__ 的 zlib
ba = sp / "py2app" / "build_app.py"
src = ba.read_text()
old = "            self.copy_file(zlib.__file__, os.path.dirname(arcdir))"
new = ("            zf = getattr(zlib, \"__file__\", None)\n"
       "            if zf and os.path.exists(zf):\n"
       "                self.copy_file(zf, os.path.dirname(arcdir))")
if old in src:
    ba.write_text(src.replace(old, new))
    print("    patched build_app.py (zlib)")
else:
    print("    build_app.py already patched")

# --- 补丁 2：tkinter recipe 用 base_prefix 查找，并附带 @rpath 引用的 dylib
tk = sp / "py2app" / "recipes" / "tkinter.py"
src = tk.read_text()
if "base_prefix" in src:
    print("    tkinter recipe already patched")
else:
    src = src.replace(
        "    prefix = sys.prefix if not hasattr(sys, \"real_prefix\") else sys.real_prefix",
        "    prefix = getattr(sys, \"base_prefix\", None) or sys.prefix",
    )
    src = src.replace("    for fn in os.listdir(lib):",
                      "    for fn in sorted(os.listdir(lib)):")
    src = src.replace(
        '    return {\n        "resources": [("lib", paths)],',
        '    dylibs = [os.path.join(lib, fn) for fn in sorted(os.listdir(lib))\n'
        '              if fn.startswith("libtcl") or fn.startswith("libtk")]\n\n'
        '    return {\n        "resources": [("lib", paths + dylibs)],',
    )
    tk.write_text(src)
    print("    patched recipes/tkinter.py")
PYEOF

# ------------------------------------------------------------- 打包
# 构建在临时目录中进行：py2app 会在 build/ 下产生大量中间文件并反复清理，
# 在版本库目录内构建既拖慢速度，也会与工作区的批量删除保护冲突。
# 最终只把成品 .app 复制回项目 dist/。
STAGE="$(mktemp -d /tmp/pt-build.XXXXXX)"
trap 'rm -rf "${STAGE}"' EXIT
cp "${PROJECT_DIR}/color_watcher.py" "${PROJECT_DIR}/platform_backend.py" \
   "${PROJECT_DIR}/setup.py" \
   "${PROJECT_DIR}/donation.png" "${PROJECT_DIR}/icon.icns" "${STAGE}/"

echo "==> 运行 py2app（构建目录 ${STAGE}）"
cd "${STAGE}"
"${VENV_DIR}/bin/python" setup.py py2app

BUILT_APP="${STAGE}/dist/${APP_NAME}.app"
[[ -d "${BUILT_APP}" ]] || { echo "错误：未生成 ${BUILT_APP}" >&2; exit 1; }

mkdir -p "${PROJECT_DIR}/dist"
APP="${PROJECT_DIR}/dist/${APP_NAME}.app"
# 用 ditto 增量同步而非 rm -rf + cp -R：既更快，也避免大批量删除操作
ditto "${BUILT_APP}" "${APP}"

# --------------------------------------------------- 关键修复：lib 锚点
# 解释器启动时在自身所在目录查找 lib/pythonX.Y 作为 stdlib 锚点；py2app 把
# stdlib 放在 Contents/Resources/lib 下，两者不相邻，必须显式建立符号链接，
# 否则启动时报 ModuleNotFoundError: No module named 'encodings'。
echo "==> 补充 stdlib 定位锚点"
ln -sfn ../Resources/lib "${APP}/Contents/MacOS/lib"

# --------------------------------------------------------------- 验证
# 注意：必须在签名前完成验证，且验证进程不能写入字节码——否则 __pycache__
# 会在签名之后落盘，破坏 bundle 的 resource seal，导致 Gatekeeper 拒绝。
echo "==> 验证产物（只读，不写入字节码）"
"${VENV_DIR}/bin/python" - "${APP}" <<'PYEOF'
import subprocess, sys
app = sys.argv[1]
exe = f"{app}/Contents/MacOS/python"
probe = (
    "import tkinter, PIL.ImageTk, Quartz, objc, json, subprocess, threading;"
    "from ApplicationServices import AXIsProcessTrusted;"
    "r=tkinter.Tk();print('RUNTIME_OK');r.destroy()"
)
env = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/Users/youwei",
    "PYTHONDONTWRITEBYTECODE": "1",
}
res = subprocess.run([exe, "-B", "-c", probe], capture_output=True, text=True,
                     env=env, timeout=120)
if "RUNTIME_OK" in res.stdout:
    print("    [OK] 运行时自举 + GUI + 全部关键模块导入通过")
else:
    print("    [FAIL]", (res.stdout + res.stderr)[-600:])
    sys.exit(1)
PYEOF

# 验证已通过，最后再签名：签名动作必须收尾，否则任何一次字节码写入
# 都会让 resource seal 失效。
echo "==> 签名（ad-hoc）"
codesign --force --deep --sign - "${APP}" 2>/dev/null
codesign --verify --deep --strict "${APP}" && echo "    [OK] 代码签名校验通过"

SIZE="$(du -sh "${APP}" | cut -f1)"
echo ""
echo "构建完成: ${APP} (${SIZE})"

# --------------------------------------------------------------- DMG
if [[ "${MAKE_DMG}" == "1" ]]; then
  # 从 setup.py 解析 VERSION，保证 DMG 文件名与 .app 内版本号始终一致，
  # 避免升级版本时漏改其中一处。
  APP_VERSION="$("${VENV_DIR}/bin/python" -c "import ast;print(next(n.value.value for n in ast.walk(ast.parse(open('${PROJECT_DIR}/setup.py').read())) if isinstance(n,ast.Assign) and getattr(n.targets[0],'id','')=='VERSION'))")"
  DMG="${PROJECT_DIR}/dist/${APP_NAME}-${APP_VERSION}.dmg"
  echo "==> 生成 DMG"
  DMG_STAGE="$(mktemp -d /tmp/pt-dmg.XXXXXX)"
  # 必须用 cp -R：ditto 在目标已存在时会展开 bundle 内容，丢失 .app 目录层级
  cp -R "${APP}" "${DMG_STAGE}/"
  ln -s /Applications "${DMG_STAGE}/Applications"
  # 直接覆盖写入 DMG（不先删除），避免大批量删除操作
  hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_STAGE}" \
                -ov -format UDZO "${DMG}" -quiet
  rm -rf "${DMG_STAGE}"
  # 校验 DMG 内确实包含完整的 .app（防止 bundle 层级被压平）
  if hdiutil attach -nobrowse -readonly "${DMG}" >/dev/null 2>&1; then
    VOL="/Volumes/${APP_NAME}"
    if [[ -d "${VOL}/${APP_NAME}.app" ]]; then
      echo "    [OK] DMG 内 ${APP_NAME}.app 结构完整"
    else
      echo "    [FAIL] DMG 内缺少 ${APP_NAME}.app，请检查打包逻辑"; exit 1
    fi
    hdiutil detach "${VOL}" >/dev/null 2>&1 || true
  fi
  echo "    DMG: ${DMG}"
fi