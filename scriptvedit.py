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

__all__ = [
    # コアクラス
    "Project", "Object", "Transform", "TransformChain", "Effect", "EffectChain",
    "AudioEffect", "AudioEffectChain",
    "VideoView", "AudioView",
    # ファクトリ関数
    "resize", "rotate", "crop", "pad", "blur", "eq",
    "scale", "fade", "move", "morph_to", "rotate_to",
    "move_along", "path_bezier", "throw", "inertia", "look_at", "perlin",
    "explode_to", "assemble_from", "group", "tile",
    "wipe", "zoom", "color_shift", "shake",
    "chroma_key", "vignette", "pixelize", "glow", "lut", "glitch",
    "perspective_warp", "lens", "ken_burns", "drop_shadow", "outline",
    "slideshow", "transition", "video_sequence",
    # 合成・コンポジション
    "mask", "mask_wipe", "opacity", "blend_mode", "rounded", "pip",
    "blur_background_fill", "progress_bar",
    # 時間操作（映像）
    "speed", "reverse", "freeze_frame",
    "again", "afade", "adelete", "delete", "trim", "atrim", "atempo",
    # テキスト・字幕（drawtext/subtitlesベース）
    "text", "typewriter", "counter", "subtitles", "karaoke",
    # オーディオ系
    "duck_under", "loop", "audio_sequence", "sfx", "audio_viz", "voice",
    # 外部モジュール統合（svtts/svbeat/web）
    "narrate", "Narration", "beat_sync", "slide",
    # アンカー/同期
    "anchor", "pause", "scene",
    # Expr
    "Expr", "Const", "Var",
    # 数学関数
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "floor", "ceil", "trunc",
    "log10", "cbrt", "lerp", "clip", "clamp",
    "step", "smoothstep", "mod", "frac", "deg2rad", "rad2deg",
    # 条件分岐・比較
    "if_", "lt", "gt", "lte", "gte", "eq_", "neq",
    "and_", "or_", "not_", "between", "case",
    "sign", "random",
    # Python組み込み互換
    "abs", "min", "max", "round", "pow",
    # 定数
    "PI", "E",
    # DSL糖衣
    "P",
    # イージング関数
    "linear",
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    "ease_in_quint", "ease_out_quint", "ease_in_out_quint",
    "ease_in_sine", "ease_out_sine", "ease_in_out_sine",
    "ease_in_expo", "ease_out_expo", "ease_in_out_expo",
    "ease_in_circ", "ease_out_circ", "ease_in_out_circ",
    "ease_in_back", "ease_out_back", "ease_in_out_back",
    "ease_in_elastic", "ease_out_elastic", "ease_in_out_elastic",
    "ease_in_bounce", "ease_out_bounce", "ease_in_out_bounce",
    "ease_cubic_bezier", "ease_spring", "steps", "apply_easing",
    # シーケンス・キーフレーム
    "phase", "sequence_param", "repeat", "bounce", "alternate", "staircase",
    "keyframes",
    # テンプレートラッパー
    "subtitle", "subtitle_box", "bubble", "diagram",
    # 図形ビルダー
    "circle", "rect", "arrow", "label", "spotlight",
]


# --- Expr（式ビルダー） ---

class Expr:
    """ffmpeg式ビルダー基底クラス"""
    def to_ffmpeg(self, u_expr):
        raise NotImplementedError

    def eval_at(self, u_value):
        """u=u_valueでの数値評価"""
        raise NotImplementedError

    def __add__(self, other):
        return _make_binop("+", self, _to_expr(other))

    def __radd__(self, other):
        return _make_binop("+", _to_expr(other), self)

    def __sub__(self, other):
        return _make_binop("-", self, _to_expr(other))

    def __rsub__(self, other):
        return _make_binop("-", _to_expr(other), self)

    def __mul__(self, other):
        return _make_binop("*", self, _to_expr(other))

    def __rmul__(self, other):
        return _make_binop("*", _to_expr(other), self)

    def __truediv__(self, other):
        return _make_binop("/", self, _to_expr(other))

    def __rtruediv__(self, other):
        return _make_binop("/", _to_expr(other), self)

    def __pow__(self, other):
        return _make_func("pow", [self, _to_expr(other)])

    def __rpow__(self, other):
        return _make_func("pow", [_to_expr(other), self])

    def __neg__(self):
        return _make_unop("-", self)

    def __abs__(self):
        return _make_func("abs", [self])

    def smooth(self):
        """smoothstep: 3t²-2t³"""
        return self * self * (Const(3) - Const(2) * self)

    def invert(self):
        """反転: 1 - self"""
        return Const(1) - self

    def pingpong(self):
        """三角波(0→1→0): |1 - 2*mod(self, 1)|"""
        return Const(1) - _make_func("abs", [Const(2) * _make_func("mod", [self, Const(1)]) - Const(1)])

    def map(self, lo, hi):
        """値をlo〜hiにマッピング: self * (hi - lo) + lo"""
        return self * (_to_expr(hi) - _to_expr(lo)) + _to_expr(lo)

    def clamped(self, lo=0, hi=1):
        """値をlo〜hiにクランプ"""
        return _make_func("clip", [self, _to_expr(lo), _to_expr(hi)])

    def oscillate(self, frequency=1, amplitude=1, offset=0):
        """正弦波: offset + amplitude * sin(self * frequency * 2π)"""
        f = _to_expr(frequency)
        a = _to_expr(amplitude)
        o = _to_expr(offset)
        return o + a * _make_func("sin", [self * f * Const(2 * 3.141592653589793)])

    def sawtooth(self, frequency=1):
        """ノコギリ波: 0→1を周期的に繰り返す"""
        return _make_func("mod", [self * _to_expr(frequency), Const(1)])

    def triangle(self, frequency=1):
        """三角波: 0→1→0を周期的に繰り返す"""
        phase = _make_func("mod", [self * _to_expr(frequency), Const(1)])
        return Const(1) - _make_func("abs", [Const(2) * phase - Const(1)])

    def plot(self, samples=60, height=15, width=60):
        """u=0..1でサンプルしてターミナルにアスキーグラフを表示（デバッグ用）

        matplotlib非依存。self.eval_at(u) をサンプルし、標準出力へ折れ線グラフ
        を描画する。値域は自動スケーリング。描画した文字列を返す。
        """
        if samples < 2:
            raise ValueError("plot: samples は2以上が必要です")
        us = [i / (samples - 1) for i in range(samples)]
        try:
            ys = [float(self.eval_at(u)) for u in us]
        except Exception as exc:
            raise ValueError(
                f"plot: 式を数値評価できません（uのみに依存する式が必要）: {exc}"
            ) from exc
        y_lo = _builtins.min(ys)
        y_hi = _builtins.max(ys)
        span = y_hi - y_lo
        if span < 1e-12:
            # 定数式: 中央に平坦な線を描く
            span = 1.0
            y_lo -= 0.5
        # width列にリサンプリング（samples != width でも桁を揃える）
        cols = width
        grid = [[" "] * cols for _ in range(height)]
        for cx in range(cols):
            u = cx / (cols - 1)
            # 最近傍サンプル
            idx = int(_builtins.round(u * (samples - 1)))
            y = ys[idx]
            norm = (y - y_lo) / span
            row = height - 1 - int(_builtins.round(norm * (height - 1)))
            row = _builtins.min(height - 1, _builtins.max(0, row))
            grid[row][cx] = "*"
        lines = []
        lines.append(f"  {y_hi:+.3f} +" + "-" * cols)
        for r, cells in enumerate(grid):
            lines.append("         |" + "".join(cells))
        lines.append(f"  {y_lo:+.3f} +" + "-" * cols)
        lines.append("         u=0" + " " * (cols - 6) + "u=1")
        out = "\n".join(lines)
        print(out)
        return out


class Const(Expr):
    """定数ノード"""
    def __init__(self, value):
        self.value = value

    def to_ffmpeg(self, u_expr):
        return str(self.value)

    def eval_at(self, u_value):
        return self.value


class Var(Expr):
    """変数ノード"""
    def __init__(self, name):
        self.name = name

    def to_ffmpeg(self, u_expr):
        if self.name == "u":
            return u_expr
        return self.name

    def eval_at(self, u_value):
        if self.name == "u":
            return u_value
        raise ValueError(f"変数 '{self.name}' は数値評価できません")


class _BinOp(Expr):
    """二項演算ノード"""
    def __init__(self, op, left, right):
        self.op = op
        self.left = left
        self.right = right

    def to_ffmpeg(self, u_expr):
        l = self.left.to_ffmpeg(u_expr)
        r = self.right.to_ffmpeg(u_expr)
        return f"({l}{self.op}{r})"

    def eval_at(self, u_value):
        l = self.left.eval_at(u_value)
        r = self.right.eval_at(u_value)
        if self.op == '+': return l + r
        if self.op == '-': return l - r
        if self.op == '*': return l * r
        if self.op == '/': return l / r
        raise ValueError(f"未対応の演算子: {self.op}")


class _UnOp(Expr):
    """単項演算ノード"""
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand

    def to_ffmpeg(self, u_expr):
        x = self.operand.to_ffmpeg(u_expr)
        return f"({self.op}{x})"

    def eval_at(self, u_value):
        x = self.operand.eval_at(u_value)
        if self.op == '-': return -x
        raise ValueError(f"未対応の単項演算子: {self.op}")


class _FuncCall(Expr):
    """関数呼び出しノード"""
    def __init__(self, name, args):
        self.name = name
        self.args = args

    def to_ffmpeg(self, u_expr):
        arg_strs = [a.to_ffmpeg(u_expr) for a in self.args]
        sep = "\\,"
        return f"{self.name}({sep.join(arg_strs)})"

    _EVAL_FUNCS = None

    @classmethod
    def _get_eval_funcs(cls):
        if cls._EVAL_FUNCS is None:
            cls._EVAL_FUNCS = {
                'sin': _math.sin, 'cos': _math.cos, 'tan': _math.tan,
                'asin': _math.asin, 'acos': _math.acos, 'atan': _math.atan,
                'atan2': _math.atan2, 'sinh': _math.sinh, 'cosh': _math.cosh,
                'tanh': _math.tanh, 'exp': _math.exp, 'log': _math.log,
                'sqrt': _math.sqrt, 'floor': _math.floor, 'ceil': _math.ceil,
                'trunc': _math.trunc, 'round': _builtins.round,
                'abs': _builtins.abs, 'pow': _builtins.pow,
                'min': _builtins.min, 'max': _builtins.max,
                'mod': lambda a, b: a % b,
                'clip': lambda v, lo, hi: _builtins.max(lo, _builtins.min(hi, v)),
                'gte': lambda x, e: 1.0 if x >= e else 0.0,
                'lte': lambda x, e: 1.0 if x <= e else 0.0,
                'lt': lambda x, e: 1.0 if x < e else 0.0,
                'gt': lambda x, e: 1.0 if x > e else 0.0,
                'eq': lambda a, b: 1.0 if a == b else 0.0,
                'if': lambda c, t, e: t if c != 0 else e,
                'and': lambda a, b: 1.0 if (a != 0 and b != 0) else 0.0,
                'or': lambda a, b: 1.0 if (a != 0 or b != 0) else 0.0,
                'not': lambda a: 1.0 if a == 0 else 0.0,
                'between': lambda x, lo, hi: 1.0 if lo <= x <= hi else 0.0,
                'sign': lambda x: (1.0 if x > 0 else (-1.0 if x < 0 else 0.0)),
                'random': lambda seed: 0.5,  # eval_at用ダミー（ffmpegランタイムで評価）
                'log10': lambda x: _math.log10(x),
                'cbrt': lambda x: x ** (1/3) if x >= 0 else -((-x) ** (1/3)),
            }
        return cls._EVAL_FUNCS

    def eval_at(self, u_value):
        args = [a.eval_at(u_value) for a in self.args]
        funcs = self._get_eval_funcs()
        if self.name not in funcs:
            raise ValueError(f"eval_at未対応の関数: {self.name}")
        return funcs[self.name](*args)


def _to_expr(x):
    """float/int→Const, Expr→そのまま, それ以外→TypeError"""
    if isinstance(x, Expr):
        return x
    if isinstance(x, (int, float)):
        return Const(x)
    raise TypeError(f"Exprに変換できません: {type(x)}")


_NONFOLDABLE_FUNCS = frozenset({'random'})

def _make_binop(op, left, right):
    """定数畳み込み・恒等式簡約付きBinOp生成"""
    if isinstance(left, Const) and isinstance(right, Const):
        l, r = left.value, right.value
        if op == '+': return Const(l + r)
        if op == '-': return Const(l - r)
        if op == '*': return Const(l * r)
        if op == '/' and r != 0: return Const(l / r)
    if op == '+':
        if isinstance(left, Const) and left.value == 0: return right
        if isinstance(right, Const) and right.value == 0: return left
    elif op == '-':
        if isinstance(right, Const) and right.value == 0: return left
    elif op == '*':
        if isinstance(left, Const) and left.value == 0: return Const(0)
        if isinstance(right, Const) and right.value == 0: return Const(0)
        if isinstance(left, Const) and left.value == 1: return right
        if isinstance(right, Const) and right.value == 1: return left
    elif op == '/':
        if isinstance(right, Const) and right.value == 1: return left
    return _BinOp(op, left, right)

def _make_unop(op, operand):
    """定数畳み込み付きUnOp生成"""
    if isinstance(operand, Const):
        if op == '-': return Const(-operand.value)
    if op == '-' and isinstance(operand, _UnOp) and operand.op == '-':
        return operand.operand
    return _UnOp(op, operand)

def _make_func(name, args):
    """定数畳み込み付きFuncCall生成"""
    if name == 'if' and len(args) == 3 and isinstance(args[0], Const):
        return args[1] if args[0].value != 0 else args[2]
    if name in _NONFOLDABLE_FUNCS:
        return _FuncCall(name, args)
    if all(isinstance(a, Const) for a in args):
        funcs = _FuncCall._get_eval_funcs()
        if name in funcs:
            try:
                vals = [a.value for a in args]
                result = funcs[name](*vals)
                if isinstance(result, (int, float)) and _math.isfinite(result):
                    return Const(result)
            except (ValueError, ZeroDivisionError, OverflowError):
                pass
    return _FuncCall(name, args)


def _resolve_param(param):
    """float→Const, callable→Var('u')で評価してExpr化, Expr→そのまま"""
    if isinstance(param, Expr):
        return param
    if isinstance(param, (int, float)):
        return Const(param)
    if callable(param):
        u = Var("u")
        try:
            result = param(u)
        except TypeError as e:
            raise TypeError(
                "lambda内でmath関数は使えません。scriptveditの関数を使ってください。\n"
                "使用可能: sin, cos, tan, exp, log, sqrt, lerp, clip, abs, min, max, "
                "floor, ceil, smoothstep, step, mod, frac, PI, E"
            ) from e
        return _to_expr(result)
    raise TypeError(f"Effect引数にはfloat, lambda, Exprのいずれかを渡してください: {type(param)}")


# --- 数学関数（Exprラッパー） ---

def sin(x):
    return _make_func("sin", [_to_expr(x)])

def cos(x):
    return _make_func("cos", [_to_expr(x)])

def tan(x):
    return _make_func("tan", [_to_expr(x)])

def asin(x):
    return _make_func("asin", [_to_expr(x)])

def acos(x):
    return _make_func("acos", [_to_expr(x)])

def atan(x):
    return _make_func("atan", [_to_expr(x)])

def atan2(y, x):
    return _make_func("atan2", [_to_expr(y), _to_expr(x)])

def sinh(x):
    return _make_func("sinh", [_to_expr(x)])

def cosh(x):
    return _make_func("cosh", [_to_expr(x)])

def tanh(x):
    return _make_func("tanh", [_to_expr(x)])

def exp(x):
    return _make_func("exp", [_to_expr(x)])

def log(x):
    return _make_func("log", [_to_expr(x)])

def sqrt(x):
    return _make_func("sqrt", [_to_expr(x)])

def floor(x):
    return _make_func("floor", [_to_expr(x)])

def ceil(x):
    return _make_func("ceil", [_to_expr(x)])

def trunc(x):
    return _make_func("trunc", [_to_expr(x)])

_LN10 = 2.302585092994046  # math.log(10)

def log10(x):
    return _make_func("log", [_to_expr(x)]) / Const(_LN10)

def cbrt(x):
    return _make_func("pow", [_to_expr(x), Const(1/3)])

def lerp(a, b, t):
    a, b, t = _to_expr(a), _to_expr(b), _to_expr(t)
    return a + (b - a) * t

def clip(x, lo, hi):
    return _make_func("clip", [_to_expr(x), _to_expr(lo), _to_expr(hi)])

clamp = clip

def step(edge, x):
    return _make_func("gte", [_to_expr(x), _to_expr(edge)])

def smoothstep(edge0, edge1, x):
    e0, e1, xv = _to_expr(edge0), _to_expr(edge1), _to_expr(x)
    t = clip((xv - e0) / (e1 - e0), 0, 1)
    return t * t * (Const(3) - Const(2) * t)

def mod(a, b):
    return _make_func("mod", [_to_expr(a), _to_expr(b)])

def frac(x):
    xv = _to_expr(x)
    return xv - floor(xv)

def deg2rad(x):
    return _to_expr(x) * Const(3.141592653589793 / 180)

def rad2deg(x):
    return _to_expr(x) * Const(180 / 3.141592653589793)

# Python組み込みと衝突する関数（両方対応）
def abs(x):
    if isinstance(x, Expr):
        return _make_func("abs", [x])
    return _builtins.abs(x)

def min(*args):
    if any(isinstance(a, Expr) for a in args):
        return _make_func("min", [_to_expr(a) for a in args])
    return _builtins.min(*args)

def max(*args):
    if any(isinstance(a, Expr) for a in args):
        return _make_func("max", [_to_expr(a) for a in args])
    return _builtins.max(*args)

def round(x):
    if isinstance(x, Expr):
        return _make_func("round", [x])
    return _builtins.round(x)

def pow(x, y):
    if isinstance(x, Expr) or isinstance(y, Expr):
        return _make_func("pow", [_to_expr(x), _to_expr(y)])
    return _builtins.pow(x, y)

# 定数
PI = 3.141592653589793
E = 2.718281828459045


# --- 条件分岐・比較 ---

def if_(cond, then_val, else_val):
    """条件分岐: cond≠0ならthen_val、そうでなければelse_val"""
    return _make_func("if", [_to_expr(cond), _to_expr(then_val), _to_expr(else_val)])

def lt(a, b):
    """a < b → 1.0, else → 0.0"""
    return _make_func("lt", [_to_expr(a), _to_expr(b)])

def gt(a, b):
    """a > b → 1.0, else → 0.0"""
    return _make_func("gt", [_to_expr(a), _to_expr(b)])

def lte(a, b):
    """a <= b → 1.0, else → 0.0"""
    return _make_func("lte", [_to_expr(a), _to_expr(b)])

def gte(a, b):
    """a >= b → 1.0, else → 0.0"""
    return _make_func("gte", [_to_expr(a), _to_expr(b)])

def eq_(a, b):
    """a == b → 1.0, else → 0.0"""
    return _make_func("eq", [_to_expr(a), _to_expr(b)])

def neq(a, b):
    """a != b → 1.0, else → 0.0"""
    return _make_func("not", [_make_func("eq", [_to_expr(a), _to_expr(b)])])

def and_(a, b):
    """論理AND"""
    return _make_func("and", [_to_expr(a), _to_expr(b)])

def or_(a, b):
    """論理OR"""
    return _make_func("or", [_to_expr(a), _to_expr(b)])

def not_(a):
    """論理NOT"""
    return _make_func("not", [_to_expr(a)])

def between(x, lo, hi):
    """lo <= x <= hi → 1.0"""
    return _make_func("between", [_to_expr(x), _to_expr(lo), _to_expr(hi)])

def case(*when_then_pairs, default=0):
    """多岐条件分岐: ネストif_の糖衣

    使用例:
        case(
            (lt(u, 0.3), 0.5),      # u<0.3 → 0.5
            (lt(u, 0.7), 1.0),      # u<0.7 → 1.0
            default=0.2,            # それ以外 → 0.2
        )
    """
    result = _to_expr(default)
    for cond, val in reversed(when_then_pairs):
        result = if_(cond, val, result)
    return result

def sign(x):
    """符号関数: x>0→1, x==0→0, x<0→-1"""
    xv = _to_expr(x)
    return if_(gt(xv, 0), 1, if_(lt(xv, 0), -1, 0))

def random(seed=0):
    """疑似乱数 [0, 1)（ffmpegランタイムで評価）"""
    return _make_func("random", [_to_expr(seed)])


# --- DSL糖衣: パーセント記法 ---

class Percent:
    """パーセント記法: 50%P → 0.5"""
    def __rmod__(self, other):
        if isinstance(other, (int, float)):
            return other / 100.0
        return NotImplemented
    def __repr__(self):
        return "P"

P = Percent()


# --- media_type判定 ---

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_WEB_EXTS = {".html", ".htm"}


def _detect_media_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _WEB_EXTS:
        return "web"
    return "image"  # フォールバック


# --- ffmpeg実行ヘルパー ---

# Windowsのコマンドライン長制限対策: フィルタ文字列がこの長さを超えたら一時ファイル経由で渡す
_FILTER_SCRIPT_THRESHOLD = 4000


def _externalize_long_filters(cmd):
    """フィルタ文字列が閾値を超える場合、一時ファイル + FFmpeg 8 の `-/オプション` 構文に差し替える

    例: `-filter_complex <長大な文字列>` → `-/filter_complex <一時ファイルパス>`
    Returns: (実行用cmd, 一時ファイルパスのリスト)
    """
    import tempfile
    new_cmd = list(cmd)
    tmp_files = []
    for opt in ("-filter_complex", "-vf", "-af"):
        for i in range(len(new_cmd) - 1):
            if new_cmd[i] == opt and len(new_cmd[i + 1]) >= _FILTER_SCRIPT_THRESHOLD:
                fd, path = tempfile.mkstemp(suffix=".txt", prefix="svfilter_")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_cmd[i + 1])
                new_cmd[i] = f"-/{opt.lstrip('-')}"
                new_cmd[i + 1] = path
                tmp_files.append(path)
                break
    return new_cmd, tmp_files


def _run_ffmpeg(cmd, timeout=600):
    """ffmpegコマンドを実行（長大フィルタは一時ファイル経由で渡し、実行後に削除）"""
    run_cmd, tmp_files = _externalize_long_filters(cmd)
    try:
        subprocess.run(run_cmd, check=True, timeout=timeout)
    finally:
        for path in tmp_files:
            try:
                os.remove(path)
            except OSError:
                pass


def _run_ffmpeg_to_cache(cmd, cache_path, timeout=600):
    """ffmpegを一時パスへ出力し、成功時のみ os.replace でキャッシュパスに確定する

    タイムアウトやCtrl-Cで壊れた部分ファイルがキャッシュとして残り、
    以後 os.path.exists() 判定で恒久的に使われ続けるのを防ぐ。
    cmd 内の cache_path と一致する引数を一時パス（拡張子は維持）に差し替えて実行する。
    """
    base, ext = os.path.splitext(cache_path)
    tmp_path = f"{base}.tmp{ext}"
    replaced = sum(1 for arg in cmd if arg == cache_path)
    if replaced == 0:
        # 置換0件のまま実行すると非アトミック書き込み後にos.replaceが
        # FileNotFoundErrorになるため、ここで即座に検出する
        raise ValueError(
            f"_run_ffmpeg_to_cache: cmd内に出力先cache_pathが見つかりません: {cache_path}\n"
            f"コマンド構築時と実行時で出力パスが食い違っています。")
    run_cmd = [tmp_path if arg == cache_path else arg for arg in cmd]
    try:
        _run_ffmpeg(run_cmd, timeout=timeout)
        os.replace(tmp_path, cache_path)
        with _GEN_COUNTER_LOCK:  # 並列レイヤー生成からの同時更新をアトミック化
            _GEN_COUNTER[0] += 1  # render統計用: 生成した中間ファイル数
    finally:
        # 失敗時に残った一時ファイルを削除（成功時はos.replace済みで存在しない）
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# --- configure許可キー ---

_CONFIGURE_KEYS = {"width", "height", "fps", "duration", "background_color",
                   "preset", "encoder", "parallel"}

# 出力プリセット: name -> (width, height, fps)
_PRESETS = {
    "shorts": (1080, 1920, 30),
    "reel":   (1080, 1920, 30),
    "reels":  (1080, 1920, 30),
    "tiktok": (1080, 1920, 30),
    "vertical": (1080, 1920, 30),
    "square": (1080, 1080, 30),
    "hd":     (1920, 1080, 30),
    "fhd":    (1920, 1080, 30),
    "1080p":  (1920, 1080, 30),
    "720p":   (1280, 720, 30),
    "2k":     (2560, 1440, 30),
    "4k":     (3840, 2160, 30),
}

# エンコーダ名 -> {cv: -c:v の値, args: 追加エンコード引数, draft: ドラフト用引数}
_ENCODER_MAP = {
    # libx264 の既定は追加引数なし（従来の出力・スナップショットと一致させる）
    "libx264":    {"cv": "libx264", "args": [],
                   "draft": ["-preset", "ultrafast", "-crf", "28"]},
    "nvenc":      {"cv": "h264_nvenc", "args": ["-preset", "p5", "-cq", "23"],
                   "draft": ["-preset", "p1", "-cq", "30"]},
    "hevc_nvenc": {"cv": "hevc_nvenc", "args": ["-preset", "p5", "-cq", "25"],
                   "draft": ["-preset", "p1", "-cq", "32"]},
    "qsv":        {"cv": "h264_qsv", "args": ["-global_quality", "23"],
                   "draft": ["-global_quality", "32"]},
    "hevc":       {"cv": "libx265", "args": ["-preset", "medium", "-crf", "24"],
                   "draft": ["-preset", "ultrafast", "-crf", "30"]},
}

# 生成した中間ファイル数のカウンタ（render統計用。render開始時にリセット）
_GEN_COUNTER = [0]
# _GEN_COUNTER の並列更新保護（並列レイヤー生成での過少計上を防ぐ）
import threading as _threading
_GEN_COUNTER_LOCK = _threading.Lock()

# 有効な出力品質サフィックス（draft時にチェックポイント鍵へ混ぜ本番と分離）
_ACTIVE_QUALITY = [""]

# ffmpeg 利用可能エンコーダ集合のキャッシュ（None=未取得）
_AVAILABLE_ENCODERS = [None]


def _ffmpeg_available_encoders():
    """ffmpeg -encoders を1回だけ実行し、利用可能なエンコーダ名の集合を返す"""
    if _AVAILABLE_ENCODERS[0] is not None:
        return _AVAILABLE_ENCODERS[0]
    names = set()
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30)
        for line in out.stdout.splitlines():
            # 例: " V..... libx264   ..." 先頭にフラグ列、続いてエンコーダ名
            parts = line.split()
            if len(parts) >= 2 and parts[0] and parts[0][0] in "VAS":
                names.add(parts[1])
    except Exception:
        names = set()
    _AVAILABLE_ENCODERS[0] = names
    return names


def _suggest_hint(name, candidates, prefix="\nもしかして: "):
    """未知の名前に対し近い候補を difflib で探し、'もしかして: X?' を返す。
    候補が無ければ空文字列。エラーメッセージ末尾に連結して使う。"""
    try:
        matches = _difflib.get_close_matches(
            str(name), [str(c) for c in candidates], n=3, cutoff=0.6)
    except Exception:
        matches = []
    if not matches:
        return ""
    return f"{prefix}{', '.join(matches)}?"

_CACHE_DIR = "__cache__"
_CHECKPOINT_DIR = os.path.join(_CACHE_DIR, "checkpoints")
_ARTIFACT_DIR = os.path.join(_CACHE_DIR, "artifacts")
_ENGINE_VER = "7"
_BAKEABLE_EFFECTS = {"scale", "fade", "trim", "morph_to", "rotate_to", "wipe", "color_shift",
                     "chroma_key", "vignette", "pixelize", "glow", "lut", "glitch",
                     "perspective_warp", "lens", "ken_burns", "drop_shadow", "outline",
                     "explode_to", "assemble_from",
                     "mask", "mask_wipe", "opacity", "rounded"}

# 終端フレーム生成Effect（bakeable末尾に1つだけ・映像を生成する）
_TERMINAL_FRAME_EFFECTS = {"morph_to", "explode_to", "assemble_from"}

# 時間操作系の live Effect（setpts/reverse/concat による時間変形）。
# チェックポイントベイクの表示尺基準と食い違うため bakeable にはしない
# （ベイク済みソースに対して毎レンダ live で適用する）。
_TIME_LIVE_EFFECTS = {"speed", "reverse", "freeze_frame"}

# reverse Effect の実効尺上限（全フレームをメモリに保持するため長尺は危険）
_REVERSE_MAX_SEC = 30.0


# --- テキスト/字幕（drawtext・subtitles）ヘルパー ---

# 日本語表示用フォントの既定候補（Windows）。先頭から存在するものを採用。
_DEFAULT_FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/msmincho.ttc",
]


def _resolve_font(font):
    """フォントパスを解決。font省略時は既定候補から存在するものを返す。
    見つからない場合は日本語エラーで案内する。"""
    if font is not None:
        path = font.replace("\\", "/")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"指定フォントが見つかりません: {font}\n"
                f"日本語表示には .ttc/.ttf の実在パスを指定してください "
                f"(例: C:/Windows/Fonts/meiryo.ttc)")
        return path
    for cand in _DEFAULT_FONT_CANDIDATES:
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(
        "既定の日本語フォントが見つかりませんでした。\n"
        "font= に実在するフォントパスを明示してください "
        "(例: font='C:/Windows/Fonts/meiryo.ttc')。\n"
        f"探索した候補: {', '.join(_DEFAULT_FONT_CANDIDATES)}")


def _escape_ffpath(path):
    """フィルタグラフのファイルパスをエスケープ（\\→/、:→\\:）してクォート。
    fontfile / subtitles=filename 用。"""
    p = path.replace("\\", "/").replace(":", "\\:")
    return f"'{p}'"


def _escape_textfile_content(s):
    """drawtext textfile の中身用エスケープ。ファイル内容には filtergraph の
    引用符/区切りは作用せず、drawtext のテキスト展開(% と \\)のみ効くため、
    \\→\\\\ と %→\\% だけをエスケープすればよい（:や'はそのまま literal 表示）。
    実測で確認済み（単一引用符 inline は ' の literal 化が描画されず不可）。"""
    return s.replace("\\", "\\\\").replace("%", "\\%")


def _ensure_textfile(content):
    """テキスト内容を content-addressed なキャッシュファイルに書き出しパスを返す。
    drawtext の textfile= で参照する。任意の文字（'、:、% 等）を確実に表示できる。"""
    body = _escape_textfile_content(content)
    key = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    path = os.path.join(_ARTIFACT_DIR, "text", f"{key}.txt")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    return path


def _escape_counter_literal(s):
    """counter の format 前後リテラル（inline text= 内）用エスケープ。
    inline 値は単一引用符で包むが、FFmpeg 8.0 では引用符内でも : , が区切り
    扱いになるためエスケープする。' は inline では確実に描画できないため拒否。"""
    if "'" in s:
        raise ValueError(
            "counter: format のリテラル部分にアポストロフィ(')は使用できません。"
            "アポストロフィを含む固定文字は text() を併用してください。")
    return (s.replace("\\", "\\\\").replace("%", "\\%")
             .replace(":", "\\:").replace(",", "\\,"))


def _validate_text_size(func, size_expr):
    """size は定数のみ許可。FFmpeg 8.0 の drawtext は fontsize を式にすると
    SEGV(0xC0000005)する（copy/setsar バリアでも回避不可・実測）。
    x/y/alpha のアニメーションは安全に利用できる。"""
    if not isinstance(size_expr, Const):
        raise ValueError(
            f"{func}: size は定数のみ対応です（アニメーション不可）。\n"
            f"FFmpeg 8.0 の drawtext は fontsize を式にすると SEGV するため、"
            f"サイズ変化は非対応です。x/y/alpha はアニメーション可能です。")
    return size_expr


def _text_size_opt(size_expr, u_expr):
    """fontsize オプション文字列を返す（size は定数のみ・_validate_text_size で担保）"""
    return f"fontsize={int(size_expr.value)}"


def _text_anchor_xy(x_expr, y_expr, u_expr, anchor):
    """テキスト配置の x/y drawtext 式を返す。
    anchor='center': (frac*W - text_w/2, frac*H - text_h/2)
    anchor='left'  : (frac*W, frac*H)   ※左上基準
    x/y は 0..1 のキャンバス比率。"""
    xf = x_expr.to_ffmpeg(u_expr)
    yf = y_expr.to_ffmpeg(u_expr)
    if anchor == "left":
        return f"x='({xf})*W'", f"y='({yf})*H'"
    return f"x='({xf})*W-text_w/2'", f"y='({yf})*H-text_h/2'"


def _build_drawtext_filter(spec, text_opt, start, dur, *, enable=None):
    """1個の drawtext フィルタ文字列を構築（text/typewriter/counter 共通）。
    text_opt: 完成済みの "textfile=..." または "text=..." オプション文字列。"""
    u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
    font = _escape_ffpath(spec["font"])
    x_opt, y_opt = _text_anchor_xy(spec["x"], spec["y"], u_expr, spec["anchor"])
    opts = [f"fontfile={font}"]
    opts.append(text_opt)
    opts.append(_text_size_opt(spec["size"], u_expr))
    opts.append(f"fontcolor={spec['color']}")
    opts.append(x_opt)
    opts.append(y_opt)
    alpha_expr = spec["alpha"]
    if not (isinstance(alpha_expr, Const) and alpha_expr.value == 1.0):
        opts.append(f"alpha='clip({alpha_expr.to_ffmpeg(u_expr)}\\,0\\,1)'")
    if spec.get("box"):
        opts.append("box=1")
        opts.append(f"boxcolor={spec['box_color']}")
        opts.append(f"boxborderw={spec['box_border']}")
    if enable is not None:
        opts.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(opts)


def _build_text_filters(obj, start, dur):
    """media_type=='text' Object の映像フィルタ（drawtext/subtitles）を返す。
    start/dur はタイムライン上の表示開始時刻/尺（u 正規化に使用）。"""
    spec = obj._text_spec
    kind = spec["kind"]

    if kind == "progress_bar":
        # 動画全体の進行バー: 透明キャンバスに geq で帯を描画。
        # 進行は t/総尺（clip(T/total, 0, 1)）で毎フレーム更新する。
        proj = Project._current
        total = proj.duration if proj and proj.duration else dur
        h = spec["height"]
        yfrac = spec["y"]
        br, bgc, bb, ba = spec["bar_rgba"]
        tr, tg, tb, ta = spec["track_rgba"]
        top = f"({yfrac}*(H-{h}))"
        prog = f"clip(T/{total}\\,0\\,1)"
        bar = f"lte(X\\,W*{prog})"
        band = f"gte(Y\\,{top})*lt(Y\\,{top}+{h})"
        return [
            "format=rgba",
            f"geq=r='if({bar}\\,{br}\\,{tr})'"
            f":g='if({bar}\\,{bgc}\\,{tg})'"
            f":b='if({bar}\\,{bb}\\,{tb})'"
            f":a='({band})*if({bar}\\,{ba}\\,{ta})'",
        ]

    if kind == "subtitles":
        parts = [f"subtitles=filename={_escape_ffpath(spec['srt'])}"]
        if spec.get("style"):
            raw = spec["style"]
            # force_style は単一引用符で囲むため、'→\' ではクォートが閉じて
            # filtergraph が壊れる。アポストロフィを含む style は早期に拒否する。
            if "'" in raw:
                raise ValueError(
                    "subtitles: style にアポストロフィ(')は使用できません "
                    f"(force_style のクォートが壊れます): {raw!r}")
            style = raw.replace("\\", "\\\\")
            parts[0] += f":force_style='{style}'"
        return parts

    if kind == "text":
        text_opt = f"textfile={_escape_ffpath(_ensure_textfile(spec['content']))}"
        return [_build_drawtext_filter(spec, text_opt, start, dur)]

    if kind == "typewriter":
        content = spec["content"]
        n = len(content)
        if n == 0:
            return []
        cps = spec["cps"]
        filters = []
        for i in range(n):
            prefix = content[:i + 1]
            t_on = start + i / cps
            if i < n - 1:
                # 右端 exclusive の半開区間（隣接窓の境界フレーム二重描画を防ぐ）
                t_off = start + (i + 1) / cps
                enable = f"gte(t\\,{t_on:.4f})*lt(t\\,{t_off:.4f})"
            else:
                # 最後の全文は終了まで保持（上限はオーバーレイ側のenableで制御）
                enable = f"gte(t\\,{t_on:.4f})"
            text_opt = f"textfile={_escape_ffpath(_ensure_textfile(prefix))}"
            filters.append(
                _build_drawtext_filter(spec, text_opt, start, dur, enable=enable))
        return filters

    if kind == "counter":
        # value = from_ + (to-from_)*u を drawtext の %{eif} で整数表示（inline展開）
        # %{eif} は切り捨てのため、四捨五入相当に +0.5*sign(to-from_) を加えて
        # 目標値 to に到達させる（u<1 でも to まで表示されるように）。
        u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
        val_expr = (spec["from_"] + (spec["to"] - spec["from_"]) * Var("u")
                    + 0.5 * sign(spec["to"] - spec["from_"]))
        val_ff = val_expr.to_ffmpeg(u_expr)
        eif = f"%{{eif\\:{val_ff}\\:d"
        if spec["width"] is not None:
            eif += f"\\:{spec['width']}"
        eif += "}"
        prefix = _escape_counter_literal(spec["prefix"])
        suffix = _escape_counter_literal(spec["suffix"])
        text_opt = "text='" + prefix + eif + suffix + "'"
        return [_build_drawtext_filter(spec, text_opt, start, dur)]

    raise ValueError(f"未知のテキスト種別: {kind}")


def _new_text_object(spec):
    """media_type=='text' の Object を生成して現在のProjectに登録する。
    実体ファイルを持たず、レンダ時に透明lavfi + drawtext/subtitles で描画する。"""
    obj = Object.__new__(Object)
    obj.source = spec["synthetic_source"]
    obj.transforms = []
    obj.effects = []
    obj.audio_effects = []
    obj.duration = None
    obj._duration_auto = False
    obj.start_time = 0
    obj.priority = 0
    obj.media_type = "text"
    obj._until_anchor = None
    obj._until_offset = 0.0
    obj._anchor_name = None
    obj._advance = True
    obj._priority_override = None
    obj._video_deleted = False
    obj._audio_deleted = False
    obj._web_source = None
    obj._web_size = None
    obj._web_fps = None
    obj._web_data = {}
    obj._web_name = None
    obj._web_debug_frames = False
    obj._web_deps = []
    obj._has_video = True
    obj._has_audio = False
    obj._text_spec = spec
    if Project._current is not None:
        Project._current.objects.append(obj)
    return obj


