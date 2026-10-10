"""把 setup.py 里的 VERSION 导出成 version.txt，供界面显示版本号。

`setup.py` 的 `VERSION` 依然是**唯一版本源**；本脚本只做「导出」：
在打包前生成 version.txt，随产物一起分发，运行期由
`color_watcher.get_app_version()` 读取。

用法（打包前执行一次）：
    python gen_version.py
"""

import ast
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def read_version():
    """从 setup.py 解析 VERSION 字面量（与 build_app.sh 同一口径）。"""
    try:
        src = (HERE / "setup.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Assign) and \
               getattr(node.targets[0], "id", "") == "VERSION":
                return str(getattr(node.value, "value", "") or "").strip()
    except Exception:
        pass
    return ""


def main():
    version = read_version() or "unknown"
    try:
        (HERE / "version.txt").write_text(version + "\n", encoding="utf-8")
    except Exception as e:
        # 版本标识只是锦上添花，绝不能因此中断构建
        print(f"gen_version: 写入 version.txt 失败（已忽略）：{e}")
        return
    print(f"gen_version: version.txt = {version}")


if __name__ == "__main__":
    main()
