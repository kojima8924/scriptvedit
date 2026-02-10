import subprocess
import os
import json
import hashlib
import warnings
import builtins as _builtins

__all__ = [
    # コアクラス
    "Project", "Object", "Transform", "TransformChain", "Effect", "EffectChain",
    "AudioEffect", "AudioEffectChain",
    "VideoView", "AudioView",
    # ファクトリ関数
    "resize", "scale", "fade", "move",
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
            import math as _m
            cls._EVAL_FUNCS = {
                'sin': _m.sin, 'cos': _m.cos, 'tan': _m.tan,
                'asin': _m.asin, 'acos': _m.acos, 'atan': _m.atan,
                'atan2': _m.atan2, 'sinh': _m.sinh, 'cosh': _m.cosh,
                'tanh': _m.tanh, 'exp': _m.exp, 'log': _m.log,
                'sqrt': _m.sqrt, 'floor': _m.floor, 'ceil': _m.ceil,
                'trunc': _m.trunc, 'round': _builtins.round,
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

def _layer_cache_paths(filename):
    basename = os.path.splitext(os.path.basename(filename))[0]
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
        except Exception:
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
        self._current_layer_file = None

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
            # web Objectのsourceを予定webmパスに仮差し替え
            for obj in self.objects:
                if isinstance(obj, Object) and obj.media_type == "web":
                    name = obj._web_name
                    obj.source = os.path.join(_CACHE_DIR, "webclip", f"{name}.webm")
                    obj.media_type = "video"
            cmd = self._build_ffmpeg_cmd(output_path)
            all_extra = {}
            if cache_cmds:
                all_extra.update(cache_cmds)
            if web_cmds:
                all_extra.update(web_cmds)
            if all_extra:
                return {"main": cmd, "cache": all_extra}
            return cmd  # 後方互換: cache不要ならlistのまま

        self._ensure_web_objects()
        cmd = self._build_ffmpeg_cmd(output_path)
        print(f"実行コマンド:")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        print()
        subprocess.run(cmd, check=True)
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
                if self._should_use_cache(spec):
                    self._load_cached_layer(spec)
                else:
                    self._exec_layer(spec["filename"], spec["priority"])
            self._resolve_anchors(check_unresolved=False)
            if self._anchors == old_anchors and iteration > 0:
                converged = True
                break
        # 収束しなかった場合
        if not converged and self._anchors:
            warnings.warn(
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
                webm_path, json_path = _layer_cache_paths(spec["filename"])
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
            webm_path, _ = _layer_cache_paths(spec["filename"])
            return os.path.exists(webm_path)
        return False  # off, make

    def _load_cached_layer(self, spec):
        """キャッシュからObject生成 + anchors.jsonマージ"""
        webm_path, json_path = _layer_cache_paths(spec["filename"])
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
                        webm_path, _ = _layer_cache_paths(spec["filename"])
                        cache_cmds[webm_path] = cmd
        return cache_cmds

    def _collect_web_cmds(self):
        """dry_run用: web Objectのwebmエンコードコマンドを収集"""
        cmds = {}
        for obj in self.objects:
            if isinstance(obj, Object) and obj.media_type == "web":
                name = obj._web_name
                webm_path = os.path.join(_CACHE_DIR, "webclip", f"{name}.webm")
                cmds[webm_path] = obj._build_web_cmd(self)
        return cmds

    def _ensure_web_objects(self):
        """web ObjectのPlaywrightレンダ+ffmpegエンコード実行、sourceをwebmに差し替え"""
        for obj in self.objects:
            if not isinstance(obj, Object) or obj.media_type != "web":
                continue
            name = obj._web_name
            cache_dir = os.path.join(_CACHE_DIR, "webclip")
            webm_path = os.path.join(cache_dir, f"{name}.webm")
            frames_dir = os.path.join(cache_dir, f"{name}_frames")

            if not os.path.exists(webm_path):
                print(f"Webクリップ生成: {obj.source}")
                obj._render_web_frames(self)
                cmd = obj._build_web_cmd(self)
                os.makedirs(cache_dir, exist_ok=True)
                print(f"  ffmpeg {' '.join(cmd[1:])}")
                subprocess.run(cmd, check=True)
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
        webm_path, _ = _layer_cache_paths(spec["filename"])
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
        webm_path, json_path = _layer_cache_paths(spec["filename"])
        os.makedirs(_CACHE_DIR, exist_ok=True)

        cmd = self._build_layer_cache_cmd(spec_index)
        print(f"キャッシュ生成: {webm_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        subprocess.run(cmd, check=True)
        print(f"  完了: {webm_path}")

        # anchors.json書き出し
        objects, anchors = self._get_layer_data(spec_index)
        dur = self.duration or self._calc_total_duration()
        cache_meta = {"duration": dur, "anchors": anchors}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cache_meta, f, indent=2, ensure_ascii=False)
        print(f"  アンカー保存: {json_path}")

    def render_object(self, obj, output_path, *, bg=None, fps=None):
        """単体Objectをレンダリングしてファイル出力"""
        bg = bg or self.background_color
        fps = fps or self.fps
        dur = obj.duration or 5
        is_image_out = _detect_media_type(output_path) == "image"

        if is_image_out:
            cmd = self._build_image_cache_cmd(obj, output_path)
        else:
            cmd = self._build_video_cache_cmd(obj, output_path, bg=bg, fps=fps, dur=dur)

        print(f"キャッシュ生成: {output_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        subprocess.run(cmd, check=True)
        print(f"  完了: {output_path}")

    def _build_image_cache_cmd(self, obj, output_path):
        """画像キャッシュ: 背景なし、Transformのみ適用して透過PNG出力"""
        filters = _build_transform_filters(obj)
        cmd = ["ffmpeg", "-y", "-i", obj.source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", output_path])
        return cmd

    def _build_video_cache_cmd(self, obj, output_path, *, bg, fps, dur):
        """動画キャッシュ: 背景あり、全Effect適用"""
        inputs = []
        filter_parts = []

        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c={bg}:s={self.width}x{self.height}:d={dur}:r={fps}",
        ])

        if obj.media_type == "image":
            inputs.extend(["-loop", "1", "-r", str(fps), "-i", obj.source])
        else:
            inputs.extend(["-i", obj.source])

        base_dims = _get_base_dimensions(obj)
        obj_filters = _build_transform_filters(obj)
        eff_filters, pad_size = _build_effect_filters(obj, 0, dur, base_dims=base_dims)
        obj_filters.extend(eff_filters)

        obj_label = "[obj1]"
        if obj_filters:
            filter_parts.append(f"[1:v]{','.join(obj_filters)}{obj_label}")
        else:
            obj_label = "[1:v]"

        x_expr, y_expr = _build_move_exprs(obj, 0, dur, pad_size=pad_size)

        out_label = "[vout]"
        filter_parts.append(f"[0:v]{obj_label}overlay={x_expr}:{y_expr}{out_label}")

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", out_label])

        cmd.extend([
            "-c:v", "libx264",
            "-t", str(dur),
            "-pix_fmt", "yuv420p",
            output_path,
        ])
        return cmd

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
            capture_output=True, text=True, check=True)
        parts = result.stdout.strip().split(',')
        return int(parts[0]), int(parts[1])
    except Exception:
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
    return filters


def _build_effect_filters(obj, start, dur, base_dims=None):
    """scale/fade等のeffectフィルタリストを生成（move/trim/delete以外）
    base_dims指定時、scaleエフェクトにpadを追加して固定サイズ出力にする。
    Returns: (filters, pad_size) — pad_size は (max_w, max_h) or None
    """
    import math as _math
    filters = []
    pad_size = None
    for e in obj.effects:
        if e.name in ("move", "trim", "delete"):
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
                s0 = scale_expr.eval_at(0)
                s1 = scale_expr.eval_at(1)
                max_s = _builtins.max(s0, s1)
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
        if isinstance(other, _DisabledTransform):
            return TransformChain(self.transforms + [other])
        return NotImplemented

    def __invert__(self):
        return _DisabledTransform(self)

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
        if isinstance(other, _DisabledEffect):
            return EffectChain(self.effects + [other])
        return NotImplemented

    def __invert__(self):
        return _DisabledEffect(self)

    def __repr__(self):
        return f"EffectChain({self.effects})"


class _DisabledTransform:
    """無効化Transform（Object.__le__でスキップ）"""
    def __init__(self, original):
        self.original = original

    def __or__(self, other):
        if isinstance(other, (Transform, _DisabledTransform)):
            return TransformChain([self, other])
        if isinstance(other, TransformChain):
            return TransformChain([self] + other.transforms)
        return NotImplemented

    def __ror__(self, other):
        if isinstance(other, Transform):
            return TransformChain([other, self])
        if isinstance(other, TransformChain):
            return TransformChain(other.transforms + [self])
        return NotImplemented

    def __invert__(self):
        return self.original


class _DisabledEffect:
    """無効化Effect（Object.__le__でスキップ）"""
    def __init__(self, original):
        self.original = original

    def __and__(self, other):
        if isinstance(other, (Effect, _DisabledEffect)):
            return EffectChain([self, other])
        if isinstance(other, EffectChain):
            return EffectChain([self] + other.effects)
        return NotImplemented

    def __rand__(self, other):
        if isinstance(other, Effect):
            return EffectChain([other, self])
        if isinstance(other, EffectChain):
            return EffectChain(other.effects + [self])
        return NotImplemented

    def __invert__(self):
        return self.original


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
    def __init__(self, name, **params):
        self.name = name
        self.params = params

    def __or__(self, other):
        """Transform | Transform/TransformChain → TransformChain"""
        if isinstance(other, Transform):
            return TransformChain([self, other])
        if isinstance(other, TransformChain):
            return TransformChain([self] + other.transforms)
        if isinstance(other, _DisabledTransform):
            return TransformChain([self, other])
        return NotImplemented

    def __invert__(self):
        return _DisabledTransform(self)

    def __repr__(self):
        return f"Transform({self.name}, {self.params})"


class Effect:
    def __init__(self, name, **params):
        self.name = name
        self.params = params

    def __and__(self, other):
        """Effect & Effect/EffectChain → EffectChain"""
        if isinstance(other, Effect):
            return EffectChain([self, other])
        if isinstance(other, EffectChain):
            return EffectChain([self] + other.effects)
        if isinstance(other, _DisabledEffect):
            return EffectChain([self, other])
        return NotImplemented

    def __invert__(self):
        return _DisabledEffect(self)

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


_WEB_KWARGS = {"duration", "size", "fps", "data", "name", "debug_frames"}


class Object:
    def __init__(self, source, **kwargs):
        self.source = source
        self.transforms = []
        self.effects = []
        self.audio_effects = []
        self.duration = None
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
            return True  # probe不可→True想定
        return self._has_audio

    def time(self, duration):
        """表示時間を設定"""
        self.duration = duration
        return self

    def until(self, name):
        """durationをアンカー時刻まで伸長"""
        self._until_anchor = name
        return self

    def __le__(self, rhs):
        """<= 演算子: Transform/Effect/AudioEffect等を適用"""
        if isinstance(rhs, (_DisabledTransform, _DisabledEffect, _DisabledAudioEffect)):
            return self  # 無効化→スキップ
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(
                t for t in rhs.transforms if not isinstance(t, _DisabledTransform))
        elif isinstance(rhs, Effect):
            if rhs.name == "delete":
                self._video_deleted = True
            else:
                self.effects.append(rhs)
        elif isinstance(rhs, EffectChain):
            for e in rhs.effects:
                if isinstance(e, _DisabledEffect):
                    continue
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

    def _make_cached_object(self, path):
        """キャッシュObject（transforms/effectsなし）を生成してProjectに登録"""
        proj = Project._current
        cached = Object.__new__(Object)
        cached.source = path
        cached.transforms = []
        cached.effects = []
        cached.audio_effects = []
        cached.duration = self.duration
        cached.start_time = self.start_time
        cached.priority = self.priority
        cached.media_type = _detect_media_type(path)
        cached._until_anchor = self._until_anchor
        cached._video_deleted = False
        cached._audio_deleted = False
        cached._has_video = True if cached.media_type != "audio" else False
        cached._has_audio = True if cached.media_type != "image" else False
        cached._web_source = None
        cached._web_size = None
        cached._web_fps = None
        cached._web_data = {}
        cached._web_name = None
        cached._web_debug_frames = False
        if proj is not None and self in proj.objects:
            idx = proj.objects.index(self)
            proj.objects[idx] = cached
        return cached

    def cache(self, path, *, overwrite=True, bg=None, fps=None):
        """単体レンダしてキャッシュファイルを生成、そのファイルを sourceに持つ新Objectを返す"""
        proj = Project._current
        if proj is None:
            raise RuntimeError("cache()にはアクティブなProjectが必要です")
        if proj._mode == "plan":
            # Planモード: renderと同形式のオブジェクトを返す（ファイル生成なし）
            return self._make_cached_object(path)
        if overwrite or not os.path.exists(path):
            proj.render_object(self, path, bg=bg, fps=fps)
        return self._make_cached_object(path)

    @classmethod
    def load_cache(cls, path):
        """キャッシュファイルからObjectを生成"""
        return cls(path)

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

    def _build_web_cmd(self, project):
        """webクリップ用ffmpegコマンド"""
        cache_dir = os.path.join(_CACHE_DIR, "webclip")
        name = self._web_name
        webm_path = os.path.join(cache_dir, f"{name}.webm")
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
        if isinstance(rhs, (Transform, TransformChain, Effect, EffectChain,
                           _DisabledTransform, _DisabledEffect)):
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
             name=None, debug_frames=False):
    """字幕テンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("subtitle.html")
    data = {"text": text, "who": who, "style": style or {}}
    if name is None:
        name = f"subtitle_{_data_hash(data)}"
    return Object(tpl, duration=duration, size=size, data=data,
                  name=name, debug_frames=debug_frames)


def bubble(text, duration=2.5, *, anchor=None, pos=None, box=None,
           style=None, size=None, name=None, debug_frames=False):
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
    return Object(tpl, duration=duration, size=size, data=data,
                  name=name, debug_frames=debug_frames)


def diagram(objects, duration=3.0, *, style=None, size=None,
            name=None, debug_frames=False):
    """SVG図解テンプレートObjectを生成"""
    size = _resolve_size(size)
    tpl = _template_path("diagram_svg.html")
    data = {"objects": objects, "style": style or {}}
    if name is None:
        name = f"diagram_{_data_hash(data)}"
    return Object(tpl, duration=duration, size=size, data=data,
                  name=name, debug_frames=debug_frames)


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