def _file_fingerprint(path):
    """ファイルの(絶対パス, サイズ, mtime_ns)タプルを返す"""
    abs_path = os.path.abspath(path).replace("\\", "/")
    stat = os.stat(path)
    return (abs_path, stat.st_size, stat.st_mtime_ns)


def _is_cache_artifact_path(path):
    """パスがキャッシュディレクトリ(__cache__)配下の生成物かどうか判定"""
    abs_path = os.path.abspath(path).replace("\\", "/")
    cache_root = os.path.abspath(_CACHE_DIR).replace("\\", "/")
    return abs_path.startswith(cache_root + "/")


def _is_pending_cache_path(path):
    """未生成のキャッシュ予定パスかどうか判定（dry_run中のprobe抑制用）

    dry_runではチェックポイント等のsourceが「これから生成される予定のパス」に
    差し替わるため、存在しないキャッシュ配下パスへのffprobeは警告スパムになる。
    """
    return (not os.path.exists(path)) and _is_cache_artifact_path(path)


def _op_fingerprint_str(op):
    """単一opのフィンガープリント文字列を生成"""
    parts = [op.name]
    for k in sorted(op.params):
        v = op.params[k]
        parts.append(f"{k}={v.to_ffmpeg('u') if isinstance(v, Expr) else repr(v)}")
    # policy はレンダ結果に影響しないためフィンガープリントに含めない
    quality = getattr(op, 'quality', 'final')
    parts.append(f"q={quality}")
    # morph_to: ターゲット画像のFFPをsignatureに含める
    if op.name == "morph_to" and hasattr(op, '_morph_target'):
        try:
            tgt_ffp = _file_fingerprint(op._morph_target.source)
            parts.append(f"tgt_ffp={tgt_ffp}")
        except OSError:
            parts.append(f"tgt_src={op._morph_target.source}")
    # assemble_from: 集合元画像のFFPをsignatureに含める
    if op.name == "assemble_from" and hasattr(op, '_assemble_source'):
        try:
            parts.append(f"asm_ffp={_file_fingerprint(op._assemble_source.source)}")
        except OSError:
            parts.append(f"asm_src={op._assemble_source.source}")
    # lut: LUTファイルのFFPをsignatureに含める（内容変更でキャッシュ無効化）
    if op.name == "lut":
        lut_file = op.params.get("file")
        try:
            parts.append(f"lut_ffp={_file_fingerprint(lut_file)}")
        except (OSError, TypeError):
            parts.append(f"lut_src={lut_file}")
    # mask/mask_wipe: マスク画像のFFPをsignatureに含める（内容変更でキャッシュ無効化）
    if op.name in ("mask", "mask_wipe"):
        mask_img = op.params.get("image")
        try:
            parts.append(f"mask_ffp={_file_fingerprint(mask_img)}")
        except (OSError, TypeError):
            parts.append(f"mask_src={mask_img}")
    return "|".join(parts)


