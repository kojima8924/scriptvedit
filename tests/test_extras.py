# -*- coding: utf-8 -*-
"""pyproject.toml の extras と各機能モジュールの実依存の整合性検証（issue #13 P1-5）

過去に [morph] に tqdm、[beat] に scipy、[tools] に Pillow が無く、
案内どおり extra を入れてもモジュールが ImportError になる事故があった。
各モジュールの top-level サードパーティ import を AST で抽出し、
対応する extra が全て宣言していることを静的に検証する。
"""
import ast
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

# import名 → pip配布名
_PIP_NAMES = {
    "numpy": "numpy",
    "scipy": "scipy",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "tqdm": "tqdm",
    "playwright": "playwright",
    "edge_tts": "edge-tts",
}

# 機能モジュール → 対応する extra
_MODULE_EXTRAS = {
    "morph.py": "morph",
    "beat.py": "beat",
    "testkit.py": "tools",
    "web.py": "web",
    "tts.py": "tts",
}


def _load_extras():
    """pyproject.toml の [project.optional-dependencies] を読む
    （Python 3.10 に tomllib が無いため素朴にパースする）"""
    path = os.path.join(_ROOT, "pyproject.toml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    section = re.search(
        r"\[project\.optional-dependencies\](.*?)(?:\n\[|\Z)", text, re.S)
    assert section, "optional-dependencies セクションが見つからない"
    extras = {}
    for m in re.finditer(r"^(\w+)\s*=\s*\[(.*?)\]", section.group(1), re.M | re.S):
        deps = re.findall(r'"([^"]+)"', m.group(2))
        # バージョン指定を除いた配布名に正規化
        extras[m.group(1)] = {re.split(r"[<>=!\[; ]", d)[0] for d in deps}
    return extras


def _top_level_third_party_imports(py_path):
    """モジュール直下（try/except外）の import からサードパーティ名を抽出"""
    with open(py_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in tree.body:  # top-level のみ（関数内・try内の遅延importは対象外）
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return {n for n in names if n in _PIP_NAMES}


@pytest.mark.parametrize("module,extra", sorted(_MODULE_EXTRAS.items()))
def test_extra_covers_module_imports(module, extra):
    """extra を入れれば対応モジュールが import できる（依存漏れがない）"""
    extras = _load_extras()
    assert extra in extras, f"extra [{extra}] が宣言されていない"
    py_path = os.path.join(_ROOT, "src", "scriptvedit", module)
    needed = {_PIP_NAMES[n] for n in _top_level_third_party_imports(py_path)}
    missing = needed - extras[extra]
    assert not missing, (
        f"[{extra}] に不足している依存: {sorted(missing)} "
        f"（{module} が top-level で import している）")


def test_all_extra_is_superset():
    """[all] は他の全 extra の和集合を含む"""
    extras = _load_extras()
    union = set()
    for name, deps in extras.items():
        if name != "all":
            union |= deps
    missing = union - extras.get("all", set())
    assert not missing, f"[all] に不足: {sorted(missing)}"
