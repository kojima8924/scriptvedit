# -*- coding: utf-8 -*-

import subprocess
import os
import re
import sys
import json
import hashlib
import math as _math
import warnings
import builtins as _builtins
import time as _time
import difflib as _difflib
import shutil as _shutil
import concurrent.futures as _futures
import inspect as _inspect


# --- テンプレートラッパー ---

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _template_path(name):
    """テンプレートHTMLの絶対パスを返す（存在チェック付き）"""
    path = os.path.join(_TEMPLATES_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"テンプレートが見つかりません: {path}\n"
            f"templates/ ディレクトリにファイルを配置してください。")
    return path


def _data_hash(data):
    """dataのJSON文字列からsha1先頭8桁のハッシュを返す"""
    s = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def _resolve_size(size):
    """size省略時はProject._currentのwidth/heightを使う"""
    if size is not None:
        return size
    proj = Project._current
    if proj is None:
        raise RuntimeError(
            "size省略時はアクティブなProjectが必要です。"
            "Project()を作成してからsubtitle/bubble/diagram等を呼んでください。")
    return (proj.width, proj.height)


def subtitle(text, who=None, duration=2.5, *, style=None, size=None,
             name=None, debug_frames=False, deps=None):
    """字幕テンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("subtitle.html")
    data = {"text": text, "who": who, "style": style or {}}
    if name is None:
        name = f"subtitle_{_data_hash(data)}"
    kw = dict(duration=duration, size=size, data=data,
              name=name, debug_frames=debug_frames)
    if deps is not None:
        kw["deps"] = deps
    return Object(tpl, **kw)


def subtitle_box(text, duration=2.5, *, style=None, size=None,
                 name=None, debug_frames=False, deps=None):
    """ボックス型字幕テンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("subtitle_box.html")
    data = {"text": text, "style": style or {}}
    if name is None:
        name = f"subtitle_box_{_data_hash(data)}"
    kw = dict(duration=duration, size=size, data=data,
              name=name, debug_frames=debug_frames)
    if deps is not None:
        kw["deps"] = deps
    return Object(tpl, **kw)


def bubble(text, duration=2.5, *, anchor=None, pos=None, box=None,
           style=None, size=None, name=None, debug_frames=False, deps=None):
    """吹き出しテンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("bubble.html")
    anch = {"x": anchor[0], "y": anchor[1]} if anchor else {"x": 0.2, "y": 0.7}
    p = {"x": pos[0], "y": pos[1]} if pos else {"x": 0.25, "y": 0.3}
    sz = {"w": box[0], "h": box[1]} if box else {"w": 0.45, "h": 0.2}
    data = {"text": text, "anchor": anch, "pos": p, "size": sz,
            "style": style or {}}
    if name is None:
        name = f"bubble_{_data_hash(data)}"
    kw = dict(duration=duration, size=size, data=data,
              name=name, debug_frames=debug_frames)
    if deps is not None:
        kw["deps"] = deps
    return Object(tpl, **kw)


def diagram(objects, duration=3.0, *, style=None, size=None,
            name=None, debug_frames=False, deps=None):
    """SVG図解テンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("diagram_svg.html")
    data = {"objects": objects, "style": style or {}}
    if name is None:
        name = f"diagram_{_data_hash(data)}"
    kw = dict(duration=duration, size=size, data=data,
              name=name, debug_frames=debug_frames)
    if deps is not None:
        kw["deps"] = deps
    return Object(tpl, **kw)


def slide(html_file, page=None, *, duration=5.0, width=None, height=None,
          name=None, debug_frames=False, deps=None):
    """HTMLスライドを既存のweb Object機構でキャプチャする正式API。

    page省略時: html_file全体を通常のWeb Object（renderFrame(state)による
        アニメーション）としてduration秒キャプチャする（既存のObject(html,...)
        直接呼び出しと同じ）。

    page指定時（複数ページを持つ1つのHTMLをスライドデッキとして扱う規約）:
        キャプチャ直前に以下のJSフックを実行してからduration秒分キャプチャする。
          1. `window.showSlide` 関数があれば `window.showSlide(page)` を呼ぶ。
          2. 無ければ `id="page-<page>"` の要素だけを表示し、他の
             `id^="page-"` 要素は非表示（style.display='none'）にする。
          3. HTML側に `renderFrame(state)` が定義されていなければ、
             自動的にno-op実装を注入する（静止スライドはrenderFrame不要）。
        この規約に沿ったHTMLを用意すれば、1ファイルで複数ページのスライドを
        page番号違いのslide()呼び出しだけで使い分けられる。

    width/height省略時はアクティブなProjectの解像度を使う。
    キャッシュはWeb Objectと同じsignature方式（データ内容が変わればキー変化）。
    """
    if not isinstance(html_file, str):
        raise TypeError(f"slide: html_file はパス文字列で指定してください: {html_file!r}")
    if not os.path.exists(html_file):
        raise FileNotFoundError(f"slide: HTMLファイルが見つかりません: {html_file}")
    if os.path.splitext(html_file)[1].lower() not in (".html", ".htm"):
        raise ValueError(f"slide: .html/.htm ファイルを指定してください: {html_file}")
    _require_number("slide", "duration", duration, 0.01, None)
    proj = Project._current
    if width is None or height is None:
        if proj is None:
            raise RuntimeError(
                "slide: width/height省略時はアクティブなProjectが必要です。"
                "Project()を作成してからslide()を呼んでください。")
    w = int(width) if width is not None else proj.width
    h = int(height) if height is not None else proj.height

    data = {}
    if page is not None:
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            raise ValueError(f"slide: page は0以上の整数で指定してください: {page!r}")
        data[_SLIDE_PAGE_KEY] = page

    if name is None:
        base = os.path.splitext(os.path.basename(html_file))[0]
        name = f"slide_{base}_p{page}" if page is not None else f"slide_{base}"
    kw = dict(duration=float(duration), size=(w, h), data=data, name=name,
              debug_frames=debug_frames)
    if deps is not None:
        kw["deps"] = deps
    return Object(html_file, **kw)


# --- 図形ビルダー ---

def circle(x, y, r, **kw):
    """円オブジェクト定義を返す"""
    return {"type": "circle", "x": x, "y": y, "r": r, **kw}


def rect(x, y, w, h, **kw):
    """矩形オブジェクト定義を返す"""
    return {"type": "rect", "x": x, "y": y, "w": w, "h": h, **kw}


def arrow(x1, y1, x2, y2, **kw):
    """矢印オブジェクト定義を返す"""
    return {"type": "arrow", "x1": x1, "y1": y1, "x2": x2, "y2": y2, **kw}


def label(x, y, text, **kw):
    """テキストラベルオブジェクト定義を返す"""
    return {"type": "text", "x": x, "y": y, "text": text, **kw}


def spotlight(x, y, r, **kw):
    """スポットライト（暗幕くり抜き）オブジェクト定義を返す"""
    return {"type": "spotlight", "x": x, "y": y, "r": r, **kw}


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.objects import Object, _SLIDE_PAGE_KEY
from scriptvedit.project import Project
from scriptvedit.text import text
from scriptvedit.timeline import anchor
from scriptvedit.validate import _require_number
