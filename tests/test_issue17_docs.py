# -*- coding: utf-8 -*-
"""issue #17: manifest・ドキュメントと実装の整合テスト

machine-readable マニフェスト（describe）が無効な DSL を案内していないこと、
CLAUDE.md の件数記載が describe の実測とずれていないことを検証する。
"""
import json
import os
import re
import subprocess
import sys

import pytest

from scriptvedit import Project, describe

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _project_layer_cache_values():
    """実装側（project.py の検証タプル）から layer cache の許可値を抽出する。

    許可値の正は Project.layer の検証コードそのもの。名前付き定数が無いため
    ソースをパースして取り出す（二重管理を防ぐガード）。
    """
    src_path = os.path.join(_ROOT, "src", "scriptvedit", "project.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"if\s+cache\s+not\s+in\s+\(([^)]*)\)", src)
    assert m, "project.py に cache の検証タプルが見つからない"
    return sorted(v.strip().strip("'\"") for v in m.group(1).split(",") if v.strip())


def test_manifest_layer_cache_enum_matches_implementation():
    """manifest の layer_cache enum == 実装（Project.layer 検証タプル）の許可値"""
    manifest_enum = sorted(describe()["enums"]["layer_cache"])
    impl_enum = _project_layer_cache_values()
    assert manifest_enum == impl_enum, (
        f"manifest={manifest_enum} と実装={impl_enum} がずれている")


def test_layer_cache_enum_values_accepted_by_implementation():
    """manifest の enum 値は実際に Project.layer が受理し、enum 外は拒否する"""
    for val in describe()["enums"]["layer_cache"]:
        p = Project()
        p.layer("dummy_layer.py", cache=val)  # 受理される（検証は即時）
    with pytest.raises(ValueError):
        Project().layer("dummy_layer.py", cache="on")


def test_manifest_has_no_cache_on():
    """manifest 全体に存在しない cache='on' の案内が現れない"""
    text = json.dumps(describe(), ensure_ascii=False)
    assert "cache='on'" not in text
    assert 'cache="on"' not in text
    assert "cache=\\\"on\\\"" not in text


def test_manifest_until_examples_use_anchor_suffix():
    """usage.dsl / examples がサフィックス無しの .until('intro') を案内しない。

    time(name='intro') が生成するアンカーは intro.start / intro.end のみ。
    """
    text = json.dumps(describe(), ensure_ascii=False)
    for m in re.finditer(r"\.until\(\s*['\"]([^'\"]+)['\"]", text):
        name = m.group(1)
        assert name.endswith(".start") or name.endswith(".end"), (
            f"manifest がサフィックス無しの until({name!r}) を案内している"
            "（intro.start / intro.end を使うこと）")


def test_manifest_show_not_described_as_sequential():
    """show() を「順次配置」と説明しない（実装は _advance=False の並行表示）"""
    text = json.dumps(describe(), ensure_ascii=False)
    assert "順次配置" not in text


def test_claude_md_counts_match_describe():
    """CLAUDE.md に記載の effects/audio_effects/factories 等の件数が describe と一致。

    他テストがプロセス内でプラグインを登録すると describe() の件数が変わるため、
    素の環境の件数をサブプロセスの `python -m scriptvedit describe` で取得する。
    """
    out = subprocess.run(
        [sys.executable, "-m", "scriptvedit", "describe"],
        capture_output=True, text=True, encoding="utf-8", cwd=_ROOT, check=True)
    d = json.loads(out.stdout)
    claude_md = os.path.join(_ROOT, "CLAUDE.md")
    with open(claude_md, encoding="utf-8") as f:
        text = f.read()
    checked = 0
    for key in ("effects", "transforms", "audio_effects", "factories",
                "objects", "object_methods", "project_methods", "expr",
                "plugins"):
        m = re.search(r"`%s`\((\d+)\)" % re.escape(key), text)
        if m is None:
            continue  # 記載が無ければ件数ずれも起きない
        checked += 1
        assert int(m.group(1)) == len(d[key]), (
            f"CLAUDE.md の `{key}`({m.group(1)}) が describe の実測"
            f"（{len(d[key])}）とずれている。CLAUDE.md を更新すること")
    # 監査対象の3種（effects/audio_effects/factories）は必ず記載・検証されること
    for key in ("effects", "audio_effects", "factories"):
        assert re.search(r"`%s`\(\d+\)" % re.escape(key), text), (
            f"CLAUDE.md に `{key}`(N) の記載が見つからない")
    assert checked >= 3
