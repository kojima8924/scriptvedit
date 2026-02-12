import subprocess
import os
import json
import hashlib
import math as _math
import warnings
import builtins as _builtins

__all__ = [
    # コアクラス
    "Project", "Object", "Transform", "TransformChain", "Effect", "EffectChain",
    "AudioEffect", "AudioEffectChain",
    "VideoView", "AudioView",
    # ファクトリ関数
    "resize", "rotate", "scale", "fade", "move", "morph_to", "rotate_to",
    "again", "afade", "adelete", "delete", "trim", "atrim", "atempo",
    # アンカー/同期
    "anchor", "pause",
    # Expr
    "Expr", "Const", "Var",
    # 数学関数
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "floor", "ceil", "trunc",
    "log10", "cbrt", "lerp", "clip", "clamp",
    "step", "smoothstep", "mod", "frac", "deg2rad", "rad2deg",
    # Python組み込み互換
    "abs", "min", "max", "round", "pow",
    # 定数
    "PI", "E",
    # DSL糖衣
    "P",
    # テンプレートラッパー
    "subtitle", "bubble", "diagram",
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
        return _BinOp("+", self, _to_expr(other))

    def __radd__(self, other):
        return _BinOp("+", _to_expr(other), self)

    def __sub__(self, other):
        return _BinOp("-", self, _to_expr(other))

    def __rsub__(self, other):
        return _BinOp("-", _to_expr(other), self)

    def __mul__(self, other):
        return _BinOp("*", self, _to_expr(other))

    def __rmul__(self, other):
        return _BinOp("*", _to_expr(other), self)

    def __truediv__(self, other):
        return _BinOp("/", self, _to_expr(other))

    def __rtruediv__(self, other):
        return _BinOp("/", _to_expr(other), self)

    def __pow__(self, other):
        return _FuncCall("pow", [self, _to_expr(other)])

    def __rpow__(self, other):
        return _FuncCall("pow", [_to_expr(other), self])

    def __neg__(self):
        return _UnOp("-", self)

    def __abs__(self):
        return _FuncCall("abs", [self])


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
    return _FuncCall("sin", [_to_expr(x)])

def cos(x):
    return _FuncCall("cos", [_to_expr(x)])

def tan(x):
    return _FuncCall("tan", [_to_expr(x)])

def asin(x):
    return _FuncCall("asin", [_to_expr(x)])

def acos(x):
    return _FuncCall("acos", [_to_expr(x)])

def atan(x):
    return _FuncCall("atan", [_to_expr(x)])

def atan2(y, x):
    return _FuncCall("atan2", [_to_expr(y), _to_expr(x)])

def sinh(x):
    return _FuncCall("sinh", [_to_expr(x)])

def cosh(x):
    return _FuncCall("cosh", [_to_expr(x)])

def tanh(x):
    return _FuncCall("tanh", [_to_expr(x)])

def exp(x):
    return _FuncCall("exp", [_to_expr(x)])

def log(x):
    return _FuncCall("log", [_to_expr(x)])

def sqrt(x):
    return _FuncCall("sqrt", [_to_expr(x)])

def floor(x):
    return _FuncCall("floor", [_to_expr(x)])

def ceil(x):
    return _FuncCall("ceil", [_to_expr(x)])

def trunc(x):
    return _FuncCall("trunc", [_to_expr(x)])

_LN10 = 2.302585092994046  # math.log(10)

def log10(x):
    return _FuncCall("log", [_to_expr(x)]) / Const(_LN10)

def cbrt(x):
    return _FuncCall("pow", [_to_expr(x), Const(1/3)])

def lerp(a, b, t):
    a, b, t = _to_expr(a), _to_expr(b), _to_expr(t)
    return a + (b - a) * t

def clip(x, lo, hi):
    return _FuncCall("clip", [_to_expr(x), _to_expr(lo), _to_expr(hi)])

clamp = clip

def step(edge, x):
    return _FuncCall("gte", [_to_expr(x), _to_expr(edge)])

def smoothstep(edge0, edge1, x):
    e0, e1, xv = _to_expr(edge0), _to_expr(edge1), _to_expr(x)
    t = clip((xv - e0) / (e1 - e0), 0, 1)
    return t * t * (Const(3) - Const(2) * t)

def mod(a, b):
    return _FuncCall("mod", [_to_expr(a), _to_expr(b)])

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
        return _FuncCall("abs", [x])
    return _builtins.abs(x)

def min(*args):
    if any(isinstance(a, Expr) for a in args):
        return _FuncCall("min", [_to_expr(a) for a in args])
    return _builtins.min(*args)

def max(*args):
    if any(isinstance(a, Expr) for a in args):
        return _FuncCall("max", [_to_expr(a) for a in args])
    return _builtins.max(*args)

def round(x):
    if isinstance(x, Expr):
        return _FuncCall("round", [x])
    return _builtins.round(x)

def pow(x, y):
    if isinstance(x, Expr) or isinstance(y, Expr):
        return _FuncCall("pow", [_to_expr(x), _to_expr(y)])
    return _builtins.pow(x, y)

# 定数
PI = 3.141592653589793
E = 2.718281828459045


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


# --- configure許可キー ---

_CONFIGURE_KEYS = {"width", "height", "fps", "duration", "background_color"}

_CACHE_DIR = "__cache__"
_CHECKPOINT_DIR = os.path.join(_CACHE_DIR, "checkpoints")
_ARTIFACT_DIR = os.path.join(_CACHE_DIR, "artifacts")
_ENGINE_VER = "3"
_BAKEABLE_EFFECTS = {"scale", "fade", "trim", "morph_to", "rotate_to"}


def _file_fingerprint(path):
    """ファイルの(絶対パス, サイズ, mtime_ns)タプルを返す"""
    abs_path = os.path.abspath(path).replace("\\", "/")
    stat = os.stat(path)
    return (abs_path, stat.st_size, stat.st_mtime_ns)


def _op_fingerprint_str(op):
    """単一opのフィンガープリント文字列を生成"""
    parts = [op.name]
    for k in sorted(op.params):
        v = op.params[k]
        parts.append(f"{k}={v.to_ffmpeg('u') if isinstance(v, Expr) else repr(v)}")
    policy = getattr(op, 'policy', 'auto')
    quality = getattr(op, 'quality', 'final')
    parts.append(f"p={policy}")
    parts.append(f"q={quality}")
    # morph_to: ターゲット画像のFFPをsignatureに含める
    if op.name == "morph_to" and hasattr(op, '_morph_target'):
        try:
            tgt_ffp = _file_fingerprint(op._morph_target.source)
            parts.append(f"tgt_ffp={tgt_ffp}")
        except OSError:
            parts.append(f"tgt_src={op._morph_target.source}")
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
        if policy == "auto" and _is_bakeable(typ, op) and policy != "off":
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
    sigs.append(f"ev={_ENGINE_VER}")
    if duration is not None:
        sigs.append(f"dur={duration}")
    if fps is not None:
        sigs.append(f"fps={fps}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    # video入力 + transform-only でも動画ならwebm
    is_video = _detect_media_type(original_source) in ("video",)
    ext = ".webm" if (duration is not None or is_video) else ".png"
    src_hash = hashlib.sha256(original_source.replace("\\", "/").encode()).hexdigest()[:8]
    cache_dir = os.path.join(_ARTIFACT_DIR, "checkpoint", src_hash)
    return os.path.join(cache_dir, f"{key}{ext}")


def _morph_cache_path(src_path, morph_op, duration, fps, quality="final"):
    """morph WebMのキャッシュパスを計算"""
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
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    src_hash = hashlib.sha256(src_path.replace("\\", "/").encode()).hexdigest()[:8]
    cache_dir = os.path.join(_ARTIFACT_DIR, "morph", src_hash)
    return os.path.join(cache_dir, f"{key}.webm")


def _validate_morph_position(bakeable_ops):
    """morph_toがbakeable opsの末尾であることを検証"""
    morph_idx = None
    for i, (typ, op) in enumerate(bakeable_ops):
        if typ == "effect" and op.name == "morph_to":
            morph_idx = i
    if morph_idx is None:
        return
    # morph_to の後に他のbakeable opがあればエラー
    for i in range(morph_idx + 1, len(bakeable_ops)):
        after_op = bakeable_ops[i][1]
        raise ValueError(
            f"morph_to はbakeable opsの末尾に配置してください。"
            f"morph_to(idx={morph_idx})の後に "
            f"{after_op.name}(idx={i})があります。\n"
            f"回避策: {after_op.name} を morph_to の前に移動するか、"
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
        return (os.path.join(layer_dir, f"{key}.webm"),
                os.path.join(layer_dir, f"{key}.anchors.json"))
    # フォールバック（後方互換）
    return (os.path.join(_CACHE_DIR, f"{basename}.webm"),
            os.path.join(_CACHE_DIR, f"{basename}.anchors.json"))


class Project:
    _current = None

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
        Project._current = self

    def configure(self, **kwargs):
        unknown = set(kwargs.keys()) - _CONFIGURE_KEYS
        if unknown:
            raise ValueError(
                f"不明な設定キー: {', '.join(sorted(unknown))}。"
                f"使用可能: {', '.join(sorted(_CONFIGURE_KEYS))}"
            )
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "duration" in kwargs:
            self._configured_duration = kwargs["duration"]

    def _reset_runtime_state(self):
        """render()用の実行時状態をリセット"""
        self.duration = self._configured_duration
        self.objects = []
        self._layers = []
        self._anchors = {}
        self._anchor_defined_in = {}

    def _probe_media(self, path):
        """ffprobeでメディア情報を取得（キャッシュあり）"""
        if path in self._probe_cache:
            return self._probe_cache[path]
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                capture_output=True, text=True, timeout=10
            )
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            duration_str = data.get("format", {}).get("duration")
            duration = float(duration_str) if duration_str else None
            info = {"has_audio": has_audio, "duration": duration}
            self._probe_cache[path] = info
            return info
        except FileNotFoundError:
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
        Project._current = self
        with open(filename, encoding="utf-8") as f:
            code = f.read()
        namespace = {}
        exec(compile(code, filename, "exec"), namespace)
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, priority))
        for obj in self.objects[start_idx:end_idx]:
            obj.priority = priority
        self._fill_auto_durations(start_idx, end_idx)
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
        """各レイヤーの最大durationを返す"""
        max_dur = 0
        for start_idx, end_idx, _ in self._layers:
            layer_dur = 0
            for item in self.objects[start_idx:end_idx]:
                if isinstance(item, _AnchorMarker):
                    continue
                if item.duration is not None:
                    layer_dur += item.duration
            max_dur = max(max_dur, layer_dur)
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
                    item.start_time = current_time
                    # until解決
                    until_name = getattr(item, '_until_anchor', None)
                    if until_name:
                        anchor_time = self._anchors.get(until_name)
                        if anchor_time is not None:
                            new_dur = max(0, anchor_time - current_time)
                            if item.duration != new_dur:
                                item.duration = new_dur
                                changed = True
                    if item.duration is not None:
                        current_time += item.duration
            if not changed:
                break
        if check_unresolved:
            for item in self.objects:
                until_name = getattr(item, '_until_anchor', None)
                if until_name and until_name not in self._anchors:
                    raise RuntimeError(f"未定義のアンカー: '{until_name}'")

    def render(self, output_path, *, dry_run=False):
        self._reset_runtime_state()
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
            cache_cmds = self._collect_cache_cmds()
            web_cmds = self._collect_web_cmds()
            # web Objectのsourceを予定webmパスに仮差し替え（checkpoint収集より前）
            for obj in self.objects:
                if isinstance(obj, Object) and obj.media_type == "web":
                    obj.source = _web_cache_path(obj, self)
                    obj.media_type = "video"
            checkpoint_cmds = self._collect_checkpoint_cmds()
            cmd = self._build_ffmpeg_cmd(output_path)
            all_extra = {}
            if cache_cmds:
                all_extra.update(cache_cmds)
            if web_cmds:
                all_extra.update(web_cmds)
            if checkpoint_cmds:
                all_extra.update(checkpoint_cmds)
            if all_extra:
                return {"main": cmd, "cache": all_extra}
            return cmd  # 後方互換: cache不要ならlistのまま

        self._ensure_web_objects()
        self._ensure_checkpoints()
        cmd = self._build_ffmpeg_cmd(output_path)
        print(f"実行コマンド:")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        print()
        subprocess.run(cmd, check=True, timeout=1800)
        self._generate_pending_caches()
        print(f"\n完了: {output_path}")

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
                if isinstance(item, Pause):
                    details.append(f"  pause.until('{name}')")
                elif isinstance(item, Object):
                    details.append(f"  Object('{item.source}').until('{name}')")
                else:
                    details.append(f"  {type(item).__name__}.until('{name}')")
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

    def _should_use_cache(self, spec):
        """キャッシュ利用判定"""
        cache = spec["cache"]
        if cache == "use":
            return True
        if cache == "auto":
            webm_path, _ = _layer_cache_paths(spec["filename"], self)
            return os.path.exists(webm_path)
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
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                cache_meta = json.load(f)
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
            if item.duration is not None:
                current_time += item.duration
        return objects, anchors

    def _collect_cache_cmds(self):
        """dry_run用のキャッシュ生成コマンド辞書構築"""
        cache_cmds = {}
        for i, spec in enumerate(self._layer_specs):
            if spec["cache"] in ("make", "auto") and not self._should_use_cache(spec):
                if spec["cache"] == "make" or spec["cache"] == "auto":
                    if spec["cache"] == "make":
                        cmd = self._build_layer_cache_cmd(i)
                        webm_path, _ = _layer_cache_paths(spec["filename"], self)
                        cache_cmds[webm_path] = cmd
        return cache_cmds

    def _build_checkpoint_image_cmd(self, source, transforms, cache_path, quality="final"):
        """画像チェックポイント: Transform適用→透過PNG"""
        filters = []
        for t in transforms:
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
        cmd = ["ffmpeg", "-y", "-i", source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", cache_path])
        return cmd

    def _build_checkpoint_video_cmd(self, source, media_type, transforms, effects,
                                     cache_path, dur, fps, quality="final"):
        """動画チェックポイント: Transform+Effect適用→透明VP9"""
        cmd = ["ffmpeg", "-y"]
        if media_type == "image":
            cmd.extend(["-loop", "1", "-r", str(fps), "-i", source])
        else:
            cmd.extend(["-i", source])

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

        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        crf = "40" if quality == "fast" else "30"
        cmd.extend([
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", crf, "-auto-alt-ref", "0",
            "-t", str(dur), cache_path,
        ])
        return cmd

    def _build_morph_webm_cmd(self, frame_pattern, cache_path, duration, fps, quality="final"):
        """PNG連番 → alpha webm のffmpegコマンドを構築"""
        crf = "40" if quality == "fast" else "30"
        return ["ffmpeg", "-y", "-framerate", str(fps),
                "-i", frame_pattern,
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", crf, "-auto-alt-ref", "0",
                "-t", str(duration), cache_path]

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
        dur = obj.duration
        # video + duration未指定 → obj.length() で補完
        if dur is None and _detect_media_type(original_source) in ("video",):
            dur = obj.length()
        fps = self.fps

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
                            subprocess.run(cmd, check=True, timeout=600)
                    current_source = morph_path
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
                        subprocess.run(cmd, check=True, timeout=600)
                    current_source = cache_path
                    current_media_type = _detect_media_type(cache_path)

                executed = executed + remaining_ops[:pos + 1]
                remaining_ops = remaining_ops[pos + 1:]
                pos = 0
                continue
            pos += 1

        # Objectを更新: source差し替え、残余bakeable ops + live opsを再設定
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

        has_effects = any(t == "effect" for t, _ in ops)
        is_video = _detect_media_type(original_source) in ("video",)
        for idx in candidates:
            segment_ops = ops[:idx + 1]
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
            dur = obj.duration
            # video + duration未指定 → obj.length() で補完
            if dur is None and _detect_media_type(original_source) in ("video",):
                dur = obj.length()
            fps = self.fps
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
                    morph_path = _morph_cache_path(current_source, sp_op, dur, fps, quality)
                    frame_pattern = os.path.join("__morph_frames__", "frame_%05d.png")
                    cmd = self._build_morph_webm_cmd(
                        frame_pattern, morph_path, dur, fps, quality)
                    cmds[morph_path] = cmd
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
            else:
                last_seg = bakeable_ops[:last_sp + 1]
                last_has_eff = any(t == "effect" for t, _ in last_seg)
                last_is_video = _detect_media_type(original_source) in ("video",)
                last_path = _checkpoint_cache_path(
                    original_source, last_seg,
                    dur if (last_has_eff or last_is_video) else None,
                    fps if (last_has_eff or last_is_video) else None,
                    getattr(last_op, 'quality', 'final'))
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
                obj._render_web_frames(self)
                cmd = obj._build_web_cmd(self, webm_path)
                os.makedirs(os.path.dirname(webm_path), exist_ok=True)
                print(f"  ffmpeg {' '.join(cmd[1:])}")
                subprocess.run(cmd, check=True, timeout=600)
                print(f"  完了: {webm_path}")
                # フレーム削除
                if not obj._web_debug_frames and os.path.exists(frames_dir):
                    import shutil
                    shutil.rmtree(frames_dir)

            obj.source = webm_path
            obj.media_type = "video"

    def _generate_pending_caches(self):
        """実際のキャッシュ生成実行"""
        for i, spec in enumerate(self._layer_specs):
            if spec["cache"] == "make":
                self._render_layer_to_cache(i)

    def _build_layer_cache_cmd(self, spec_index):
        """レイヤーキャッシュ用ffmpegコマンド（透明webm VP9 alpha）"""
        spec = self._layer_specs[spec_index]
        webm_path, _ = _layer_cache_paths(spec["filename"], self)
        objects, anchors = self._get_layer_data(spec_index)
        renderable = [o for o in objects if isinstance(o, Object)]

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

            if obj.media_type == "image":
                inputs.extend(["-loop", "1", "-r", str(self.fps), "-i", obj.source])
            else:
                inputs.extend(["-i", obj.source])

            obj_dur = obj.duration or dur
            start = obj.start_time

            base_dims = _get_base_dimensions(obj)
            obj_filters = _build_transform_filters(obj)
            eff_filters, pad_size = _build_effect_filters(obj, start, obj_dur, base_dims=base_dims)
            obj_filters.extend(eff_filters)

            obj_label = f"[obj{input_idx}]"
            if obj_filters:
                filter_parts.append(
                    f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}"
                )
            else:
                obj_label = f"[{input_idx}:v]"

            x_expr, y_expr = _build_move_exprs(obj, start, obj_dur, pad_size=pad_size)

            enable_str = ""
            if obj.duration is not None:
                end = start + obj.duration
                enable_str = f":enable='between(t\\,{start}\\,{end})'"

            out_label = f"[v{input_idx}]"
            filter_parts.append(
                f"{current_base}{obj_label}overlay={x_expr}:{y_expr}{enable_str}{out_label}"
            )
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

        cmd = self._build_layer_cache_cmd(spec_index)
        print(f"キャッシュ生成: {webm_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        subprocess.run(cmd, check=True, timeout=600)
        print(f"  完了: {webm_path}")

        # anchors.json書き出し
        objects, anchors = self._get_layer_data(spec_index)
        dur = self.duration or self._calc_total_duration()
        cache_meta = {"duration": dur, "anchors": anchors}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cache_meta, f, indent=2, ensure_ascii=False)
        print(f"  アンカー保存: {json_path}")

    def _build_ffmpeg_cmd(self, output_path):
        inputs = []
        filter_parts = []

        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c={self.background_color}:s={self.width}x{self.height}:d={self.duration}:r={self.fps}",
        ])

        renderable = [o for o in self.objects if isinstance(o, Object)]
        sorted_objects = sorted(renderable, key=lambda o: o.priority)

        # 入力を追加（映像+音声共通）
        input_map = {}  # obj id → input_idx
        for i, obj in enumerate(sorted_objects):
            input_idx = i + 1
            input_map[id(obj)] = input_idx
            if obj.media_type == "image":
                inputs.extend(["-loop", "1", "-r", str(self.fps), "-i", obj.source])
            elif obj.media_type == "audio":
                inputs.extend(["-i", obj.source])
            else:  # video
                # WebM(VP9 alpha)はlibvpx-vp9デコーダが必要
                # (ffmpeg 8.0のネイティブVP9デコーダはalpha非対応)
                if obj.source.lower().endswith(".webm"):
                    inputs.extend(["-c:v", "libvpx-vp9", "-i", obj.source])
                else:
                    inputs.extend(["-i", obj.source])

        # --- 映像チェーン ---
        current_base = "[0:v]"
        video_objects = [o for o in sorted_objects if o.has_video]

        for obj in video_objects:
            input_idx = input_map[id(obj)]
            dur = obj.duration or 5
            start = obj.start_time

            base_dims = _get_base_dimensions(obj)
            pre_filters = _build_video_pre_filters(obj)
            obj_filters = pre_filters + _build_transform_filters(obj)
            eff_filters, pad_size = _build_effect_filters(obj, start, dur, base_dims=base_dims)
            obj_filters.extend(eff_filters)

            obj_label = f"[obj{input_idx}]"
            if obj_filters:
                filter_parts.append(
                    f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}"
                )
            else:
                obj_label = f"[{input_idx}:v]"

            x_expr, y_expr = _build_move_exprs(obj, start, dur, pad_size=pad_size)

            enable_str = ""
            if obj.duration is not None:
                end = start + obj.duration
                enable_str = f":enable='between(t\\,{start}\\,{end})'"

            out_label = f"[v{input_idx}]"
            filter_parts.append(
                f"{current_base}{obj_label}overlay={x_expr}:{y_expr}{enable_str}{out_label}"
            )
            current_base = out_label

        # --- 音声チェーン ---
        audio_objects = [o for o in sorted_objects if o.has_audio]
        audio_out = None

        if audio_objects:
            audio_labels = []
            for ai, obj in enumerate(audio_objects):
                input_idx = input_map[id(obj)]
                dur = obj.duration or 5
                start = obj.start_time

                a_filters = []
                # atrim/atempo前処理
                a_pre = _build_audio_pre_filters(obj)
                # auto atrim: obj.durationがあり、明示atrimがなければ自動トリム
                has_explicit_atrim = any(
                    e.name == "atrim" for e in obj.audio_effects)
                if not has_explicit_atrim and obj.duration is not None:
                    a_pre = [f"atrim=duration={obj.duration}",
                             "asetpts=PTS-STARTPTS"] + a_pre
                a_filters.extend(a_pre)
                # 音声エフェクト（again/afade）
                a_filters.extend(_build_audio_effect_filters(obj, dur))
                # adelay（タイミングシフト）
                delay_ms = int(start * 1000)
                if delay_ms > 0:
                    a_filters.append(f"adelay={delay_ms}|{delay_ms}")

                a_label = f"[a{ai}]"
                if a_filters:
                    filter_parts.append(
                        f"[{input_idx}:a]{','.join(a_filters)}{a_label}"
                    )
                else:
                    a_label = f"[{input_idx}:a]"
                audio_labels.append(a_label)

            if len(audio_labels) == 1:
                audio_out = audio_labels[0]
            else:
                amix_in = "".join(audio_labels)
                audio_out = "[aout]"
                filter_parts.append(
                    f"{amix_in}amix=inputs={len(audio_labels)}:normalize=0{audio_out}"
                )

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", current_base])
            if audio_out:
                cmd.extend(["-map", audio_out])

        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
        if audio_out:
            cmd.extend(["-c:a", "aac"])
        else:
            cmd.extend(["-an"])
        cmd.extend(["-t", str(self.duration), output_path])

        return cmd