def _op_prefix_fingerprint(ops_list):
    """ops列のSHA256[:16]フィンガープリントを計算"""
    sigs = []
    for typ, op in ops_list:
        sigs.append(f"{typ}:{_op_fingerprint_str(op)}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    return key


def _is_bakeable(op_type, op):
    """opがbakeable（チェックポイント保存対象）かどうか判定"""
    if op_type == "transform":
        return True
    if op_type == "effect" and op.name in _BAKEABLE_EFFECTS:
        return True
    return False


def _compute_save_points(ops):
    """保存点を計算: FSP(forceの全位置) + RAA(最右auto、force以降になければ)
    ops: [(type, op), ...]
    戻り値: set of indices
    """
    save_points = set()
    # FSP: policy="force" の全位置（bakeableかつforce）
    force_indices = []
    for i, (typ, op) in enumerate(ops):
        if getattr(op, 'policy', 'auto') == "force" and _is_bakeable(typ, op):
            save_points.add(i)
            force_indices.append(i)

    # RAA: bakeable ops中の最右 policy="auto"（最後のFSP以降にforceがなければ）
    last_force = max(force_indices) if force_indices else -1
    raa_candidate = None
    for i, (typ, op) in enumerate(ops):
        policy = getattr(op, 'policy', 'auto')
        if policy == "auto" and _is_bakeable(typ, op):
            raa_candidate = i
    # RAAはFSP以降にforceがない場合のみ有効（= 最後のforce以降にautoがある場合）
    if raa_candidate is not None and raa_candidate > last_force:
        save_points.add(raa_candidate)

    return save_points


def _checkpoint_cache_path(original_source, ops, duration=None, fps=None, quality="final"):
    """チェックポイントのキャッシュファイルパスを計算（signature方式）"""
    try:
        ffp = _file_fingerprint(original_source)
        sigs = [f"ffp={ffp}"]
    except OSError:
        sigs = [f"src={original_source.replace(chr(92), '/')}"]
    opfp = _op_prefix_fingerprint(ops)
    sigs.append(opfp)
    sigs.append(f"q={quality}")
    # 注: 生成される中間物の内容は draft/本番で同一のため、_ACTIVE_QUALITY(rq)は
    # 鍵に含めない（含めると本番↔draft で全キャッシュミスになり無駄な再生成が起きる）
    sigs.append(f"ev={_ENGINE_VER}")
    if duration is not None:
        sigs.append(f"dur={duration}")
    if fps is not None:
        sigs.append(f"fps={fps}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    # video入力 + transform-only でも動画ならmkv (ffv1)
    is_video = _detect_media_type(original_source) in ("video",)
    ext = ".mkv" if (duration is not None or is_video) else ".png"
    src_hash = hashlib.sha256(original_source.replace("\\", "/").encode()).hexdigest()[:8]
    cache_dir = os.path.join(_ARTIFACT_DIR, "checkpoint", src_hash)
    return os.path.join(cache_dir, f"{key}{ext}")


def _morph_cache_path(src_path, morph_op, duration, fps, quality="final"):
    """morph WebMのキャッシュパスを計算"""
    if _is_cache_artifact_path(src_path):
        # キャッシュ生成物はパス自体が内容由来の鍵を含むため、常にパス文字列署名を使う
        # （dry_runでは未生成でFFP不可→実レンダとの鍵不一致を防ぐ）
        sigs = [f"src={src_path.replace(chr(92), '/')}"]
    else:
        try:
            sigs = [f"ffp={_file_fingerprint(src_path)}"]
        except OSError:
            sigs = [f"src={src_path.replace(chr(92), '/')}"]
    # ターゲットFFP
    if hasattr(morph_op, '_morph_target'):
        try:
            sigs.append(f"tgt_ffp={_file_fingerprint(morph_op._morph_target.source)}")
        except OSError:
            sigs.append(f"tgt_src={morph_op._morph_target.source}")
    sigs.append(f"op={_op_fingerprint_str(morph_op)}")
    sigs.append(f"dur={duration}")
    sigs.append(f"fps={fps}")
    sigs.append(f"q={quality}")
    # 中間物は draft/本番で同一内容のため rq(_ACTIVE_QUALITY)は鍵に含めない
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    src_hash = hashlib.sha256(src_path.replace("\\", "/").encode()).hexdigest()[:8]
    cache_dir = os.path.join(_ARTIFACT_DIR, "morph", src_hash)
    return os.path.join(cache_dir, f"{key}.mkv")


def _particle_cache_path(img_path, particle_op, duration, fps, quality="final"):
    """explode_to/assemble_from の粒子アニメmkvキャッシュパスを計算

    img_path: 粒子化する単一画像（explode=直前ソース, assemble=集合元）
    """
    if _is_cache_artifact_path(img_path):
        sigs = [f"src={img_path.replace(chr(92), '/')}"]
    else:
        try:
            sigs = [f"ffp={_file_fingerprint(img_path)}"]
        except OSError:
            sigs = [f"src={img_path.replace(chr(92), '/')}"]
    sigs.append(f"op={_op_fingerprint_str(particle_op)}")
    sigs.append(f"dur={duration}")
    sigs.append(f"fps={fps}")
    sigs.append(f"q={quality}")
    # 中間物は draft/本番で同一内容のため rq(_ACTIVE_QUALITY)は鍵に含めない
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    src_hash = hashlib.sha256(img_path.replace("\\", "/").encode()).hexdigest()[:8]
    cache_dir = os.path.join(_ARTIFACT_DIR, "particle", src_hash)
    return os.path.join(cache_dir, f"{key}.mkv")


def _morph_input_frame_path(src_path):
    """morph入力用の最終フレームPNGの置き場所を導出

    morph（PIL）は画像しか読めないため、動画ソース（前ベイクの.mkv等）は
    最終フレームをRGBA PNGに抽出してからmorphの入力にする。
    """
    if _is_cache_artifact_path(src_path):
        # キャッシュ生成物: 拡張子差し替え（パス自体が内容由来の鍵を含む）
        return os.path.splitext(src_path)[0] + ".morphsrc.png"
    # 元素材が動画: キャッシュ配下に内容由来の鍵で生成
    try:
        sig = f"ffp={_file_fingerprint(src_path)}"
    except OSError:
        sig = f"src={src_path.replace(chr(92), '/')}"
    key = hashlib.sha256(sig.encode()).hexdigest()[:16]
    return os.path.join(_ARTIFACT_DIR, "morph", "src", f"{key}.png")


def _build_morph_frame_extract_cmd(src_path, frame_path):
    """動画の最終フレームをRGBA PNGに抽出するffmpegコマンド（morph入力用）

    -sseof -0.5: 終端0.5秒前からデコード
    -update 1: 残り全フレームを同一ファイルへ上書き → 最終フレームが残る
    -pix_fmt rgba: alpha維持（前ベイクのffv1 yuva444p等の透過を保つ）
    """
    cmd = ["ffmpeg", "-y", "-sseof", "-0.5"]
    cmd.extend(_decoder_input_args(src_path, "video", None))
    cmd.extend(["-update", "1", "-pix_fmt", "rgba", frame_path])
    return cmd


def _validate_morph_position(bakeable_ops):
    """終端フレーム生成Effect(morph_to/explode_to/assemble_from)が
    bakeable opsの末尾に1つだけあることを検証"""
    term_indices = [i for i, (typ, op) in enumerate(bakeable_ops)
                    if typ == "effect" and op.name in _TERMINAL_FRAME_EFFECTS]
    if not term_indices:
        return
    if len(term_indices) > 1:
        names = [bakeable_ops[i][1].name for i in term_indices]
        raise ValueError(
            f"morph_to/explode_to/assemble_from は1つのObjectに1回しか適用できません"
            f"（{len(term_indices)}個指定: {names}, idx={term_indices}）。\n"
            f"複数段には compute() 等で中間素材を生成して分割してください。")
    term_idx = term_indices[0]
    term_name = bakeable_ops[term_idx][1].name
    # 終端Effectの後に他のbakeable opがあればエラー（policy='off'は実質ライブなのでスキップ）
    for i in range(term_idx + 1, len(bakeable_ops)):
        after_op = bakeable_ops[i][1]
        if getattr(after_op, 'policy', 'auto') == "off":
            continue
        raise ValueError(
            f"{term_name} はbakeable opsの末尾に配置してください。"
            f"{term_name}(idx={term_idx})の後に "
            f"{after_op.name}(idx={i})があります。\n"
            f"回避策: {after_op.name} を {term_name} の前に移動するか、"
            f"-{after_op.name}(...) で checkpoint対象から除外してください。")


def _build_unified_ops(obj):
    """transforms + effects を統合ops列に変換（2-tuple: type, op）"""
    ops = []
    for t in obj.transforms:
        ops.append(("transform", t))
    for e in obj.effects:
        ops.append(("effect", e))
    return ops


def _split_ops(ops):
    """ops列をbakeable/liveに分離"""
    bakeable = [(t, op) for t, op in ops if _is_bakeable(t, op)]
    live = [(t, op) for t, op in ops if not _is_bakeable(t, op)]
    return bakeable, live


def _apply_time_effects_to_duration(dur, effects):
    """時間系 live Effect（speed/freeze_frame）を尺に反映した表示尺を返す。

    speed: 尺 / factor、freeze_frame: 尺 + duration、reverse: 変化なし。
    effects の並び順に適用する。
    """
    cur = dur
    for e in effects:
        name = getattr(e, "name", None)
        if name == "speed":
            f = e.params.get("factor", 1.0)
            if f:
                cur = cur / f
        elif name == "freeze_frame":
            cur = cur + e.params.get("duration", 0.0)
    return cur


def _web_cache_path(obj, project):
    """Web Objectのsignatureベースキャッシュパスを計算"""
    sigs = []
    # テンプレートファイルのフィンガープリント
    try:
        ffp = _file_fingerprint(obj._web_source)
        sigs.append(f"ffp={ffp}")
    except (OSError, TypeError):
        sigs.append(f"src={obj._web_source}")
    # データハッシュ
    data_str = json.dumps(obj._web_data, sort_keys=True, default=str)
    sigs.append(f"data={hashlib.sha256(data_str.encode()).hexdigest()[:12]}")
    sigs.append(f"dur={obj.duration}")
    fps = obj._web_fps or project.fps
    sigs.append(f"fps={fps}")
    if obj._web_size:
        sigs.append(f"size={obj._web_size[0]}x{obj._web_size[1]}")
    if obj._web_deps:
        deps_fps = []
        for dep in sorted(obj._web_deps):
            try:
                deps_fps.append(str(_file_fingerprint(dep)))
            except OSError:
                deps_fps.append(dep)
        sigs.append(f"deps={hashlib.sha256('|'.join(deps_fps).encode()).hexdigest()[:12]}")
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    name = obj._web_name or "web"
    return os.path.join(_ARTIFACT_DIR, "web", name, f"{key}.webm")


def _layer_cache_paths(filename, project=None):
    """レイヤーキャッシュパスを計算（signature方式）"""
    basename = os.path.splitext(os.path.basename(filename))[0]
    if project is not None:
        # signatureベース
        sigs = []
        try:
            ffp = _file_fingerprint(filename)
            sigs.append(f"ffp={ffp}")
        except (OSError, TypeError):
            sigs.append(f"src={filename}")
        sigs.append(f"ev={_ENGINE_VER}")
        sigs.append(f"w={project.width}")
        sigs.append(f"h={project.height}")
        sigs.append(f"fps={project.fps}")
        sigs.append(f"bg={project.background_color}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        layer_dir = os.path.join(_ARTIFACT_DIR, "layer", basename)
        return (os.path.join(layer_dir, f"{key}.mkv"),
                os.path.join(layer_dir, f"{key}.anchors.json"))
    # フォールバック（後方互換）
    return (os.path.join(_CACHE_DIR, f"{basename}.mkv"),
            os.path.join(_CACHE_DIR, f"{basename}.anchors.json"))


class Project:
    _current = None
    # レイヤー実行中のProjectスタック（from_projectでの親特定用。
    # レイヤー内で sub = Project() すると _current が奪われるため別管理）
    _exec_stack = []

    def __init__(self):
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.duration = None
        self._configured_duration = None
        self.background_color = "black"
        self.objects = []
        self._layers = []  # [(start_idx, end_idx, priority)]
        self._anchors = {}  # anchor name → time
        self._anchor_defined_in = {}  # anchor name → filename（診断用）
        self._layer_specs = []  # [{"filename": str, "priority": int, "cache": str}]
        self._mode = "render"  # "plan" or "render"
        self._current_layer_file = None  # 現在実行中のレイヤーファイル
        self._probe_cache = {}  # path → {"duration": float, "has_audio": bool}
        self._layer_sources = {}  # layer filename → [参照ソースパス]（キャッシュ鮮度検証用）
        self._extra_layer_deps = {}  # layer filename → [追加依存パス]（morph_toターゲット等）
        self._layer_meta_cache = {}  # anchors.jsonパス → パース済みメタ（二重読み防止）
        self._loudnorm_target = None  # normalize_audio() 設定時のLUFS目標
        self._markers = []  # [(time, label)] チャプターマーカー
        self._param_overrides = None  # p.param() 用の遅延パース済み上書き値
        self._render_window = None  # 部分レンダの (start, end)
        self.encoder = "libx264"    # 映像エンコーダ（configure(encoder=...)で変更）
        self._encoder_cv = "libx264"  # 解決済み -c:v の値（フォールバック反映後）
        self._encoder_args = list(_ENCODER_MAP["libx264"]["args"])       # []
        self._encoder_draft_args = list(_ENCODER_MAP["libx264"]["draft"])
        self._parallel = None       # キャッシュ並列生成のワーカ数（None=自動）
        self._draft = False         # ドラフトレンダ中フラグ
        self._render_quality = "final"
        self._thumbnail_at = None   # thumbnail()実行中のみ非None
        Project._current = self

    def configure(self, **kwargs):
        unknown = set(kwargs.keys()) - _CONFIGURE_KEYS
        if unknown:
            hint = _suggest_hint(sorted(unknown)[0], _CONFIGURE_KEYS)
            raise ValueError(
                f"不明な設定キー: {', '.join(sorted(unknown))}。"
                f"使用可能: {', '.join(sorted(_CONFIGURE_KEYS))}{hint}"
            )
        # preset: width/height/fps をまとめて設定（個別指定で上書き可能なので先に適用）
        if "preset" in kwargs:
            name = kwargs.pop("preset")
            if name not in _PRESETS:
                hint = _suggest_hint(str(name), _PRESETS.keys())
                raise ValueError(
                    f"不明なプリセット: {name}。"
                    f"使用可能: {', '.join(sorted(_PRESETS))}{hint}")
            pw, ph, pfps = _PRESETS[name]
            self.width, self.height, self.fps = pw, ph, pfps
        # encoder: 利用可能性を検出し、不可なら libx264 にフォールバック
        if "encoder" in kwargs:
            self._set_encoder(kwargs.pop("encoder"))
        # parallel: キャッシュ並列生成のワーカ数
        if "parallel" in kwargs:
            pval = kwargs.pop("parallel")
            if pval is not None:
                pval = int(pval)
                if pval < 1:
                    raise ValueError(f"parallel は1以上が必要です: {pval}")
            self._parallel = pval
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "duration" in kwargs:
            self._configured_duration = kwargs["duration"]

    def _set_encoder(self, encoder):
        """エンコーダを設定。ffmpegで利用不可なら libx264 へフォールバック（警告）。"""
        if encoder not in _ENCODER_MAP:
            hint = _suggest_hint(str(encoder), _ENCODER_MAP.keys())
            raise ValueError(
                f"不明なエンコーダ: {encoder}。"
                f"使用可能: {', '.join(sorted(_ENCODER_MAP))}{hint}")
        info = _ENCODER_MAP[encoder]
        cv = info["cv"]
        available = _ffmpeg_available_encoders()
        # available が空（検出失敗）の場合は指定を尊重（検出不能≠利用不可）
        if available and cv not in available and encoder != "libx264":
            warnings.warn(
                f"エンコーダ '{encoder}' ({cv}) はこのffmpegで利用できません。"
                f"libx264 にフォールバックします。")
            encoder = "libx264"
            info = _ENCODER_MAP["libx264"]
            cv = info["cv"]
        self.encoder = encoder
        self._encoder_cv = cv
        self._encoder_args = list(info["args"])
        self._encoder_draft_args = list(info["draft"])

    def normalize_audio(self, target=-14):
        """最終音声にloudnorm(EBU R128)を適用しラウドネスを正規化する。
        target: 目標ラウドネス(LUFS)。既定 -14（配信向け）。"""
        _require_number("normalize_audio", "target", target, -70, 0)
        self._loudnorm_target = target

    # --- テンプレート変数 ---

    def _parse_param_sources(self):
        """CLI(--param name=value)と環境変数(SCRIPTVEDIT_PARAM_<name>)を収集"""
        overrides = {}
        argv = sys.argv[1:]
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok == "--param" and i + 1 < len(argv):
                kv = argv[i + 1]
                i += 2
            elif tok.startswith("--param="):
                kv = tok[len("--param="):]
                i += 1
            else:
                i += 1
                continue
            if "=" in kv:
                k, v = kv.split("=", 1)
                overrides[k] = v
        # 環境変数は CLI を上書きしない（CLI 優先）
        for key, val in os.environ.items():
            if key.startswith("SCRIPTVEDIT_PARAM_"):
                name = key[len("SCRIPTVEDIT_PARAM_"):]
                overrides.setdefault(name, val)
        return overrides

    def param(self, name, default=None):
        """CLI/環境変数から差し替え可能なテンプレート変数を返す。

        `--param name=値` または環境変数 SCRIPTVEDIT_PARAM_<name> で上書きできる。
        default の型（int/float/bool）に合わせて文字列値を変換する。バッチ生成用。
        """
        if self._param_overrides is None:
            self._param_overrides = self._parse_param_sources()
        if name in self._param_overrides:
            raw = self._param_overrides[name]
        else:
            # 大文字小文字を無視して再検索（Windowsの環境変数は大文字化されるため）
            raw = next((v for k, v in self._param_overrides.items()
                        if k.lower() == name.lower()), None)
            if raw is None:
                return default
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            try:
                return int(raw)
            except ValueError:
                return default
        if isinstance(default, float):
            try:
                return float(raw)
            except ValueError:
                return default
        return raw

    # --- チャプターマーカー ---

    def marker(self, time, label):
        """タイムライン上のマーカーを記録（mp4チャプター/YouTube目次用）"""
        _require_number("marker", "time", time, 0)
        self._markers.append((float(time), str(label)))
        return self

    def _sorted_markers(self):
        """重複除去 + 時刻昇順のマーカー列を返す"""
        seen = set()
        uniq = []
        for t, label in self._markers:
            key = (t, label)
            if key in seen:
                continue
            seen.add(key)
            uniq.append((t, label))
        uniq.sort(key=lambda m: m[0])
        return uniq

    @staticmethod
    def _fmt_timestamp(sec):
        """秒 → H:MM:SS または M:SS（YouTube目次形式）"""
        sec = int(sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def export_chapters(self, path):
        """YouTube用のチャプター目次テキスト（0:00 ラベル形式）を出力する"""
        markers = self._sorted_markers()
        lines = []
        # YouTube仕様上、先頭は 0:00 が必要。無ければ補う
        if not markers or markers[0][0] > 0.001:
            lines.append("0:00 イントロ")
        for t, label in markers:
            lines.append(f"{self._fmt_timestamp(t)} {label}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def export_metadata(self, path=None, *, title=None, description=None, tags=None):
        """YouTube投稿用メタデータ（チャプター+タイトル+説明+タグ）を1ファイルに出力する。

        title省略時は self.param("title") があればそれを使う（無ければNone）。
        path省略時は "metadata.json"（カレントディレクトリ）に書き出す。
        拡張子で出力形式を切替: .json ならJSON（構造化データ）、
        .txt ならYouTube概要欄にそのまま貼れるプレーンテキスト
        （タイトル→説明→チャプター目次→#タグ の順）。

        戻り値: 書き出したパス。
        """
        if title is None:
            title = self.param("title", None)
        markers = self._sorted_markers()
        chapter_lines = []
        if not markers or markers[0][0] > 0.001:
            chapter_lines.append("0:00 イントロ")
        for t, label in markers:
            chapter_lines.append(f"{self._fmt_timestamp(t)} {label}")
        chapters = [{"time": t, "label": label} for t, label in markers]
        tag_list = [str(t) for t in tags] if tags else []

        if path is None:
            path = "metadata.json"
        ext = os.path.splitext(path)[1].lower()
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp_path = path + ".tmp"
        if ext == ".txt":
            lines = []
            if title:
                lines.append(title)
                lines.append("")
            if description:
                lines.append(description)
                lines.append("")
            if chapter_lines:
                lines.extend(chapter_lines)
                lines.append("")
            if tag_list:
                lines.append(" ".join(f"#{t}" for t in tag_list))
            content = "\n".join(lines).rstrip("\n") + "\n"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            data = {
                "title": title,
                "description": description,
                "tags": tag_list,
                "chapters": chapters,
                "chapters_text": "\n".join(chapter_lines),
            }
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return path

    def _chapters_metadata_path(self):
        """FFMETADATAチャプターファイルのキャッシュパス（内容由来の鍵）"""
        total = self.duration if self.duration is not None else 0
        sig = "||".join(f"{t}:{label}" for t, label in self._sorted_markers())
        sig += f"||dur={total}||ev={_ENGINE_VER}"
        key = hashlib.sha256(sig.encode()).hexdigest()[:16]
        return os.path.join(_ARTIFACT_DIR, "chapters", f"{key}.txt")

    def _write_chapters_metadata(self, path):
        """FFMETADATA1形式のチャプターファイルを書き出す（絶対時刻）。

        部分レンダ(render(start,end))では出力側 -ss/-t により FFmpeg が
        チャプター時刻を自動でシフト/クランプするため（実測: ffmpeg 8.0）、
        ここでは常に絶対時刻で書き出す。手動で window 減算すると二重シフトになり、
        窓開始時にアクティブなチャプターも失われるため行わない。"""
        markers = self._sorted_markers()
        total = self.duration if self.duration is not None else (
            markers[-1][0] + 1 if markers else 1)
        lines = [";FFMETADATA1"]
        for i, (t, label) in enumerate(markers):
            start_ms = int(t * 1000)
            end_ms = int((markers[i + 1][0] if i + 1 < len(markers) else total) * 1000)
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            safe = label.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\r", " ").replace("\n", " ")
            lines.append("[CHAPTER]")
            lines.append("TIMEBASE=1/1000")
            lines.append(f"START={start_ms}")
            lines.append(f"END={end_ms}")
            lines.append(f"title={safe}")
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # --- シーン ---

    def scene(self, name, duration):
        """シーンのコンテキストマネージャを返す（with p.scene("intro", 5): ...）。

        with 内で定義したObjectはシーン相対の時刻になり、シーンは時間軸上に
        順次配置される（既存の time anchor / pause 機構を土台に、シーン末尾を
        duration までパディングする）。
        """
        return Scene(self, name, duration)

    # --- デバッグ ---

    def explain(self, obj):
        """objに最終適用されるフィルタチェーンと u 正規化の分母(dur)を表示する。

        「dur がどこ由来か」を明示し、u=(t-start)/dur の分母の出所を一目で
        分かるようにする（デバッグ用）。表示文字列を返す。
        """
        if not isinstance(obj, Object):
            raise TypeError("explain: 対象は Object が必要です")
        start = getattr(obj, "start_time", 0)
        # dur の出所を判定
        if obj.duration:
            dur = obj.duration
            dur_src = "obj.duration（time()で明示指定）"
        elif getattr(obj, "_resolved_length", None):
            dur = obj._resolved_length
            dur_src = "obj._resolved_length（ベイク時に確定）"
        else:
            try:
                dur = self._resolve_obj_duration(obj)
                dur_src = "length()/フォールバック（time()未指定）"
            except Exception:
                dur = None
                dur_src = "未解決"
        lines = []
        lines.append(f"=== explain: {obj.source} ===")
        lines.append(f"  media_type : {obj.media_type}")
        lines.append(f"  start_time : {start}")
        lines.append(f"  duration   : {obj.duration}")
        lines.append(f"  u 正規化分母 dur = {dur}  ← {dur_src}")
        lines.append(f"  u = clip((t-{start})/{dur}, 0, 1)")
        # transform / effect フィルタ
        try:
            tfs = _build_transform_filters(obj)
        except Exception as e:
            tfs = [f"<transform構築エラー: {e}>"]
        lines.append("  Transforms:")
        if obj.transforms:
            for t in obj.transforms:
                lines.append(f"    - {t.name}: {t.params}")
        else:
            lines.append("    (なし)")
        lines.append("  Effects:")
        if obj.effects:
            for e in obj.effects:
                pd = {}
                for k, v in e.params.items():
                    pd[k] = (v.to_ffmpeg("u")[:40] + "…") if isinstance(v, Expr) else v
                lines.append(f"    - {e.name}: {pd}")
        else:
            lines.append("    (なし)")
        lines.append("  映像フィルタチェーン:")
        try:
            base_dims = _get_base_dimensions(obj)
            eff_filters, pad_size = _build_effect_filters(
                obj, start, dur or 5, base_dims=base_dims)
            chain = _optimize_filter_chain(list(tfs) + list(eff_filters))
            for f in chain:
                lines.append(f"    {f}")
            x_expr, y_expr = _build_move_exprs(obj, start, dur or 5, pad_size=pad_size)
            lines.append(f"  overlay位置: x={x_expr}")
            lines.append(f"               y={y_expr}")
        except Exception as e:
            lines.append(f"    <フィルタ構築エラー: {e}>")
        out = "\n".join(lines)
        print(out)
        return out

    def _reset_runtime_state(self):
        """render()用の実行時状態をリセット"""
        self.duration = self._configured_duration
        self.objects = []
        self._layers = []
        self._anchors = {}
        self._anchor_defined_in = {}
        # probe失敗(None)エントリのみ破棄（renderをまたいだ再試行を許す）
        self._probe_cache = {k: v for k, v in self._probe_cache.items()
                             if v is not None}
        self._layer_meta_cache = {}

    def _probe_media(self, path):
        """ffprobeでメディア情報を取得（キャッシュあり）"""
        if path in self._probe_cache:
            return self._probe_cache[path]
        if _is_pending_cache_path(path):
            # dry_run中の未生成キャッシュ予定パス。probeせず警告なしでNoneを返す
            # （キャッシュはしない: 実レンダで生成された後は通常probeに進む）
            return None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                # ffprobe失敗（ファイル欠損等）。空JSONを成功扱いしない
                raise ValueError(f"ffprobe exit code {result.returncode}")
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            duration_str = data.get("format", {}).get("duration")
            duration = float(duration_str) if duration_str else None
            # 音声ストリームのサンプルレート（aloop の size 算出に使用）
            sample_rate = None
            for s in streams:
                if s.get("codec_type") == "audio" and s.get("sample_rate"):
                    try:
                        sample_rate = int(s["sample_rate"])
                    except (ValueError, TypeError):
                        sample_rate = None
                    break
            info = {"has_audio": has_audio, "duration": duration,
                    "sample_rate": sample_rate}
            self._probe_cache[path] = info
            return info
        except FileNotFoundError:
            # 失敗もrender内ではキャッシュ（_reset_runtime_stateでNoneのみ破棄され、
            # renderをまたげば再試行される）
            warnings.warn(f"ffprobeが見つかりません。PATHを確認してください。")
            self._probe_cache[path] = None
            return None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
                json.JSONDecodeError, ValueError) as e:
            warnings.warn(f"メディア情報の取得に失敗 ({path}): {e}")
            self._probe_cache[path] = None
            return None

    def layer(self, filename, priority=0, cache="off"):
        """レイヤーファイルを登録（実行はrender時に遅延）"""
        if cache not in ("off", "auto", "use", "make"):
            raise ValueError(f"cache引数は 'off','auto','use','make' のいずれか: {cache!r}")
        self._layer_specs.append({"filename": filename, "priority": priority, "cache": cache})

    def _exec_layer(self, filename, priority):
        """レイヤーファイルを実行してobjectsに登録"""
        start_idx = len(self.objects)
        self._current_layer_file = filename
        # exec中にmorph_to等が積む追加依存をリセット（plan/renderの再実行で重複させない）
        self._extra_layer_deps[filename] = []
        Project._current = self
        Project._exec_stack.append(self)
        try:
            with open(filename, encoding="utf-8") as f:
                code = f.read()
            namespace = {}
            exec(compile(code, filename, "exec"), namespace)
        finally:
            Project._exec_stack.pop()
            # レイヤー内で sub = Project() された場合に _current を奪還する
            Project._current = self
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, priority))
        for obj in self.objects[start_idx:end_idx]:
            override = getattr(obj, '_priority_override', None)
            obj.priority = override if override is not None else priority
        self._fill_auto_durations(start_idx, end_idx)
        # レイヤーが参照する素材ソースを記録（checkpoint等で差し替わる前の値）
        sources = []
        for o in self.objects[start_idx:end_idx]:
            if not isinstance(o, Object):
                continue
            # compute()済みは導出キャッシュパスではなく元素材を記録
            sources.extend(getattr(o, '_origin_sources', None) or [o.source])
            # web Objectの依存素材（deps=）も鮮度検証の対象にする
            if getattr(o, '_web_deps', None):
                sources.extend(o._web_deps)
        # morph_toターゲット等、objectsから除外された依存を併合
        sources.extend(self._extra_layer_deps.get(filename, []))
        self._layer_sources[filename] = sources
        self._current_layer_file = None

    def _fill_auto_durations(self, start_idx, end_idx):
        """duration_auto=Trueのオブジェクトにlength()でdurationを確定"""
        for obj in self.objects[start_idx:end_idx]:
            if (isinstance(obj, Object)
                    and obj._duration_auto
                    and obj.duration is None
                    and obj._until_anchor is None):
                obj.duration = obj.length()

    def _calc_total_duration(self):
        """各レイヤーの最大終了時刻を返す（show含む）"""
        max_dur = 0
        for start_idx, end_idx, _ in self._layers:
            for item in self.objects[start_idx:end_idx]:
                if isinstance(item, _AnchorMarker):
                    continue
                # _ScenePad は resolve 後に start_time/duration を持つため通常計上
                if item.duration is not None:
                    end = item.start_time + item.duration
                    max_dur = max(max_dur, end)
        return max_dur if max_dur > 0 else 5

    def _resolve_anchors(self, check_unresolved=True):
        """反復走査でアンカーとuntilを解決"""
        max_iter = len(self._layers) + 2
        for iteration in range(max_iter):
            changed = False
            for start_idx, end_idx, _ in self._layers:
                current_time = 0
                for item in self.objects[start_idx:end_idx]:
                    if isinstance(item, _AnchorMarker):
                        old_val = self._anchors.get(item.name)
                        self._anchors[item.name] = current_time
                        if old_val != current_time:
                            changed = True
                        continue
                    if isinstance(item, _ScenePad):
                        # シーン開始+目標尺まで current_time を進める（遅延パディング）。
                        # pad量を duration として保持し、末尾シーンのパディングも
                        # 総尺(_calc_total_duration)に反映されるようにする。
                        scene_start = self._anchors.get(
                            f"scene:{item.scene_name}", 0)
                        target_time = scene_start + item.target_duration
                        item.start_time = current_time
                        pad_amt = float(max(0.0, target_time - current_time))
                        if item.duration != pad_amt:
                            item.duration = pad_amt
                            changed = True
                        current_time += pad_amt
                        continue
                    item.start_time = current_time
                    # name anchor: X.start 登録
                    anchor_name = getattr(item, '_anchor_name', None)
                    if anchor_name:
                        start_key = f"{anchor_name}.start"
                        old_val = self._anchors.get(start_key)
                        self._anchors[start_key] = current_time
                        if old_val != current_time:
                            changed = True
                    # until解決（offset対応）
                    until_name = getattr(item, '_until_anchor', None)
                    if until_name:
                        anchor_time = self._anchors.get(until_name)
                        if anchor_time is not None:
                            offset = getattr(item, '_until_offset', 0.0)
                            target_time = anchor_time + offset
                            new_dur = max(0, target_time - current_time)
                            if item.duration != new_dur:
                                item.duration = new_dur
                                changed = True
                    # 時刻進行（advance=False なら進めない）
                    advance = getattr(item, '_advance', True)
                    if item.duration is not None:
                        if advance:
                            current_time += item.duration
                        # name anchor: X.end 登録
                        if anchor_name:
                            end_key = f"{anchor_name}.end"
                            end_time = item.start_time + item.duration
                            old_val = self._anchors.get(end_key)
                            self._anchors[end_key] = end_time
                            if old_val != end_time:
                                changed = True
            if not changed:
                break
        if check_unresolved:
            for item in self.objects:
                until_name = getattr(item, '_until_anchor', None)
                if until_name and until_name not in self._anchors:
                    raise RuntimeError(f"未定義のアンカー: '{until_name}'")

    def render(self, output_path, *, dry_run=False, timeout=1800,
               start=None, end=None, draft=False, alpha=False):
        # _ACTIVE_QUALITY を try/finally で復元（draft レンダ後に "draft" が
        # 残留して別レンダの鍵に混入するのを防ぐ。dry_run早期returnや例外時も復元）
        _prev_active_quality = _ACTIVE_QUALITY[0]
        try:
            return self._render_impl(
                output_path, dry_run=dry_run, timeout=timeout,
                start=start, end=end, draft=draft, alpha=alpha)
        finally:
            _ACTIVE_QUALITY[0] = _prev_active_quality

    def _render_impl(self, output_path, *, dry_run=False, timeout=1800,
                     start=None, end=None, draft=False, alpha=False):
        self._reset_runtime_state()
        self._dry_run = dry_run
        self._draft = bool(draft)
        self._alpha = bool(alpha)
        self._render_quality = "draft" if draft else "final"
        # draft時はチェックポイント/morph鍵を本番と分離
        _ACTIVE_QUALITY[0] = "draft" if draft else ""
        _GEN_COUNTER[0] = 0
        _t0 = _time.perf_counter()
        self._pending_compute_cmds = {}
        # 部分レンダの時間窓を検証・保持（式のt基準は保ちつつ窓外を出力しない）
        if start is not None or end is not None:
            s = 0.0 if start is None else float(start)
            e = end if end is None else float(end)
            if s < 0:
                raise ValueError(f"render: start は0以上が必要です: {start}")
            if e is not None and e <= s:
                raise ValueError(f"render: end({end}) は start({start}) より後が必要です")
            self._render_window = (s, e)
        else:
            self._render_window = None
        # cache="use" の事前検証
        self._validate_cache_specs()
        # Plan pass: アンカー解決（cache模擬、objects破棄）
        self._plan_resolve()
        # Render pass: 本実行（anchors確定済み）
        self.objects = []
        self._layers = []
        self._mode = "render"
        for spec in self._layer_specs:
            if self._should_use_cache(spec):
                self._load_cached_layer(spec)
            else:
                self._exec_layer(spec["filename"], spec["priority"])
        self._resolve_anchors()
        if self.duration is None:
            self.duration = self._calc_total_duration()

        if dry_run:
            web_cmds = self._collect_web_cmds()
            # web Objectのsourceを予定webmパスに仮差し替え
            # （layer cache / checkpoint収集より前。-i xxx.html の混入を防ぐ）
            for obj in self.objects:
                if isinstance(obj, Object) and obj.media_type == "web":
                    obj.source = _web_cache_path(obj, self)
                    obj.media_type = "video"
            cache_cmds = self._collect_cache_cmds()
            checkpoint_cmds = self._collect_checkpoint_cmds()
            cmd = self._build_ffmpeg_cmd(output_path)
            all_extra = {}
            if cache_cmds:
                all_extra.update(cache_cmds)
            if web_cmds:
                all_extra.update(web_cmds)
            if checkpoint_cmds:
                all_extra.update(checkpoint_cmds)
            if self._pending_compute_cmds:
                all_extra.update(self._pending_compute_cmds)
            if all_extra:
                return {"main": cmd, "cache": all_extra}
            return cmd  # 後方互換: cache不要ならlistのまま

        self._ensure_web_objects()
        # 統計: このレンダが参照する中間生成物のうち既存(ヒット)/未生成(ミス)を数える
        # 注意: _collect_* はdry_run用でobj.source等を予測パスへ破壊的に差し替えるため、
        #       状態をスナップショットして復元してから実生成へ進む
        planned = set()
        _snap = [(o, o.source, o.media_type, list(o.transforms), list(o.effects),
                  getattr(o, "_resolved_length", None))
                 for o in self.objects if isinstance(o, Object)]
        try:
            planned |= set(self._collect_checkpoint_cmds().keys())
            planned |= set(self._collect_cache_cmds().keys())
            planned |= set(self._collect_web_cmds().keys())
            planned |= set(self._pending_compute_cmds.keys())
        except Exception:
            planned = set()
        finally:
            for o, src, mt, tr, ef, rl in _snap:
                o.source, o.media_type = src, mt
                o.transforms, o.effects = tr, ef
                o._resolved_length = rl
        cache_hits = sum(1 for p in planned if os.path.exists(p))
        cache_misses = len(planned) - cache_hits
        self._ensure_checkpoints()
        cmd = self._build_ffmpeg_cmd(output_path)
        print(f"実行コマンド:")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        print()
        _run_ffmpeg(cmd, timeout=timeout)
        self._generate_pending_caches()
        elapsed = _time.perf_counter() - _t0
        generated = _GEN_COUNTER[0]
        print(f"\n完了: {output_path}")
        mode = "ドラフト" if draft else "本番"
        print(f"[統計] {mode} / 総時間 {elapsed:.2f}s / "
              f"キャッシュ ヒット{cache_hits} ミス{cache_misses} / "
              f"生成した中間ファイル {generated}件")

    def thumbnail(self, at, out, *, timeout=600):
        """指定時刻 at(秒) のフレームを1枚のPNGとして書き出す。

        render() と同じプラン解決・チェックポイント生成を通し、
        フィルタグラフの t 基準を保ったまま -ss + -frames:v 1 で抜き出す。
        """
        at = float(at)
        if at < 0:
            raise ValueError(f"thumbnail: at は0以上が必要です: {at}")
        self._reset_runtime_state()
        self._dry_run = False
        self._draft = False
        self._alpha = False
        self._render_quality = "final"
        _ACTIVE_QUALITY[0] = ""
        self._pending_compute_cmds = {}
        self._render_window = None
        self._validate_cache_specs()
        self._plan_resolve()
        self.objects = []
        self._layers = []
        self._mode = "render"
        for spec in self._layer_specs:
            if self._should_use_cache(spec):
                self._load_cached_layer(spec)
            else:
                self._exec_layer(spec["filename"], spec["priority"])
        self._resolve_anchors()
        if self.duration is None:
            self.duration = self._calc_total_duration()
        self._ensure_web_objects()
        self._ensure_checkpoints()
        self._thumbnail_at = at
        try:
            cmd = self._build_ffmpeg_cmd(out)
            print(f"サムネイル抽出 @{at}s: {out}")
            print(f"  ffmpeg {' '.join(cmd[1:])}")
            _run_ffmpeg(cmd, timeout=timeout)
        finally:
            self._thumbnail_at = None
        print(f"完了: {out}")
        return out

    def storyboard(self, out_path, *, cols=4, interval=None):
        """タイムラインの絵コンテ（サムネイル格子画像）を1枚のPNGとして生成する。

        interval秒ごと（省略時は 総尺/12）に thumbnail() と同じ抽出経路
        （plan解決+checkpoint確保+ffmpeg単フレーム抽出）でサムネイルを取り出し、
        PILでcols列のグリッドに結合する（各コマ左上に時刻ラベルを焼き込む）。
        事前にrender()した最終動画は不要（このメソッド単体で完結する実装方式。
        thumbnail()を都度呼ぶためコマ数ぶんffmpegが実行される）。

        戻り値: 書き出したパス(out_path)。
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as e:
            raise ImportError(
                "storyboard() には Pillow が必要です。"
                "`pip install Pillow` を実行してください。") from e
        if cols < 1:
            raise ValueError(f"storyboard: cols は1以上が必要です: {cols}")
        if interval is not None:
            _require_number("storyboard", "interval", interval, 0.001, None)

        tmp_dir = os.path.join(_ARTIFACT_DIR, "storyboard", "_frames")
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            # 1枚目の抽出で総尺を確定させる（thumbnail()の副作用でself.durationが決まる）
            first_path = os.path.join(tmp_dir, "frame_000.png")
            self.thumbnail(0.0, first_path)
            total = self.duration
            if not total or total <= 0:
                raise RuntimeError("storyboard: タイムラインの総尺を確定できませんでした")
            step = interval if interval is not None else max(total / 12.0, 0.01)

            times = [0.0]
            t = step
            while t < total - 1e-6:
                times.append(t)
                t += step

            frame_paths = [(0.0, first_path)]
            for i, tsec in enumerate(times[1:], start=1):
                fp = os.path.join(tmp_dir, f"frame_{i:03d}.png")
                self.thumbnail(min(tsec, max(0.0, total - 0.001)), fp)
                frame_paths.append((tsec, fp))

            thumbs = [Image.open(fp).convert("RGB") for _, fp in frame_paths]
            tw, th = thumbs[0].size
            n = len(thumbs)
            rows = (n + cols - 1) // cols
            gap = 4
            grid_w = cols * tw + (cols - 1) * gap
            grid_h = rows * th + (rows - 1) * gap
            canvas = Image.new("RGB", (grid_w, grid_h), (20, 20, 20))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
            for i, ((tsec, _fp), img) in enumerate(zip(frame_paths, thumbs)):
                r, c = divmod(i, cols)
                x = c * (tw + gap)
                y = r * (th + gap)
                canvas.paste(img, (x, y))
                label = self._fmt_timestamp(tsec)
                draw.rectangle([x, y, x + 68, y + 20], fill=(0, 0, 0))
                draw.text((x + 4, y + 3), label, fill=(255, 255, 0), font=font)

            d = os.path.dirname(out_path)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp_out = out_path + ".tmp.png"
            canvas.save(tmp_out)
            os.replace(tmp_out, out_path)
        finally:
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        return out_path

    def inspect(self, out_html=None, *, title=None):
        """svinspect による検査ビュー。

        out_html 指定時は HTML ガントチャートを書き出しそのパスを返す。
        省略時はプレーンテキストのレポート文字列を返す（遅延 import）。
        """
        try:
            import svinspect as _svi
        except ImportError as e:
            raise ImportError(
                "inspect() には svinspect.py が必要です。"
                "scriptvedit.py と同じディレクトリに配置してください。") from e
        if out_html is not None:
            return _svi.render_timeline(self, out_html, title=title)
        return _svi.report_text(self)

    def _plan_resolve(self):
        """Plan pass: 固定点反復でアンカーを解決"""
        converged = False
        max_iterations = len(self._layer_specs) + 2
        for iteration in range(max_iterations):
            old_anchors = dict(self._anchors)
            self.objects = []
            self._layers = []
            self._mode = "plan"
            for spec in self._layer_specs:
                # Plan passではレイヤーキャッシュを使わず常に実行
                self._exec_layer(spec["filename"], spec["priority"])
            self._resolve_anchors(check_unresolved=False)
            if self._anchors == old_anchors and iteration > 0:
                converged = True
                break
        # 収束しなかった場合
        if not converged and self._anchors:
            raise RuntimeError(
                f"アンカー解決が{max_iterations}回の反復で収束しませんでした。"
                f"循環参照の可能性があります。\n"
                f"定義済みアンカー: {dict(self._anchors)}"
            )
        # 未解決のuntilチェック（診断付き）
        unresolved = []
        for item in self.objects:
            until_name = getattr(item, '_until_anchor', None)
            if until_name and until_name not in self._anchors:
                unresolved.append((until_name, item))
        if unresolved:
            names = ", ".join(f"'{n}'" for n in sorted(set(n for n, _ in unresolved)))
            defined = ", ".join(f"'{n}'" for n in sorted(self._anchors.keys())) or "(なし)"
            details = []
            for name, item in unresolved:
                offset = getattr(item, '_until_offset', 0.0)
                offset_str = f", offset={offset}" if offset != 0.0 else ""
                if isinstance(item, Pause):
                    details.append(f"  pause.until('{name}'{offset_str})")
                elif isinstance(item, Object):
                    details.append(f"  Object('{item.source}').until('{name}'{offset_str})")
                else:
                    details.append(f"  {type(item).__name__}.until('{name}'{offset_str})")
            raise RuntimeError(
                f"未定義のアンカーが参照されています: {names}\n"
                f"定義済みアンカー: {defined}\n"
                f"参照元:\n" + "\n".join(details)
            )

    def _validate_cache_specs(self):
        """cache='use' のファイル存在チェック"""
        for spec in self._layer_specs:
            if spec["cache"] == "use":
                webm_path, json_path = _layer_cache_paths(spec["filename"], self)
                if not os.path.exists(webm_path):
                    raise FileNotFoundError(
                        f"キャッシュファイルが見つかりません: {webm_path}\n"
                        f"レイヤー '{spec['filename']}' に cache='use' が指定されていますが、"
                        f"先に cache='make' でキャッシュを生成してください。"
                    )

    def _layer_cache_is_fresh(self, spec):
        """anchors.jsonに記録された素材FFPと現在のファイル状態を比較して鮮度を判定

        旧形式（sourcesキーなし）のメタは後方互換のため常に新鮮とみなす。
        """
        _, json_path = _layer_cache_paths(spec["filename"], self)
        if not os.path.exists(json_path):
            return True  # メタなし（後方互換）
        try:
            with open(json_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return True
        # パース済みメタを保持し、_load_cached_layerでの再読込をスキップする
        self._layer_meta_cache[json_path] = meta
        sources = meta.get("sources")
        if not sources:
            return True  # 旧形式（後方互換）
        for path, ffp in sources.items():
            try:
                cur = _file_fingerprint(path)
            except OSError:
                return False  # 素材が消えた
            if [cur[1], cur[2]] != list(ffp):
                return False  # サイズ/mtimeが変わった
        return True

    def _should_use_cache(self, spec):
        """キャッシュ利用判定"""
        cache = spec["cache"]
        if cache == "use":
            if not self._layer_cache_is_fresh(spec):
                warnings.warn(
                    f"レイヤーキャッシュの素材が更新されています: {spec['filename']}。"
                    f"cache='make' で再生成してください（cache='use' 指定のため続行します）。")
            return True
        if cache == "auto":
            webm_path, _ = _layer_cache_paths(spec["filename"], self)
            # 素材更新済みの古いキャッシュは使わず再実行
            return os.path.exists(webm_path) and self._layer_cache_is_fresh(spec)
        return False  # off, make

    def _load_cached_layer(self, spec):
        """キャッシュからObject生成 + anchors.jsonマージ"""
        webm_path, json_path = _layer_cache_paths(spec["filename"], self)
        start_idx = len(self.objects)
        # キャッシュwebmをObjectとして生成
        cached_obj = Object.__new__(Object)
        cached_obj.source = webm_path
        cached_obj.transforms = []
        cached_obj.effects = []
        cached_obj.audio_effects = []
        cached_obj.duration = None
        cached_obj.start_time = 0
        cached_obj.priority = spec["priority"]
        cached_obj.media_type = "video"
        cached_obj._until_anchor = None
        cached_obj._video_deleted = False
        cached_obj._audio_deleted = False
        cached_obj._has_video = True
        cached_obj._has_audio = False
        cached_obj._web_source = None
        cached_obj._web_size = None
        cached_obj._web_fps = None
        cached_obj._web_data = {}
        cached_obj._web_name = None
        cached_obj._web_debug_frames = False
        # anchors.jsonからduration/anchorsを読み込み
        # （_layer_cache_is_freshでパース済みならそのメタを流用し二重読みを避ける）
        cache_meta = self._layer_meta_cache.get(json_path)
        if cache_meta is None and os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                cache_meta = json.load(f)
        if cache_meta is not None:
            cached_obj.duration = cache_meta.get("duration")
            for name, time_val in cache_meta.get("anchors", {}).items():
                self._anchors[name] = time_val
                self._anchor_defined_in[name] = spec["filename"]
        self.objects.append(cached_obj)
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, spec["priority"]))

    def _get_layer_data(self, spec_index):
        """指定レイヤーのオブジェクト群とアンカー群を取得"""
        spec = self._layer_specs[spec_index]
        # _layersのインデックスはspec_indexに対応
        if spec_index >= len(self._layers):
            return [], {}
        start_idx, end_idx, _ = self._layers[spec_index]
        objects = self.objects[start_idx:end_idx]
        anchors = {}
        current_time = 0
        for item in objects:
            if isinstance(item, _AnchorMarker):
                anchors[item.name] = current_time
                continue
            if isinstance(item, _ScenePad):
                # シーン開始+目標尺まで進める（遅延パディング、キャッシュ用アンカー整合）
                scene_start = anchors.get(f"scene:{item.scene_name}", 0)
                target_time = scene_start + item.target_duration
                if current_time < target_time:
                    current_time = target_time
                continue
            if item.duration is not None:
                current_time += item.duration
        return objects, anchors

    def _collect_cache_cmds(self):
        """dry_run用のキャッシュ生成コマンド辞書構築"""
        cache_cmds = {}
        for i, spec in enumerate(self._layer_specs):
            # "make" は常に生成（"auto" はキャッシュ有無に関わらず生成コマンドを持たない）
            if spec["cache"] == "make":
                webm_path, _ = _layer_cache_paths(spec["filename"], self)
                cmd = self._build_layer_cache_cmd(i, webm_path)
                cache_cmds[webm_path] = cmd
        return cache_cmds

    def _build_checkpoint_image_cmd(self, source, transforms, cache_path, quality="final"):
        """画像チェックポイント: Transform適用→透過PNG"""
        # 一時Object経由で _build_transform_filters を再利用
        temp = Object.__new__(Object)
        temp.source = source
        temp.transforms = list(transforms)
        temp.effects = []
        filters = _build_transform_filters(temp)
        cmd = ["ffmpeg", "-y", "-i", source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", cache_path])
        return cmd

    def _build_checkpoint_video_cmd(self, source, media_type, transforms, effects,
                                     cache_path, dur, fps, quality="final"):
        """動画チェックポイント: Transform+Effect適用→透明VP9"""
        cmd = ["ffmpeg", "-y"]
        cmd.extend(_decoder_input_args(source, media_type, fps))

        # フィルタ構築: 一時Object経由で既存ビルダーを再利用
        temp = Object.__new__(Object)
        temp.source = source
        temp.transforms = list(transforms)
        temp.effects = list(effects)
        temp.media_type = media_type

        base_dims = _get_base_dimensions(temp)
        filters = _build_transform_filters(temp)
        pre_filters = _build_video_pre_filters(temp)
        filters = pre_filters + filters
        eff_filters, _ = _build_effect_filters(temp, 0, dur, base_dims=base_dims)
        filters.extend(eff_filters)
        filters = _optimize_filter_chain(filters)

        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        cmd.extend([
            "-c:v", "ffv1", "-level", "3",
            "-pix_fmt", "yuva444p",
            "-t", str(dur), cache_path,
        ])
        return cmd

    def _build_morph_webm_cmd(self, frame_pattern, cache_path, duration, fps, quality="final"):
        """PNG連番 → alpha映像 のffmpegコマンドを構築"""
        return ["ffmpeg", "-y", "-framerate", str(fps),
                "-i", frame_pattern,
                "-c:v", "ffv1", "-level", "3",
                "-pix_fmt", "yuva444p",
                "-t", str(duration), cache_path]

    @staticmethod
    def _require_morph_duration(bakeable_ops, dur, source):
        """morph_toを含むObjectのduration未設定を明示エラーにする

        画像 + duration未設定のまま進むと int(fps * None) の TypeError で
        原因が分かりにくいため、ここで日本語エラーを投げる。
        """
        has_term = any(t == "effect" and op.name in _TERMINAL_FRAME_EFFECTS
                       for t, op in bakeable_ops)
        if has_term and dur is None:
            raise ValueError(
                f"morph_to/explode_to/assemble_from を含むObject ('{source}') には"
                f"表示時間の指定が必要です。obj.time(秒数) で duration を設定してください。")

    def _checkpoint_bake_duration(self, obj, original_source):
        """チェックポイントのベイク尺を決定する。

        speed/reverse/freeze_frame 等の live 時間系Effectが残るObjectは、
        表示尺(duration)ではなくソース基準の実長(trimのみ反映)でベイクする。
        表示尺でベイクすると、後段の時間系Effect適用でソース素材が
        不足/過剰になる（例: speed(2)で表示尺5s → 元素材10sが必要）ため。
        """
        is_video = _detect_media_type(original_source) in ("video",)
        has_time_live = any(
            getattr(e, "name", None) in _TIME_LIVE_EFFECTS for e in obj.effects)
        if is_video and has_time_live:
            info = self._probe_media(original_source)
            base = info.get("duration") if info else None
            if base is None:
                base = getattr(obj, "_resolved_length", None) or obj.duration
            if base:
                cur = base
                for e in obj.effects:
                    if e.name == "trim" and e.params.get("duration") is not None:
                        cur = _builtins.min(cur, e.params["duration"])
                return cur
        dur = obj.duration
        # video + duration未指定 → obj.length() で補完
        if dur is None and is_video:
            dur = obj.length()
        return dur

    def _process_checkpoints(self, obj):
        """1つのObjectのチェックポイント処理（実レンダ）"""
        ops = _build_unified_ops(obj)
        bakeable_ops, live_ops = _split_ops(ops)
        # bakeable ops があるか確認
        if not bakeable_ops:
            return
        # 全opがpolicy="off"ならスキップ
        if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
            return

        _validate_morph_position(bakeable_ops)

        save_points = _compute_save_points(bakeable_ops)
        if not save_points:
            return

        original_source = obj.source
        original_media_type = obj.media_type
        dur = self._checkpoint_bake_duration(obj, original_source)
        fps = self.fps
        self._require_morph_duration(bakeable_ops, dur, original_source)

        # 復元点チェック（bakeable_opsベース）
        resume_idx, resume_path = self._find_resume_point(original_source, bakeable_ops, dur, fps, save_points)
        if resume_idx is not None:
            current_source = resume_path
            current_media_type = _detect_media_type(resume_path)
            remaining_ops = bakeable_ops[resume_idx + 1:]
        else:
            current_source = original_source
            current_media_type = original_media_type
            remaining_ops = list(bakeable_ops)

        # 前方実行: 保存点でのみチェックポイント生成
        executed = bakeable_ops[:len(bakeable_ops) - len(remaining_ops)]
        pos = 0
        while pos < len(remaining_ops):
            global_idx = len(executed) + pos
            if global_idx in save_points:
                typ, op = remaining_ops[pos]
                segment_ops = executed + remaining_ops[:pos + 1]
                has_effects = any(t == "effect" for t, _ in segment_ops)
                is_video = _detect_media_type(original_source) in ("video",)
                cp_dur = dur if (has_effects or is_video) else None
                cp_fps = fps if cp_dur is not None else None
                quality = getattr(op, 'quality', 'final')

                # morph_to 分岐
                if typ == "effect" and op.name == "morph_to" and hasattr(op, '_morph_target'):
                    # morph直前の未ベイクopsを先に中間チェックポイントへベイク
                    # （破棄するとmorph前のresize等が黙って消えるため）
                    if pos > 0:
                        pre_ops = remaining_ops[:pos]
                        pre_segment = executed + pre_ops
                        pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                        pre_dur = dur if (pre_has_effects or is_video) else None
                        pre_fps = fps if pre_dur is not None else None
                        pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                        pre_path = _checkpoint_cache_path(
                            original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                        if not os.path.exists(pre_path):
                            pre_transforms = [o for t, o in pre_ops if t == "transform"]
                            pre_effects = [o for t, o in pre_ops if t == "effect"]
                            os.makedirs(os.path.dirname(pre_path), exist_ok=True)
                            if pre_dur is None:
                                pre_cmd = self._build_checkpoint_image_cmd(
                                    current_source, pre_transforms, pre_path, pre_quality)
                            else:
                                pre_cmd = self._build_checkpoint_video_cmd(
                                    current_source, current_media_type,
                                    pre_transforms, pre_effects,
                                    pre_path, pre_dur, fps, pre_quality)
                            print(f"チェックポイント保存 (morph前処理): {pre_path}")
                            _run_ffmpeg_to_cache(pre_cmd, pre_path, timeout=600)
                        current_source = pre_path
                        current_media_type = _detect_media_type(pre_path)
                    # morph（PIL）は画像のみ対応: 直前ソースが動画（前ベイクの.mkv等）
                    # なら最終フレームをRGBA PNGに抽出してmorphの入力にする
                    if _detect_media_type(current_source) == "video":
                        frame_path = _morph_input_frame_path(current_source)
                        if not os.path.exists(frame_path):
                            frame_cmd = _build_morph_frame_extract_cmd(
                                current_source, frame_path)
                            os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                            print(f"モーフ入力フレーム抽出: {frame_path}")
                            _run_ffmpeg_to_cache(frame_cmd, frame_path, timeout=600)
                        current_source = frame_path
                        current_media_type = "image"
                    morph_path = _morph_cache_path(current_source, op, dur, fps, quality)
                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(morph_path)
                    if need_render:
                        import tempfile
                        from morph import generate_rgba_frames
                        with tempfile.TemporaryDirectory() as tmpdir:
                            n_frames = int(fps * dur)
                            # blend Exprを数値関数に変換
                            blend_expr = op.params.get("blend")
                            if blend_expr is not None and isinstance(blend_expr, Expr):
                                blend_fn = lambda t, _e=blend_expr: _e.eval_at(t)
                            else:
                                blend_fn = None
                            morph_kw = {k: v for k, v in op.params.items() if k != "blend"}
                            generate_rgba_frames(
                                current_source, op._morph_target.source,
                                tmpdir, n_frames, blend_fn=blend_fn, **morph_kw)
                            frame_pattern = os.path.join(tmpdir, "frame_%05d.png")
                            os.makedirs(os.path.dirname(morph_path), exist_ok=True)
                            cmd = self._build_morph_webm_cmd(
                                frame_pattern, morph_path, dur, fps, quality)
                            print(f"モーフキャッシュ保存: {morph_path}")
                            _run_ffmpeg_to_cache(cmd, morph_path, timeout=600)
                    current_source = morph_path
                    current_media_type = "video"
                elif typ == "effect" and op.name in ("explode_to", "assemble_from"):
                    from morph import (generate_explode_frames,
                                       generate_assemble_frames)
                    if op.name == "explode_to":
                        # explode: 直前の未ベイクopsを先にベイク（morphと同じ経路）
                        if pos > 0:
                            pre_ops = remaining_ops[:pos]
                            pre_segment = executed + pre_ops
                            pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                            pre_dur = dur if (pre_has_effects or is_video) else None
                            pre_fps = fps if pre_dur is not None else None
                            pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                            pre_path = _checkpoint_cache_path(
                                original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                            if not os.path.exists(pre_path):
                                pre_transforms = [o for t, o in pre_ops if t == "transform"]
                                pre_effects = [o for t, o in pre_ops if t == "effect"]
                                os.makedirs(os.path.dirname(pre_path), exist_ok=True)
                                if pre_dur is None:
                                    pre_cmd = self._build_checkpoint_image_cmd(
                                        current_source, pre_transforms, pre_path, pre_quality)
                                else:
                                    pre_cmd = self._build_checkpoint_video_cmd(
                                        current_source, current_media_type,
                                        pre_transforms, pre_effects,
                                        pre_path, pre_dur, fps, pre_quality)
                                print(f"チェックポイント保存 (explode前処理): {pre_path}")
                                _run_ffmpeg_to_cache(pre_cmd, pre_path, timeout=600)
                            current_source = pre_path
                            current_media_type = _detect_media_type(pre_path)
                        img_path = current_source
                        gen = generate_explode_frames
                    else:  # assemble_from: 集合元画像を入力にする
                        img_path = op._assemble_source.source
                        gen = generate_assemble_frames
                    # 粒子生成（PIL）は画像のみ: 動画ソースは最終フレームを抽出
                    if _detect_media_type(img_path) == "video":
                        frame_path = _morph_input_frame_path(img_path)
                        if not os.path.exists(frame_path):
                            frame_cmd = _build_morph_frame_extract_cmd(img_path, frame_path)
                            os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                            print(f"粒子入力フレーム抽出: {frame_path}")
                            _run_ffmpeg_to_cache(frame_cmd, frame_path, timeout=600)
                        img_path = frame_path
                    part_path = _particle_cache_path(img_path, op, dur, fps, quality)
                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(part_path)
                    if need_render:
                        import tempfile
                        with tempfile.TemporaryDirectory() as tmpdir:
                            n_frames = int(fps * dur)
                            blend_expr = op.params.get("blend")
                            if blend_expr is not None and isinstance(blend_expr, Expr):
                                blend_fn = lambda t, _e=blend_expr: _e.eval_at(t)
                            else:
                                blend_fn = None
                            part_kw = {k: v for k, v in op.params.items() if k != "blend"}
                            gen(img_path, tmpdir, n_frames, blend_fn=blend_fn, **part_kw)
                            frame_pattern = os.path.join(tmpdir, "frame_%05d.png")
                            os.makedirs(os.path.dirname(part_path), exist_ok=True)
                            cmd = self._build_morph_webm_cmd(
                                frame_pattern, part_path, dur, fps, quality)
                            print(f"粒子キャッシュ保存: {part_path}")
                            _run_ffmpeg_to_cache(cmd, part_path, timeout=600)
                    current_source = part_path
                    current_media_type = "video"
                else:
                    cache_path = _checkpoint_cache_path(
                        original_source, segment_ops, cp_dur, cp_fps, quality)

                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(cache_path)
                    if need_render:
                        local_ops = remaining_ops[:pos + 1]
                        local_transforms = [op for t, op in local_ops if t == "transform"]
                        local_effects = [op for t, op in local_ops if t == "effect"]

                        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                        if cp_dur is None:
                            cmd = self._build_checkpoint_image_cmd(
                                current_source, local_transforms, cache_path, quality)
                        else:
                            cmd = self._build_checkpoint_video_cmd(
                                current_source, current_media_type,
                                local_transforms, local_effects,
                                cache_path, cp_dur, fps, quality)
                        print(f"チェックポイント保存: {cache_path}")
                        _run_ffmpeg_to_cache(cmd, cache_path, timeout=600)
                    current_source = cache_path
                    current_media_type = _detect_media_type(cache_path)

                executed = executed + remaining_ops[:pos + 1]
                remaining_ops = remaining_ops[pos + 1:]
                pos = 0
                continue
            pos += 1

        # Objectを更新: source差し替え、残余bakeable ops + live opsを再設定
        # 差し替え前に解決した実長を保持（差し替え後のprobe依存を排除し、
        # dry_runと実レンダで式を一致させる）。
        # live 時間系Effect（speed/freeze_frame）が残る場合は表示尺に換算する
        if dur:
            obj._resolved_length = _apply_time_effects_to_duration(
                dur, [op for t, op in live_ops if t == "effect"])
        obj.source = current_source
        obj.media_type = current_media_type
        obj.transforms = [op for t, op in remaining_ops if t == "transform"]
        obj.effects = ([op for t, op in remaining_ops if t == "effect"]
                       + [op for t, op in live_ops if t == "effect"])

    def _find_resume_point(self, original_source, ops, duration, fps, save_points):
        """force地点より左のauto保存点のみresume候補"""
        # 最左force位置
        first_force = None
        for i, (typ, op) in enumerate(ops):
            if getattr(op, 'policy', 'auto') == "force" and _is_bakeable(typ, op):
                first_force = i
                break
        boundary = (first_force - 1) if first_force is not None else len(ops) - 1

        # boundary以下のauto保存点を右から探索
        candidates = sorted([i for i in save_points
                            if i <= boundary and getattr(ops[i][1], 'policy', 'auto') == "auto"],
                           reverse=True)

        is_video = _detect_media_type(original_source) in ("video",)
        for idx in candidates:
            segment_ops = ops[:idx + 1]
            # 保存側と同じくセグメント（保存点までのprefix）単位でhas_effectsを計算
            # （全ops基準だとキャッシュキーが食い違い、永久にキャッシュミスする）
            has_effects = any(t == "effect" for t, _ in segment_ops)
            cp_dur = duration if (has_effects or is_video) else None
            cp_fps = fps if cp_dur is not None else None
            quality = getattr(ops[idx][1], 'quality', 'final')
            path = _checkpoint_cache_path(original_source, segment_ops, cp_dur, cp_fps, quality)
            if os.path.exists(path):
                return idx, path
        return None, None

    def _ensure_checkpoints(self):
        """bakeable opsを持つ全Objectのチェックポイント処理"""
        for obj in self.objects:
            if not isinstance(obj, Object):
                continue
            if obj.media_type == "text":
                continue  # テキスト系は実体ファイルを持たずベイク対象外
            bakeable_ops, _ = _split_ops(_build_unified_ops(obj))
            if not bakeable_ops:
                continue
            # 全opがpolicy="off"ならスキップ
            if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
                continue
            self._process_checkpoints(obj)

    def _collect_checkpoint_cmds(self):
        """dry_run用: 全チェックポイントコマンドを収集"""
        cmds = {}
        for obj in self.objects:
            if not isinstance(obj, Object):
                continue
            if obj.media_type == "text":
                continue  # テキスト系は実体ファイルを持たずベイク対象外
            ops = _build_unified_ops(obj)
            bakeable_ops, live_ops = _split_ops(ops)
            if not bakeable_ops:
                continue
            if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
                continue

            _validate_morph_position(bakeable_ops)

            save_points = _compute_save_points(bakeable_ops)
            if not save_points:
                continue

            original_source = obj.source
            dur = self._checkpoint_bake_duration(obj, original_source)
            fps = self.fps
            self._require_morph_duration(bakeable_ops, dur, original_source)
            current_source = original_source
            current_media_type = obj.media_type

            sorted_sps = sorted(save_points)
            for sp_idx in sorted_sps:
                segment_ops = bakeable_ops[:sp_idx + 1]
                has_effects = any(t == "effect" for t, _ in segment_ops)
                is_video = _detect_media_type(original_source) in ("video",)
                cp_dur = dur if (has_effects or is_video) else None
                cp_fps = fps if cp_dur is not None else None
                sp_typ, sp_op = bakeable_ops[sp_idx]
                quality = getattr(sp_op, 'quality', 'final')

                # current_sourceの解決（前の保存点からの更新）
                prev_sps = [j for j in sorted_sps if j < sp_idx]
                if prev_sps:
                    prev_sp_idx = prev_sps[-1]
                    prev_sp_typ, prev_sp_op = bakeable_ops[prev_sp_idx]
                    # 前の保存点がmorph_toの場合
                    if prev_sp_typ == "effect" and prev_sp_op.name == "morph_to" and hasattr(prev_sp_op, '_morph_target'):
                        current_source = _morph_cache_path(
                            current_source, prev_sp_op, dur, fps,
                            getattr(prev_sp_op, 'quality', 'final'))
                    else:
                        prev_seg = bakeable_ops[:prev_sp_idx + 1]
                        prev_has_eff = any(t == "effect" for t, _ in prev_seg)
                        prev_is_video = _detect_media_type(original_source) in ("video",)
                        current_source = _checkpoint_cache_path(
                            original_source, prev_seg,
                            dur if (prev_has_eff or prev_is_video) else None,
                            fps if (prev_has_eff or prev_is_video) else None,
                            getattr(prev_sp_op, 'quality', 'final'))
                    current_media_type = _detect_media_type(current_source)

                # morph_to 分岐
                if sp_typ == "effect" and sp_op.name == "morph_to" and hasattr(sp_op, '_morph_target'):
                    # morph直前の未ベイクopsの中間チェックポイントコマンドも収集
                    # （実レンダの_process_checkpointsと同じ経路）
                    pre_start = prev_sps[-1] + 1 if prev_sps else 0
                    pre_ops = bakeable_ops[pre_start:sp_idx]
                    if pre_ops:
                        pre_segment = bakeable_ops[:sp_idx]
                        pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                        pre_dur = dur if (pre_has_effects or is_video) else None
                        pre_fps = fps if pre_dur is not None else None
                        pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                        pre_path = _checkpoint_cache_path(
                            original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                        pre_transforms = [o for t, o in pre_ops if t == "transform"]
                        pre_effects = [o for t, o in pre_ops if t == "effect"]
                        if pre_dur is None:
                            pre_cmd = self._build_checkpoint_image_cmd(
                                current_source, pre_transforms, pre_path, pre_quality)
                        else:
                            pre_cmd = self._build_checkpoint_video_cmd(
                                current_source, current_media_type,
                                pre_transforms, pre_effects,
                                pre_path, pre_dur, fps, pre_quality)
                        cmds[pre_path] = pre_cmd
                        current_source = pre_path
                        current_media_type = _detect_media_type(pre_path)
                    # 動画ソースは最終フレームPNG抽出を挟む（実レンダと同じ経路）
                    if _detect_media_type(current_source) == "video":
                        frame_path = _morph_input_frame_path(current_source)
                        cmds[frame_path] = _build_morph_frame_extract_cmd(
                            current_source, frame_path)
                        current_source = frame_path
                        current_media_type = "image"
                    morph_path = _morph_cache_path(current_source, sp_op, dur, fps, quality)
                    frame_pattern = os.path.join("__morph_frames__", "frame_%05d.png")
                    cmd = self._build_morph_webm_cmd(
                        frame_pattern, morph_path, dur, fps, quality)
                    cmds[morph_path] = cmd
                elif sp_typ == "effect" and sp_op.name in ("explode_to", "assemble_from"):
                    # 粒子Effect分岐（実レンダの_process_checkpointsと同じ経路）
                    if sp_op.name == "explode_to":
                        pre_start = prev_sps[-1] + 1 if prev_sps else 0
                        pre_ops = bakeable_ops[pre_start:sp_idx]
                        if pre_ops:
                            pre_segment = bakeable_ops[:sp_idx]
                            pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                            pre_dur = dur if (pre_has_effects or is_video) else None
                            pre_fps = fps if pre_dur is not None else None
                            pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                            pre_path = _checkpoint_cache_path(
                                original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                            pre_transforms = [o for t, o in pre_ops if t == "transform"]
                            pre_effects = [o for t, o in pre_ops if t == "effect"]
                            if pre_dur is None:
                                pre_cmd = self._build_checkpoint_image_cmd(
                                    current_source, pre_transforms, pre_path, pre_quality)
                            else:
                                pre_cmd = self._build_checkpoint_video_cmd(
                                    current_source, current_media_type,
                                    pre_transforms, pre_effects,
                                    pre_path, pre_dur, fps, pre_quality)
                            cmds[pre_path] = pre_cmd
                            current_source = pre_path
                            current_media_type = _detect_media_type(pre_path)
                        img_path = current_source
                    else:  # assemble_from
                        img_path = sp_op._assemble_source.source
                    if _detect_media_type(img_path) == "video":
                        frame_path = _morph_input_frame_path(img_path)
                        cmds[frame_path] = _build_morph_frame_extract_cmd(
                            img_path, frame_path)
                        img_path = frame_path
                    part_path = _particle_cache_path(img_path, sp_op, dur, fps, quality)
                    frame_pattern = os.path.join("__particle_frames__", "frame_%05d.png")
                    cmds[part_path] = self._build_morph_webm_cmd(
                        frame_pattern, part_path, dur, fps, quality)
                else:
                    cache_path = _checkpoint_cache_path(
                        original_source, segment_ops, cp_dur, cp_fps, quality)

                    local_ops_start = 0
                    if prev_sps:
                        local_ops_start = prev_sps[-1] + 1

                    local_ops = bakeable_ops[local_ops_start:sp_idx + 1]
                    local_transforms = [op for t, op in local_ops if t == "transform"]
                    local_effects = [op for t, op in local_ops if t == "effect"]

                    if cp_dur is None:
                        cmd = self._build_checkpoint_image_cmd(
                            current_source, local_transforms, cache_path, quality)
                    else:
                        cmd = self._build_checkpoint_video_cmd(
                            current_source, current_media_type,
                            local_transforms, local_effects,
                            cache_path, cp_dur, fps, quality)
                    cmds[cache_path] = cmd

            # Object source差し替え（最後の保存点）
            last_sp = sorted_sps[-1]
            last_typ, last_op = bakeable_ops[last_sp]
            if last_typ == "effect" and last_op.name == "morph_to" and hasattr(last_op, '_morph_target'):
                last_path = _morph_cache_path(
                    current_source, last_op, dur, fps,
                    getattr(last_op, 'quality', 'final'))
            elif last_typ == "effect" and last_op.name in ("explode_to", "assemble_from"):
                if last_op.name == "assemble_from":
                    img_path = last_op._assemble_source.source
                else:
                    img_path = current_source
                if _detect_media_type(img_path) == "video":
                    img_path = _morph_input_frame_path(img_path)
                last_path = _particle_cache_path(
                    img_path, last_op, dur, fps,
                    getattr(last_op, 'quality', 'final'))
            else:
                last_seg = bakeable_ops[:last_sp + 1]
                last_has_eff = any(t == "effect" for t, _ in last_seg)
                last_is_video = _detect_media_type(original_source) in ("video",)
                last_path = _checkpoint_cache_path(
                    original_source, last_seg,
                    dur if (last_has_eff or last_is_video) else None,
                    fps if (last_has_eff or last_is_video) else None,
                    getattr(last_op, 'quality', 'final'))
            # 差し替え前に解決した実長を保持（未生成予定パスへのprobe fallback防止）。
            # live 時間系Effect（speed/freeze_frame）が残る場合は表示尺に換算する
            if dur:
                obj._resolved_length = _apply_time_effects_to_duration(
                    dur, [op for t, op in live_ops if t == "effect"])
            obj.source = last_path
            obj.media_type = _detect_media_type(last_path)
            remaining = bakeable_ops[last_sp + 1:]
            obj.transforms = [op for t, op in remaining if t == "transform"]
            obj.effects = ([op for t, op in remaining if t == "effect"]
                           + [op for t, op in live_ops if t == "effect"])

        return cmds

    def _collect_web_cmds(self):
        """dry_run用: web Objectのwebmエンコードコマンドを収集"""
        cmds = {}
        for obj in self.objects:
            if isinstance(obj, Object) and obj.media_type == "web":
                webm_path = _web_cache_path(obj, self)
                cmds[webm_path] = obj._build_web_cmd(self, webm_path)
        return cmds

    def _ensure_web_objects(self):
        """web ObjectのPlaywrightレンダ+ffmpegエンコード実行、sourceをwebmに差し替え"""
        for obj in self.objects:
            if not isinstance(obj, Object) or obj.media_type != "web":
                continue
            webm_path = _web_cache_path(obj, self)
            name = obj._web_name
            cache_dir = os.path.join(_CACHE_DIR, "webclip")
            frames_dir = os.path.join(cache_dir, f"{name}_frames")

            if not os.path.exists(webm_path):
                print(f"Webクリップ生成: {obj.source}")
                try:
                    obj._render_web_frames(self)
                    cmd = obj._build_web_cmd(self, webm_path)
                    os.makedirs(os.path.dirname(webm_path), exist_ok=True)
                    print(f"  ffmpeg {' '.join(cmd[1:])}")
                    _run_ffmpeg_to_cache(cmd, webm_path, timeout=600)
                    print(f"  完了: {webm_path}")
                finally:
                    # フレーム削除（失敗時も中間フレームを残さない）
                    if not obj._web_debug_frames and os.path.exists(frames_dir):
                        import shutil
                        shutil.rmtree(frames_dir, ignore_errors=True)

            obj.source = webm_path
            obj.media_type = "video"

    def _parallel_workers(self):
        """キャッシュ並列生成のワーカ数を決定（configure(parallel=N)優先、既定は控えめ）"""
        if self._parallel is not None:
            return _builtins.max(1, int(self._parallel))
        cpu = os.cpu_count() or 2
        # ffmpeg自体がマルチスレッドのため控えめに（CPU数-1、上限4）
        return _builtins.max(1, _builtins.min(cpu - 1, 4))

    def _generate_pending_caches(self):
        """レイヤーキャッシュ生成を実行（独立レイヤーは ThreadPoolExecutor で並列）"""
        pending = [i for i, spec in enumerate(self._layer_specs)
                   if spec["cache"] == "make"]
        if not pending:
            return
        workers = _builtins.min(self._parallel_workers(), len(pending))
        if workers <= 1 or len(pending) == 1:
            for i in pending:
                self._render_layer_to_cache(i)
            return
        # 各レイヤーキャッシュは独立（相互に入力参照しない）ため並列化して差し支えない
        print(f"レイヤーキャッシュを並列生成: {len(pending)}件 (workers={workers})")
        errors = []
        with _futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._render_layer_to_cache, i): i for i in pending}
            for fut in _futures.as_completed(futs):
                try:
                    fut.result()
                except Exception as e:  # 1件失敗しても他の結果は確定させる
                    errors.append((futs[fut], e))
        if errors:
            i, e = errors[0]
            raise RuntimeError(
                f"レイヤーキャッシュ生成に失敗しました "
                f"({self._layer_specs[i]['filename']}): {e}") from e

    def _build_layer_cache_cmd(self, spec_index, webm_path):
        """レイヤーキャッシュ用ffmpegコマンド（透明webm VP9 alpha）

        webm_path: 出力先パス。呼び出し側で計算して渡す
        （_layer_cache_pathsはFFP依存のため、二重計算するとレイヤーファイルの
        mtime変化等で構築時と実行時のパスが食い違うおそれがある）。
        """
        spec = self._layer_specs[spec_index]
        objects, anchors = self._get_layer_data(spec_index)
        # 本レンダと同じく priority ソート + 映像を持つオブジェクトのみ合成
        renderable = sorted(
            [o for o in objects if isinstance(o, Object) and o.has_video],
            key=lambda o: o.priority)
        # レイヤーキャッシュは映像のみ保存するため、音声を含むレイヤーは明示警告
        audio_sources = [o.source for o in objects
                         if isinstance(o, Object) and o.has_audio]
        if audio_sources:
            warnings.warn(
                f"レイヤーキャッシュ ({spec['filename']}) は映像のみ保存します。"
                f"以下の音声はキャッシュ再生時に脱落します: {', '.join(audio_sources)}\n"
                f"回避策: 音声を持つ素材は cache を付けない別レイヤーに分離してください"
                f"（透過VP9への音声多重化はレイヤー内amix/adelay/duck_underの"
                f"再現が必要で本ウェーブでは見送り）。")

        dur = self.duration or self._calc_total_duration()

        inputs = []
        filter_parts = []

        # 入力0: 透明キャンバス
        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={self.width}x{self.height}:d={dur}:r={self.fps},format=rgba",
        ])

        current_base = "[0:v]"

        for i, obj in enumerate(renderable):
            input_idx = i + 1
            inputs.extend(_build_input_args(obj, self.fps))
            # 本レンダと同じ解決ロジックでu正規化の分母を統一
            # （レイヤー全体尺fallbackだとcache有無でアニメ速度が変わる）
            obj_dur = self._resolve_obj_duration(obj)
            parts, out_label = _build_video_overlay_parts(
                obj, input_idx, current_base, obj_dur)
            filter_parts.extend(parts)
            current_base = out_label

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", current_base])

        cmd.extend([
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "0",
            "-crf", "30",
            "-auto-alt-ref", "0",
            "-t", str(dur),
            webm_path,
        ])
        return cmd

    def _render_layer_to_cache(self, spec_index):
        """レイヤーキャッシュ生成実行"""
        spec = self._layer_specs[spec_index]
        webm_path, json_path = _layer_cache_paths(spec["filename"], self)
        os.makedirs(os.path.dirname(webm_path), exist_ok=True)

        cmd = self._build_layer_cache_cmd(spec_index, webm_path)
        print(f"キャッシュ生成: {webm_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        _run_ffmpeg_to_cache(cmd, webm_path, timeout=600)
        print(f"  完了: {webm_path}")

        # anchors.json書き出し（素材FFPも記録してキャッシュ鮮度検証に使う）
        objects, anchors = self._get_layer_data(spec_index)
        dur = self.duration or self._calc_total_duration()
        sources_meta = {}
        for src in self._layer_sources.get(spec["filename"], []):
            try:
                ffp = _file_fingerprint(src)
                sources_meta[ffp[0]] = [ffp[1], ffp[2]]
            except OSError:
                pass
        cache_meta = {"duration": dur, "anchors": anchors, "sources": sources_meta}
        # アトミック書き込み（webmと同様、中断による壊れたメタの残留を防ぐ）
        tmp_json = f"{json_path}.tmp"
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(cache_meta, f, indent=2, ensure_ascii=False)
        os.replace(tmp_json, json_path)
        print(f"  アンカー保存: {json_path}")

    def _loop_trim_duration(self, obj, loop_effect):
        """loop(until=...) の実効トリム尺を返す（until優先→duration→全体尺）"""
        start = obj.start_time
        until = loop_effect.params.get("until")
        if until is not None:
            return max(0.0, until - start)
        if obj.duration is not None:
            return obj.duration
        total = self.duration or self._calc_total_duration()
        return max(0.0, total - start)

    def _build_aloop_filter(self, obj, loop_effect):
        """aloop フィルタ文字列を構築（元素材長からループ用サンプル数を決定）。
        aloopは無限ループ(loop=-1)し、後段のatrim/durationで尺を確定する。"""
        length = _probe_audio_length(obj.source)
        # 実サンプルレートを取得（高SR素材でも1周期分を確実に確保するため）。
        info = self._probe_media(obj.source)
        sr = info.get("sample_rate") if info else None
        if length and sr:
            size = int(_math.ceil(length * sr)) + sr
        elif length:
            # SR不明時は大きめ（192kHz相当）で1周期分＋余裕を確保
            size = int(_math.ceil(length * 192000)) + 192000
        else:
            size = 192000 * 60  # 取得不能時のフォールバック（約1分・192kHz相当）
        return f"aloop=loop=-1:size={size}"

    def _resolve_obj_duration(self, obj, fallback=5):
        """objのduration未設定/0のとき実長で補完（取得不能・0のときのみfallback）

        duration=0 をそのまま返すと u正規化 clip((t-start)/0,...) のゼロ除算で
        ffmpegがEINVAL失敗するため、0はfallbackに落とす。
        """
        if obj.duration:
            return obj.duration
        # checkpoint等でsourceが予定パスに差し替わる前に解決した実長を最優先
        resolved = getattr(obj, '_resolved_length', None)
        if resolved:
            return resolved
        if obj.media_type not in ("image", "text"):
            # trim/atrim/atempoを反映した加工後長（チェックポイントベイクと同一基準）
            try:
                length = obj.length()
            except Exception:
                return fallback
            if length:
                return length
        return fallback

    def _resolve_output_format(self, output_path):
        """出力パスの拡張子・draft/alpha/thumbnail設定から出力形式を決定する。

        戻り値 dict:
          kind:  "h264" | "gif" | "webp" | "pngseq" | "webm" | "thumb"
          alpha: 背景を透過にするか
          has_audio: この形式が音声トラックを持てるか
          output_path: 実際にffmpegへ渡す出力パス（連番PNGは %05d 化）
        """
        alpha = bool(getattr(self, "_alpha", False))
        if getattr(self, "_thumbnail_at", None) is not None:
            return {"kind": "thumb", "alpha": False, "has_audio": False,
                    "output_path": output_path}
        ext = os.path.splitext(output_path)[1].lower()
        if ext == ".gif":
            return {"kind": "gif", "alpha": False, "has_audio": False,
                    "output_path": output_path}
        if ext == ".webp":
            return {"kind": "webp", "alpha": alpha, "has_audio": False,
                    "output_path": output_path}
        if ext == ".png":
            # 連番PNG（out.png -> out_%05d.png）。既に%が含まれるなら尊重
            op = output_path
            if "%" not in op:
                base, _e = os.path.splitext(output_path)
                op = f"{base}_%05d.png"
            return {"kind": "pngseq", "alpha": True, "has_audio": False,
                    "output_path": op}
        if ext == ".webm":
            return {"kind": "webm", "alpha": alpha, "has_audio": True,
                    "output_path": output_path}
        return {"kind": "h264", "alpha": alpha, "has_audio": True,
                "output_path": output_path}

    def _build_ffmpeg_cmd(self, output_path):
        inputs = []
        filter_parts = []
        fmt = self._resolve_output_format(output_path)
        output_path = fmt["output_path"]

        # 背景入力（alpha出力時は透明キャンバス）
        if fmt["alpha"]:
            bg_src = (f"color=c=black@0.0:s={self.width}x{self.height}"
                      f":d={self.duration}:r={self.fps},format=rgba")
        else:
            bg_src = (f"color=c={self.background_color}:s={self.width}x{self.height}"
                      f":d={self.duration}:r={self.fps}")
        inputs.extend(["-f", "lavfi", "-i", bg_src])

        renderable = [o for o in self.objects if isinstance(o, Object)]
        sorted_objects = sorted(renderable, key=lambda o: o.priority)

        # 入力を追加（映像+音声共通）
        input_map = {}  # obj id → input_idx
        for i, obj in enumerate(sorted_objects):
            input_idx = i + 1
            input_map[id(obj)] = input_idx
            inputs.extend(_build_input_args(obj, self.fps))

        # --- 映像チェーン ---
        current_base = "[0:v]"
        video_objects = [o for o in sorted_objects if o.has_video]

        for obj in video_objects:
            input_idx = input_map[id(obj)]
            dur = self._resolve_obj_duration(obj)
            parts, out_label = _build_video_overlay_parts(
                obj, input_idx, current_base, dur)
            filter_parts.extend(parts)
            current_base = out_label

        # --- 音声チェーン ---
        audio_objects = [o for o in sorted_objects if o.has_audio]
        audio_out = None

        if audio_objects:
            audio_labels = []
            idx_by_id = {}  # id(obj) → audio_labels内index（duck_underのother参照用）
            for ai, obj in enumerate(audio_objects):
                idx_by_id[id(obj)] = ai
                input_idx = input_map[id(obj)]
                dur = self._resolve_obj_duration(obj)
                start = obj.start_time

                a_filters = []
                # loop（aloop）: atrim/adelayより前に置き、以降のトリムで尺を確定
                loop_effect = next(
                    (e for e in obj.audio_effects if e.name == "loop"), None)
                if loop_effect is not None:
                    a_filters.append(self._build_aloop_filter(obj, loop_effect))
                # atrim/atempo前処理
                a_pre = _build_audio_pre_filters(obj)
                # auto atrim: obj.durationがあり、明示atrimがなければ自動トリム
                has_explicit_atrim = any(
                    e.name == "atrim" for e in obj.audio_effects)
                if not has_explicit_atrim and obj.duration is not None:
                    a_pre = [f"atrim=duration={obj.duration}",
                             "asetpts=PTS-STARTPTS"] + a_pre
                # loop で until 指定かつ obj.duration 未設定なら until までトリム
                if (loop_effect is not None and not has_explicit_atrim
                        and obj.duration is None):
                    lt = self._loop_trim_duration(obj, loop_effect)
                    a_pre = [f"atrim=duration={lt}", "asetpts=PTS-STARTPTS"] + a_pre
                a_filters.extend(a_pre)
                # 音声エフェクト（again/afade）
                a_filters.extend(_build_audio_effect_filters(obj, dur))
                # adelay（タイミングシフト）: all=1 で全チャンネルに適用（2ch前提を排除）
                delay_ms = int(start * 1000)
                if delay_ms > 0:
                    a_filters.append(f"adelay={delay_ms}:all=1")

                a_label = f"[a{ai}]"
                if a_filters:
                    filter_parts.append(
                        f"[{input_idx}:a]{','.join(a_filters)}{a_label}"
                    )
                else:
                    a_label = f"[{input_idx}:a]"
                audio_labels.append(a_label)

            # duck_under（sidechaincompress）: other音声再生中に自音量を下げる。
            # otherをasplitでミックス用/サイドチェーン用に分岐して供給する。
            for ai, obj in enumerate(audio_objects):
                duck = next(
                    (e for e in obj.audio_effects if e.name == "duck_under"), None)
                if duck is None:
                    continue
                other = duck.params["other"]
                if other is obj:
                    raise ValueError("duck_under: other に自分自身は指定できません")
                if id(other) not in idx_by_id:
                    raise ValueError(
                        "duck_under: other が同じProjectの再生対象音声に含まれていません。"
                        "other 側の音声が adelete 等で除外されていないか確認してください。")
                oi = idx_by_id[id(other)]
                other_ref = audio_labels[oi]
                filter_parts.append(
                    f"{other_ref}asplit[dmix{ai}][dside{ai}]")
                audio_labels[oi] = f"[dmix{ai}]"
                my_ref = audio_labels[ai]
                p = duck.params
                filter_parts.append(
                    f"{my_ref}[dside{ai}]sidechaincompress="
                    f"threshold={p['threshold']}:ratio={p['ratio']}"
                    f":attack={p['attack']}:release={p['release']}[duck{ai}]")
                audio_labels[ai] = f"[duck{ai}]"

            if len(audio_labels) == 1:
                audio_out = audio_labels[0]
                # フィルタなしの生入力参照（[N:a]）はフィルタグラフのラベルではないため、
                # -map にはブラケットを外したストリーム指定（N:a）で渡す
                inner = audio_out[1:-1]
                if audio_out.startswith("[") and inner.endswith(":a") \
                        and inner[:-2].isdigit():
                    audio_out = inner
            else:
                amix_in = "".join(audio_labels)
                audio_out = "[aout]"
                filter_parts.append(
                    f"{amix_in}amix=inputs={len(audio_labels)}:normalize=0{audio_out}"
                )

            # normalize_audio（loudnorm）: 最終音声にラウドネス正規化を適用
            if self._loudnorm_target is not None and audio_out is not None:
                ln_in = audio_out if audio_out.startswith("[") else f"[{audio_out}]"
                filter_parts.append(
                    f"{ln_in}loudnorm=I={self._loudnorm_target}:TP=-1.5:LRA=11[aout_ln]")
                audio_out = "[aout_ln]"

        # 出力前の映像後処理（draft縮小・GIFパレット生成）
        video_map = current_base
        if getattr(self, "_draft", False):
            # ドラフト: 解像度を半分に（幾何は保持、偶数寸法に丸め）
            filter_parts.append(
                f"{video_map}scale=trunc(iw/4)*2:trunc(ih/4)*2[vdraft]")
            video_map = "[vdraft]"
        if fmt["kind"] == "gif":
            # 高品質パレット: split→palettegen→paletteuse を1グラフで実行
            filter_parts.append(
                f"{video_map}split[gsrc][gpg];"
                f"[gpg]palettegen=stats_mode=diff[gpal];"
                f"[gsrc][gpal]paletteuse=dither=bayer:bayer_scale=5"
                f":diff_mode=rectangle[vgif]")
            video_map = "[vgif]"

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        # チャプター: FFMETADATAを追加入力にして -map_metadata で埋め込む
        meta_idx = None
        emit_meta = bool(self._markers) and fmt["has_audio"]
        if emit_meta:
            meta_path = self._chapters_metadata_path()
            if not getattr(self, "_dry_run", False):
                self._write_chapters_metadata(meta_path)
            # メタ入力のストリーム index = 既存 -i 個数（color 1 + オブジェクト入力数）
            meta_idx = 1 + len(sorted_objects)
            cmd.extend(["-f", "ffmetadata", "-i", meta_path])

        use_audio = bool(audio_out) and fmt["has_audio"]
        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", video_map])
            if use_audio:
                cmd.extend(["-map", audio_out])

        if meta_idx is not None:
            cmd.extend(["-map_metadata", str(meta_idx)])

        # --- 出力形式ごとのエンコード指定 ---
        cmd.extend(self._encode_args(fmt, use_audio))

        # thumbnail: 単一フレーム抽出（-ss + -frames:v 1、-update で単一画像出力）
        if fmt["kind"] == "thumb":
            cmd.extend(["-ss", str(self._thumbnail_at), "-frames:v", "1",
                        "-update", "1", output_path])
            return cmd

        # 部分レンダ: 出力側 -ss/-t で窓を切り出す（フィルタのt基準は保つ）
        window = getattr(self, "_render_window", None)
        if window is not None:
            w_start, w_end = window
            w_end = self.duration if w_end is None else min(w_end, self.duration)
            out_dur = max(0.0, w_end - w_start)
            if w_start > 0:
                cmd.extend(["-ss", str(w_start)])
            cmd.extend(["-t", str(out_dur), output_path])
        else:
            cmd.extend(["-t", str(self.duration), output_path])

        return cmd

    def _encode_args(self, fmt, use_audio):
        """出力形式に応じた -c:v / -pix_fmt / -c:a 等のエンコード引数を返す"""
        kind = fmt["kind"]
        draft = bool(getattr(self, "_draft", False))
        args = []
        if kind == "thumb":
            return ["-pix_fmt", "rgba", "-an"]
        if kind == "gif":
            # パレット適用済みなのでコーデック指定は不要。音声なし。
            return ["-an"]
        if kind == "webp":
            q = "60" if draft else "80"
            return ["-c:v", "libwebp", "-lossless", "0", "-q:v", q,
                    "-loop", "0", "-an"]
        if kind == "pngseq":
            return ["-c:v", "png", "-pix_fmt", "rgba", "-an"]
        if kind == "webm":
            pix = "yuva420p" if fmt["alpha"] else "yuv420p"
            crf = "34" if draft else "24"
            args = ["-c:v", "libvpx-vp9", "-pix_fmt", pix,
                    "-b:v", "0", "-crf", crf, "-auto-alt-ref", "0"]
            if use_audio:
                args.extend(["-c:a", "libopus"])
            else:
                args.append("-an")
            return args
        # h264 / 指定エンコーダ（yuv420p固定・透過非対応コンテナ）
        if getattr(self, "_alpha", False):
            raise ValueError(
                f"alpha=True は透過対応の出力(.webm/.webp/.png)でのみ有効です。\n"
                f"現在の出力形式({kind})では yuv420p 固定のため透明背景が黒潰れします。\n"
                f"透過が必要なら .webm / .webp / 連番.png で出力してください。")
        args = ["-c:v", self._encoder_cv]
        if draft:
            args.extend(self._encoder_draft_args)
        else:
            args.extend(self._encoder_args)
        args.extend(["-pix_fmt", "yuv420p"])
        if use_audio:
            args.extend(["-c:a", "aac"])
        else:
            args.append("-an")
        return args


# --- メディア情報ヘルパー ---

def _get_media_dimensions(filepath):
    """メディアの幅・高さを取得 (ffprobe)"""
    if _is_pending_cache_path(filepath):
        # dry_run中の未生成キャッシュ予定パスはprobeしない（警告スパム防止）
        return None, None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", filepath],
            capture_output=True, text=True, check=True, timeout=10)
        parts = result.stdout.strip().split(',')
        return int(parts[0]), int(parts[1])
    except FileNotFoundError:
        warnings.warn(f"ffprobeが見つかりません。PATHを確認してください。")
        return None, None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        warnings.warn(f"メディアサイズの取得に失敗 ({filepath}): {e}")
        return None, None
    except (ValueError, IndexError) as e:
        warnings.warn(f"ffprobe出力のパースに失敗 ({filepath}): {e}")
        return None, None


def _get_base_dimensions(obj):
    """オブジェクトのscaleエフェクト適用前の基底サイズを取得

    resizeに加えてcrop/pad/rotate(expand)のサイズ変化も反映する
    （scaleエフェクトのpadサイズ過小による実行時エラーを防ぐ）。
    """
    if getattr(obj, "media_type", None) == "text":
        # テキスト系はキャンバス全面（Project解像度）を基底サイズとする
        proj = Project._current
        if proj is not None:
            return proj.width, proj.height
        return None, None
    src_w, src_h = _get_media_dimensions(obj.source)
    if src_w is None:
        return None, None
    for t in obj.transforms:
        if t.name == "resize":
            sx = t.params.get("sx", 1)
            sy = t.params.get("sy", 1)
            src_w = int(src_w * sx)
            src_h = int(src_h * sy)
        elif t.name in ("crop", "pad"):
            # w/h が式文字列等の非数値ならサイズ反映をスキップ（従来挙動へフォールバック）
            try:
                new_w = int(t.params["w"])
                new_h = int(t.params["h"])
            except (TypeError, ValueError):
                continue
            src_w, src_h = new_w, new_h
        elif t.name == "rotate" and t.params.get("expand"):
            # 静的角度なら expand 後の外接矩形サイズを反映
            ang = t.params.get("rad")
            try:
                a = ang.eval_at(0) if isinstance(ang, Expr) else float(ang)
            except Exception:
                continue
            c = _builtins.abs(_math.cos(a))
            s = _builtins.abs(_math.sin(a))
            new_w = int(_math.ceil(src_w * c + src_h * s))
            new_h = int(_math.ceil(src_w * s + src_h * c))
            src_w, src_h = new_w, new_h
        elif t.name == "grid":
            cols = t.params["cols"]
            rows = t.params["rows"]
            gap = t.params.get("gap", 0)
            src_w = src_w * cols + gap * (cols - 1)
            src_h = src_h * rows + gap * (rows - 1)
    return src_w, src_h


# --- フィルタ生成ヘルパー ---

def _decoder_input_args(source, media_type, fps):
    """メディア種別に応じたffmpeg入力デコーダ引数を構築（全経路共通）

    本レンダ/レイヤーキャッシュ/チェックポイント/computeで共通利用し、
    webmデコーダ判定等の重複と乖離を防ぐ。
    """
    if media_type == "image":
        return ["-loop", "1", "-r", str(fps), "-i", source]
    if media_type != "audio" and source.lower().endswith(".webm"):
        # WebM(VP9 alpha)はlibvpx-vp9デコーダが必要
        # (ffmpeg 8.0のネイティブVP9デコーダはalpha非対応)
        return ["-c:v", "libvpx-vp9", "-i", source]
    return ["-i", source]


def _build_input_args(obj, fps):
    """メディア種別に応じたffmpeg入力引数を構築（本レンダ/レイヤーキャッシュ共通）"""
    if obj.media_type == "text":
        # テキスト系は実体ファイルを持たず、透明lavfiキャンバスを入力にする。
        # drawtext/subtitles は _build_video_overlay_parts でpre-filterとして重畳。
        proj = Project._current
        w = proj.width if proj else 1920
        h = proj.height if proj else 1080
        d = obj.duration or getattr(obj, "_resolved_length", None)
        if d is None and getattr(obj, "_text_spec", {}).get("kind") == "progress_bar":
            # progress_bar は duration 未設定で動画全体に表示するため、
            # 入力キャンバスも全体尺で生成する（5s固定だとEOF後にバーが消える）
            d = proj.duration if proj and proj.duration else None
        d = d or 5
        return ["-f", "lavfi",
                "-i", f"color=c=black@0.0:s={w}x{h}:d={d}:r={fps},format=rgba"]
    return _decoder_input_args(obj.source, obj.media_type, fps)


def _build_video_overlay_parts(obj, input_idx, current_base, dur):
    """1オブジェクト分の映像フィルタチェーン + overlay行を構築
    （本レンダとレイヤーキャッシュで共通利用し、両経路の乖離を防ぐ）

    Returns: (filter_parts, out_label)
    """
    start = obj.start_time
    base_dims = _get_base_dimensions(obj)
    obj_filters = list(_build_video_pre_filters(obj, label_prefix=f"pre{input_idx}"))
    # ビデオ入力が start_time > 0 の場合、tpad で先頭にフレームを追加
    # (overlay有効化前にフレームが消費されるのを防ぐ)
    # trim/setpts の後に挿入し、trim がクローンフレーム込みで尺を切らないようにする
    if obj.media_type != "image" and start > 0:
        obj_filters.append(f"tpad=start_duration={start}:start_mode=clone")
    # テキスト系: tpad後（タイムライン時刻に整列した後）にdrawtext/subtitlesを重畳
    if obj.media_type == "text":
        obj_filters.extend(_build_text_filters(obj, start, dur))
    obj_filters.extend(_build_transform_filters(obj))
    eff_filters, pad_size = _build_effect_filters(
        obj, start, dur, base_dims=base_dims, label_prefix=f"fx{input_idx}")
    obj_filters.extend(eff_filters)
    obj_filters = _optimize_filter_chain(obj_filters)

    parts = []
    obj_label = f"[obj{input_idx}]"
    if obj_filters:
        parts.append(f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}")
    else:
        obj_label = f"[{input_idx}:v]"

    x_expr, y_expr = _build_move_exprs(obj, start, dur, pad_size=pad_size)

    enable_expr = None
    if obj.duration is not None:
        end = start + obj.duration
        enable_expr = f"between(t\\,{start}\\,{end})"
    enable_str = f":enable='{enable_expr}'" if enable_expr else ""

    out_label = f"[v{input_idx}]"
    blend_eff = next((e for e in obj.effects if e.name == "blend_mode"), None)
    if blend_eff is not None and blend_eff.params.get("mode") != "normal":
        # blend_mode: overlayフィルタは合成モード非対応のため、
        # このオブジェクトのみ「透明キャンバスへ通常overlayした全面フレーム」を
        # blend=cN_mode=<mode> でベースと合成し、オブジェクトのアルファ領域だけ
        # maskedmerge で採用する経路に切り替える。
        # （blendはアルファ非考慮のため、透明領域まで合成されるのを防ぐ）
        proj = Project._current
        cw = proj.width if proj else 1920
        ch = proj.height if proj else 1080
        cfps = proj.fps if proj else 30
        cdur = (proj.duration if proj and proj.duration else None) or (start + dur)
        mode = blend_eff.params["mode"]
        q = f"bm{input_idx}"
        # 1) 透明キャンバスへ通常overlay（位置/enableは通常経路と同一）
        parts.append(f"color=c=black@0.0:s={cw}x{ch}:r={cfps}:d={cdur}[{q}c]")
        parts.append(
            f"[{q}c]{obj_label}overlay={x_expr}:{y_expr}:eof_action=pass{enable_str},"
            f"format=rgba,split[{q}o1][{q}o2]")
        # 2) アルファ抽出（maskedmergeのマスク。gbrapに揃えて全plane一致）
        parts.append(f"[{q}o2]alphaextract,format=gbrap[{q}m]")
        parts.append(f"[{q}o1]format=gbrap[{q}oc]")
        # 3) 全面blend（obj=top, base=bottom。c3=アルファは指定せずtopを透過）
        parts.append(f"{current_base}format=gbrap,split[{q}b1][{q}b2]")
        parts.append(
            f"[{q}oc][{q}b1]blend=c0_mode={mode}:c1_mode={mode}:c2_mode={mode}[{q}bl]")
        # 4) オブジェクトのアルファ領域のみ合成結果を採用（enable外はベース素通し）
        merge_enable = f"=enable='{enable_expr}'" if enable_expr else ""
        parts.append(f"[{q}b2][{q}bl][{q}m]maskedmerge{merge_enable}{out_label}")
        return parts, out_label
    parts.append(
        f"{current_base}{obj_label}overlay={x_expr}:{y_expr}:eof_action=pass{enable_str}{out_label}"
    )
    return parts, out_label


def _build_transform_filters(obj):
    """Transform処理のフィルタリストを生成"""
    filters = []
    for t in obj.transforms:
        if t.name == "resize":
            sx = t.params.get("sx", 1)
            sy = t.params.get("sy", 1)
            filters.append(f"scale=iw*{sx}:ih*{sy}")
        elif t.name == "rotate":
            ang = t.params.get("rad")
            ang_str = ang.to_ffmpeg("u") if isinstance(ang, Expr) else str(ang)
            expand = t.params.get("expand", False)
            fill = t.params.get("fill", "0x00000000")
            filters.append("format=rgba")
            if expand:
                filters.append(
                    f"rotate=angle='{ang_str}':fillcolor={fill}"
                    f":ow='rotw({ang_str})':oh='roth({ang_str})'"
                )
            else:
                filters.append(
                    f"rotate=angle='{ang_str}':fillcolor={fill}:ow=iw:oh=ih"
                )
        elif t.name == "crop":
            x = t.params.get("x", 0)
            y = t.params.get("y", 0)
            w = t.params["w"]
            h = t.params["h"]
            filters.append(f"crop={w}:{h}:{x}:{y}")
        elif t.name == "pad":
            w = t.params["w"]
            h = t.params["h"]
            x = t.params.get("x", -1)
            y = t.params.get("y", -1)
            color = t.params.get("color", "black")
            x_str = "(ow-iw)/2" if x == -1 else str(x)
            y_str = "(oh-ih)/2" if y == -1 else str(y)
            filters.append(f"pad={w}:{h}:{x_str}:{y_str}:color={color}")
        elif t.name == "blur":
            r = t.params.get("radius", 5)
            filters.append(f"boxblur={r}:{r}")
        elif t.name == "eq":
            b = t.params.get("brightness", 0)
            c = t.params.get("contrast", 1)
            s = t.params.get("saturation", 1)
            g = t.params.get("gamma", 1)
            filters.append(f"eq=brightness={b}:contrast={c}:saturation={s}:gamma={g}")
        elif t.name == "grid":
            # 静止素材を cols×rows のグリッドに複製（背景パターン生成用）。
            # -loop 1 の入力は全フレームが同一なので、tile フィルタで
            # cols*rows フレームを並べると同一画像のグリッドになる。
            cols = t.params["cols"]
            rows = t.params["rows"]
            gap = t.params.get("gap", 0)
            filters.append(
                f"tile={cols}x{rows}:padding={gap}:margin=0:color=0x00000000")
    return filters


def _build_effect_filters(obj, start, dur, base_dims=None, label_prefix="fx"):
    """scale/fade等のeffectフィルタリストを生成（move/trim/delete以外）
    base_dims指定時、scaleエフェクトにpadを追加して固定サイズ出力にする。
    label_prefix: 複合フィルタ（split/blend等）の中間ラベル接頭辞。
    複数入力を扱う本レンダでは入力indexを含めて一意化する。
    Returns: (filters, pad_size) — pad_size は (max_w, max_h) or None

    注意: glow/drop_shadow/outline は split を含む複合サブグラフ文字列を
    1要素として返す（"split[a][b];[b]...[c];[a][c]blend=..." 形式）。
    カンマ結合されたチェーンに埋め込んでも有効な filtergraph になる。
    """
    filters = []
    pad_size = None
    for eff_idx, e in enumerate(obj.effects):
        if e.name in ("move", "trim", "delete", "morph_to", "shake",
                      "blend_mode", "speed", "reverse", "freeze_frame"):
            # blend_mode は overlay合成段（_build_video_overlay_parts）、
            # speed/reverse/freeze_frame は前処理（_build_video_pre_filters）で処理
            continue
        if e.name == "scale":
            scale_expr = e.params.get("value", Const(1))
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            ffmpeg_str = scale_expr.to_ffmpeg(u_expr)
            filters.append(
                f"scale=w='trunc(iw*({ffmpeg_str})/2)*2':h='trunc(ih*({ffmpeg_str})/2)*2':eval=frame"
            )
            # pad: scaleの出力を最大サイズの固定フレームに収め、overlay位置を安定化
            if base_dims and base_dims[0] is not None:
                bw, bh = base_dims
                # 定数スケールはサンプリング不要（101点評価の短絡）
                if isinstance(scale_expr, Const):
                    max_s = scale_expr.value
                else:
                    # 101点サンプリングで最大スケールを推定（中間ピークの取りこぼしを低減）
                    try:
                        max_s = _builtins.max(
                            scale_expr.eval_at(i / 100) for i in range(101))
                    except Exception as exc:
                        raise ValueError(
                            f"scale式を数値評価できないため、padサイズを決定できません: {exc}\n"
                            f"scale() には u のみに依存する数値評価可能な式を渡してください。"
                        ) from exc
                max_w = _math.ceil(bw * max_s / 2) * 2
                max_h = _math.ceil(bh * max_s / 2) * 2
                filters.append("format=rgba")
                filters.append(
                    f"pad={max_w}:{max_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000:eval=frame"
                )
                # SEGVバリア: FFmpeg 8.0では scale(eval=frame)+rotate の組み合わせで
                # SEGV(0xC0000005)が発生し、pad/format=rgba 単体では防げない。
                # copy フィルタによるバッファ分離が必要（検証済みの回避策）。
                filters.append("copy")
                pad_size = (max_w, max_h)
        elif e.name == "fade":
            alpha_expr = e.params.get("alpha", Const(1.0))
            filters.append("format=rgba")
            # ネイティブfadeを試行（geq比で10倍高速）
            native = _try_native_fade(alpha_expr, start, dur)
            if native:
                filters.extend(native)
            else:
                # 複雑なパターンはgeqにフォールバック
                u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
                ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
                filters.append(
                    f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({ffmpeg_str}\\,0\\,1)'"
                )
        elif e.name == "rotate_to":
            rad_expr = e.params.get("rad", Const(0))
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            ang_str = rad_expr.to_ffmpeg(u_expr)
            expand = e.params.get("expand", True)
            fill = e.params.get("fill", "0x00000000")
            filters.append("format=rgba")
            if expand:
                # 動的回転: ow/ohは初期化時に1度だけ評価されるため
                # rotw/rothではなく対角線長で固定サイズにする
                filters.append(
                    f"rotate=angle='{ang_str}':fillcolor={fill}"
                    f":ow='hypot(iw,ih)':oh='hypot(iw,ih)'"
                )
            else:
                filters.append(
                    f"rotate=angle='{ang_str}':fillcolor={fill}:ow=iw:oh=ih"
                )
        elif e.name == "wipe":
            prog_expr = e.params.get("progress", Const(1))
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            ffmpeg_str = prog_expr.to_ffmpeg(u_expr)
            direction = e.params.get("direction", "left")
            filters.append("format=rgba")
            if direction == "left":
                filters.append(f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='if(lte(X\\,W*({ffmpeg_str}))\\,alpha(X\\,Y)\\,0)'")
            elif direction == "right":
                filters.append(f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='if(gte(X\\,W*(1-({ffmpeg_str})))\\,alpha(X\\,Y)\\,0)'")
            elif direction == "up":
                filters.append(f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='if(gte(Y\\,H*(1-({ffmpeg_str})))\\,alpha(X\\,Y)\\,0)'")
            elif direction == "down":
                filters.append(f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='if(lte(Y\\,H*({ffmpeg_str}))\\,alpha(X\\,Y)\\,0)'")
        elif e.name == "color_shift":
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            parts = []
            if "hue" in e.params:
                h_str = e.params["hue"].to_ffmpeg(u_expr)
                parts.append(f"hue=h={h_str}")
            eq_parts = []
            if "saturation" in e.params:
                s_str = e.params["saturation"].to_ffmpeg(u_expr)
                eq_parts.append(f"saturation={s_str}")
            if "brightness" in e.params:
                b_str = e.params["brightness"].to_ffmpeg(u_expr)
                eq_parts.append(f"brightness={b_str}")
            for p in parts:
                filters.append(p)
            if eq_parts:
                filters.append("eq=" + ":".join(eq_parts))
        elif e.name == "chroma_key":
            color = e.params.get("color", "green")
            sim = e.params.get("similarity", 0.1)
            bl = e.params.get("blend", 0.0)
            filters.append(f"chromakey=color={color}:similarity={sim}:blend={bl}")
            # chromakeyはyuva出力 → 後段のgeq/overlay向けにrgbaへ正規化
            filters.append("format=rgba")
        elif e.name == "vignette":
            # 注意: vignetteフィルタはアルファ非対応（透明部分は失われる）。全画面素材向け。
            ang = e.params.get("angle", Const(_math.pi / 5))
            if isinstance(ang, Const):
                filters.append(
                    f"vignette=angle='clip({ang.to_ffmpeg('0')}\\,0\\,PI/2)'")
            else:
                # 時間依存式: eval=frame で毎フレーム評価（uは正規化時刻）
                u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
                filters.append(
                    f"vignette=angle='clip({ang.to_ffmpeg(u_expr)}\\,0\\,PI/2)':eval=frame")
        elif e.name == "pixelize":
            s = e.params.get("size", 16)
            filters.append(f"pixelize=w={s}:h={s}")
        elif e.name == "glow":
            # split→gblur→blend=screen の複合チェーン（発光合成）
            r = e.params.get("radius", 10)
            it = e.params.get("intensity", 1.0)
            p = f"{label_prefix}e{eff_idx}"
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]gblur=sigma={r}[{p}c];"
                f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={it}"
            )
        elif e.name == "lut":
            # lut3d: パスはフィルタグラフ用に / 区切り + ':' エスケープ
            lut_path = e.params["file"].replace("\\", "/").replace(":", "\\:")
            filters.append(f"lut3d=file='{lut_path}'")
        elif e.name == "glitch":
            # rgbashift + noise のプリセット。interval指定時は間欠発動
            strength = e.params.get("strength", 1.0)
            iv = e.params.get("interval")
            shift = _builtins.max(1, int(_builtins.round(4 * strength)))
            shift_v = _builtins.max(1, shift // 2)
            nstr = _builtins.min(100, _builtins.max(1, int(_builtins.round(20 * strength))))
            enable = ""
            if iv is not None:
                # 各interval周期の先頭30%区間のみ有効化
                on_dur = iv * 0.3
                enable = f":enable='lt(mod(t-{start}\\,{iv})\\,{on_dur})'"
            filters.append("format=rgba")
            filters.append(f"rgbashift=rh={shift}:bh=-{shift}:gv={shift_v}{enable}")
            filters.append(f"noise=alls={nstr}:allf=t+u{enable}")
        elif e.name == "perspective_warp":
            # sense=destination: 入力の4隅を指定座標へ移動（左上,右上,左下,右下）
            coords = ":".join(
                f"{k}={e.params[k]}"
                for k in ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"))
            filters.append(f"perspective={coords}:sense=destination")
        elif e.name == "lens":
            k1 = e.params.get("k1", 0)
            k2 = e.params.get("k2", 0)
            filters.append(f"lenscorrection=k1={k1}:k2={k2}")
        elif e.name == "ken_burns":
            # 動的scale + 固定サイズcrop で (x,y,w,h) 矩形間をパン&ズーム
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            s_str = e.params["s"].to_ffmpeg(u_expr)
            x_str = e.params["x"].to_ffmpeg(u_expr)
            y_str = e.params["y"].to_ffmpeg(u_expr)
            ow = e.params["w"]
            oh = e.params["h"]
            filters.append(
                f"scale=w='trunc(iw*({s_str})/2)*2':h='trunc(ih*({s_str})/2)*2':eval=frame")
            filters.append(f"crop={ow}:{oh}:x='{x_str}':y='{y_str}'")
            # SEGVバリア: scale(eval=frame)後のバッファ分離（既存scale実装と同じ回避策）
            filters.append("copy")
        elif e.name == "drop_shadow":
            # split→色付け+ぼかし→本体を影の上にoverlay（キャンバスは影が収まるよう拡張）
            dxv = e.params.get("dx", 5)
            dyv = e.params.get("dy", 5)
            bl = e.params.get("blur", 8)
            op_ = e.params.get("opacity", 0.5)
            cr, cg, cb = _parse_color_rgb(e.params.get("color", "black"))
            m = int(_math.ceil(3 * bl))  # gblurの裾野(約3σ)
            left = _builtins.max(0, m - dxv)
            right = _builtins.max(0, m + dxv)
            top = _builtins.max(0, m - dyv)
            bottom = _builtins.max(0, m + dyv)
            p = f"{label_prefix}e{eff_idx}"
            # ぼかしは pad の後に適用（端まで不透明な素材でも影が枠外へにじむように）
            blur_part = f",gblur=sigma={bl}" if bl > 0 else ""
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]geq=r='{cr}':g='{cg}':b='{cb}':a='alpha(X\\,Y)*{op_}',"
                f"pad=iw+{left + right}:ih+{top + bottom}:{left + dxv}:{top + dyv}:color=0x00000000"
                f"{blur_part}[{p}s];"
                f"[{p}s][{p}a]overlay={left}:{top}:eof_action=pass"
            )
            # scale等で固定サイズ化済み(pad_size設定済み)なら、影の拡張分を加算して
            # overlay中央配置((W-pad_size[0])/2)のずれを防ぐ
            if pad_size:
                pad_size = (pad_size[0] + left + right, pad_size[1] + top + bottom)
        elif e.name == "outline":
            # alpha膨張（dilationをwidth回連結）ベースの縁取り。
            # 色付けした複製のalphaを膨張させ、本体をその上にoverlayする。
            wd = e.params.get("width", 2)
            cr, cg, cb = _parse_color_rgb(e.params.get("color", "white"))
            p = f"{label_prefix}e{eff_idx}"
            dil = ",".join(["dilation"] * wd)
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]pad=iw+{2 * wd}:ih+{2 * wd}:{wd}:{wd}:color=0x00000000,"
                f"geq=r='{cr}':g='{cg}':b='{cb}':a='alpha(X\\,Y)',"
                f"{dil}[{p}o];"
                f"[{p}o][{p}a]overlay={wd}:{wd}:eof_action=pass"
            )
            # scale等で固定サイズ化済みなら、縁取りの拡張分(2*wd)を加算して中央配置ずれを防ぐ
            if pad_size:
                pad_size = (pad_size[0] + 2 * wd, pad_size[1] + 2 * wd)
        elif e.name == "mask":
            # 画像の輝度をアルファとして乗算。追加 -i 入力の配線を避けるため
            # movie= ソースをチェーン内サブグラフで読み込む。
            # マスクは scale2ref で素材サイズへ自動スケールし、
            # blend='A*B/255' で元アルファと乗算 → alphamerge で書き戻す。
            img = _escape_ffpath(e.params["image"])
            p = f"{label_prefix}e{eff_idx}"
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]alphaextract[{p}oa];"
                f"movie=filename={img}[{p}mi];"
                f"[{p}mi][{p}oa]scale2ref[{p}ms][{p}oa2];"
                f"[{p}ms]format=gray[{p}mg];"
                f"[{p}oa2][{p}mg]blend=all_expr='A*B/255':eof_action=repeat[{p}na];"
                f"[{p}a][{p}na]alphamerge"
            )
        elif e.name == "mask_wipe":
            # マスク画像の輝度をしきい値に使うワイプ
            # （輝度 <= progress*255 の画素から順に現れる）。
            # 注意: movie= の1フレーム入力をそのまま blend に渡すと
            # framesync の T 評価が壊れる（実測: 約5倍速で進行）ため、
            # loop+fps+setpts でメイン入力と同じタイムベースに正規化する。
            # 無限ループは全レンダ経路の -t 指定で確実に打ち切られる。
            prog_expr = e.params.get("progress", Const(1))
            u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
            prog_str = prog_expr.to_ffmpeg(u_expr)
            img = _escape_ffpath(e.params["image"])
            proj = Project._current
            m_fps = proj.fps if proj else 30
            p = f"{label_prefix}e{eff_idx}"
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]alphaextract[{p}oa];"
                f"movie=filename={img},loop=loop=-1:size=1,fps={m_fps},"
                f"setpts=N/({m_fps}*TB)[{p}mi];"
                f"[{p}mi][{p}oa]scale2ref[{p}ms][{p}oa2];"
                f"[{p}ms]format=gray[{p}mg];"
                f"[{p}oa2][{p}mg]blend="
                f"all_expr='if(lte(B\\,255*({prog_str}))\\,A\\,0)'"
                f":eof_action=repeat[{p}na];"
                f"[{p}a][{p}na]alphamerge"
            )
        elif e.name == "opacity":
            # 不透明度: 定数は colorchannelmixer（高速）、Expr は geq で live 変化
            val = e.params.get("value", Const(1.0))
            filters.append("format=rgba")
            if isinstance(val, Const):
                filters.append(f"colorchannelmixer=aa={val.value}")
            else:
                u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
                ffmpeg_str = val.to_ffmpeg(u_expr)
                filters.append(
                    f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)'"
                    f":a='alpha(X\\,Y)*clip({ffmpeg_str}\\,0\\,1)'"
                )
        elif e.name == "rounded":
            # 角丸: 角の中心からの距離が radius を超える画素のアルファを0に。
            # clip でX/Yを内側矩形にクランプ → 中央十字帯では距離0（常に表示）
            r = e.params["radius"]
            corner = (f"lte(hypot(X-clip(X\\,{r}\\,W-1-{r})\\,"
                      f"Y-clip(Y\\,{r}\\,H-1-{r}))\\,{r})")
            filters.append("format=rgba")
            filters.append(
                f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)'"
                f":a='alpha(X\\,Y)*{corner}'"
            )
        elif e.name == "blur_background_fill":
            # 縦動画変換の定番: ぼかした自分自身をキャンバス全面に敷き、
            # 中央に本体を fit で重ねる（出力はキャンバスサイズ固定）
            proj = Project._current
            cw = proj.width if proj else 1920
            ch = proj.height if proj else 1080
            sigma = e.params.get("blur", 20)
            p = f"{label_prefix}e{eff_idx}"
            filters.append("format=rgba")
            filters.append(
                f"split[{p}a][{p}b];"
                f"[{p}b]scale={cw}:{ch}:force_original_aspect_ratio=increase,"
                f"crop={cw}:{ch},gblur=sigma={sigma}[{p}bg];"
                f"[{p}a]scale={cw}:{ch}:force_original_aspect_ratio=decrease[{p}fg];"
                f"[{p}bg][{p}fg]overlay=(W-w)/2:(H-h)/2:eof_action=pass"
            )
            # 出力はキャンバスサイズ固定 → overlay中央配置の基準を更新
            pad_size = (cw, ch)
    return filters, pad_size


def _build_move_exprs(obj, start, dur, pad_size=None):
    """objのeffectsからmoveを探し、overlay用のx_expr/y_exprを返す
    pad_size: (max_w, max_h) padで固定サイズ化済みの場合、定数で位置を計算
    """
    move_effect = None
    for e in obj.effects:
        if e.name == "move":
            move_effect = e

    # pad_size指定時は定数でhalf計算（overlayが完全固定 or move式のみで決まる）
    if pad_size:
        half_w = str(pad_size[0] // 2)
        half_h = str(pad_size[1] // 2)
    else:
        half_w = "w/2"
        half_h = "h/2"

    if move_effect is None:
        # move なしでも shake は適用できるよう、中央配置をベースにして続行する
        x_result = f"(W-{pad_size[0]})/2" if pad_size else "(W-w)/2"
        y_result = f"(H-{pad_size[1]})/2" if pad_size else "(H-h)/2"
    else:
        p = move_effect.params
        anchor_val = p.get("anchor", "center")

        x_param = p.get("x", Const(0.5))
        y_param = p.get("y", Const(0.5))

        u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
        base_x = f"{x_param.to_ffmpeg(u_expr)}*W"
        base_y = f"{y_param.to_ffmpeg(u_expr)}*H"

        if anchor_val == "center":
            x_result = f"trunc({base_x}-{half_w})"
            y_result = f"trunc({base_y}-{half_h})"
        else:
            x_result = f"trunc({base_x})"
            y_result = f"trunc({base_y})"

    # shake Effect: overlay座標にsin/cosオフセットを加算
    shake_effect = None
    for e in obj.effects:
        if e.name == "shake":
            shake_effect = e
    if shake_effect:
        amp = shake_effect.params.get("amplitude", 0.02)
        freq = shake_effect.params.get("frequency", 10)
        u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
        x_shake = f"{amp}*W*sin({freq}*2*PI*{u_expr}+0.7)"
        y_shake = f"{amp}*H*cos({freq}*2.3*PI*{u_expr}+1.3)"
        x_result = f"trunc({x_result}+{x_shake})"
        y_result = f"trunc({y_result}+{y_shake})"

    return x_result, y_result


def _try_native_fade(alpha_expr, start, dur):
    """alpha式をサンプリングし、ffmpegネイティブfadeフィルタで近似を試みる。
    成功時はフィルタ文字列のリスト、失敗時はNoneを返す。
    ネイティブfadeはgeq比で10倍以上高速（Cの内部ループ）。"""
    N = 100
    samples = []
    try:
        for i in range(N + 1):
            samples.append(alpha_expr.eval_at(i / N))
    except Exception:
        return None

    # 中間領域が1.0近い標準的なfadeパターンかチェック
    mid = samples[N // 2]
    if mid < 0.95:
        return None  # 中間で不透明でない複雑パターン

    # fade-in区間を検出: alpha >= 0.99 の最初のサンプル位置
    fade_in_end_u = 0.0
    for i in range(N + 1):
        if samples[i] >= 0.99:
            fade_in_end_u = i / N
            break

    # fade-out区間を検出: alpha >= 0.99 の最後のサンプル位置
    fade_out_start_u = 1.0
    for i in range(N, -1, -1):
        if samples[i] >= 0.99:
            fade_out_start_u = i / N
            break

    # 値が途中で大きく変動しないか確認
    for i in range(int(fade_in_end_u * N), int(fade_out_start_u * N) + 1):
        if i <= N and samples[i] < 0.95:
            return None  # 中間領域で不透明度が下がる複雑パターン

    result = []
    if fade_in_end_u > 0.005:
        fade_in_dur = fade_in_end_u * dur
        result.append(f"fade=t=in:st={start}:d={fade_in_dur}:alpha=1")
    if fade_out_start_u < 0.995:
        fade_out_dur = (1.0 - fade_out_start_u) * dur
        fade_out_st = start + fade_out_start_u * dur
        result.append(f"fade=t=out:st={fade_out_st}:d={fade_out_dur}:alpha=1")

    return result if result else None


def _optimize_filter_chain(filters):
    """フィルタチェーンの最適化: 連続format重複を除去"""
    if not filters:
        return filters
    result = []
    for f in filters:
        if f.startswith("format=") and result and result[-1] == f:
            continue
        result.append(f)
    return result


def _estimate_effect_input_length(obj, upto_effect):
    """時間系Effect直前の実効尺を推定する（probe不能時はNone）。

    reverse の長尺ガード用。obj.source の実長に、upto_effect より前の
    trim/speed/freeze_frame を並び順に適用した値を返す。
    """
    proj = Project._current
    base = None
    if proj is not None and getattr(obj, "media_type", None) not in ("image", "text"):
        info = proj._probe_media(obj.source)
        if info:
            base = info.get("duration")
    if base is None:
        base = getattr(obj, "_resolved_length", None)
    if not base:
        return None
    cur = base
    for e in obj.effects:
        if e is upto_effect:
            break
        if e.name == "trim" and e.params.get("duration") is not None:
            cur = _builtins.min(cur, e.params["duration"])
        elif e.name == "speed":
            f = e.params.get("factor", 1.0)
            if f:
                cur = cur / f
        elif e.name == "freeze_frame":
            cur = cur + e.params.get("duration", 0.0)
    return cur


def _build_video_pre_filters(obj, label_prefix="pre"):
    """trim/speed/reverse/freeze_frame 等の時間系前処理フィルタ（記述順に適用）

    label_prefix: freeze_frame の複合サブグラフ（split/concat）の中間ラベル接頭辞。
    複数入力を扱う本レンダでは入力indexを含めて一意化する。
    """
    filters = []
    for eff_idx, e in enumerate(obj.effects):
        if e.name == "trim":
            d = e.params.get("duration")
            if d is not None:
                filters.append(f"trim=duration={d}")
                filters.append("setpts=PTS-STARTPTS")
        elif e.name == "speed":
            factor = e.params.get("factor", 1.0)
            filters.append(f"setpts=PTS/{factor}")
        elif e.name == "reverse":
            # reverse は全フレームをメモリに保持するため長尺を明示エラーにする
            eff_len = _estimate_effect_input_length(obj, e)
            if eff_len is not None and eff_len > _REVERSE_MAX_SEC:
                raise ValueError(
                    f"reverse: 実効尺 {eff_len:.1f}s が上限 {_REVERSE_MAX_SEC:.0f}s "
                    f"を超えています ('{obj.source}')。\n"
                    f"reverse は全フレームをメモリに保持するため長尺には使えません。"
                    f"trim() で対象区間を短くしてから適用してください。")
            filters.append("reverse")
        elif e.name == "freeze_frame":
            # 指定時刻のフレームで duration 秒静止 → 続きを再生（総尺 +duration）
            # trim 3分割 + loop(先頭フレーム複製) + concat のチェーン内サブグラフ
            at = e.params["at"]
            fdur = e.params["duration"]
            p = f"{label_prefix}f{eff_idx}"
            filters.append(
                f"split=3[{p}a][{p}b][{p}c];"
                f"[{p}a]trim=duration={at},setpts=PTS-STARTPTS[{p}s1];"
                f"[{p}b]trim=start={at},setpts=PTS-STARTPTS,"
                f"loop=loop=-1:size=1,trim=duration={fdur},setpts=PTS-STARTPTS[{p}s2];"
                f"[{p}c]trim=start={at},setpts=PTS-STARTPTS[{p}s3];"
                f"[{p}s1][{p}s2][{p}s3]concat=n=3:v=1:a=0"
            )
    return filters


def _atempo_chain_rates(rate):
    """atempoの有効範囲(0.5〜100)を超えるレートを複数段に分解する。
    範囲内はそのまま1段で返す（既存出力との互換維持）。"""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return [rate]
    if r <= 0 or 0.5 <= r <= 100.0:
        return [rate]  # 範囲内（or 不正値はffmpegに検出させる）
    rates = []
    while r < 0.5:
        rates.append(0.5)
        r /= 0.5
    while r > 100.0:
        rates.append(100.0)
        r /= 100.0
    rates.append(_builtins.round(r, 6))
    return rates


def _build_audio_pre_filters(obj):
    """atrim/atempo等の前処理フィルタ"""
    filters = []
    for e in obj.audio_effects:
        if e.name == "atrim":
            d = e.params.get("duration")
            if d is not None:
                filters.append(f"atrim=duration={d}")
                filters.append("asetpts=PTS-STARTPTS")
        elif e.name == "atempo":
            rate = e.params.get("rate", 1.0)
            for r in _atempo_chain_rates(rate):
                filters.append(f"atempo={r}")
    return filters


def _build_audio_effect_filters(obj, dur):
    """音声エフェクトフィルタを生成（again/afade）"""
    filters = []
    for e in obj.audio_effects:
        if e.name == "again":
            value_expr = e.params.get("value", Const(1))
            u_expr = f"clip((t)/{dur}\\,0\\,1)"
            ffmpeg_str = value_expr.to_ffmpeg(u_expr)
            filters.append(f"volume=volume='{ffmpeg_str}':eval=frame")
        elif e.name == "afade":
            alpha_expr = e.params.get("alpha", Const(1.0))
            u_expr = f"clip((t)/{dur}\\,0\\,1)"
            ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
            filters.append(f"volume=volume='{ffmpeg_str}':eval=frame")
    return filters


class TransformChain:
    """複数のTransformをまとめたチェーン"""
    def __init__(self, transforms):
        self.transforms = list(transforms)

    def __or__(self, other):
        """TransformChain | Transform/TransformChain → TransformChain"""
        if isinstance(other, Transform):
            return TransformChain(self.transforms + [other])
        if isinstance(other, TransformChain):
            return TransformChain(self.transforms + other.transforms)
        return NotImplemented

    def __invert__(self):
        """~(tf1 | tf2 | tf3) → chain内全opに quality='fast' 付与"""
        new_list = [t._copy(quality="fast") for t in self.transforms]
        return TransformChain(new_list)

    def __pos__(self):
        """+(tf1 | tf2 | tf3) → 末尾opに policy='force'"""
        new_list = list(self.transforms)
        new_list[-1] = new_list[-1]._copy(policy="force")
        return TransformChain(new_list)

    def __neg__(self):
        """-(tf1 | tf2 | tf3) → 末尾opに policy='off'"""
        new_list = list(self.transforms)
        new_list[-1] = new_list[-1]._copy(policy="off")
        return TransformChain(new_list)

    def __repr__(self):
        return f"TransformChain({self.transforms})"


class EffectChain:
    """複数のEffectをまとめたチェーン"""
    def __init__(self, effects):
        self.effects = list(effects)

    def __and__(self, other):
        """EffectChain & Effect/EffectChain → EffectChain"""
        if isinstance(other, Effect):
            return EffectChain(self.effects + [other])
        if isinstance(other, EffectChain):
            return EffectChain(self.effects + other.effects)
        return NotImplemented

    def __invert__(self):
        """~(eff1 & eff2) → chain内全opに quality='fast' 付与"""
        new_list = [e._copy(quality="fast") for e in self.effects]
        return EffectChain(new_list)

    def __pos__(self):
        """+(eff1 & eff2) → 末尾opに policy='force'"""
        new_list = list(self.effects)
        new_list[-1] = new_list[-1]._copy(policy="force")
        return EffectChain(new_list)

    def __neg__(self):
        """-(eff1 & eff2) → 末尾opに policy='off'"""
        new_list = list(self.effects)
        new_list[-1] = new_list[-1]._copy(policy="off")
        return EffectChain(new_list)

    def __repr__(self):
        return f"EffectChain({self.effects})"


class AudioEffect:
    """音声エフェクト（again, afade, adelete, atrim, atempo等）"""
    def __init__(self, name, **params):
        self.name = name
        self.params = params

    def __and__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain([self, other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain([self] + other.effects)
        if isinstance(other, _DisabledAudioEffect):
            return AudioEffectChain([self, other])
        return NotImplemented

    def __invert__(self):
        return _DisabledAudioEffect(self)

    def __repr__(self):
        return f"AudioEffect({self.name}, {self.params})"


class AudioEffectChain:
    """複数のAudioEffectをまとめたチェーン"""
    def __init__(self, effects):
        self.effects = list(effects)

    def __and__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain(self.effects + [other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain(self.effects + other.effects)
        if isinstance(other, _DisabledAudioEffect):
            return AudioEffectChain(self.effects + [other])
        return NotImplemented

    def __invert__(self):
        return _DisabledAudioEffect(self)

    def __repr__(self):
        return f"AudioEffectChain({self.effects})"


class _DisabledAudioEffect:
    """無効化AudioEffect"""
    def __init__(self, original):
        self.original = original

    def __and__(self, other):
        if isinstance(other, (AudioEffect, _DisabledAudioEffect)):
            return AudioEffectChain([self, other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain([self] + other.effects)
        return NotImplemented

    def __rand__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain([other, self])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain(other.effects + [self])
        return NotImplemented

    def __invert__(self):
        return self.original


class Transform:
    def __init__(self, name, *, policy="auto", quality="final", **params):
        self.name = name
        self.params = params
        self.policy = policy
        self.quality = quality

    def _copy(self, **overrides):
        """属性をコピーした新Transformを返す"""
        kw = dict(policy=self.policy, quality=self.quality, **self.params)
        kw.update(overrides)
        return Transform(self.name, **kw)

    def __or__(self, other):
        """Transform | Transform/TransformChain → TransformChain"""
        if isinstance(other, Transform):
            return TransformChain([self, other])
        if isinstance(other, TransformChain):
            return TransformChain([self] + other.transforms)
        return NotImplemented

    def __invert__(self):
        """~op → quality='fast'"""
        return self._copy(quality="fast")

    def __pos__(self):
        """+op → policy='force'"""
        return self._copy(policy="force")

    def __neg__(self):
        """-op → policy='off'"""
        return self._copy(policy="off")

    def __repr__(self):
        return f"Transform({self.name}, {self.params})"


class Effect:
    def __init__(self, name, *, policy="auto", quality="final", **params):
        self.name = name
        self.params = params
        self.policy = policy
        self.quality = quality

    def _copy(self, **overrides):
        """属性をコピーした新Effectを返す"""
        kw = dict(policy=self.policy, quality=self.quality, **self.params)
        kw.update(overrides)
        new = Effect(self.name, **kw)
        if hasattr(self, '_morph_target'):
            new._morph_target = self._morph_target
        return new

    def __and__(self, other):
        """Effect & Effect/EffectChain → EffectChain"""
        if isinstance(other, Effect):
            return EffectChain([self, other])
        if isinstance(other, EffectChain):
            return EffectChain([self] + other.effects)
        return NotImplemented

    def __invert__(self):
        """~op → quality='fast'"""
        return self._copy(quality="fast")

    def __pos__(self):
        """+op → policy='force'"""
        return self._copy(policy="force")

    def __neg__(self):
        """-op → policy='off'"""
        return self._copy(policy="off")

    def __repr__(self):
        return f"Effect({self.name}, {self.params})"


class _AnchorMarker:
    """アンカー位置マーカー（タイムライン上の位置を記録、レンダリングなし）"""
    def __init__(self, name):
        self.name = name
        self.duration = None
        self.start_time = 0
        self.priority = 0


class Pause:
    """非描画タイムラインアイテム（時間のみ占有、レンダリングなし）"""
    def __init__(self):
        self.duration = None
        self.start_time = 0
        self.priority = 0
        self._until_anchor = None
        self._until_offset = 0.0

    def time(self, duration):
        self.duration = duration
        return self

    def until(self, name, offset=0.0):
        self._until_anchor = name
        self._until_offset = offset
        return self


class _ScenePad:
    """シーン末尾の遅延パディングマーカー（レンダリングなし）。

    _resolve_anchors 実行時に「シーン開始時刻 + 目標尺」まで current_time を進める。
    自動尺(.time()省略/until)の尺確定後に実 used が反映されるため、
    exec 時点で即 pad するより正確（pad 過大で後続シーンがずれるのを防ぐ）。
    """
    def __init__(self, scene_name, target_duration):
        self.scene_name = scene_name
        self.target_duration = target_duration
        self.duration = None
        self.start_time = 0
        self.priority = 0


class Scene:
    """シーンのコンテキストマネージャ（p.scene() が返す）。

    with 内で定義したObjectはシーン相対の時刻になり、シーン終端を duration まで
    パディングすることで、複数シーンが時間軸上に順次配置される。開始位置に
    `scene:<name>` アンカーを張り、他レイヤーから参照できる。
    """
    def __init__(self, project, name, duration):
        if duration is None or duration <= 0:
            raise ValueError(f"scene '{name}': duration は正の値が必要です")
        self.project = project
        self.name = name
        self.duration = duration
        self._start_index = None

    def __enter__(self):
        # 開始位置にアンカー（他レイヤー/シーンからの参照点）
        anchor(f"scene:{self.name}")
        self._start_index = len(self.project.objects)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        # 目安の used（確定尺のみ）で明らかな超過だけ警告する。
        # 実パディングは _ScenePad による遅延解決（自動尺/until 確定後に正確化）。
        est_used = 0.0
        for o in self.project.objects[self._start_index:]:
            if isinstance(o, (_AnchorMarker, _ScenePad)):
                continue
            if getattr(o, "_advance", True) and getattr(o, "duration", None):
                est_used += o.duration
        if est_used - self.duration > 1e-6:
            warnings.warn(
                f"scene '{self.name}': 内容尺 {est_used:.3f}s が duration "
                f"{self.duration}s を超えています（シーンが重なります）")
        # 遅延パディングマーカー（_resolve_anchors でシーン開始+duration まで進める）
        self.project.objects.append(_ScenePad(self.name, self.duration))
        # 終端アンカー（pad 後の時刻 = シーン開始 + duration に解決される）
        anchor(f"scene:{self.name}.end")
        return False


_WEB_KWARGS = {"duration", "size", "fps", "data", "name", "debug_frames", "deps"}

# slide(): web Objectの_web_dataに埋め込むページ切替キー（内部規約・非公開API）
_SLIDE_PAGE_KEY = "__svt_slide_page__"


class Object:
    def __init__(self, source, **kwargs):
        self.source = source
        self.transforms = []
        self.effects = []
        self.audio_effects = []
        self.duration = None
        self._duration_auto = False
        self.start_time = 0
        self.priority = 0
        self.media_type = _detect_media_type(source)
        self._until_anchor = None
        self._until_offset = 0.0
        self._anchor_name = None
        self._advance = True
        self._priority_override = None
        self._video_deleted = False
        self._audio_deleted = False
        # web専用属性（常に初期化）
        self._web_source = None
        self._web_size = None
        self._web_fps = None
        self._web_data = {}
        self._web_name = None
        self._web_debug_frames = False
        self._web_deps = []

        # web Object のバリデーションと属性設定
        if self.media_type == "web":
            unknown = set(kwargs.keys()) - _WEB_KWARGS
            if unknown:
                hint = _suggest_hint(sorted(unknown)[0], _WEB_KWARGS)
                raise TypeError(
                    f"不明なキーワード引数: {', '.join(sorted(unknown))}。"
                    f"使用可能: {', '.join(sorted(_WEB_KWARGS))}{hint}")
            if "duration" not in kwargs:
                raise ValueError("web Object には duration が必須です")
            if "size" not in kwargs:
                raise ValueError("web Object には size が必須です")
            self._web_source = source
            self.duration = kwargs["duration"]
            self._web_size = kwargs["size"]
            self._web_fps = kwargs.get("fps")
            self._web_data = kwargs.get("data", {})
            self._web_name = kwargs.get("name") or os.path.splitext(os.path.basename(source))[0]
            self._web_debug_frames = kwargs.get("debug_frames", False)
            self._web_deps = kwargs.get("deps", [])
        elif kwargs:
            raise TypeError(
                f"キーワード引数は web Object (.html/.htm) 専用です: "
                f"{', '.join(sorted(kwargs.keys()))}")

        # has_video / has_audio のデフォルト
        if self.media_type == "image":
            self._has_video = True
            self._has_audio = False
        elif self.media_type == "audio":
            self._has_video = False
            self._has_audio = True
        elif self.media_type == "web":
            self._has_video = True
            self._has_audio = False
        else:  # video
            self._has_video = True
            self._has_audio = None  # 未判定→ffprobeで解決
        # 現在のProjectに自動登録
        if Project._current is not None:
            Project._current.objects.append(self)

    @property
    def has_video(self):
        if self._video_deleted:
            return False
        return self._has_video if self._has_video is not None else True

    @property
    def has_audio(self):
        if self._audio_deleted:
            return False
        if self._has_audio is None:
            proj = Project._current
            if proj:
                info = proj._probe_media(self.source)
                if info:
                    self._has_audio = info.get("has_audio", False)
                    return self._has_audio
            return False  # probe不可→音声なしと推定（安全側）
        return self._has_audio

    def time(self, duration=None, *, name=None):
        """表示時間を設定。省略時は加工後長(length())で自動決定（layer exec後に確定）"""
        if duration is None:
            if self.media_type in ("image", "text"):
                raise TypeError(
                    "画像/テキストには time() 省略は使えません。time(seconds) を指定してください。")
            self.duration = None
            self._duration_auto = True
        else:
            self.duration = duration
            self._duration_auto = False
        if name is not None:
            self._anchor_name = name
        return self

    def until(self, name, offset=0.0):
        """durationをアンカー時刻まで伸長"""
        self._until_anchor = name
        self._until_offset = offset
        return self

    def show(self, duration, *, priority=None):
        """current_timeを進めずに表示。start=current_time, duration=指定値"""
        self.duration = duration
        self._advance = False
        if priority is not None:
            self._priority_override = priority
        return self

    def show_until(self, name, offset=0.0, *, priority=None):
        """current_timeを進めずにアンカーまで表示"""
        self._until_anchor = name
        self._until_offset = offset
        self._advance = False
        if priority is not None:
            self._priority_override = priority
        return self

    def _append_effect(self, e):
        """Effect追加の共通経路（delete処理・時間系の検証・speedの音声追従）"""
        if e.name == "delete":
            self._video_deleted = True
            return
        if e.name in _TIME_LIVE_EFFECTS and self.media_type in ("image", "text", "web"):
            raise ValueError(
                f"{e.name}: 時間操作Effectは動画素材にのみ適用できます"
                f"（{self.media_type} には適用不可）: {self.source}")
        self.effects.append(e)
        if e.name == "speed" and not self._audio_deleted:
            # 音声付き動画のテンポを自動追従させる（atempo）。
            # length()での二重計上を防ぐためフラグを付ける
            ae = AudioEffect("atempo", rate=e.params.get("factor", 1.0))
            ae._auto_from_speed = True
            self.audio_effects.append(ae)

    def __le__(self, rhs):
        """<= 演算子: Transform/Effect/AudioEffect等を適用"""
        if isinstance(rhs, _DisabledAudioEffect):
            return self  # AudioのDisableだけ残す
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(rhs.transforms)
        elif isinstance(rhs, Effect):
            self._append_effect(rhs)
        elif isinstance(rhs, EffectChain):
            for e in rhs.effects:
                self._append_effect(e)
        elif isinstance(rhs, AudioEffect):
            if rhs.name == "adelete":
                self._audio_deleted = True
            else:
                self.audio_effects.append(rhs)
        elif isinstance(rhs, AudioEffectChain):
            for e in rhs.effects:
                if isinstance(e, _DisabledAudioEffect):
                    continue
                if e.name == "adelete":
                    self._audio_deleted = True
                else:
                    self.audio_effects.append(e)
        else:
            raise TypeError(f"Object <= に渡せるのは Transform/Effect/AudioEffect 等のみ: {type(rhs)}")
        return self

    def compute(self, duration=None):
        """タイムライン外で素材を生成。PNG(静止) or WebM(動画)を返す"""
        # live effects チェック（時間系 speed/reverse/freeze_frame は
        # _build_compute_video_cmd の前処理フィルタでベイクできるため許可）
        for e in self.effects:
            if e.name in ("move", "delete", "shake", "blend_mode"):
                raise ValueError(
                    f"compute() では live Effect '{e.name}' は使用できません。"
                    f"bakeable Effect のみ使用可能です。")
        # Project.objects から除外
        proj = Project._current
        if proj is not None and self in proj.objects:
            proj.objects.remove(self)
        # キャッシュパス計算
        cache_path = self._compute_cache_path(duration)
        # 差し替え前の元素材パスを保持（レイヤーキャッシュの依存記録で
        # 導出キャッシュパスではなく元素材の変更を検知できるようにする）
        self._origin_sources = (getattr(self, '_origin_sources', None) or []) + [self.source]
        # ベイク尺を保持（差し替え後の未生成予定パスへのprobe fallback防止）
        if duration:
            self._resolved_length = duration
        # plan pass: source差し替えのみ
        if proj is not None and proj._mode == "plan":
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # キャッシュ存在チェック
        if os.path.exists(cache_path):
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # 生成コマンド構築
        if duration is None:
            cmd = self._build_compute_image_cmd(cache_path)
        else:
            cmd = self._build_compute_video_cmd(cache_path, duration)
        # dry_run: コマンドを記録して生成スキップ
        if proj is not None and getattr(proj, '_dry_run', False):
            proj._pending_compute_cmds[cache_path] = cmd
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # 実生成
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        _run_ffmpeg_to_cache(cmd, cache_path, timeout=600)
        self.source = cache_path
        self.media_type = _detect_media_type(cache_path)
        self.transforms = []
        self.effects = []
        return self

    @staticmethod
    def from_project(sub_project, *, cache="auto"):
        """ネストコンポジション（プリコンポーズ）: サブProjectを透過webm素材化して
        1つのObjectとして親タイムラインに配置する。

        sub_project: layer() 登録済みの Project。render(alpha=True) 機構で
        透過webmキャッシュ生成物を作り、そのwebmをsourceとするObjectを返す。
        キャッシュ鍵は configure + レイヤーファイルFFP群 + レイヤーが参照する
        素材FFP群から導出する（素材更新で自動再生成）。dry_run 対応。
        cache: 'auto'（キャッシュがあれば再利用）/ 'force'（常に再生成）。
        """
        if not isinstance(sub_project, Project):
            raise TypeError(
                f"from_project: sub_project には Project を指定してください: "
                f"{type(sub_project)}")
        if cache not in ("auto", "force"):
            hint = _suggest_hint(cache, ("auto", "force"))
            raise ValueError(
                f"from_project: cache は 'auto' か 'force' のいずれか: {cache!r}{hint}")
        # 親 = 現在レイヤーを実行中のProject（sub = Project() が _current を
        # 奪うため、_exec_stack から特定する）。レイヤー外では復元先のみ保持
        parent = Project._exec_stack[-1] if Project._exec_stack else None
        if sub_project is parent:
            raise ValueError("from_project: 親Project自身は指定できません")
        if not sub_project._layer_specs:
            raise ValueError(
                "from_project: sub_project に layer() が登録されていません。"
                "sub.layer('xxx.py') でレイヤーを登録してから渡してください。")
        # サブProjectをdry_runで解決し、総尺・依存素材を確定する
        # （Project._current が切り替わるため必ず親へ復元する）
        try:
            sub_project.render("__from_project_probe__.webm",
                               dry_run=True, alpha=True)
        finally:
            Project._current = parent
        total = sub_project.duration

        # 署名: configure + レイヤーファイルFFP群 + レイヤー参照素材FFP群
        sigs = ["from_project",
                f"cfg={sub_project.width}x{sub_project.height}"
                f"@{sub_project.fps}|bg={sub_project.background_color}"
                f"|dur={total}"]
        layer_files = []
        for spec in sub_project._layer_specs:
            sigs.append(
                f"layer={_source_signature(spec['filename'])}|p={spec['priority']}")
            layer_files.append(spec["filename"])
        dep_sources = []
        for srcs in sub_project._layer_sources.values():
            dep_sources.extend(srcs)
        dep_sources = sorted(set(dep_sources))
        for src in dep_sources:
            sigs.append(f"dep={_source_signature(src)}")
        sigs.append(f"ev={_ENGINE_VER}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        cache_path = os.path.join(_ARTIFACT_DIR, "subproject", f"{key}.webm")

        parent_mode = getattr(parent, "_mode", None) if parent else None
        parent_dry = bool(getattr(parent, "_dry_run", False)) if parent else False
        if parent is not None and parent_mode == "plan":
            pass  # plan pass: 生成スキップ（尺解決のみ）
        elif cache == "auto" and os.path.exists(cache_path):
            pass  # キャッシュ命中
        elif parent_dry:
            # dry_run: サブProjectの生成コマンド（dict/list）をpendingに記録
            try:
                sub_cmd = sub_project.render(cache_path, dry_run=True, alpha=True)
            finally:
                Project._current = parent
            parent._pending_compute_cmds[cache_path] = sub_cmd
        else:
            # 実生成: 一時パスへレンダし成功時のみ確定（アトミック書き込み）
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            base, ext = os.path.splitext(cache_path)
            tmp_path = f"{base}.tmp{ext}"
            print(f"サブプロジェクト生成: {cache_path}")
            try:
                sub_project.render(tmp_path, alpha=True)
                os.replace(tmp_path, cache_path)
                with _GEN_COUNTER_LOCK:
                    _GEN_COUNTER[0] += 1
            finally:
                Project._current = parent
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        # 親レイヤーの依存として登録（レイヤーキャッシュの鮮度検証に載せる）
        if parent is not None and parent._current_layer_file:
            parent._extra_layer_deps.setdefault(
                parent._current_layer_file, []).extend(layer_files + dep_sources)
        obj = Object(cache_path)
        obj._origin_sources = list(layer_files) + list(dep_sources)
        obj._resolved_length = total
        # 音声有無: dry_run解決済みのサブオブジェクトから確定（未生成キャッシュの
        # probe不能でFalse固定になるのを防ぐ）
        obj._has_audio = any(
            isinstance(o, Object) and o.has_audio for o in sub_project.objects)
        return obj

    def _compute_cache_path(self, duration=None):
        """compute用キャッシュパスを計算"""
        ops = _build_unified_ops(self)
        sigs = []
        try:
            sigs.append(f"ffp={_file_fingerprint(self.source)}")
        except OSError:
            sigs.append(f"src={self.source.replace(chr(92), '/')}")
        sigs.append(_op_prefix_fingerprint(ops))
        quality = "final"
        for _, op in ops:
            if getattr(op, 'quality', 'final') == "fast":
                quality = "fast"
        sigs.append(f"q={quality}")
        sigs.append(f"ev={_ENGINE_VER}")
        if duration is not None:
            proj = Project._current
            fps = proj.fps if proj else 30
            sigs.append(f"dur={duration}")
            sigs.append(f"fps={fps}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        src_hash = hashlib.sha256(
            self.source.replace("\\", "/").encode()).hexdigest()[:8]
        ext = ".mkv" if duration is not None else ".png"
        return os.path.join(_ARTIFACT_DIR, "compute", src_hash, f"{key}{ext}")

    def _build_compute_image_cmd(self, cache_path):
        """compute静止画: Transform適用→PNG"""
        temp = Object.__new__(Object)
        temp.source = self.source
        temp.transforms = list(self.transforms)
        temp.effects = []
        filters = _build_transform_filters(temp)
        cmd = ["ffmpeg", "-y", "-i", self.source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", cache_path])
        return cmd

    def _build_compute_video_cmd(self, cache_path, duration):
        """compute動画: Transform+Effect適用→WebM VP9 alpha"""
        proj = Project._current
        fps = proj.fps if proj else 30
        temp = Object.__new__(Object)
        temp.source = self.source
        temp.transforms = list(self.transforms)
        temp.effects = list(self.effects)
        temp.media_type = self.media_type
        base_dims = _get_base_dimensions(temp)
        filters = _build_transform_filters(temp)
        pre_filters = _build_video_pre_filters(temp)
        filters = pre_filters + filters
        eff_filters, _ = _build_effect_filters(temp, 0, duration, base_dims=base_dims)
        filters.extend(eff_filters)
        cmd = ["ffmpeg", "-y"]
        cmd.extend(_decoder_input_args(self.source, self.media_type, fps))
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend([
            "-c:v", "ffv1", "-level", "3",
            "-pix_fmt", "yuva444p",
            "-t", str(duration), cache_path,
        ])
        return cmd

    def length(self):
        """加工後の再生時間を返す（ffprobe + 時間影響エフェクト反映）"""
        if self.media_type in ("image", "text"):
            raise TypeError("画像/テキストにはlength()を使えません。動画/音声のみ対応です。")
        if self.media_type == "web":
            if self.duration is None:
                raise TypeError("web Objectにはduration引数が必須です")
            return self.duration
        proj = Project._current
        if proj is None:
            raise RuntimeError("length()にはアクティブなProjectが必要です")
        info = proj._probe_media(self.source)
        if info is None or info.get("duration") is None:
            raise FileNotFoundError(
                f"メディアの長さを取得できません: {self.source}")
        base_dur = info["duration"]
        result = base_dur
        # 映像 時間系（trim/speed/freeze_frame）を並び順に反映
        for e in self.effects:
            if e.name == "trim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
            elif e.name == "speed":
                factor = e.params.get("factor", 1.0)
                if factor > 0:
                    result = result / factor
            elif e.name == "freeze_frame":
                result = result + e.params.get("duration", 0.0)
        # 音声atrim/atempo
        for e in self.audio_effects:
            if e.name == "atrim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
            elif e.name == "atempo":
                if getattr(e, "_auto_from_speed", False):
                    continue  # speed()由来の自動atempoは映像側で反映済み（二重計上防止）
                rate = e.params.get("rate", 1.0)
                if rate > 0:
                    result = result / rate
        return result

    def _build_web_cmd(self, project, webm_path=None):
        """webクリップ用ffmpegコマンド"""
        cache_dir = os.path.join(_CACHE_DIR, "webclip")
        name = self._web_name
        if webm_path is None:
            webm_path = _web_cache_path(self, project)
        frames_dir = os.path.join(cache_dir, f"{name}_frames")
        frames_pattern = os.path.join(frames_dir, "frame_%05d.png")
        fps = self._web_fps or project.fps
        dur = self.duration
        return [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", "30",
            "-auto-alt-ref", "0",
            "-t", str(dur),
            webm_path,
        ]

    def _render_web_frames(self, project):
        """Playwrightで HTML を連番PNGにキャプチャ"""
        from playwright.sync_api import sync_playwright
        name = self._web_name
        cache_dir = os.path.join(_CACHE_DIR, "webclip")
        frames_dir = os.path.join(cache_dir, f"{name}_frames")
        os.makedirs(frames_dir, exist_ok=True)
        w, h = self._web_size
        fps = self._web_fps or project.fps
        dur = self.duration
        N = int(dur * fps)
        html_path = os.path.abspath(self._web_source)
        url = f"file:///{html_path.replace(os.sep, '/')}"

        # slide(): ページ切替規約（_SLIDE_PAGE_KEY）が指定されていれば、
        # renderFrame待機の前にページ切替JSフックを実行する
        slide_page = self._web_data.get(_SLIDE_PAGE_KEY)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(url)
                if slide_page is not None:
                    # window.showSlide(n) があれば呼び出し、無ければ
                    # id="page-N" 要素のみ表示（他のid^="page-"要素は非表示）。
                    # renderFrame未定義ならno-opを注入し、静止スライドとして
                    # 通常のWeb Objectキャプチャ経路をそのまま利用できるようにする。
                    page.evaluate(
                        "(n) => {"
                        "  if (typeof window.showSlide === 'function') {"
                        "    window.showSlide(n);"
                        "  } else {"
                        "    document.querySelectorAll('[id^=\"page-\"]').forEach(function(el) {"
                        "      el.style.display = (el.id === ('page-' + n)) ? '' : 'none';"
                        "    });"
                        "  }"
                        "  if (typeof window.renderFrame !== 'function') {"
                        "    window.renderFrame = function(state) {};"
                        "  }"
                        "}", slide_page)
                page.wait_for_function("typeof globalThis.renderFrame === 'function'", timeout=5000)
                for i in range(N):
                    t = i / fps
                    u = 1.0 if N <= 1 else i / (N - 1)
                    state = {
                        "frame": i, "t": t, "u": u,
                        "fps": fps, "duration": dur,
                        "width": w, "height": h,
                        "data": self._web_data, "seed": 0,
                    }
                    page.evaluate("state => globalThis.renderFrame(state)", state)
                    page.screenshot(
                        path=os.path.join(frames_dir, f"frame_{i:05d}.png"),
                        omit_background=True)
            finally:
                # 失敗時もブラウザプロセスを残さない
                browser.close()

    def grid(self, cols, rows, *, gap=0):
        """このObjectを cols×rows のグリッドに複製配置する Transform を追加。

        出力サイズは (cols*iw + gap*(cols-1)) × (rows*ih + gap*(rows-1))。
        背景パターン生成向け。静止画（-loop 1）を tile フィルタで並べる。
        """
        if self.media_type not in ("image",):
            raise TypeError("grid() は画像素材にのみ使用できます")
        if cols < 1 or rows < 1:
            raise ValueError("grid: cols/rows は1以上が必要です")
        self.transforms.append(
            Transform("grid", cols=int(cols), rows=int(rows), gap=int(gap)))
        return self

    def split(self):
        """(VideoView or None, AudioView or None) を返す"""
        v = VideoView(self) if self.has_video else None
        a = AudioView(self) if self.has_audio else None
        return v, a

    def __repr__(self):
        return f"Object({self.source}, transforms={self.transforms}, effects={self.effects}, audio_effects={self.audio_effects})"


class VideoView:
    """映像ビュー（split()で生成、参照専用）"""
    def __init__(self, clip):
        self._clip = clip

    def __le__(self, rhs):
        """映像系のみ受け入れ"""
        if isinstance(rhs, (Transform, TransformChain, Effect, EffectChain)):
            self._clip.__le__(rhs)
            return self
        raise TypeError(f"VideoView <= には映像系のみ: {type(rhs)}")

    def time(self, *args, **kwargs):
        raise TypeError("VideoView.time() は禁止です。clip.time() を使ってください。")

    def until(self, *args, **kwargs):
        raise TypeError("VideoView.until() は禁止です。clip.until() を使ってください。")


class AudioView:
    """音声ビュー（split()で生成、参照専用）"""
    def __init__(self, clip):
        self._clip = clip

    def __le__(self, rhs):
        """音声系のみ受け入れ"""
        if isinstance(rhs, (AudioEffect, AudioEffectChain, _DisabledAudioEffect)):
            self._clip.__le__(rhs)
            return self
        raise TypeError(f"AudioView <= には音声系のみ: {type(rhs)}")

    def time(self, *args, **kwargs):
        raise TypeError("AudioView.time() は禁止です。clip.time() を使ってください。")

    def until(self, *args, **kwargs):
        raise TypeError("AudioView.until() は禁止です。clip.until() を使ってください。")


# --- Transform関数 ---

def resize(**kwargs):
    return Transform("resize", **kwargs)


def rotate(*, deg=None, rad=None, expand=False, fill="0x00000000"):
    """固定角回転Transform。deg/radどちらか一方のみ指定。"""
    if deg is None and rad is None:
        raise ValueError("rotate: deg または rad のどちらかが必要")
    if deg is not None and rad is not None:
        raise ValueError("rotate: deg と rad は同時に指定できません")
    if deg is not None:
        rad_val = deg2rad(deg)
    else:
        rad_val = _to_expr(rad)
    # 時間依存式（uを含む式）は静的Transformでは未定義変数uがフィルタに漏れるため拒否
    if isinstance(rad_val, Expr) and rad_val.to_ffmpeg("0") != rad_val.to_ffmpeg("1"):
        raise ValueError(
            "rotate() に時間依存の式（u を含む式）は使えません。"
            "時間変化する回転には rotate_to() を使ってください。")
    return Transform("rotate", rad=rad_val, expand=expand, fill=fill)


def crop(x=0, y=0, w=None, h=None):
    """クロップTransform。x,y: 左上起点(px)、w,h: 出力サイズ(px)。"""
    if w is None or h is None:
        raise ValueError("crop: w と h は必須です")
    return Transform("crop", x=x, y=y, w=w, h=h)


def pad(w=None, h=None, x=-1, y=-1, color="black"):
    """パディングTransform。w,h: 出力サイズ、x,y: 配置位置(-1=中央)。"""
    if w is None or h is None:
        raise ValueError("pad: w と h は必須です")
    return Transform("pad", w=w, h=h, x=x, y=y, color=color)


def blur(radius=5):
    """ガウスぼかしTransform。"""
    return Transform("blur", radius=radius)


def eq(*, brightness=0, contrast=1, saturation=1, gamma=1):
    """色調補正Transform（EQ）。brightness: -1..1, contrast: 0..inf, saturation: 0..inf"""
    return Transform("eq", brightness=brightness, contrast=contrast,
                     saturation=saturation, gamma=gamma)


# --- Effect用バリデーションヘルパー ---

_COLOR_NAME_RGB = {
    "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 128, 0), "lime": (0, 255, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "cyan": (0, 255, 255),
    "magenta": (255, 0, 255), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "orange": (255, 165, 0), "purple": (128, 0, 128), "pink": (255, 192, 203),
    "brown": (165, 42, 42), "navy": (0, 0, 128),
}


def _parse_color_rgb(color):
    """色名/16進文字列を (R, G, B) タプルに変換（drop_shadow/outline のgeq色付け用）"""
    if not isinstance(color, str) or not color:
        raise ValueError(f"color には色名か16進(#RRGGBB)の文字列を指定してください: {color!r}")
    s = color.strip().lower()
    if s.startswith("#"):
        s = s[1:]
    elif s.startswith("0x"):
        s = s[2:]
    else:
        if s in _COLOR_NAME_RGB:
            return _COLOR_NAME_RGB[s]
        raise ValueError(
            f"未対応の色名です: '{color}'。"
            f"対応色名: {', '.join(sorted(_COLOR_NAME_RGB))} または16進(#RRGGBB)")
    if len(s) != 6 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError(f"16進カラーは #RRGGBB / 0xRRGGBB 形式で指定してください: '{color}'")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _validate_ffmpeg_color(func_name, color):
    """ffmpegに渡す色指定（色名 or 16進）を検証し正規化して返す"""
    if not isinstance(color, str) or not color:
        raise ValueError(f"{func_name}: color には色名か16進の文字列を指定してください: {color!r}")
    s = color.strip()
    if s.startswith("#") or s.lower().startswith("0x"):
        h = s[1:] if s.startswith("#") else s[2:]
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            raise ValueError(f"{func_name}: 16進カラーは #RRGGBB / 0xRRGGBB 形式です: '{color}'")
        return "0x" + h.upper()
    if not s.isalpha():
        raise ValueError(f"{func_name}: 無効な色指定です: '{color}'")
    return s.lower()


def _require_number(func_name, param_name, value, lo=None, hi=None):
    """定数数値パラメータの型・範囲検証（Expr/lambda不可）"""
    if isinstance(value, Expr) or callable(value):
        raise ValueError(
            f"{func_name}: {param_name} には Expr/lambda は使えません（定数のみ）")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{func_name}: {param_name} は数値で指定してください: {value!r}")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        rng = f"{lo if lo is not None else ''}〜{hi if hi is not None else ''}"
        raise ValueError(
            f"{func_name}: {param_name} は {rng} の範囲で指定してください: {value}")
    return value


# --- Effect関数 ---

def scale(value=1):
    return Effect("scale", value=_resolve_param(value))


def fade(alpha=1.0):
    return Effect("fade", alpha=_resolve_param(alpha))


def move(**kwargs):
    resolved = {}
    # from/to アニメーション → lerp Exprに自動変換
    has_anim = "from_x" in kwargs or "from_y" in kwargs or "to_x" in kwargs or "to_y" in kwargs
    if has_anim:
        fx = kwargs.get("from_x", kwargs.get("x", 0.5))
        fy = kwargs.get("from_y", kwargs.get("y", 0.5))
        tx = kwargs.get("to_x", kwargs.get("x", 0.5))
        ty = kwargs.get("to_y", kwargs.get("y", 0.5))
        resolved["x"] = _resolve_param(lambda u: lerp(fx, tx, u))
        resolved["y"] = _resolve_param(lambda u: lerp(fy, ty, u))
    else:
        if "x" in kwargs:
            resolved["x"] = _resolve_param(kwargs["x"])
        if "y" in kwargs:
            resolved["y"] = _resolve_param(kwargs["y"])
    if "anchor" in kwargs:
        resolved["anchor"] = kwargs["anchor"]
    return Effect("move", **resolved)


def rotate_to(deg=None, rad=None, *, from_deg=None, from_rad=None,
              to_deg=None, to_rad=None, follow=None, offset_deg=0.0,
              expand=True, fill="0x00000000"):
    """時間依存回転Effect。deg/rad直接指定 or from/to でlerp。

    follow: move系Effect（move_along/path_bezier/throw等）を渡すと、
      そのパスの進行方向を向く回転になる（look_at と同義）。offset_deg で
      向きを補正する。
    """
    if follow is not None:
        return look_at(follow, offset_deg=offset_deg, expand=expand, fill=fill)
    has_from_to = any(v is not None for v in (from_deg, from_rad, to_deg, to_rad))
    if has_from_to:
        fr = _to_expr(from_rad) if from_rad is not None else (
            deg2rad(from_deg) if from_deg is not None else Const(0))
        tr = _to_expr(to_rad) if to_rad is not None else (
            deg2rad(to_deg) if to_deg is not None else Const(0))
        rad_expr = _resolve_param(lambda u: lerp(fr, tr, u))
    else:
        if deg is None and rad is None:
            raise ValueError("rotate_to: deg/rad か from/to の指定が必要")
        if rad is not None:
            rad_expr = _resolve_param(rad)
        else:
            rad_expr = deg2rad(_resolve_param(deg))
    return Effect("rotate_to", rad=rad_expr, expand=expand, fill=fill)


def morph_to(target, blend=None, **morph_params):
    """モーフィングEffect: 画像→画像の最適輸送モーフ動画を生成"""
    if not isinstance(target, Object):
        raise TypeError(f"morph_to の target は Object のみ: {type(target)}")
    # パラメータのタイポはレンダ深部（チェックポイント生成後）ではなく
    # 構築時点で検出する。morph モジュールが無い環境ではレンダ時に検出される
    try:
        from morph import MORPH_PARAM_KEYS
    except ImportError:
        pass
    else:
        unknown = set(morph_params) - set(MORPH_PARAM_KEYS)
        if unknown:
            raise ValueError(
                f"morph_to: 未知のパラメータ {sorted(unknown)}"
                f"（有効なキー: {sorted(MORPH_PARAM_KEYS)}）"
            )
    # ターゲットObjectをProjectから除外（morphに消費される）
    proj = Project._current
    if proj is not None and target in proj.objects:
        proj.objects.remove(target)
        warnings.warn(
            f"morph_to: ターゲット '{target.source}' はモーフィングに消費されるため"
            f"Projectから自動的に除外されました。"
        )
    # ターゲット素材をレイヤー依存として記録（objectsから除外されるため
    # _layer_sourcesの通常記録に載らず、キャッシュ鮮度検証から漏れるのを防ぐ）
    if proj is not None and proj._current_layer_file:
        tgt_deps = getattr(target, '_origin_sources', None) or [target.source]
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).extend(tgt_deps)
    if blend is None:
        blend = _resolve_param(lambda u: u * u * (3 - 2 * u))
    else:
        blend = _resolve_param(blend)
    eff = Effect("morph_to", blend=blend, **morph_params)
    eff._morph_target = target
    return eff


def _check_particle_params(func, params):
    """explode_to/assemble_from のパラメータのタイポを構築時に検出"""
    try:
        from morph import PARTICLE_PARAM_KEYS
    except ImportError:
        return
    unknown = set(params) - set(PARTICLE_PARAM_KEYS)
    if unknown:
        raise ValueError(
            f"{func}: 未知のパラメータ {sorted(unknown)}"
            f"（有効なキー: {sorted(PARTICLE_PARAM_KEYS)}）")


def explode_to(blend=None, **particle_params):
    """パーティクル飛散Effect: 適用対象自身が粒子化して飛散する。

    morph_to と同じ機構でベイクされる（中間フレーム抽出→mkvキャッシュ）。
    bakeable opsの末尾に配置する必要がある。blend で進行カーブを指定できる。
    particle_params: max_pixels, speed, gravity, spread, swirl,
      particle_size, seed, dissolve, expand。
    """
    _check_particle_params("explode_to", particle_params)
    if blend is None:
        blend = _resolve_param(lambda u: u)
    else:
        blend = _resolve_param(blend)
    return Effect("explode_to", blend=blend, **particle_params)


def assemble_from(source, blend=None, **particle_params):
    """パーティクル集合Effect: source の粒子が集合して画像になる。

    適用したObjectは「source が集合していくアニメーション」に置き換わる
    （source はモーフ同様Projectから消費される）。morph_to と同じベイク機構。
    bakeable opsの末尾に配置する。
    """
    if not isinstance(source, Object):
        raise TypeError(f"assemble_from の source は Object のみ: {type(source)}")
    _check_particle_params("assemble_from", particle_params)
    proj = Project._current
    if proj is not None and source in proj.objects:
        proj.objects.remove(source)
        warnings.warn(
            f"assemble_from: source '{source.source}' は集合アニメに消費されるため"
            f"Projectから自動的に除外されました。")
    # source素材をレイヤー依存として記録（objectsから外れるため鮮度検証に載せる）
    if proj is not None and proj._current_layer_file:
        src_deps = getattr(source, '_origin_sources', None) or [source.source]
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).extend(src_deps)
    if blend is None:
        blend = _resolve_param(lambda u: u)
    else:
        blend = _resolve_param(blend)
    eff = Effect("assemble_from", blend=blend, **particle_params)
    eff._assemble_source = source
    return eff


# --- パス・物理・ノイズ（move系Effect / Expr） ---

# パス/キーフレームの区分式で許容する最大点数（ネスト式の肥大化を防ぐ）
_MAX_PATH_POINTS = 128


def _piecewise_tree(u, values, bounds):
    """区分式を二分探索木で構築（ネスト深度 O(log n)、MEMORY規約準拠）。

    values[i] は境界で区切られた各区間の値 Expr（len(values)==len(bounds)+1）。
    bounds は昇順の分割点。u < bounds[mid] で左右に再帰分岐する。
    線形右畳み込み（O(n)ネスト）を避け、深い if_ ネストによる式肥大を防ぐ。
    """
    u = _to_expr(u)

    def build(vals, bnds):
        if not bnds:
            return vals[0]
        mid = len(bnds) // 2
        left = build(vals[:mid + 1], bnds[:mid])
        right = build(vals[mid + 1:], bnds[mid + 1:])
        return if_(lt(u, Const(bnds[mid])), left, right)

    return build(list(values), list(bounds))


def _piecewise_scalar_expr(u, points, easing=None):
    """(t, v) の点列から u∈[0,1] 上の区分線形補間 Expr を構築（keyframes同型）

    points は t 昇順。区間ごとに lerp し、二分探索木で連結する。easing 指定時は
    各区間のローカル進行度に適用する。
    """
    u = _to_expr(u)
    values = []
    bounds = []
    for i in range(len(points) - 1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        seg = t1 - t0
        if seg <= 0:
            continue
        local = clip((u - Const(t0)) / Const(seg), 0, 1)
        if easing is not None:
            local = easing(local)
        values.append(lerp(v0, v1, local))
        bounds.append(t1)
    values.append(Const(points[-1][1]))  # u>=最後の境界の既定値
    return _piecewise_tree(u, values, bounds)


def _validate_points(func, points, min_n=2):
    if not isinstance(points, (list, tuple)) or len(points) < min_n:
        raise ValueError(f"{func}: 座標列は最低{min_n}点必要です")
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValueError(f"{func}: 各点は (x, y) の2要素タプルが必要です: {pt!r}")


def move_along(points, *, easing=None, anchor="center"):
    """座標列 [(x0,y0), ...] に沿ったパスアニメーションの move Effect。

    各点は u を等間隔に割り当てて区分線形補間する（x/y それぞれに適用）。
    x/y は画面比率（0..1）。move の拡張なので既存の overlay 経路で描画される。
    """
    _validate_points("move_along", points)
    n = len(points)
    if n > _MAX_PATH_POINTS:
        raise ValueError(
            f"move_along: 点数は最大{_MAX_PATH_POINTS}点までです（指定={n}）")
    ts = [i / (n - 1) for i in range(n)]
    x_pts = [(ts[i], float(points[i][0])) for i in range(n)]
    y_pts = [(ts[i], float(points[i][1])) for i in range(n)]
    x_expr = _piecewise_scalar_expr(Var("u"), x_pts, easing)
    y_expr = _piecewise_scalar_expr(Var("u"), y_pts, easing)
    eff = Effect("move", x=x_expr, y=y_expr, anchor=anchor)
    eff._path_xy = (x_expr, y_expr)  # look_at 用にパスを保持
    return eff


def _bezier_segment_expr(s, p0, p1, p2, p3):
    """3次ベジェの1座標式（s∈[0,1] は Expr）"""
    s = _to_expr(s)
    one = Const(1) - s
    return (Const(p0) * one * one * one
            + Const(3 * p1) * s * one * one
            + Const(3 * p2) * s * s * one
            + Const(p3) * s * s * s)


def path_bezier(*points, anchor="center"):
    """3次ベジェ曲線パスの move Effect。

    制御点は (x,y) を 3n+1 個（p0,p1,p2,p3[,p4,p5,p6...]）。各セグメントは
    直前セグメントの終点を始点に共有する。cubic_bezier イージングと同系の資産。
    """
    _validate_points("path_bezier", points, min_n=4)
    n = len(points)
    if n > _MAX_PATH_POINTS:
        raise ValueError(
            f"path_bezier: 制御点は最大{_MAX_PATH_POINTS}点までです（指定={n}）")
    if (n - 1) % 3 != 0:
        raise ValueError(
            f"path_bezier: 制御点は 3n+1 個必要です（p0..p3, +3点ずつ）。指定={n}")
    seg_count = (n - 1) // 3
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    # if_ 連結は右畳み込みのため、区間逆順で構築（_bezier_path_coord内で処理）
    x_expr = _bezier_path_coord_rev(xs, seg_count)
    y_expr = _bezier_path_coord_rev(ys, seg_count)
    eff = Effect("move", x=x_expr, y=y_expr, anchor=anchor)
    eff._path_xy = (x_expr, y_expr)
    return eff


def _bezier_path_coord_rev(ctrl, seg_count):
    """複数セグメントを二分探索木で連結（ネスト深度 O(log n)）。

    最終セグメント(u>=(seg_count-1)/seg_count)が既定区間となる。
    """
    u = Var("u")
    values = []
    bounds = []
    for k in range(seg_count):
        i0 = 3 * k
        p0, p1, p2, p3 = ctrl[i0], ctrl[i0 + 1], ctrl[i0 + 2], ctrl[i0 + 3]
        t0 = k / seg_count
        t1 = (k + 1) / seg_count
        s = clip((_to_expr(u) - Const(t0)) / Const(t1 - t0), 0, 1)
        values.append(_bezier_segment_expr(s, p0, p1, p2, p3))
        if k < seg_count - 1:
            bounds.append(t1)
    return _piecewise_tree(u, values, bounds)


def throw(vx, vy, *, gravity=1.0, x0=0.5, y0=0.5, anchor="center"):
    """物理ベース（初速+重力）の放物運動 move Effect。

    位置は画面比率。u を正規化時間として
      x(u) = x0 + vx*u,  y(u) = y0 + vy*u + 0.5*gravity*u^2
    （+y が下方向）。move に統合されるため既存 overlay 経路で描画される。
    """
    u = Var("u")
    x_expr = Const(x0) + Const(vx) * u
    y_expr = Const(y0) + Const(vy) * u + Const(0.5 * gravity) * u * u
    eff = Effect("move", x=x_expr, y=y_expr, anchor=anchor)
    eff._path_xy = (x_expr, y_expr)
    return eff


def inertia(vx, vy, *, damping=3.0, x0=0.5, y0=0.5, anchor="center"):
    """初速から指数減衰する慣性移動 move Effect（滑らかな減速）。

    x(u) = x0 + vx*(1-exp(-damping*u))/damping。damping が大きいほど早く止まる。
    """
    if damping <= 0:
        raise ValueError("inertia: damping は正の値が必要です")
    u = Var("u")
    decay = (Const(1) - exp(Const(-damping) * u)) / Const(damping)
    x_expr = Const(x0) + Const(vx) * decay
    y_expr = Const(y0) + Const(vy) * decay
    eff = Effect("move", x=x_expr, y=y_expr, anchor=anchor)
    eff._path_xy = (x_expr, y_expr)
    return eff


class _LookAtExpr(Expr):
    """パス(x_expr, y_expr)の進行方向角(rad)を有限差分で求めるExpr。

    to_ffmpeg では u を ±du ずらした座標式を atan2 に渡す。x はW比率、
    y はH比率だが、アスペクト補正は行わず比率空間での方向を返す（近似）。
    """
    def __init__(self, x_expr, y_expr, offset_rad=0.0, du=1e-3):
        self.x_expr = x_expr
        self.y_expr = y_expr
        self.offset_rad = offset_rad
        self.du = du

    def to_ffmpeg(self, u_expr):
        up = f"(({u_expr})+{self.du})"
        um = f"(({u_expr})-{self.du})"
        dx = f"(({self.x_expr.to_ffmpeg(up)})-({self.x_expr.to_ffmpeg(um)}))"
        dy = f"(({self.y_expr.to_ffmpeg(up)})-({self.y_expr.to_ffmpeg(um)}))"
        return f"(atan2({dy}\\,{dx})+{self.offset_rad})"

    def eval_at(self, u_value):
        du = self.du
        dx = self.x_expr.eval_at(u_value + du) - self.x_expr.eval_at(u_value - du)
        dy = self.y_expr.eval_at(u_value + du) - self.y_expr.eval_at(u_value - du)
        return _math.atan2(dy, dx) + self.offset_rad


def look_at(path, *, offset_deg=0.0, expand=True, fill="0x00000000"):
    """パスの進行方向を向く回転Effect（rotate_to のパス追従版）。

    path: move系Effect（move_along/path_bezier/throw/inertia）または
      (x_expr, y_expr) のタプル。パスの微分(有限差分)から角度を求める。
    """
    if isinstance(path, Effect) and hasattr(path, "_path_xy"):
        x_expr, y_expr = path._path_xy
    elif isinstance(path, (tuple, list)) and len(path) == 2:
        x_expr, y_expr = _to_expr(path[0]), _to_expr(path[1])
    else:
        raise TypeError(
            "look_at: path は move系Effect か (x_expr, y_expr) を渡してください")
    offset_rad = offset_deg * _math.pi / 180.0
    rad_expr = _LookAtExpr(x_expr, y_expr, offset_rad)
    return Effect("rotate_to", rad=rad_expr, expand=expand, fill=fill)


def perlin(u, *, octaves=2, seed=0, frequency=1.0, amplitude=1.0):
    """sin合成による滑らかな擬似ノイズ Expr（手ブレカメラ等に使用）。

    複数オクターブの sin を重ね合わせ、u∈[0,1] で滑らかに変動する値を返す。
    出力はおおよそ [-amplitude, amplitude] に収まる。shake Effect が
    規則的な正弦振動なのに対し、perlin は非整数周波数の重ね合わせで
    不規則で自然な揺れを作る（値式なので move/rotate_to 等に渡せる）。
    """
    if octaves < 1:
        raise ValueError("perlin: octaves は1以上が必要です")
    u = _to_expr(u)
    rng = __import__("random").Random(seed)
    total = None
    norm = 0.0
    for k in range(octaves):
        freq = frequency * (2 ** k) * (1 + 0.13 * (k + 1))  # 非整数比で周期性を崩す
        phase = rng.uniform(0, 2 * _math.pi)
        amp = 0.5 ** k
        norm += amp
        wave = sin(u * Const(2 * _math.pi * freq) + Const(phase)) * Const(amp)
        total = wave if total is None else total + wave
    return total * Const(amplitude / norm)


def tile(obj, cols, rows, gap=0):
    """obj を cols×rows のグリッドに複製配置（Object.grid の関数版）。obj を返す。"""
    if not isinstance(obj, Object):
        raise TypeError("tile: 第1引数は Object が必要です")
    return obj.grid(cols, rows, gap=gap)


class Group:
    """複数Objectをまとめて同一Transform/Effectを一括適用するプロキシ。

    使用例:
        group(a, b, c) <= move(x=0.5, y=0.5)   # 各Objectへ委譲
        group(a, b).time(3)                     # time/until も委譲
    各適用は個々のObjectの __le__ / time / until へ転送する。
    """
    def __init__(self, *objects):
        flat = []
        for o in objects:
            if isinstance(o, Group):
                flat.extend(o.objects)
            elif isinstance(o, Object):
                flat.append(o)
            else:
                raise TypeError(f"group: Object のみ渡せます: {type(o)}")
        if not flat:
            raise ValueError("group: 最低1つのObjectが必要です")
        self.objects = flat

    def __le__(self, rhs):
        for o in self.objects:
            o.__le__(rhs)
        return self

    def time(self, duration=None, *, name=None):
        """各メンバーを time() で「順次配置」する（メンバーが順番に並ぶ）。

        注意: time() は各メンバーを直列に配置するため、グループ全体の尺は
        メンバー数 N 倍（N*duration）になる。全メンバーを同一開始時刻に
        「同時に重ねて」配置したい場合は stack() または show() を使うこと。
        """
        # name は先頭Objectにのみ付与（アンカー重複を避ける）
        for i, o in enumerate(self.objects):
            o.time(duration, name=name if i == 0 else None)
        return self

    def until(self, name, offset=0.0):
        for o in self.objects:
            o.until(name, offset=offset)
        return self

    def show(self, duration, *, priority=None):
        for o in self.objects:
            o.show(duration, priority=priority)
        return self

    def stack(self, duration, *, priority=None):
        """全メンバーを同一開始時刻に重ねて配置し、タイムラインを duration だけ進める。

        time() が各メンバーを順次配置（グループ尺 N 倍）するのに対し、stack() は
        全メンバーを同時表示する。各メンバーは show() で配置（advance しない）し、
        タイムライン全体は末尾に一度だけ pause を挟んで duration 進める。
        """
        for o in self.objects:
            o.show(duration, priority=priority)
        # メンバーは advance しないため、タイムラインを一度だけ duration 進める
        if self.objects and Project._current is not None:
            pause.time(duration)
        return self


def group(*objects):
    """複数ObjectをまとめるGroupプロキシを返す（group(a,b,c) <= move(...)）。"""
    return Group(*objects)


def wipe(direction="left", progress=None):
    """ワイプEffect。direction: left/right/up/down"""
    if progress is None:
        progress = _resolve_param(lambda u: u)
    else:
        progress = _resolve_param(progress)
    return Effect("wipe", direction=direction, progress=progress)


def zoom(value=None, *, from_value=1, to_value=None):
    """ズームEffect。valueまたはfrom/to指定。scaleのエイリアス。"""
    if value is not None:
        return Effect("scale", value=_resolve_param(value))
    if to_value is None:
        raise ValueError("zoom: value か to_value の指定が必要です")
    expr = _resolve_param(lambda u: lerp(from_value, to_value, u))
    return Effect("scale", value=expr)


def color_shift(*, hue=None, saturation=None, brightness=None):
    """時間依存の色調変化Effect。各パラメータはExpr/lambda/数値。"""
    params = {}
    if hue is not None:
        params["hue"] = _resolve_param(hue)
    if saturation is not None:
        params["saturation"] = _resolve_param(saturation)
    if brightness is not None:
        params["brightness"] = _resolve_param(brightness)
    if not params:
        raise ValueError("color_shift: hue/saturation/brightness のいずれかが必要です")
    return Effect("color_shift", **params)


def shake(amplitude=0.02, frequency=10):
    """振動Effect（ライブ、overlay座標でシェイク）"""
    return Effect("shake", amplitude=amplitude, frequency=frequency)


def chroma_key(color="green", similarity=0.1, blend=0.0):
    """クロマキーEffect: 指定色を透明化（chromakeyフィルタ）。

    color: 色名 or 16進（#RRGGBB / 0xRRGGBB）
    similarity: 透明化する色の類似度（1e-5〜1.0、大きいほど広範囲）
    blend: 境界のブレンド量（0〜1）
    """
    color = _validate_ffmpeg_color("chroma_key", color)
    _require_number("chroma_key", "similarity", similarity, 1e-5, 1.0)
    _require_number("chroma_key", "blend", blend, 0.0, 1.0)
    return Effect("chroma_key", color=color, similarity=similarity, blend=blend)


def vignette(angle=None, strength=None):
    """ビネットEffect（vignetteフィルタ）。

    angle: レンズ角度(rad, 0〜PI/2, Expr/lambda可) または
    strength: 強度(0〜1, Expr/lambda可)をangle=strength*PI/2に変換。
    どちらか一方のみ指定（両方省略時はffmpegデフォルトのPI/5）。
    注意: vignetteフィルタはアルファ非対応のため透明部分は失われる（全画面素材向け）。
    """
    if angle is not None and strength is not None:
        raise ValueError("vignette: angle と strength は同時に指定できません")
    if angle is None and strength is None:
        angle_expr = Const(_math.pi / 5)
    elif angle is not None:
        angle_expr = _resolve_param(angle)
    else:
        angle_expr = _resolve_param(strength) * Const(_math.pi / 2)
    return Effect("vignette", angle=angle_expr)


def pixelize(size=16):
    """モザイクEffect（pixelizeフィルタ）。size: ブロックサイズpx（1〜1024）。

    ffmpegのpixelizeフィルタはサイズの式指定に非対応のため定数のみ。
    """
    if isinstance(size, Expr) or callable(size):
        raise ValueError(
            "pixelize: size に Expr/lambda は使えません"
            "（ffmpeg pixelizeフィルタが式評価非対応のため定数のみ）")
    _require_number("pixelize", "size", size, 1, 1024)
    return Effect("pixelize", size=int(size))


def glow(radius=10, intensity=1.0):
    """発光Effect: split→gblur→blend=screen の合成チェーン。

    radius: ぼかしのシグマ（0.1〜1024）
    intensity: 発光の強さ（0〜1、blendのall_opacity）
    """
    _require_number("glow", "radius", radius, 0.1, 1024)
    _require_number("glow", "intensity", intensity, 0.0, 1.0)
    return Effect("glow", radius=radius, intensity=intensity)


_LUT_EXTS = {".cube", ".3dl", ".dat", ".m3d", ".csp"}


def lut(file):
    """3D LUT Effect（lut3dフィルタ）。file: .cube等のLUTファイルパス。

    ファイルの存在を構築時に検証し、内容(FFP)をフィンガープリントに含める。
    """
    if not isinstance(file, str) or not file:
        raise ValueError("lut: file にはLUTファイルパスの文字列を指定してください")
    if not os.path.exists(file):
        raise ValueError(f"lut: LUTファイルが見つかりません: {file}")
    ext = os.path.splitext(file)[1].lower()
    if ext not in _LUT_EXTS:
        raise ValueError(
            f"lut: 未対応のLUT形式です: '{ext}'（対応: {', '.join(sorted(_LUT_EXTS))}）")
    return Effect("lut", file=file)


def glitch(strength=1.0, interval=None):
    """グリッチEffect: rgbashift + noise のプリセット。

    strength: 強度（0〜5、RGBずらし量とノイズ量に反映）
    interval: 秒指定で間欠発動（各周期の先頭30%区間のみ有効）。Noneで常時。
    """
    _require_number("glitch", "strength", strength, 0.0, 5.0)
    if interval is not None:
        _require_number("glitch", "interval", interval, 0.01, None)
    return Effect("glitch", strength=strength, interval=interval)


def perspective_warp(x0, y0, x1, y1, x2, y2, x3, y3):
    """透視変形Effect（perspectiveフィルタ, sense=destination）。

    入力の4隅（左上, 右上, 左下, 右下）の移動先座標(px)を指定する。
    """
    for name, v in zip(("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"),
                       (x0, y0, x1, y1, x2, y2, x3, y3)):
        _require_number("perspective_warp", name, v)
    return Effect("perspective_warp", x0=x0, y0=y0, x1=x1, y1=y1,
                  x2=x2, y2=y2, x3=x3, y3=y3)


def lens(k1=0, k2=0):
    """レンズ歪みEffect（lenscorrectionフィルタ）。

    k1: 2次歪み係数（-1〜1、負で樽型・正で糸巻き型の補正）
    k2: 4次歪み係数（-1〜1）
    """
    _require_number("lens", "k1", k1, -1.0, 1.0)
    _require_number("lens", "k2", k2, -1.0, 1.0)
    return Effect("lens", k1=k1, k2=k2)


def ken_burns(from_rect, to_rect, easing=None):
    """Ken Burns Effect: 2つの矩形 (x, y, w, h) 間を補間してパン&ズーム。

    zoompanは使わず、動的scale + 固定サイズcropで実現する。
    from_rect/to_rect: 元素材ピクセル座標の (x, y, w, h) タプル（同一アスペクト比）
    easing: イージング関数（ease_in_out_quad等）。省略時は線形。
    出力サイズは両矩形の最大寸法（偶数丸め）に正規化される。
    """
    rects = {}
    for nm, rect in (("from_rect", from_rect), ("to_rect", to_rect)):
        if not isinstance(rect, (tuple, list)) or len(rect) != 4:
            raise ValueError(
                f"ken_burns: {nm} は (x, y, w, h) の4要素タプルで指定してください: {rect!r}")
        for i, v in enumerate(rect):
            _require_number("ken_burns", f"{nm}[{i}]", v)
        if rect[2] <= 0 or rect[3] <= 0:
            raise ValueError(f"ken_burns: {nm} の w, h は正の値が必要です: {rect!r}")
        rects[nm] = tuple(rect)
    fx, fy, fw, fh = rects["from_rect"]
    tx, ty, tw, th = rects["to_rect"]
    # アスペクト比の一致検証（1%許容）
    if _builtins.abs(fw / fh - tw / th) > 0.01 * (fw / fh):
        raise ValueError(
            f"ken_burns: from_rect と to_rect のアスペクト比が一致していません"
            f"（from: {fw}x{fh} = {fw / fh:.4f}, to: {tw}x{th} = {tw / th:.4f}）。"
            f"同じアスペクト比の矩形を指定してください。")
    out_w = int(_math.ceil(_builtins.max(fw, tw) / 2) * 2)
    out_h = int(_math.ceil(_builtins.max(fh, th) / 2) * 2)
    e_expr = _resolve_param(easing) if easing is not None else Var("u")
    # overshoot 系イージング(ease_out_back/elastic 等)は e>1 になり得る。
    # e>1 だと w_expr>元幅 → scale後幅<crop幅 となり FFmpeg が
    # "Invalid too big size for width" でレンダを中断する。
    # スケール算出用の補間係数のみ [0,1] にクランプする（x/y パンには overshoot を残す）。
    e_clamped = clip(e_expr, 0, 1)
    w_expr = lerp(fw, tw, e_clamped)
    s_expr = Const(out_w) / w_expr          # 全体スケール係数
    x_expr = lerp(fx, tx, e_expr) * s_expr  # スケール後座標でのcrop位置
    y_expr = lerp(fy, ty, e_expr) * s_expr
    return Effect("ken_burns", s=s_expr, x=x_expr, y=y_expr, w=out_w, h=out_h)


def drop_shadow(dx=5, dy=5, blur=8, color="black", opacity=0.5):
    """ドロップシャドウEffect: split→色付け+gblur→本体の背後にoverlay。

    dx, dy: 影のオフセット(px)。blur: ぼかしシグマ（0でシャープな影）。
    出力キャンバスは影が収まるよう自動拡張される。
    """
    _require_number("drop_shadow", "dx", dx)
    _require_number("drop_shadow", "dy", dy)
    _require_number("drop_shadow", "blur", blur, 0.0, 100.0)
    _require_number("drop_shadow", "opacity", opacity, 0.0, 1.0)
    _parse_color_rgb(color)  # 構築時に色を検証
    return Effect("drop_shadow", dx=int(_builtins.round(dx)),
                  dy=int(_builtins.round(dy)), blur=blur,
                  color=color, opacity=opacity)


def outline(width=2, color="white"):
    """縁取りEffect: alpha膨張（dilationフィルタをwidth回連結）ベース。

    色付けした複製のalphaをdilationで膨張させ、本体をその上にoverlayする。
    width: 縁取り幅px（1〜16の整数、dilation 1回につき1px膨張）
    """
    if isinstance(width, bool) or not isinstance(width, int) or not (1 <= width <= 16):
        raise ValueError(f"outline: width は 1〜16 の整数で指定してください: {width!r}")
    _parse_color_rgb(color)  # 構築時に色を検証
    return Effect("outline", width=width, color=color)


# --- 合成・コンポジション系Effect ---

def _validate_mask_image(func, image_path):
    """マスク画像パスの検証（文字列・存在・画像形式）"""
    if not isinstance(image_path, str) or not image_path:
        raise TypeError(
            f"{func}: image_path にはマスク画像のパス文字列を指定してください: {image_path!r}")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"{func}: マスク画像が見つかりません: {image_path}")
    if _detect_media_type(image_path) != "image":
        raise ValueError(f"{func}: マスクには画像のみ指定できます: {image_path}")


def _register_material_dep(path):
    """素材をレイヤー依存として登録（レイヤーキャッシュの鮮度検証に載せる）"""
    proj = Project._current
    if proj is not None and proj._current_layer_file:
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).append(path)


def mask(image_path):
    """マスクEffect: 画像の輝度をアルファとして乗算する。

    白い部分は不透明のまま、黒い部分は透明になる（グレーは半透明）。
    追加 -i 入力の配線を避けるため movie= ソースで filter chain 内に読み込み、
    scale2ref で素材サイズへ自動スケールする。元素材のアルファとは乗算合成。
    """
    _validate_mask_image("mask", image_path)
    _register_material_dep(image_path)
    return Effect("mask", image=image_path)


def mask_wipe(image_path, progress=None):
    """マスクワイプEffect: マスク画像の輝度をしきい値に使うワイプ。

    輝度 <= progress*255 の画素から順に現れる（黒い部分が先、白い部分が最後）。
    progress は 0→1 の進行（Expr/lambda可、省略時は線形 u）。
    グラデーション画像を使うと方向・形状を自由に制御できる。
    """
    _validate_mask_image("mask_wipe", image_path)
    _register_material_dep(image_path)
    if progress is None:
        progress = _resolve_param(lambda u: u)
    else:
        progress = _resolve_param(progress)
    return Effect("mask_wipe", image=image_path, progress=progress)


def opacity(value):
    """不透明度Effect。定数(0〜1)は colorchannelmixer（高速）、
    Expr/lambda は geq による live アニメーション対応。"""
    v = _resolve_param(value)
    if isinstance(v, Const):
        _require_number("opacity", "value", v.value, 0.0, 1.0)
    return Effect("opacity", value=v)


# FFmpeg blend フィルタの合成モード（normal は通常overlayと同義のため許可のみ）
_BLEND_MODES = {
    "addition", "addition128", "grainmerge", "and", "average", "burn",
    "darken", "difference", "difference128", "grainextract", "divide",
    "dodge", "exclusion", "extremity", "freeze", "glow", "hardlight",
    "hardmix", "heat", "lighten", "linearlight", "multiply", "multiply128",
    "negation", "normal", "or", "overlay", "phoenix", "pinlight", "reflect",
    "screen", "softlight", "subtract", "vividlight", "xor", "softdifference",
    "geometric", "harmonic", "bleach", "stain", "interpolate", "hardoverlay",
}
_BLEND_MODE_ALIASES = {"add": "addition", "plus": "addition"}


def blend_mode(mode):
    """オブジェクトの合成モードを変更するEffect（screen/multiply/overlay等）。

    overlayフィルタは合成モード非対応のため、このオブジェクトのみ
    「キャンバス全面へ透明パドした入力」を blend=cN_mode=<mode> で合成し、
    アルファ領域だけ maskedmerge で採用する経路に切り替わる（live）。
    """
    if not isinstance(mode, str):
        raise TypeError(f"blend_mode: mode には合成モード名の文字列を指定してください: {mode!r}")
    m = _BLEND_MODE_ALIASES.get(mode.strip().lower(), mode.strip().lower())
    if m not in _BLEND_MODES:
        hint = _suggest_hint(m, _BLEND_MODES)
        raise ValueError(
            f"blend_mode: 未知の合成モード '{mode}'。{hint}\n"
            f"有効なモード: {', '.join(sorted(_BLEND_MODES))}")
    return Effect("blend_mode", mode=m)


def rounded(radius):
    """角丸Effect: geq でアルファに角丸矩形マスクを乗算する。

    radius: 角の半径px（0で無効）。
    """
    _require_number("rounded", "radius", radius, 0, 4096)
    return Effect("rounded", radius=int(_builtins.round(radius)))


def pip(x=0.7, y=0.7, scale=0.3, radius=12, border=2, border_color="white",
        shadow=True):
    """ピクチャインピクチャのプリセット（既存Effectの組を返すEffectChain）。

    scale縮小 → rounded角丸 → outline縁取り → drop_shadow → move配置 の合成。
    x/y: 配置位置（キャンバス比率、中央anchor）。scale: 縮小率。
    radius: 角丸半径px（0で無効）。border: 縁取り幅px（0で無効）。
    """
    _require_number("pip", "x", x, 0.0, 1.0)
    _require_number("pip", "y", y, 0.0, 1.0)
    _require_number("pip", "scale", scale, 0.01, 1.0)
    _require_number("pip", "radius", radius, 0, 4096)
    if isinstance(border, bool) or not isinstance(border, int) or not (0 <= border <= 16):
        raise ValueError(f"pip: border は 0〜16 の整数で指定してください: {border!r}")
    effs = [Effect("scale", value=Const(float(scale)))]
    if radius > 0:
        effs.append(Effect("rounded", radius=int(radius)))
    if border > 0:
        effs.append(outline(border, border_color))
    if shadow:
        effs.append(drop_shadow(dx=4, dy=4, blur=8, opacity=0.4))
    effs.append(move(x=x, y=y, anchor="center"))
    return EffectChain(effs)


def blur_background_fill(blur=20):
    """縦横変換の定番「ぼかした自分自身を背景に敷く」Effect。

    素材をキャンバス全面に cover で拡大ぼかしし、中央に本体を fit で重ねる。
    出力はキャンバスサイズ固定。live Effect（キャンバスサイズのffv1キャッシュ
    肥大とProject解像度依存を避けるためチェックポイント対象外）。
    """
    _require_number("blur_background_fill", "blur", blur, 0.1, 200)
    return Effect("blur_background_fill", blur=blur)


def _parse_color_alpha(func, color):
    """'white@0.2' 形式の色指定を (R, G, B, A0-255) に分解する"""
    if not isinstance(color, str) or not color:
        raise ValueError(
            f"{func}: color には色名か16進の文字列を指定してください: {color!r}")
    body, sep, alpha_str = color.partition("@")
    alpha = 1.0
    if sep:
        try:
            alpha = float(alpha_str)
        except ValueError:
            raise ValueError(f"{func}: 不正なアルファ指定です: '{color}'")
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"{func}: アルファは0〜1で指定してください: '{color}'")
    r, g, b = _parse_color_rgb(body)
    return (r, g, b, int(_builtins.round(alpha * 255)))


def progress_bar(*, height=6, color="white", bg="white@0.2", y=1.0):
    """動画全体の進行バーを表示する特殊Object（透明lavfi + geq、textと同方式）。

    duration 未設定のまま動画全体に表示される（time/show は不要）。
    color: バー色、bg: 背景トラック色（'white@0.2' のようにアルファ指定可）。
    y: 縦位置（0=上端, 1=下端）。
    """
    _require_number("progress_bar", "height", height, 1, 512)
    _require_number("progress_bar", "y", y, 0.0, 1.0)
    bar_rgba = _parse_color_alpha("progress_bar", color)
    track_rgba = _parse_color_alpha("progress_bar", bg)
    spec = {
        "kind": "progress_bar",
        "height": int(height), "y": float(y),
        "bar_rgba": bar_rgba, "track_rgba": track_rgba,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"pbar|{height}|{color}|{bg}|{y}")
    obj = _new_text_object(spec)
    obj._advance = False  # タイムラインを進めない（全体に重ねる表示専用）
    return obj


# --- 音声エフェクト関数 ---

def again(value=1.0):
    """音量倍率"""
    return AudioEffect("again", value=_resolve_param(value))


def afade(alpha=1.0):
    """音量フェード"""
    return AudioEffect("afade", alpha=_resolve_param(alpha))


def adelete():
    """音声をミックスから除外"""
    return AudioEffect("adelete")


def delete():
    """映像をオーバーレイから除外"""
    return Effect("delete")


def trim(duration=None):
    """映像トリム（時間影響あり）"""
    return Effect("trim", duration=duration)


def atrim(duration=None):
    """音声トリム（時間影響あり）"""
    return AudioEffect("atrim", duration=duration)


def atempo(rate=1.0):
    """音声テンポ変更（時間影響あり）"""
    return AudioEffect("atempo", rate=rate)


# --- 時間操作Effect（映像・live） ---

def speed(factor):
    """再生速度Effect（setpts=PTS/factor）。映像の実効尺は 元尺/factor になる
    （length()/duration自動決定に反映される）。

    音声付き動画には <= 適用時に対応する atempo が自動適用される
    （atempo有効範囲0.5〜100を超える場合は多段に自動分解）。
    live Effect（チェックポイントベイク対象外。ベイク済みソースに毎レンダ適用）。
    """
    _require_number("speed", "factor", factor, 0.01, 100.0)
    return Effect("speed", factor=float(factor))


def reverse():
    """逆再生Effect（reverseフィルタ）。

    注意: 全フレームをメモリに保持するため、実効尺が30秒を超える素材には
    使用できません（明示エラー）。長い素材は trim() で短くしてから適用すること。
    音声は反転されません（必要なら adelete() で除外するか別素材を用意）。
    live Effect（チェックポイントベイク対象外）。
    """
    return Effect("reverse")


def freeze_frame(at, duration):
    """フリーズフレームEffect: 時刻 at のフレームで duration 秒静止してから
    続きを再生する（トータル尺は +duration。length()に反映される）。

    trim 3分割 + loop + concat のチェーン内サブグラフで実装。
    音声は変化しません（音声も止めたい場合は別途編集）。
    live Effect（チェックポイントベイク対象外）。
    """
    _require_number("freeze_frame", "at", at, 0.0, None)
    _require_number("freeze_frame", "duration", duration, 0.01, None)
    return Effect("freeze_frame", at=float(at), duration=float(duration))


# --- テキスト系ファクトリ（映像Object, drawtext/subtitlesベース） ---

_TEXT_ANCHORS = ("center", "left")


def _text_synthetic_source(spec_key):
    """テキストObject用の合成ソースパス（実体なし・署名/一意化用）"""
    h = hashlib.sha256(spec_key.encode("utf-8")).hexdigest()[:12]
    return f"text://{h}.txt"


def text(content, *, x=0.5, y=0.5, size=48, color="white", font=None,
         box=False, box_color="black@0.5", box_border=10,
         alpha=1.0, anchor="center"):
    """drawtextでテキストを直接描画する映像Object（透明キャンバス全面）。

    x/y/alpha は 0..1 のキャンバス比率で Expr/lambda 可（liveアニメ）。
    size は定数のみ（FFmpeg 8.0 drawtext の fontsize 式は SEGV のため）。
    日本語表示にはfont指定を推奨（未指定はmeiryo等の既定候補を自動探索）。
    タイムラインには image と同様 .time(秒) で配置する。
    """
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"text: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    spec = {
        "kind": "text",
        "content": str(content),
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("text", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"text|{content}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def typewriter(content, *, cps=10, x=0.5, y=0.5, size=48, color="white",
               font=None, box=False, box_color="black@0.5", box_border=10,
               alpha=1.0, anchor="left"):
    """textの派生。1文字ずつ表示（n個のdrawtextを各文字の表示時刻でenable）。
    cps: 1秒あたりの表示文字数。既定anchorは左上（左揃えで打ち出す）。"""
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"typewriter: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    if cps <= 0:
        raise ValueError(f"typewriter: cps は正の数を指定してください: {cps}")
    spec = {
        "kind": "typewriter",
        "content": str(content), "cps": float(cps),
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("typewriter", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"tw|{content}|{cps}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def _parse_counter_format(fmt):
    """counterのformatを (prefix, suffix, width) に分解。整数指定のみ対応。"""
    i = fmt.find("%")
    if i < 0:
        raise ValueError(
            f"counter: format に数値プレースホルダ(%d 等)が必要です: {fmt!r}")
    j = i + 1
    zero = False
    if j < len(fmt) and fmt[j] == "0":
        zero = True
        j += 1
    digits = ""
    while j < len(fmt) and fmt[j].isdigit():
        digits += fmt[j]
        j += 1
    if j >= len(fmt):
        raise ValueError(f"counter: format の変換指定が不完全です: {fmt!r}")
    conv = fmt[j]
    if conv not in ("d", "i"):
        raise ValueError(
            f"counter: format は整数指定(%d, %03d 等)のみ対応です: {fmt!r}\n"
            f"小数表示は未対応です。")
    width = int(digits) if (zero and digits) else None
    return fmt[:i], fmt[j + 1:], width


def counter(from_, to, *, format="%d", x=0.5, y=0.5, size=48, color="white",
            font=None, box=False, box_color="black@0.5", box_border=10,
            alpha=1.0, anchor="center"):
    """数値カウントアップ映像Object。drawtextの%{eif}式で from_→to を補間表示。
    format は整数指定(%d, %03d 等)。前後のリテラル文字も表示可能。"""
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"counter: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    prefix, suffix, width = _parse_counter_format(format)
    _escape_counter_literal(prefix)  # アポストロフィ等の早期検証（inline不可文字）
    _escape_counter_literal(suffix)
    spec = {
        "kind": "counter",
        "from_": _resolve_param(from_), "to": _resolve_param(to),
        "prefix": prefix, "suffix": suffix, "width": width,
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("counter", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"counter|{from_}|{to}|{format}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def subtitles(srt_file, *, style=None):
    """SRT字幕ファイルをsubtitlesフィルタで合成する映像Object。
    style: ASSのforce_styleスタイル文字列（例 "FontName=Meiryo,FontSize=28"）。
    SRTは自身のタイムコードで表示されるため .time(全体尺) で開始0に配置する想定。"""
    if not isinstance(srt_file, str):
        raise TypeError(f"subtitles: srt_file はパス文字列で指定してください: {srt_file!r}")
    if not os.path.exists(srt_file):
        raise FileNotFoundError(f"subtitles: 字幕ファイルが見つかりません: {srt_file}")
    ext = os.path.splitext(srt_file)[1].lower()
    if ext not in (".srt", ".ass", ".vtt"):
        raise ValueError(
            f"subtitles: 対応拡張子は .srt/.ass/.vtt です: {srt_file}")
    spec = {
        "kind": "subtitles",
        "srt": srt_file,
        "style": style,
        # drawtext系オプションは未使用だが _new_text_object の一貫性のため保持
        "x": Const(0.5), "y": Const(0.5), "size": Const(48), "alpha": Const(1.0),
        "color": "white", "font": None, "box": False,
        "box_color": "black@0.5", "box_border": 10, "anchor": "center",
    }
    try:
        ffp = _file_fingerprint(srt_file)
        spec["synthetic_source"] = _text_synthetic_source(
            f"subs|{ffp[0]}|{ffp[1]}|{ffp[2]}|{style}")
    except OSError:
        spec["synthetic_source"] = _text_synthetic_source(f"subs|{srt_file}|{style}")
    obj = _new_text_object(spec)
    # SRTをレイヤー依存として登録（cache鮮度検証で字幕変更を検知）
    proj = Project._current
    if proj is not None and proj._current_layer_file:
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).append(srt_file)
    return obj


# --- karaoke（ASS \k タグによるカラオケ風ハイライト字幕） ---

# 既知の色名 -> #RRGGBB（karaoke styleの簡易色指定用）
_ASS_NAMED_COLORS = {
    "white": "FFFFFF", "black": "000000", "red": "FF0000", "green": "00FF00",
    "blue": "0000FF", "yellow": "FFFF00", "cyan": "00FFFF", "magenta": "FF00FF",
    "orange": "FFA500", "gray": "808080", "grey": "808080", "pink": "FFC0CB",
}


def _color_to_ass(color, alpha=0):
    """色指定をASSの &HAABBGGRR 16進文字列に変換する。
    'white'等の既知色名 / '#RRGGBB' / 既にASS形式('&H..'始まり)のいずれかを受け付ける。"""
    if isinstance(color, str) and color.upper().startswith("&H"):
        return color
    if not isinstance(color, str):
        raise ValueError(f"karaoke: 色指定は文字列で指定してください: {color!r}")
    name = color.lower()
    hexrgb = _ASS_NAMED_COLORS.get(name, color.lstrip("#"))
    if len(hexrgb) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexrgb):
        raise ValueError(
            f"karaoke: 未対応の色指定です: {color!r}"
            f"（既知色名 {sorted(_ASS_NAMED_COLORS)} か #RRGGBB を指定してください）")
    rr, gg, bb = hexrgb[0:2], hexrgb[2:4], hexrgb[4:6]
    return f"&H{alpha:02X}{bb}{gg}{rr}".upper()


def _fmt_ass_time(t):
    """秒 -> ASSタイムコード（H:MM:SS.cc、センチ秒単位）"""
    cs_total = int(round(float(t) * 100))
    h, rem = divmod(cs_total, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(s):
    """ASSダイアログテキスト用エスケープ（\\、{}、改行）"""
    return (s.replace("\\", "\\\\").replace("{", "\\{")
             .replace("}", "\\}").replace("\r\n", "\\N").replace("\n", "\\N"))


def _karaoke_tokenize(text):
    """カラオケ行を\\kタグの単位（語）に分割する。
    空白を含む場合は空白区切り（末尾の空白を保持）、無ければ1文字ずつに分割
    （日本語歌詞のように分かち書きが無い場合の既定挙動）。"""
    if any(c.isspace() for c in text):
        toks = re.findall(r"\S+\s*", text)
        return toks if toks else [text]
    return list(text)


def karaoke(lines, *, style=None):
    """カラオケ風ハイライト字幕（ASSの\\kタグ）を生成する映像Object。

    lines: [(start, end, "歌詞"), ...] または
           [(start, end, "歌詞", [word_durations...]), ...] のリスト。
    - word_durations省略時: 行内の語（分割規約は_karaoke_tokenize参照）に
      (end-start)を均等割りして\\kタグを割り当てる。
    - word_durations指定時: 分割された語の数と同じ長さの秒数リストを指定する
      （語ごとのハイライト時間、\\kタグの単位はセンチ秒に変換）。
    style: {"font", "size", "primary"（既に発音済みの色）, "secondary"（未発音の色）,
            "outline_color", "back_color", "alignment", "margin_v", "outline",
            "shadow", "bold"} を上書きする辞書（省略キーは既定値）。

    生成したASSは歌詞+タイミング+styleのSHA256でcontent-addressedキャッシュに
    書き出し、subtitles()経由でsubtitlesフィルタとして合成する。
    SRT/ASSと同様に .time(全体尺) で開始0に配置する想定。
    """
    if not isinstance(lines, (list, tuple)) or len(lines) == 0:
        raise ValueError("karaoke: lines には1行以上指定してください")
    st = dict(style or {})
    font = st.get("font", "Meiryo")
    size = int(st.get("size", 48))
    primary = _color_to_ass(st.get("primary", "yellow"))
    secondary = _color_to_ass(st.get("secondary", "white"))
    outline_color = _color_to_ass(st.get("outline_color", "black"))
    back_color = _color_to_ass(st.get("back_color", "black"), alpha=0x80)
    alignment = int(st.get("alignment", 2))
    margin_v = int(st.get("margin_v", 60))
    outline_w = st.get("outline", 2)
    shadow = st.get("shadow", 0)
    bold = -1 if st.get("bold", True) else 0

    body_lines = []
    for idx, line in enumerate(lines):
        if not isinstance(line, (list, tuple)) or len(line) not in (3, 4):
            raise ValueError(
                f"karaoke: lines[{idx}] は (start,end,text) または "
                f"(start,end,text,word_durations) を指定してください: {line!r}")
        if len(line) == 3:
            t0, t1, txt = line
            word_durs = None
        else:
            t0, t1, txt, word_durs = line
        t0 = float(t0)
        t1 = float(t1)
        if t1 <= t0:
            raise ValueError(
                f"karaoke: lines[{idx}] の end は start より後が必要です: {line!r}")
        tokens = _karaoke_tokenize(str(txt))
        if not tokens:
            continue
        if word_durs is not None:
            word_durs = list(word_durs)
            if len(word_durs) != len(tokens):
                raise ValueError(
                    f"karaoke: lines[{idx}] の word_durations 数({len(word_durs)})が"
                    f"分割語数({len(tokens)})と一致しません。分割結果: {tokens}\n"
                    f"（分割規約: 空白を含む行は空白区切り、無ければ1文字ずつ）")
            for d in word_durs:
                _require_number("karaoke", "word_durations要素", d, 0.001, None)
        else:
            each = (t1 - t0) / len(tokens)
            word_durs = [each] * len(tokens)
        k_text = "".join(
            f"{{\\k{max(1, round(float(d) * 100))}}}{_escape_ass_text(tok)}"
            for tok, d in zip(tokens, word_durs))
        body_lines.append(
            f"Dialogue: 0,{_fmt_ass_time(t0)},{_fmt_ass_time(t1)},Karaoke,,0,0,0,,{k_text}")

    if not body_lines:
        raise ValueError("karaoke: 有効な行がありません（全行が空テキストでした）")

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Karaoke,{font},{size},{primary},{secondary},{outline_color},"
        f"{back_color},{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},"
        f"{alignment},20,20,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    content = header + "\n".join(body_lines) + "\n"

    key = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    ass_path = os.path.join(_ARTIFACT_DIR, "karaoke", f"{key}.ass")
    if not os.path.exists(ass_path):
        os.makedirs(os.path.dirname(ass_path), exist_ok=True)
        tmp_path = ass_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, ass_path)

    return subtitles(ass_path)


# --- オーディオ系ファクトリ ---

def duck_under(other, *, ratio=8, threshold=0.05, attack=20, release=250):
    """sidechaincompress で other（ナレーション等）再生中に自音量を下げるAudioEffect。
    other は同じProjectに存在する音声Objectを指定する。"""
    if not isinstance(other, Object):
        raise TypeError(f"duck_under: other は音声Objectを指定してください: {type(other)}")
    return AudioEffect("duck_under", other=other, ratio=ratio,
                       threshold=threshold, attack=attack, release=release)


def loop(until=None):
    """aloop で音声を until 時刻までループさせるAudioEffect。
    until 省略時は Project.duration までループする。"""
    return AudioEffect("loop", until=until)


def _probe_audio_length(path):
    """音声/動画の長さを取得（取得不能時はNone）"""
    proj = Project._current
    if proj is not None:
        info = proj._probe_media(path)
        if info and info.get("duration"):
            return info["duration"]
    return None


def _validate_audio_source(func, path):
    if not isinstance(path, str):
        raise TypeError(f"{func}: ソースはパス文字列で指定してください: {path!r}")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{func}: 音声ファイルが見つかりません: {path}")
    if _detect_media_type(path) not in ("audio", "video"):
        raise ValueError(f"{func}: 音声(または動画音声)のみ指定できます: {path}")


def audio_sequence(*objs, crossfade=1.0):
    """複数の音声を acrossfade で連結した1つの音声Objectを生成（キャッシュ生成物）。
    objs は音声Object または音声パス文字列（2つ以上）。"""
    if len(objs) < 2:
        raise ValueError("audio_sequence: 2つ以上の音声を指定してください")
    _require_number("audio_sequence", "crossfade", crossfade, 0.01, None)
    proj = Project._current
    sources = []
    for o in objs:
        if isinstance(o, Object):
            if o.media_type != "audio":
                raise ValueError(
                    f"audio_sequence: 音声Objectのみ連結できます: {o.source}")
            sources.append(o.source)
            if proj is not None and o in proj.objects:
                proj.objects.remove(o)  # 合成に消費（タイムラインから除外）
        elif isinstance(o, str):
            _validate_audio_source("audio_sequence", o)
            sources.append(o)
        else:
            raise TypeError(f"audio_sequence: 音声Objectかパス文字列のみ: {type(o)}")
    n = len(sources)
    lengths = [_probe_audio_length(s) or 5.0 for s in sources]
    # acrossfade は各入力が crossfade 以上の長さを要する。
    # 素材長 < crossfade だと total が 0/負値になり後続配置が破綻するため拒否。
    for s, ln in zip(sources, lengths):
        if ln < crossfade:
            raise ValueError(
                f"audio_sequence: 素材長({ln:.3f}s)が crossfade({crossfade}s)未満です: {s}\n"
                f"crossfade を短くするか、より長い素材を指定してください。")
    total = sum(lengths) - crossfade * (n - 1)

    sigs = ["audio_sequence"]
    sigs.extend(_source_signature(s) for s in sources)
    sigs.extend([f"cf={crossfade}", f"ev={_ENGINE_VER}"])
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "aseq", f"{key}.m4a")

    cmd = ["ffmpeg", "-y"]
    for s in sources:
        cmd.extend(["-i", s])
    parts = []
    cur = "[0:a]"
    for i in range(1, n):
        out = f"[axf{i}]"
        parts.append(f"{cur}[{i}:a]acrossfade=d={crossfade}{out}")
        cur = out
    cmd.extend(["-filter_complex", ";".join(parts), "-map", cur,
                "-c:a", "aac", "-b:a", "192k", cache_path])
    return _finalize_generated_object(cache_path, cmd, list(sources), total)


def sfx(source, at, *, volume=1.0):
    """同一音源を複数時刻(at)に配置した1つの音声Objectを生成（adelay+amix合成）。
    at は秒のリスト。生成Objectは開始0でタイムラインに配置する想定。"""
    _validate_audio_source("sfx", source)
    if not isinstance(at, (list, tuple)) or len(at) == 0:
        raise ValueError("sfx: at には配置時刻(秒)のリストを指定してください")
    for t in at:
        _require_number("sfx", "at要素", t, 0, None)
    _require_number("sfx", "volume", volume, 0, None)
    srclen = _probe_audio_length(source) or 5.0
    times = list(at)
    n = len(times)
    total = _builtins.max(times) + srclen

    sigs = ["sfx", _source_signature(source),
            "at=" + ",".join(str(t) for t in times),
            f"vol={volume}", f"ev={_ENGINE_VER}"]
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "sfx", f"{key}.m4a")

    parts = ["[0:a]asplit=" + str(n) + "".join(f"[s{i}]" for i in range(n))]
    delayed = []
    for i, t in enumerate(times):
        ms = int(t * 1000)
        if ms > 0:
            parts.append(f"[s{i}]adelay={ms}:all=1[d{i}]")
        else:
            parts.append(f"[s{i}]anull[d{i}]")
        delayed.append(f"[d{i}]")
    mix_in = "".join(delayed)
    tail = f",volume={volume}" if volume != 1.0 else ""
    if n == 1:
        parts.append(f"{mix_in}anull{tail}[a]")
    else:
        parts.append(f"{mix_in}amix=inputs={n}:normalize=0{tail}[a]")
    cmd = ["ffmpeg", "-y", "-i", source,
           "-filter_complex", ";".join(parts), "-map", "[a]",
           "-c:a", "aac", "-b:a", "192k", "-t", str(total), cache_path]
    return _finalize_generated_object(cache_path, cmd, [source], total)


def voice(text, *, speaker=1, speed=1.0, pitch=0.0, volume=1.0, **tts_kwargs):
    """svtts(VOICEVOX)で text を音声合成し、その wav を素材とする音声Objectを返す。

    duration は tts_duration による実長を自動設定するため、字幕・タイムラインと
    自然に同期する。svtts.py が無い/VOICEVOX 未起動なら親切なエラーを投げる。

    使用例:
        v = voice("こんにちは、世界", speaker=3)
        v.show(v.duration)
    """
    try:
        import svtts as _svtts
    except ImportError as e:
        raise ImportError(
            "voice() には svtts.py が必要です。"
            "scriptvedit.py と同じディレクトリに配置してください。") from e
    wav = _svtts.tts(text, speaker=speaker, speed=speed, pitch=pitch, **tts_kwargs)
    dur = _svtts.tts_duration(wav)
    obj = Object(wav)
    obj.duration = dur
    if volume != 1.0:
        _require_number("voice", "volume", volume, 0, None)
        obj.audio_effects.append(again(volume))
    return obj


class Narration:
    """narrate() の返値。(audio, subtitle) としてタプルアンパック可能な軽量ラッパー。

    audio:    音声Object（voice()相当。durationはTTS実長）
    subtitle: 字幕Object（subtitle=False指定時はNone）
    duration: 音声の実長（秒）のショートカットプロパティ
    """
    __slots__ = ("audio", "subtitle")

    def __init__(self, audio, subtitle):
        self.audio = audio
        self.subtitle = subtitle

    def __iter__(self):
        yield self.audio
        yield self.subtitle

    def __repr__(self):
        return f"Narration(audio={self.audio!r}, subtitle={self.subtitle!r})"

    @property
    def duration(self):
        return self.audio.duration


def narrate(text_content, *, speaker=1, speed=1.0, pitch=0.0, volume=1.0,
            subtitle=True, subtitle_style=None,
            x=0.5, y=0.9, size=36, color="white", font=None,
            box=True, box_color="black@0.6", box_border=10, alpha=1.0,
            anchor="center", **tts_kwargs):
    """TTSナレーション音声 + 同期字幕を1回の呼び出しで生成・配置する。

    voice()(svtts)でtext_contentを音声合成し、subtitle=Trueなら同じ内容の
    text()字幕Objectも生成する。字幕の表示窓は音声の実長(tts_duration)に
    一致させ、両者は同じ開始時刻からタイムラインに配置される。
    複数回呼べば、音声の実長ぶんタイムラインが進むため順次配置される
    （字幕は各回の音声窓にだけ表示される）。

    x/y/size/color/font/box/box_color/box_border/alpha/anchor は text() と同じ
    意味の字幕スタイル引数（既定はナレーション向けに下部中央+半透明ボックス）。
    subtitle_style を渡すと、これらの既定値を辞書キー（同名）で個別に上書きできる
    （例: subtitle_style={"size": 44, "y": 0.85}）。
    volume/pitch/**tts_kwargs は voice() と同じ意味で音声側にのみ作用する。

    戻り値: Narration(audio, subtitle) （タプルとして (a, t) = narrate(...) も可）。
    svtts.py が無い/VOICEVOX未起動時のエラーはvoice()同様に透過する。

    使用例:
        n = narrate("こんにちは、世界", speaker=3)
        # n.audio / n.subtitle、または audio, sub = narrate(...)
    """
    try:
        import svtts as _svtts
    except ImportError as e:
        raise ImportError(
            "narrate() には svtts.py が必要です。"
            "scriptvedit.py と同じディレクトリに配置してください。") from e
    wav = _svtts.tts(text_content, speaker=speaker, speed=speed, pitch=pitch,
                     **tts_kwargs)
    dur = _svtts.tts_duration(wav)

    text_obj = None
    if subtitle:
        st = dict(subtitle_style or {})
        text_obj = text(
            text_content,
            x=st.get("x", x), y=st.get("y", y), size=st.get("size", size),
            color=st.get("color", color), font=st.get("font", font),
            box=st.get("box", box), box_color=st.get("box_color", box_color),
            box_border=st.get("box_border", box_border),
            alpha=st.get("alpha", alpha), anchor=st.get("anchor", anchor))
        # current_timeを進めず音声と同じ開始点に配置（音声側で進行させる）
        text_obj.show(dur)

    # text_objより後にaudio_objをobjects列へ追加することで、
    # 「同じ開始時刻→音声側だけがタイムラインを進める」順序を保証する
    audio_obj = Object(wav)
    audio_obj.duration = dur
    if volume != 1.0:
        _require_number("narrate", "volume", volume, 0, None)
        audio_obj.audio_effects.append(again(volume))

    return Narration(audio_obj, text_obj)


def audio_viz(source, *, kind="waves", color="white", size=None, duration=None):
    """音声を showwaves/showspectrum/showcqt で可視化した映像Objectを生成（キャッシュ生成物）。
    kind: 'waves' | 'spectrum' | 'cqt'。"""
    _validate_audio_source("audio_viz", source)
    if kind not in ("waves", "spectrum", "cqt"):
        hint = _suggest_hint(str(kind), ("waves", "spectrum", "cqt"))
        raise ValueError(
            f"audio_viz: kind は 'waves'/'spectrum'/'cqt': {kind!r}{hint}")
    proj = Project._current
    fps = proj.fps if proj else 30
    dur = duration or _probe_audio_length(source) or 5.0
    if size is not None:
        if not isinstance(size, (tuple, list)) or len(size) != 2:
            raise ValueError(f"audio_viz: size は (w, h) タプル: {size!r}")
        w, h = int(size[0]), int(size[1])
    elif kind == "waves":
        w, h = (proj.width if proj else 1280), 240
    else:
        w, h = (proj.width if proj else 1280), (proj.height if proj else 720)

    if kind == "waves":
        viz = f"showwaves=s={w}x{h}:mode=cline:rate={fps}:colors={color}"
    elif kind == "spectrum":
        viz = f"showspectrum=s={w}x{h}:slide=scroll:fps={fps}"
    else:
        viz = f"showcqt=s={w}x{h}:fps={fps}"

    sigs = ["audio_viz", _source_signature(source),
            f"kind={kind}", f"color={color}", f"size={w}x{h}",
            f"fps={fps}", f"dur={dur}", f"ev={_ENGINE_VER}"]
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "aviz", f"{key}.mkv")

    cmd = ["ffmpeg", "-y", "-i", source,
           "-filter_complex", f"[0:a]{viz}[v]", "-map", "[v]",
           "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p",
           "-t", str(dur), cache_path]
    return _finalize_generated_object(cache_path, cmd, [source], dur)


def beat_sync(audio_source, *, min_bpm=60, max_bpm=200):
    """svbeat(numpy/scipyのみのビート検出)をDSLに統合し、拍時刻を返す。

    audio_source: 音声/動画ファイルパス（svbeatがffmpegでデコードする）
    min_bpm/max_bpm: svbeat.detect_beatsに渡すテンポ探索範囲

    戻り値: {"bpm": float, "beats": [秒,...], "onsets": [秒,...], "duration": float}
    （svbeat.detect_beats() と同じ形式。そのまま snap_times()/beats_to_keyframes()
    に渡せる）

    解析結果は audio_source のFFP + min_bpm/max_bpm をキーに
    __cache__/artifacts/beats/ へJSONキャッシュし、同じ入力の再解析を避ける。
    svbeat.py または numpy/scipy が無い場合は導入方法を含む日本語エラーにする。
    """
    if not isinstance(audio_source, str):
        raise TypeError(
            f"beat_sync: audio_source はパス文字列で指定してください: {audio_source!r}")
    if not os.path.exists(audio_source):
        raise FileNotFoundError(
            f"beat_sync: 音声/動画ファイルが見つかりません: {audio_source}")
    try:
        import svbeat as _svbeat
    except ImportError as e:
        raise ImportError(
            "beat_sync() には svbeat.py と numpy/scipy が必要です。\n"
            "scriptvedit.py と同じディレクトリに svbeat.py を配置し、"
            "`pip install numpy scipy` を実行してください。"
            f"(元エラー: {e})") from e

    sig = _source_signature(audio_source)
    key_str = (f"{sig}||min_bpm={min_bpm}||max_bpm={max_bpm}||ev={_ENGINE_VER}")
    key = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "beats", f"{key}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    try:
        result = _svbeat.detect_beats(
            audio_source, min_bpm=min_bpm, max_bpm=max_bpm)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"beat_sync: ビート検出に失敗しました: {e}") from e

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(tmp_path, cache_path)
    return result


# --- アンカー/同期 ---

def anchor(name):
    """現在のレイヤー位置にアンカーを登録"""
    proj = Project._current
    if proj is None:
        raise RuntimeError("anchor()にはアクティブなProjectが必要です")
    current_file = proj._current_layer_file or "(unknown)"
    if name in proj._anchor_defined_in:
        existing_file = proj._anchor_defined_in[name]
        if existing_file != current_file:
            raise RuntimeError(
                f"アンカー '{name}' は既に '{existing_file}' で定義されています "
                f"('{current_file}' で再定義は禁止)"
            )
    proj._anchor_defined_in[name] = current_file
    marker = _AnchorMarker(name)
    proj.objects.append(marker)


class _PauseFactory:
    """pause.time(N) / pause.until(name) でPauseを生成・登録するファクトリ"""
    def time(self, duration):
        p = Pause()
        p.duration = duration
        if Project._current is not None:
            Project._current.objects.append(p)
        return p

    def until(self, name, offset=0.0):
        p = Pause()
        p._until_anchor = name
        p._until_offset = offset
        if Project._current is not None:
            Project._current.objects.append(p)
        return p


pause = _PauseFactory()


def scene(name, duration):
    """シーンのコンテキストマネージャ（アクティブProjectに対して動作）。

    レイヤーファイル内で `with scene("intro", 5): ...` のように使う。
    p.scene() と同義だが Project._current を暗黙に使う（anchor/pause と同様）。
    """
    proj = Project._current
    if proj is None:
        raise RuntimeError("scene()にはアクティブなProjectが必要です")
    return Scene(proj, name, duration)


# --- トランジション/スライドショー（xfade） ---

# FFmpeg 8.0 の xfade transition 名（custom は式指定用のため除外）
_XFADE_TRANSITIONS = {
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite", "radial",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "vertopen", "vertclose",
    "horzopen", "horzclose", "dissolve", "pixelize",
    "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice",
    "hblur", "fadegrays", "wipetl", "wipetr", "wipebl", "wipebr",
    "squeezeh", "squeezev", "zoomin", "fadefast", "fadeslow",
    "hlwind", "hrwind", "vuwind", "vdwind",
    "coverleft", "coverright", "coverup", "coverdown",
    "revealleft", "revealright", "revealup", "revealdown",
}


def _validate_xfade_kind(func_name, kind):
    if kind not in _XFADE_TRANSITIONS:
        hint = _suggest_hint(str(kind), _XFADE_TRANSITIONS)
        raise ValueError(
            f"{func_name}: 未知のtransition '{kind}'。{hint}\n"
            f"有効な名前: {', '.join(sorted(_XFADE_TRANSITIONS))}")


def _source_signature(path):
    """素材パスの署名を返す（キャッシュ生成物はパス署名、通常素材はFFP署名）"""
    if _is_cache_artifact_path(path):
        # キャッシュ生成物はパス自体が内容由来の鍵を含む（dry_runでは未生成でFFP不可）
        return f"src={path.replace(chr(92), '/')}"
    try:
        return f"ffp={_file_fingerprint(path)}"
    except OSError:
        return f"src={path.replace(chr(92), '/')}"


def _xfade_scale_chain(w, h):
    """xfade入力の正規化フィルタ（共通サイズ・SAR・alpha付きフォーマット）"""
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"setsar=1,format=yuva444p")


def _finalize_generated_object(cache_path, cmd, origin_sources, total_dur):
    """xfade生成物のObject化共通処理（plan/dry_run/実生成の分岐、compute()と同機構）"""
    proj = Project._current
    # レイヤー依存として元素材を記録（キャッシュ鮮度検証から漏れるのを防ぐ）
    if proj is not None and proj._current_layer_file:
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).extend(origin_sources)
    if proj is not None and getattr(proj, '_mode', None) == "plan":
        pass  # plan pass: 生成スキップ
    elif os.path.exists(cache_path):
        pass  # キャッシュ命中
    elif proj is not None and getattr(proj, '_dry_run', False):
        proj._pending_compute_cmds[cache_path] = cmd
    else:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        _run_ffmpeg_to_cache(cmd, cache_path, timeout=600)
    obj = Object(cache_path)
    obj._origin_sources = list(origin_sources)
    obj._resolved_length = total_dur
    return obj


def slideshow(images, each=3.0, transition="fade", t_dur=0.5, size=None):
    """画像列をxfadeで連結した1本の合成Objectを生成（キャッシュ生成物）。

    images: 画像パスのリスト（2枚以上）
    each: 1枚あたりの表示秒数、t_dur: トランジション秒数（each未満）
    transition: xfadeのtransition名、size: (w, h)。省略時はProjectの解像度。
    合成尺は len(images) * each 秒。音声なし。
    """
    if not isinstance(images, (list, tuple)) or len(images) < 2:
        raise ValueError("slideshow: images には2枚以上の画像パスのリストを指定してください")
    for img in images:
        if not isinstance(img, str):
            raise ValueError(f"slideshow: images の要素はパス文字列のみ: {img!r}")
        if not os.path.exists(img):
            raise ValueError(f"slideshow: 画像が見つかりません: {img}")
        if _detect_media_type(img) != "image":
            raise ValueError(f"slideshow: 画像のみ指定できます: {img}")
    _validate_xfade_kind("slideshow", transition)
    _require_number("slideshow", "each", each, 0.1, None)
    _require_number("slideshow", "t_dur", t_dur, 0.01, None)
    if t_dur >= each:
        raise ValueError(
            f"slideshow: t_dur ({t_dur}) は each ({each}) より短くしてください")
    proj = Project._current
    if size is None:
        w = proj.width if proj else 1280
        h = proj.height if proj else 720
    else:
        if not isinstance(size, (tuple, list)) or len(size) != 2:
            raise ValueError(f"slideshow: size は (w, h) タプルで指定してください: {size!r}")
        w, h = int(size[0]), int(size[1])
    fps = proj.fps if proj else 30
    n = len(images)
    total = n * each

    # キャッシュ署名
    sigs = ["slideshow"]
    sigs.extend(_source_signature(img) for img in images)
    sigs.extend([f"each={each}", f"tr={transition}", f"tdur={t_dur}",
                 f"size={w}x{h}", f"fps={fps}", f"ev={_ENGINE_VER}"])
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "xfade", f"{key}.mkv")

    # コマンド構築: 各画像を each+t_dur 秒（最後は each 秒）でループ入力し xfade 連結
    cmd = ["ffmpeg", "-y"]
    for i, img in enumerate(images):
        d = each if i == n - 1 else each + t_dur
        cmd.extend(["-loop", "1", "-framerate", str(fps), "-t", str(d), "-i", img])
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]{_xfade_scale_chain(w, h)}[s{i}]")
    cur = "[s0]"
    for i in range(1, n):
        out = f"[x{i}]"
        offset = each * i
        parts.append(
            f"{cur}[s{i}]xfade=transition={transition}:duration={t_dur}:offset={offset}{out}")
        cur = out
    cmd.extend(["-filter_complex", ";".join(parts), "-map", cur,
                "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuva444p",
                "-t", str(total), cache_path])
    return _finalize_generated_object(cache_path, cmd, list(images), total)


def transition(obj_a, obj_b, kind="fade", duration=1.0):
    """2つのObjectをxfadeで1本に連結した合成Objectを生成。

    obj_a, obj_b は素のObject（Transform/Effect未適用）のみ。加工済み素材は
    先に compute() で素材化してから渡す。両Objectはこの合成に消費され、
    Projectのタイムラインからは除外される。画像は事前に .time(秒) が必要。
    合成尺は dur_a + dur_b - duration 秒。音声は含まれない。
    """
    for nm, o in (("obj_a", obj_a), ("obj_b", obj_b)):
        if not isinstance(o, Object):
            raise TypeError(f"transition: {nm} は Object のみ: {type(o)}")
        if o.transforms or o.effects or o.audio_effects:
            raise ValueError(
                f"transition: {nm} に Transform/Effect が適用されています。"
                f"先に compute() で素材化してから渡してください。")
        if o.media_type not in ("image", "video"):
            raise ValueError(f"transition: {nm} は画像/動画のみ対応: {o.media_type}")
    _validate_xfade_kind("transition", kind)
    _require_number("transition", "duration", duration, 0.01, None)
    proj = Project._current
    w = proj.width if proj else 1280
    h = proj.height if proj else 720
    fps = proj.fps if proj else 30

    def _clip_dur(o, nm):
        if o.duration is not None:
            return o.duration
        if o.media_type == "image":
            raise ValueError(
                f"transition: 画像 {nm} ('{o.source}') には事前に .time(秒) が必要です")
        rl = getattr(o, '_resolved_length', None)
        if rl:
            return rl
        return o.length()

    dur_a = _clip_dur(obj_a, "obj_a")
    dur_b = _clip_dur(obj_b, "obj_b")
    if duration >= dur_a or duration >= dur_b:
        raise ValueError(
            f"transition: duration ({duration}) は各素材の尺"
            f"（obj_a: {dur_a}, obj_b: {dur_b}）より短くしてください")
    total = dur_a + dur_b - duration

    # 両Objectはこの合成に消費される → Projectから除外
    origin_sources = []
    for o in (obj_a, obj_b):
        if proj is not None and o in proj.objects:
            proj.objects.remove(o)
        origin_sources.extend(getattr(o, '_origin_sources', None) or [o.source])

    # キャッシュ署名
    sigs = ["transition",
            _source_signature(obj_a.source), _source_signature(obj_b.source),
            f"da={dur_a}", f"db={dur_b}", f"kind={kind}", f"dur={duration}",
            f"size={w}x{h}", f"fps={fps}", f"ev={_ENGINE_VER}"]
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "xfade", f"{key}.mkv")

    # コマンド構築: 両素材を共通サイズ/fpsへ正規化し xfade で連結
    cmd = ["ffmpeg", "-y"]
    for o in (obj_a, obj_b):
        if o.media_type == "image":
            cmd.extend(["-loop", "1", "-framerate", str(fps), "-i", o.source])
        else:
            cmd.extend(_decoder_input_args(o.source, o.media_type, fps))
    parts = []
    for i, (o, d) in enumerate(((obj_a, dur_a), (obj_b, dur_b))):
        parts.append(
            f"[{i}:v]trim=duration={d},setpts=PTS-STARTPTS,"
            f"{_xfade_scale_chain(w, h)},fps={fps}[t{i}]")
    offset = dur_a - duration
    parts.append(
        f"[t0][t1]xfade=transition={kind}:duration={duration}:offset={offset}[tout]")
    cmd.extend(["-filter_complex", ";".join(parts), "-map", "[tout]",
                "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuva444p",
                "-t", str(total), cache_path])
    return _finalize_generated_object(cache_path, cmd, origin_sources, total)


def video_sequence(*objs, transition="fade", t_dur=0.5):
    """複数の動画クリップを xfade（+全クリップに音声があれば acrossfade）で
    連結した1本の合成Objectを生成する（slideshowの動画版・キャッシュ生成物）。

    objs: 動画Object または動画パス文字列（2つ以上）。素のObjectのみ
    （Transform/Effect適用済みは先に compute() で素材化する）。
    各クリップの実長は probe で取得し、t_dur が最短クリップ以上ならエラー。
    合成尺は sum(実長) - t_dur*(n-1) 秒。
    """
    if len(objs) < 2:
        raise ValueError("video_sequence: 2つ以上の動画を指定してください")
    _validate_xfade_kind("video_sequence", transition)
    _require_number("video_sequence", "t_dur", t_dur, 0.01, None)
    proj = Project._current
    sources = []
    for o in objs:
        if isinstance(o, Object):
            if o.media_type != "video":
                raise ValueError(
                    f"video_sequence: 動画Objectのみ連結できます: {o.source}")
            if o.transforms or o.effects or o.audio_effects:
                raise ValueError(
                    f"video_sequence: '{o.source}' に Transform/Effect が適用されています。"
                    f"先に compute() で素材化してから渡してください。")
            sources.append(o.source)
            if proj is not None and o in proj.objects:
                proj.objects.remove(o)  # 合成に消費（タイムラインから除外）
        elif isinstance(o, str):
            if not os.path.exists(o):
                raise FileNotFoundError(f"video_sequence: 動画が見つかりません: {o}")
            if _detect_media_type(o) != "video":
                raise ValueError(f"video_sequence: 動画のみ指定できます: {o}")
            sources.append(o)
        else:
            raise TypeError(
                f"video_sequence: 動画Objectかパス文字列のみ指定できます: {type(o)}")
    n = len(sources)
    lengths = [_probe_audio_length(s) or 5.0 for s in sources]
    # xfade は重なり区間 t_dur を要するため、最短クリップ未満を保証する
    for s, ln in zip(sources, lengths):
        if ln <= t_dur:
            raise ValueError(
                f"video_sequence: クリップ実長({ln:.3f}s)が t_dur({t_dur}s)以下です: {s}\n"
                f"t_dur を短くするか、より長いクリップを指定してください。")
    total = sum(lengths) - t_dur * (n - 1)

    # 音声: 全クリップが音声を持つ場合のみ acrossfade で連結（混在は映像のみ）
    def _has_audio(src):
        if proj is not None:
            info = proj._probe_media(src)
            if info is not None:
                return bool(info.get("has_audio"))
        return False
    all_audio = all(_has_audio(s) for s in sources)

    w = proj.width if proj else 1280
    h = proj.height if proj else 720
    fps = proj.fps if proj else 30

    sigs = ["video_sequence"]
    sigs.extend(_source_signature(s) for s in sources)
    sigs.extend([f"tr={transition}", f"tdur={t_dur}", f"size={w}x{h}",
                 f"fps={fps}", f"audio={all_audio}", f"ev={_ENGINE_VER}"])
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "xfade", f"{key}.mkv")

    # コマンド構築: 各クリップを共通サイズ/fpsへ正規化し xfade（+acrossfade）連結
    cmd = ["ffmpeg", "-y"]
    for s in sources:
        cmd.extend(_decoder_input_args(s, "video", fps))
    parts = []
    for i, (s, ln) in enumerate(zip(sources, lengths)):
        parts.append(
            f"[{i}:v]trim=duration={ln},setpts=PTS-STARTPTS,"
            f"{_xfade_scale_chain(w, h)},fps={fps}[t{i}]")
    cur = "[t0]"
    acc = lengths[0]
    for i in range(1, n):
        out = f"[x{i}]"
        offset = acc - t_dur
        parts.append(
            f"{cur}[t{i}]xfade=transition={transition}:duration={t_dur}:offset={offset}{out}")
        cur = out
        acc = offset + lengths[i]
    maps = ["-map", cur]
    if all_audio:
        for i, ln in enumerate(lengths):
            parts.append(f"[{i}:a]atrim=duration={ln},asetpts=PTS-STARTPTS[at{i}]")
        acur = "[at0]"
        for i in range(1, n):
            aout = f"[ax{i}]"
            parts.append(f"{acur}[at{i}]acrossfade=d={t_dur}{aout}")
            acur = aout
        maps.extend(["-map", acur])
    cmd.extend(["-filter_complex", ";".join(parts)])
    cmd.extend(maps)
    cmd.extend(["-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuva444p"])
    if all_audio:
        cmd.extend(["-c:a", "pcm_s16le"])
    cmd.extend(["-t", str(total), cache_path])
    obj = _finalize_generated_object(cache_path, cmd, list(sources), total)
    # dry_run では未生成キャッシュのprobeができないため音声有無を明示確定する
    obj._has_audio = all_audio
    return obj


# --- イージング関数 ---

_EASE_PI = 3.141592653589793
_EASE_C1 = 1.70158
_EASE_C3 = _EASE_C1 + 1
_EASE_C4 = (2 * _EASE_PI) / 3
_EASE_C5 = (2 * _EASE_PI) / 4.5

def _power_n(expr, n):
    """expr^n を繰り返し乗算で構築"""
    result = expr
    for _ in range(n - 1):
        result = result * expr
    return result

def _ease_in_power(t, n):
    return _power_n(_to_expr(t), n)

def _ease_out_power(t, n):
    t = _to_expr(t)
    return Const(1) - _power_n(Const(1) - t, n)

def _ease_in_out_power(t, n):
    t = _to_expr(t)
    coeff = 2 ** (n - 1)
    branch1 = Const(coeff) * _power_n(t, n)
    branch2 = Const(1) - _power_n(Const(-2) * t + Const(2), n) / Const(2)
    return if_(lt(t, 0.5), branch1, branch2)

def linear(t):
    """線形イージング"""
    return _to_expr(t)

# Quad (二次)
def ease_in_quad(t): return _ease_in_power(t, 2)
def ease_out_quad(t): return _ease_out_power(t, 2)
def ease_in_out_quad(t): return _ease_in_out_power(t, 2)

# Cubic (三次)
def ease_in_cubic(t): return _ease_in_power(t, 3)
def ease_out_cubic(t): return _ease_out_power(t, 3)
def ease_in_out_cubic(t): return _ease_in_out_power(t, 3)

# Quart (四次)
def ease_in_quart(t): return _ease_in_power(t, 4)
def ease_out_quart(t): return _ease_out_power(t, 4)
def ease_in_out_quart(t): return _ease_in_out_power(t, 4)

# Quint (五次)
def ease_in_quint(t): return _ease_in_power(t, 5)
def ease_out_quint(t): return _ease_out_power(t, 5)
def ease_in_out_quint(t): return _ease_in_out_power(t, 5)

# Sine (正弦)
def ease_in_sine(t):
    t = _to_expr(t)
    return Const(1) - cos(t * Const(_EASE_PI / 2))

def ease_out_sine(t):
    t = _to_expr(t)
    return sin(t * Const(_EASE_PI / 2))

def ease_in_out_sine(t):
    t = _to_expr(t)
    return (Const(1) - cos(t * Const(_EASE_PI))) / Const(2)

# Exponential (指数)
def ease_in_expo(t):
    t = _to_expr(t)
    return if_(lt(t, Const(0.001)), Const(0), pow(2, Const(10) * t - Const(10)))

def ease_out_expo(t):
    t = _to_expr(t)
    return if_(lt(Const(0.999), t), Const(1), Const(1) - pow(2, Const(-10) * t))

def ease_in_out_expo(t):
    t = _to_expr(t)
    branch1 = pow(2, Const(20) * t - Const(10)) / Const(2)
    branch2 = (Const(2) - pow(2, Const(-20) * t + Const(10))) / Const(2)
    inner = if_(lt(t, 0.5), branch1, branch2)
    return if_(lt(t, Const(0.001)), Const(0),
           if_(lt(Const(0.999), t), Const(1), inner))

# Circular (円)
def ease_in_circ(t):
    t = _to_expr(t)
    return Const(1) - sqrt(Const(1) - t * t)

def ease_out_circ(t):
    t = _to_expr(t)
    inv = t - Const(1)
    return sqrt(Const(1) - inv * inv)

def ease_in_out_circ(t):
    t = _to_expr(t)
    t2 = Const(2) * t
    branch1 = (Const(1) - sqrt(clip(Const(1) - t2 * t2, 0, 1))) / Const(2)
    t2m2 = Const(2) * t - Const(2)
    branch2 = (sqrt(clip(Const(1) - t2m2 * t2m2, 0, 1)) + Const(1)) / Const(2)
    return if_(lt(t, 0.5), branch1, branch2)

# Back (オーバーシュート)
def ease_in_back(t):
    t = _to_expr(t)
    return Const(_EASE_C3) * t * t * t - Const(_EASE_C1) * t * t

def ease_out_back(t):
    t = _to_expr(t)
    inv = t - Const(1)
    return Const(1) + Const(_EASE_C3) * inv * inv * inv + Const(_EASE_C1) * inv * inv

def ease_in_out_back(t):
    t = _to_expr(t)
    c2 = _EASE_C1 * 1.525
    t2 = Const(2) * t
    t2m2 = Const(2) * t - Const(2)
    branch1 = (t2 * t2 * (Const(c2 + 1) * t2 - Const(c2))) / Const(2)
    branch2 = (t2m2 * t2m2 * (Const(c2 + 1) * t2m2 + Const(c2)) + Const(2)) / Const(2)
    return if_(lt(t, 0.5), branch1, branch2)

# Elastic (弾性)
def ease_in_elastic(t):
    t = _to_expr(t)
    normal = -pow(2, Const(10) * t - Const(10)) * sin((Const(10) * t - Const(10.75)) * Const(_EASE_C4))
    return if_(lt(t, Const(0.001)), Const(0),
           if_(lt(Const(0.999), t), Const(1), normal))

def ease_out_elastic(t):
    t = _to_expr(t)
    normal = pow(2, Const(-10) * t) * sin((Const(10) * t - Const(0.75)) * Const(_EASE_C4)) + Const(1)
    return if_(lt(t, Const(0.001)), Const(0),
           if_(lt(Const(0.999), t), Const(1), normal))

def ease_in_out_elastic(t):
    t = _to_expr(t)
    branch1 = -pow(2, Const(20) * t - Const(10)) * sin((Const(20) * t - Const(11.125)) * Const(_EASE_C5)) / Const(2)
    branch2 = pow(2, Const(-20) * t + Const(10)) * sin((Const(20) * t - Const(11.125)) * Const(_EASE_C5)) / Const(-2) + Const(1)
    inner = if_(lt(t, 0.5), branch1, branch2)
    return if_(lt(t, Const(0.001)), Const(0),
           if_(lt(Const(0.999), t), Const(1), inner))

# Bounce (バウンス)
def ease_out_bounce(t):
    t = _to_expr(t)
    n1 = 7.5625
    d1 = 2.75
    s1 = Const(n1) * t * t
    t2 = t - Const(1.5 / d1)
    s2 = Const(n1) * t2 * t2 + Const(0.75)
    t3 = t - Const(2.25 / d1)
    s3 = Const(n1) * t3 * t3 + Const(0.9375)
    t4 = t - Const(2.625 / d1)
    s4 = Const(n1) * t4 * t4 + Const(0.984375)
    return if_(lt(t, Const(1 / d1)), s1,
           if_(lt(t, Const(2 / d1)), s2,
           if_(lt(t, Const(2.5 / d1)), s3, s4)))

def ease_in_bounce(t):
    t = _to_expr(t)
    return Const(1) - ease_out_bounce(Const(1) - t)

def ease_in_out_bounce(t):
    t = _to_expr(t)
    branch1 = (Const(1) - ease_out_bounce(Const(1) - Const(2) * t)) / Const(2)
    branch2 = (Const(1) + ease_out_bounce(Const(2) * t - Const(1))) / Const(2)
    return if_(lt(t, 0.5), branch1, branch2)

# Cubic Bezier (CSS互換)
def ease_cubic_bezier(x1, y1, x2, y2, segments=16):
    """CSS cubic-bezier互換イージング関数を生成

    使用例:
        ease = ease_cubic_bezier(0.25, 0.1, 0.25, 1.0)  # CSS ease
        obj.time(2) <= scale(lambda u: lerp(0.5, 1, ease(u)))
    """
    def _bx(s): return 3*x1*s*(1-s)**2 + 3*x2*s**2*(1-s) + s**3
    def _by(s): return 3*y1*s*(1-s)**2 + 3*y2*s**2*(1-s) + s**3
    def _dbx(s): return 3*x1 + (6*x2 - 12*x1)*s + (9*x1 - 9*x2 + 3)*s**2
    def _solve_s(t_val):
        if t_val <= 0: return 0.0
        if t_val >= 1: return 1.0
        s = t_val
        for _ in range(8):
            dx = _dbx(s)
            if _builtins.abs(dx) < 1e-12: break
            s -= (_bx(s) - t_val) / dx
            s = _builtins.max(0.0, _builtins.min(1.0, s))
        return s
    points = [(i / segments, _by(_solve_s(i / segments))) for i in range(segments + 1)]
    def _easing(u):
        u = _to_expr(u)
        result = Const(points[-1][1])
        for i in range(len(points) - 2, -1, -1):
            t0, v0 = points[i]
            t1, v1 = points[i + 1]
            seg_len = t1 - t0
            if seg_len <= 0: continue
            local_t = clip((u - Const(t0)) / Const(seg_len), 0, 1)
            seg_val = lerp(v0, v1, local_t)
            result = if_(lt(u, Const(t1)), seg_val, result)
        return result
    return _easing

# スプリング (バネ)
def ease_spring(stiffness=3, damping=4):
    """バネイージング: オーバーシュートしながら1.0に収束"""
    def _easing(t):
        t = _to_expr(t)
        decay = pow(Const(E), Const(-damping) * t)
        osc = cos(t * Const(stiffness) * Const(_EASE_PI))
        return Const(1) - decay * osc
    return _easing

# ステップ関数
def steps(n, jump="end"):
    """CSS steps()互換ステップ関数"""
    if n < 1:
        raise ValueError(f"steps: n は1以上が必要です（{n}）")
    if jump not in ("start", "end"):
        raise ValueError(f"steps: jump は 'start' または 'end': {jump}")
    def _easing(u):
        u = _to_expr(u)
        if jump == "end":
            return clip(floor(u * Const(n)) / Const(n), 0, 1)
        else:
            return clip(floor(u * Const(n) + Const(1)) / Const(n), 0, 1)
    return _easing

def apply_easing(easing_func, from_val, to_val):
    """イージング関数を値範囲に適用するlambdaを返す

    使用例:
        obj.time(2) <= scale(apply_easing(ease_in_quad, 0.5, 1.0))
    """
    def _inner(u):
        return lerp(from_val, to_val, easing_func(u))
    return _inner


# --- シーケンス・キーフレーム ---

def phase(start, end, fn):
    """エフェクトパラメータを時間区間[start, end]にリマッピング

    区間外ではtがclipされる（start前→t=0, end後→t=1）

    使用例:
        obj.time(6) <= fade(phase(0, 0.3, lambda t: t))  # 0-30%でフェードイン
    """
    if start >= end:
        raise ValueError(f"phase: start({start}) < end({end}) が必要です")
    if start < 0 or end > 1:
        raise ValueError(f"phase: start/end は [0, 1] の範囲が必要です")
    def _inner(u):
        u = _to_expr(u)
        t = clip((u - Const(start)) / Const(end - start), 0, 1)
        if callable(fn):
            return fn(t)
        return _to_expr(fn)
    return _inner

def sequence_param(*segments, default=0):
    """複数の時間区間でパラメータ値を切り替え

    使用例:
        obj.time(6) <= fade(sequence_param(
            (0, 0.2, lambda t: t),      # 0-20%: フェードイン
            (0.2, 0.8, 1.0),            # 20-80%: 保持
            (0.8, 1.0, lambda t: 1-t),  # 80-100%: フェードアウト
        ))
    """
    for i, (s, e, _) in enumerate(segments):
        if s >= e:
            raise ValueError(f"sequence_param: segment[{i}] の start({s}) < end({e}) が必要です")
    def _inner(u):
        u = _to_expr(u)
        result = _to_expr(default)
        for s, e, val in reversed(segments):
            t = clip((u - Const(s)) / Const(e - s), 0, 1)
            segment_val = val(t) if callable(val) else _to_expr(val)
            result = if_(lt(u, Const(e)), segment_val, result)
        return result
    return _inner

def repeat(n, fn):
    """パラメータ関数をn回繰り返す

    使用例:
        obj.time(6) <= scale(repeat(3, lambda t: 1 + 0.2 * sin(t * PI * 2)))
    """
    if n <= 0:
        raise ValueError(f"repeat: n は正の整数が必要です（{n}）")
    def _inner(u):
        u = _to_expr(u)
        local_t = clip(u * Const(n) - floor(u * Const(n)), 0, 1)
        if callable(fn):
            return fn(local_t)
        return _to_expr(fn)
    return _inner

def bounce(n, fn):
    """パラメータ関数をn回往復させる（0→1→0の三角波）

    使用例:
        obj.time(6) <= scale(bounce(2, lambda t: lerp(0.5, 1, t)))
    """
    if n <= 0:
        raise ValueError(f"bounce: n は正の整数が必要です（{n}）")
    def _inner(u):
        u = _to_expr(u)
        local = clip(u * Const(n) - floor(u * Const(n)), 0, 1)
        t = Const(1) - abs(Const(2) * local - Const(1))
        if callable(fn):
            return fn(t)
        return _to_expr(fn)
    return _inner

def alternate(n, fn_a, fn_b):
    """2つの関数をn回交互に切り替え

    使用例:
        obj.time(4) <= fade(alternate(4, lambda t: 1.0, lambda t: 0.5))
    """
    if n <= 0:
        raise ValueError(f"alternate: n は正の整数が必要です（{n}）")
    def _inner(u):
        u = _to_expr(u)
        seg = floor(u * Const(n))
        local_t = clip(u * Const(n) - seg, 0, 1)
        is_even = lt(mod(seg, Const(2)), Const(1))
        val_a = fn_a(local_t) if callable(fn_a) else _to_expr(fn_a)
        val_b = fn_b(local_t) if callable(fn_b) else _to_expr(fn_b)
        return if_(is_even, val_a, val_b)
    return _inner

def staircase(n, fn):
    """階段状に値を上昇させる

    使用例:
        obj.time(3) <= scale(staircase(3, lambda t: lerp(0.5, 1, t)))
    """
    if n <= 0:
        raise ValueError(f"staircase: n は正の整数が必要です（{n}）")
    def _inner(u):
        u = _to_expr(u)
        seg = floor(u * Const(n))
        base = seg / Const(n)
        local_t = clip(u * Const(n) - seg, 0, 1)
        if callable(fn):
            return base + fn(local_t) / Const(n)
        return base + _to_expr(fn) / Const(n)
    return _inner

def keyframes(*args, easing=None):
    """キーフレーム補間: 固定時点のパラメータ指定で自動線形補間

    使用例:
        obj.time(4) <= scale(keyframes(0, 0.5, 0.5, 1.2, 1.0, 1.0))
        obj.time(4) <= fade(keyframes((0, 0), (0.2, 1), (0.8, 1), (1.0, 0)))
        obj.time(4) <= scale(keyframes((0, 0.5), (1, 1.5), easing=ease_in_out_quad))
    """
    if len(args) == 0:
        raise ValueError("keyframes: 最低2つのキーフレームが必要です")
    if isinstance(args[0], tuple):
        points = [(float(t), float(v)) for t, v in args]
    else:
        if len(args) % 2 != 0:
            raise ValueError("keyframes: フラット形式では偶数個の引数が必要です（t0, v0, t1, v1, ...）")
        points = [(float(args[i]), float(args[i+1])) for i in range(0, len(args), 2)]
    if len(points) < 2:
        raise ValueError("keyframes: 最低2つのキーフレームが必要です")
    if len(points) > _MAX_PATH_POINTS:
        raise ValueError(
            f"keyframes: キーフレームは最大{_MAX_PATH_POINTS}点までです（指定={len(points)}）")
    points.sort(key=lambda p: p[0])
    def _inner(u):
        u = _to_expr(u)
        values = []
        bounds = []
        for i in range(len(points) - 1):
            t0, v0 = points[i]
            t1, v1 = points[i + 1]
            seg_len = t1 - t0
            if seg_len <= 0: continue
            local_t = clip((u - Const(t0)) / Const(seg_len), 0, 1)
            if easing is not None:
                local_t = easing(local_t)
            values.append(lerp(v0, v1, local_t))
            bounds.append(t1)
        values.append(Const(points[-1][1]))  # u>=最後の境界の既定値
        return _piecewise_tree(u, values, bounds)
    return _inner


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


# --- キャッシュ管理 CLI / watch モード ---

def _iter_cache_files(cache_dir=_CACHE_DIR):
    """__cache__ 配下の全ファイルを (絶対パス, カテゴリ, サイズ, mtime) で列挙する"""
    if not os.path.isdir(cache_dir):
        return
    root_abs = os.path.abspath(cache_dir)
    for dirpath, _dirs, files in os.walk(cache_dir):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            rel = os.path.relpath(path, root_abs)
            parts = rel.replace("\\", "/").split("/")
            # artifacts/<種別>/... は種別を、それ以外は先頭ディレクトリをカテゴリに
            if parts[0] == "artifacts" and len(parts) > 1:
                category = parts[1]
            elif len(parts) > 1:
                category = parts[0]
            else:
                category = "(直下)"
            yield path, category, st.st_size, st.st_mtime


def _fmt_size(n):
    """バイト数を人間可読な単位で整形"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024.0


def cache_stats(cache_dir=_CACHE_DIR):
    """種別ごとの件数・合計サイズを集計して表示する"""
    stats = {}
    total_n = 0
    total_sz = 0
    for _path, category, size, _mtime in _iter_cache_files(cache_dir):
        c = stats.setdefault(category, [0, 0])
        c[0] += 1
        c[1] += size
        total_n += 1
        total_sz += size
    print(f"=== キャッシュ統計: {os.path.abspath(cache_dir)} ===")
    if total_n == 0:
        print("  (キャッシュはありません)")
        return
    print(f"  {'種別':<16} {'件数':>8} {'サイズ':>12}")
    print("  " + "-" * 38)
    for category in sorted(stats):
        n, sz = stats[category]
        print(f"  {category:<16} {n:>8} {_fmt_size(sz):>12}")
    print("  " + "-" * 38)
    print(f"  {'合計':<16} {total_n:>8} {_fmt_size(total_sz):>12}")


def cache_gc(keep_days, cache_dir=_CACHE_DIR):
    """keep_days 日より古い（mtime基準）キャッシュファイルを削除する"""
    cutoff = _time.time() - float(keep_days) * 86400.0
    removed_n = 0
    removed_sz = 0
    for path, _category, size, mtime in list(_iter_cache_files(cache_dir)):
        if mtime < cutoff:
            try:
                os.remove(path)
                removed_n += 1
                removed_sz += size
            except OSError:
                pass
    # 空ディレクトリを掃除
    _prune_empty_dirs(cache_dir)
    print(f"GC完了: {keep_days}日より古い {removed_n}件 "
          f"({_fmt_size(removed_sz)}) を削除しました")
    return removed_n


def _prune_empty_dirs(root):
    """空ディレクトリを再帰的に削除する（bottom-up）"""
    if not os.path.isdir(root):
        return
    for dirpath, dirs, files in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def cache_clear(cache_dir=_CACHE_DIR):
    """__cache__ を丸ごと削除する"""
    if os.path.isdir(cache_dir):
        _shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"キャッシュ全削除: {os.path.abspath(cache_dir)}")
    else:
        print(f"キャッシュディレクトリはありません: {cache_dir}")


# watch が監視する拡張子（レイヤー.py + 画像/音声/フォント/字幕/HTML等の素材）
_WATCH_EXTENSIONS = {
    ".py", ".html", ".htm", ".css", ".js", ".srt", ".ass", ".vtt",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".mp4", ".mov", ".webm", ".mkv",
    ".ttf", ".otf", ".ttc",
    ".cube",
}
# 監視から除外するディレクトリ名（キャッシュ/生成物）
_WATCH_SKIP_DIRS = {"__cache__", "__pycache__", ".git", "output"}


def _watch_targets(script_path):
    """監視対象ファイル集合を返す（スクリプト自身 + サブディレクトリを含む
    .py レイヤーおよび画像/音声/フォント等の素材ファイル）。
    キャッシュ/生成物ディレクトリは除外する。"""
    script_path = os.path.abspath(script_path)
    targets = {script_path}
    d = os.path.dirname(script_path)
    try:
        for dirpath, dirs, files in os.walk(d):
            # キャッシュ/生成物ディレクトリを探索対象から除外（in-place で剪定）
            dirs[:] = [x for x in dirs if x not in _WATCH_SKIP_DIRS]
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in _WATCH_EXTENSIONS:
                    targets.add(os.path.join(dirpath, name))
    except OSError:
        pass
    return targets


def _snapshot_mtimes(paths):
    """パス集合の mtime スナップショット dict を返す"""
    snap = {}
    for p in paths:
        try:
            snap[p] = os.stat(p).st_mtime
        except OSError:
            snap[p] = None
    return snap


def watch(script_path, *, out=None, interval=0.5, max_cycles=None):
    """script_path と同ディレクトリの .py を監視し、変更時に再実行する。

    標準ライブラリのみ（os.stat ポーリング）。チェックポイント/レイヤー
    キャッシュが効くため差分再生成は高速。Ctrl-C で停止。
    max_cycles を指定するとその回数だけポーリングして戻る（テスト用）。
    """
    script_path = os.path.abspath(script_path)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"watch: スクリプトが見つかりません: {script_path}")

    def _run():
        cmd = [sys.executable, script_path]
        if out:
            cmd.append(out)
        print(f"[watch] 実行: {' '.join(cmd)}")
        t0 = _time.perf_counter()
        rc = subprocess.run(cmd, cwd=os.path.dirname(script_path)).returncode
        dt = _time.perf_counter() - t0
        status = "成功" if rc == 0 else f"失敗(rc={rc})"
        print(f"[watch] {status} ({dt:.2f}s) 変更を待機中... (Ctrl-Cで終了)")

    print(f"[watch] 監視開始: {script_path}")
    _run()  # 起動時に1回実行
    targets = _watch_targets(script_path)
    last = _snapshot_mtimes(targets)
    cycles = 0
    try:
        while True:
            _time.sleep(interval)
            cycles += 1
            targets = _watch_targets(script_path)  # 新規ファイル追加も検知
            cur = _snapshot_mtimes(targets)
            changed = [p for p in cur if cur[p] != last.get(p)]
            if changed:
                names = ", ".join(os.path.basename(p) for p in changed)
                print(f"[watch] 変更検知: {names}")
                _run()
                last = cur
            if max_cycles is not None and cycles >= max_cycles:
                print("[watch] max_cycles 到達。監視を終了します。")
                return
    except KeyboardInterrupt:
        print("\n[watch] 監視を終了しました。")


def _main(argv=None):
    """CLI エントリポイント: cache 管理 / watch モード"""
    import argparse
    parser = argparse.ArgumentParser(
        prog="scriptvedit",
        description="scriptvedit: キャッシュ管理と watch モード")
    sub = parser.add_subparsers(dest="command")

    p_cache = sub.add_parser("cache", help="__cache__ の統計・GC・全削除")
    p_cache.add_argument("--stats", action="store_true", help="種別ごとの件数・サイズを表示")
    p_cache.add_argument("--gc", action="store_true", help="古い生成物を削除")
    p_cache.add_argument("--keep-days", type=float, default=7.0,
                         help="--gc で残す日数（既定: 7）")
    p_cache.add_argument("--clear", action="store_true", help="キャッシュを全削除")
    p_cache.add_argument("--dir", default=_CACHE_DIR, help="キャッシュディレクトリ")

    p_watch = sub.add_parser("watch", help="スクリプト変更を監視して再実行")
    p_watch.add_argument("script", help="監視する Python スクリプト")
    p_watch.add_argument("--out", help="出力パス（スクリプトへ引数として渡す）")
    p_watch.add_argument("--interval", type=float, default=0.5, help="ポーリング間隔（秒）")
    p_watch.add_argument("--max-cycles", type=int, default=None,
                         help="指定回数だけポーリングして終了（テスト用）")

    args = parser.parse_args(argv)

    if args.command == "cache":
        if args.clear:
            cache_clear(args.dir)
        elif args.gc:
            cache_gc(args.keep_days, args.dir)
        elif args.stats:
            cache_stats(args.dir)
        else:
            cache_stats(args.dir)  # 既定は統計表示
        return 0
    if args.command == "watch":
        watch(args.script, out=args.out, interval=args.interval,
              max_cycles=args.max_cycles)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_main())
