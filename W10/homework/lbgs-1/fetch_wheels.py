"""pip 连不上 PyPI 时的绕道下载器：用 urllib 直接取 wheel。

为什么需要它：本机 `pip install` / `curl` / `Invoke-WebRequest` 都在 TLS 握手处失败
（`基础连接已经关闭: 接收时发生错误`），但 Python 自带的 `urllib` + `ssl` 能正常握手。
于是用本脚本把 wheel 拉到本地目录，再用
    python -m pip install --no-index --find-links <目录> matplotlib
离线安装。

用法：
    python fetch_wheels.py matplotlib contourpy cycler fonttools kiwisolver \
        pyparsing packaging python-dateutil -d .tmp\\whl

只处理两种 wheel：`py3-none-any`（纯 Python）和 `cp312-cp312-win_amd64`（本机 CPython 3.12 / Win64）。
"""

import json
import sys
import urllib.request
from pathlib import Path

PY_TAG = "cp312"
PLAT = "win_amd64"
UA = {"User-Agent": "pip/26.2.1"}


def get_json(name):
    req = urllib.request.Request(f"https://pypi.org/pypi/{name}/json", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rank(filename):
    if filename.endswith("py3-none-any.whl") or filename.endswith("py2.py3-none-any.whl"):
        return 0
    if f"{PY_TAG}-{PY_TAG}-{PLAT}" in filename:
        return 1
    return -1


def pick(data):
    """挑一个本机能装的 wheel：优先 cp312-win_amd64，其次 py3-none-any。"""
    version = data["info"]["version"]
    files = [
        f for f in data["urls"]
        if f["filename"].endswith(".whl") and f["filename"].split("-")[1] == version
    ]
    ranked = sorted(files, key=lambda f: rank(f["filename"]), reverse=True)
    return ranked[0] if ranked and rank(ranked[0]["filename"]) >= 0 else None


def deps_of(data):
    """从 requires_dist 里挑必装依赖（跳过 extra 与非本平台的标记）。"""
    out = []
    for spec in data["info"].get("requires_dist") or []:
        if "extra ==" in spec:
            continue
        name = spec.split(";")[0]
        for sep in ("(", ">", "<", "=", "!", "~"):
            name = name.split(sep)[0]
        name = name.strip()
        if name:
            out.append(name)
    return out


def main():
    args = sys.argv[1:]
    if "-d" not in args:
        print("用法：python fetch_wheels.py 包名... -d 目录")
        return 1
    i = args.index("-d")
    dest, wanted = Path(args[i + 1]), args[:i]
    dest.mkdir(parents=True, exist_ok=True)

    queue, seen = list(wanted), set()
    while queue:
        name = queue.pop(0)
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)

        data = get_json(name)
        picked = pick(data)
        if picked is None:
            print(f"[跳过] {name} {data['info']['version']}：没有 cp312/win_amd64 或 py3 wheel")
            continue

        target = dest / picked["filename"]
        if target.exists():
            print(f"[已有] {picked['filename']}")
        else:
            print(f"[下载] {picked['filename']}  {picked['size'] / 1024 / 1024:.1f} MB")
            req = urllib.request.Request(picked["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(target, "wb") as f:
                f.write(r.read())
        queue.extend(deps_of(data))

    print("完成，目录：", dest.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