# --- メディア情報ヘルパー ---

def _get_media_dimensions(filepath):
    """メディアの幅・高さを取得 (ffprobe)"""
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
    """オブジェクトのscaleエフェクト適用前の基底サイズを取得"""
    src_w, src_h = _get_media_dimensions(obj.source)
    if src_w is None:
        return None, None
    for t in obj.transforms:
        if t.name == "resize":
            sx = t.params.get("sx", 1)
            sy = t.params.get("sy", 1)
            src_w = int(src_w * sx)
            src_h = int(src_h * sy)
    return src_w, src_h


# --- フィルタ生成ヘルパー ---

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
    return filters


def _build_effect_filters(obj, start, dur, base_dims=None):
    """scale/fade等のeffectフィルタリストを生成（move/trim/delete以外）
    base_dims指定時、scaleエフェクトにpadを追加して固定サイズ出力にする。
    Returns: (filters, pad_size) — pad_size は (max_w, max_h) or None
    """
    filters = []
    pad_size = None
    for e in obj.effects:
        if e.name in ("move", "trim", "delete", "morph_to"):
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
                max_s = _builtins.max(scale_expr.eval_at(i / 10) for i in range(11))
                max_w = _math.ceil(bw * max_s / 2) * 2
                max_h = _math.ceil(bh * max_s / 2) * 2
                filters.append("format=rgba")
                filters.append(
                    f"pad={max_w}:{max_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000:eval=frame"
                )
                pad_size = (max_w, max_h)
        elif e.name == "fade":
            alpha_expr = e.params.get("alpha", Const(1.0))
            u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
            ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
            filters.append("format=rgba")
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
        return f"(W-{pad_size[0]})/2" if pad_size else "(W-w)/2", \
               f"(H-{pad_size[1]})/2" if pad_size else "(H-h)/2"

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

    return x_result, y_result


