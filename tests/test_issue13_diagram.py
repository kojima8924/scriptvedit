# -*- coding: utf-8 -*-
"""issue #13 P2-6: diagram テンプレートの SVG 属性注入対策のテスト

- fill 等のユーザー指定値に注入文字列を渡すと ValueError で拒否されること
- テンプレートが innerHTML への文字列連結を使わず DOM API で構築していること
- 正常系の色・数値・アニメ指定が従来どおり通ること
"""
import os

import pytest

from scriptvedit import (
    diagram, circle, rect, arrow, label, spotlight,
)

SIZE = (1280, 720)  # Project 非依存で diagram() を呼ぶための明示サイズ


def _tpl_path():
    import scriptvedit
    return os.path.join(os.path.dirname(os.path.abspath(scriptvedit.__file__)),
                        "templates", "diagram_svg.html")


# --- 注入文字列の拒否 ---

INJECTION = '"><img src=x onerror=window.__pwned=1>'


def test_fill_injection_rejected():
    """fill への注入文字列は ValueError"""
    with pytest.raises(ValueError, match="fill"):
        diagram([circle(0.5, 0.5, 0.1, fill=INJECTION)], size=SIZE)


def test_stroke_injection_rejected():
    """stroke への注入文字列は ValueError"""
    with pytest.raises(ValueError, match="stroke"):
        diagram([rect(0.1, 0.1, 0.3, 0.2, stroke=INJECTION)], size=SIZE)


def test_fill_javascript_url_rejected():
    """javascript: や url() 形式の色は拒否"""
    with pytest.raises(ValueError):
        diagram([circle(0.5, 0.5, 0.1, fill="javascript:alert(1)")], size=SIZE)
    with pytest.raises(ValueError):
        diagram([circle(0.5, 0.5, 0.1, fill="url(#evil)")], size=SIZE)


def test_number_injection_rejected():
    """数値属性への文字列注入は ValueError"""
    with pytest.raises(ValueError, match="strokeWidth"):
        diagram([circle(0.5, 0.5, 0.1, strokeWidth='2" onload="x')], size=SIZE)
    with pytest.raises(ValueError, match="fontSize"):
        diagram([label(0.5, 0.5, "a", fontSize=INJECTION)], size=SIZE)
    with pytest.raises(ValueError, match=r"\bx\b"):
        diagram([circle(INJECTION, 0.5, 0.1)], size=SIZE)


def test_unknown_attribute_rejected():
    """想定外の属性名（onerror 等）は ValueError"""
    with pytest.raises(ValueError, match="onerror"):
        diagram([circle(0.5, 0.5, 0.1, onerror="alert(1)")], size=SIZE)


def test_unknown_type_rejected():
    """type の whitelist 外は ValueError"""
    with pytest.raises(ValueError, match="type"):
        diagram([{"type": "script", "x": 0, "y": 0}], size=SIZE)


def test_align_injection_rejected():
    """align の列挙値外は ValueError"""
    with pytest.raises(ValueError, match="align"):
        diagram([label(0.5, 0.5, "a", align=INJECTION)], size=SIZE)


def test_animation_dict_injection_rejected():
    """from/to アニメ辞書の中身も数値のみ許可"""
    with pytest.raises(ValueError):
        diagram([circle({"from": INJECTION, "to": 1.0}, 0.5, 0.1)], size=SIZE)
    with pytest.raises(ValueError):
        diagram([circle({"from": 0.0, "to": 1.0, "evil": 1}, 0.5, 0.1)],
                size=SIZE)


def test_non_dict_object_rejected():
    """辞書以外のオブジェクト定義は TypeError"""
    with pytest.raises(TypeError):
        diagram(["<script>alert(1)</script>"], size=SIZE)


def test_text_non_string_rejected():
    """text は文字列のみ"""
    with pytest.raises(TypeError, match="text"):
        diagram([label(0.5, 0.5, ["not", "str"])], size=SIZE)


# --- テンプレートが innerHTML 連結を使っていないこと ---

def test_template_uses_dom_api_not_innerhtml():
    """diagram_svg.html は createElementNS/setAttribute/textContent で構築する"""
    with open(_tpl_path(), encoding="utf-8") as f:
        src = f.read()
    # プロパティとしての .innerHTML 使用が無いこと（コメント中の言及は許容）
    assert ".innerHTML" not in src
    assert "createElementNS" in src
    assert "setAttribute" in src
    assert "textContent" in src


def test_text_content_allows_markup_like_string():
    """text の内容は textContent 経由なのでマークアップ風文字列も許可される。
    データにはそのまま残るが、テンプレートが文字列連結しないため実行されない。"""
    d = diagram([label(0.5, 0.5, INJECTION)], size=SIZE)
    assert d._web_data["objects"][0]["text"] == INJECTION


# --- 正常系（従来どおり通ること） ---

def test_valid_diagram_passes():
    """test21 相当の正常系がそのまま通る"""
    d = diagram([
        rect(0.05, 0.1, 0.4, 0.25, rx=0.02, fill="none",
             stroke="#ffffff", strokeWidth=3),
        label(0.25, 0.22, "Step 1", fill="#ffffff", fontSize=42),
        circle(0.7, 0.3, 0.06, fill="#ff6644", stroke="#ffffff",
               strokeWidth=2, opacity={"from": 0.0, "to": 1.0}),
        arrow(0.45, 0.22, {"from": 0.45, "to": 0.62}, 0.3,
              stroke="#ffcc00", strokeWidth=4),
        spotlight(0.5, 0.7, 0.2, dim=0.5),
        label(0.5, 0.7, "Focus!", fill="#ffff00", fontSize=48,
              stroke="#000000", strokeWidth=2, align="middle"),
    ], duration=3.0, size=SIZE)
    assert d.media_type == "web"
    assert len(d._web_data["objects"]) == 6


@pytest.mark.parametrize("color", [
    "red", "none", "white", "transparent",
    "#fff", "#ffcc00", "#ffcc0080", "#f0f8",
    "rgb(255, 0, 0)", "rgba(0,0,0,0.5)",
    "hsl(120, 50%, 50%)", "hsla(120, 50%, 50%, 0.5)",
])
def test_valid_colors_accepted(color):
    """CSS色名 / #hex / rgb() / hsl() は従来どおり通る"""
    d = diagram([circle(0.5, 0.5, 0.1, fill=color, stroke=color)], size=SIZE)
    assert d._web_data["objects"][0]["fill"] == color


@pytest.mark.parametrize("value", [0, 1, 0.5, -0.2, {"from": 0.0, "to": 1.0}])
def test_valid_numbers_accepted(value):
    """数値と from/to アニメ辞書は従来どおり通る"""
    d = diagram([circle(value, 0.5, 0.1)], size=SIZE)
    assert d._web_data["objects"][0]["x"] == value