def _build_video_pre_filters(obj):
    """trim等の前処理フィルタ"""
    filters = []
    for e in obj.effects:
        if e.name == "trim":
            d = e.params.get("duration")
            if d is not None:
                filters.append(f"trim=duration={d}")
                filters.append("setpts=PTS-STARTPTS")
    return filters


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
            filters.append(f"atempo={rate}")
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

    def time(self, duration):
        self.duration = duration
        return self

    def until(self, name):
        self._until_anchor = name
        return self


_WEB_KWARGS = {"duration", "size", "fps", "data", "name", "debug_frames", "deps"}


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
                raise TypeError(
                    f"不明なキーワード引数: {', '.join(sorted(unknown))}。"
                    f"使用可能: {', '.join(sorted(_WEB_KWARGS))}")
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

    def time(self, duration=None):
        """表示時間を設定。省略時は加工後長(length())で自動決定（layer exec後に確定）"""
        if duration is None:
            if self.media_type == "image":
                raise TypeError(
                    "画像には time() 省略は使えません。time(seconds) を指定してください。")
            self.duration = None
            self._duration_auto = True
        else:
            self.duration = duration
            self._duration_auto = False
        return self

    def until(self, name):
        """durationをアンカー時刻まで伸長"""
        self._until_anchor = name
        return self

    def __le__(self, rhs):
        """<= 演算子: Transform/Effect/AudioEffect等を適用"""
        if isinstance(rhs, _DisabledAudioEffect):
            return self  # AudioのDisableだけ残す
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(rhs.transforms)
        elif isinstance(rhs, Effect):
            if rhs.name == "delete":
                self._video_deleted = True
            else:
                self.effects.append(rhs)
        elif isinstance(rhs, EffectChain):
            for e in rhs.effects:
                if e.name == "delete":
                    self._video_deleted = True
                else:
                    self.effects.append(e)
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

    def length(self):
        """加工後の再生時間を返す（ffprobe + 時間影響エフェクト反映）"""
        if self.media_type == "image":
            raise TypeError("画像にはlength()を使えません。動画/音声のみ対応です。")
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
        # 映像trim
        for e in self.effects:
            if e.name == "trim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
        # 音声atrim/atempo
        for e in self.audio_effects:
            if e.name == "atrim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
            elif e.name == "atempo":
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

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(url)
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
            browser.close()

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
    return Transform("rotate", rad=rad_val, expand=expand, fill=fill)


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
              to_deg=None, to_rad=None, expand=True, fill="0x00000000"):
    """時間依存回転Effect。deg/rad直接指定 or from/to でlerp。"""
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
            rad_expr = _resolve_param(
                lambda u, _d=deg: deg2rad(_d) if isinstance(_d, (int, float)) else deg2rad(_d))
    return Effect("rotate_to", rad=rad_expr, expand=expand, fill=fill)


def morph_to(target, blend=None, **morph_params):
    """モーフィングEffect: 画像→画像の最適輸送モーフ動画を生成"""
    if not isinstance(target, Object):
        raise TypeError(f"morph_to の target は Object のみ: {type(target)}")
    # ターゲットObjectをProjectから除外（morphに消費される）
    proj = Project._current
    if proj is not None and target in proj.objects:
        proj.objects.remove(target)
        warnings.warn(
            f"morph_to: ターゲット '{target.source}' はモーフィングに消費されるため"
            f"Projectから自動的に除外されました。"
        )
    if blend is None:
        blend = _resolve_param(lambda u: u * u * (3 - 2 * u))
    else:
        blend = _resolve_param(blend)
    eff = Effect("morph_to", blend=blend, **morph_params)
    eff._morph_target = target
    return eff


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

    def until(self, name):
        p = Pause()
        p._until_anchor = name
        if Project._current is not None:
            Project._current.objects.append(p)
        return p


pause = _PauseFactory()


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
