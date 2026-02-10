import subprocess
import os
import json
import warnings
import builtins as _builtins

__all__ = [
    # コアクラス
    "Project", "Object", "Transform", "TransformChain", "Effect", "EffectChain",
    # ファクトリ関数
    "resize", "scale", "fade", "move",
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
]


# --- Expr（式ビルダー） ---

class Expr:
    """ffmpeg式ビルダー基底クラス"""
    def to_ffmpeg(self, u_expr):
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


class Var(Expr):
    """変数ノード"""
    def __init__(self, name):
        self.name = name

    def to_ffmpeg(self, u_expr):
        if self.name == "u":
            return u_expr
        return self.name


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


class _UnOp(Expr):
    """単項演算ノード"""
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand

    def to_ffmpeg(self, u_expr):
        x = self.operand.to_ffmpeg(u_expr)
        return f"({self.op}{x})"


class _FuncCall(Expr):
    """関数呼び出しノード"""
    def __init__(self, name, args):
        self.name = name
        self.args = args

    def to_ffmpeg(self, u_expr):
        arg_strs = [a.to_ffmpeg(u_expr) for a in self.args]
        sep = "\\,"
        return f"{self.name}({sep.join(arg_strs)})"


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


def _detect_media_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
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
        cmd = self._build_ffmpeg_cmd(output_path)
        if dry_run:
            cache_cmds = self._collect_cache_cmds()
            if cache_cmds:
                return {"main": cmd, "cache": cache_cmds}
            return cmd  # 後方互換: cache不要ならlistのまま
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
        cached_obj.duration = None
        cached_obj.start_time = 0
        cached_obj.priority = spec["priority"]
        cached_obj.media_type = "video"
        cached_obj._until_anchor = None
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
                inputs.extend(["-loop", "1", "-i", obj.source])
            else:
                inputs.extend(["-i", obj.source])

            obj_dur = obj.duration or dur
            start = obj.start_time

            obj_filters = _build_transform_filters(obj)
            obj_filters.extend(_build_effect_filters(obj, start, obj_dur))

            obj_label = f"[obj{input_idx}]"
            if obj_filters:
                filter_parts.append(
                    f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}"
                )
            else:
                obj_label = f"[{input_idx}:v]"

            x_expr, y_expr = _build_move_exprs(obj, start, obj_dur)

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
            inputs.extend(["-loop", "1", "-i", obj.source])
        else:
            inputs.extend(["-i", obj.source])

        obj_filters = _build_transform_filters(obj)
        obj_filters.extend(_build_effect_filters(obj, 0, dur))

        obj_label = "[obj1]"
        if obj_filters:
            filter_parts.append(f"[1:v]{','.join(obj_filters)}{obj_label}")
        else:
            obj_label = "[1:v]"

        x_expr, y_expr = _build_move_exprs(obj, 0, dur)

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

        current_base = "[0:v]"

        for i, obj in enumerate(sorted_objects):
            input_idx = i + 1

            if obj.media_type == "image":
                inputs.extend(["-loop", "1", "-i", obj.source])
            else:
                inputs.extend(["-i", obj.source])

            dur = obj.duration or 5
            start = obj.start_time

            obj_filters = _build_transform_filters(obj)
            obj_filters.extend(_build_effect_filters(obj, start, dur))

            obj_label = f"[obj{input_idx}]"
            if obj_filters:
                filter_parts.append(
                    f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}"
                )
            else:
                obj_label = f"[{input_idx}:v]"

            x_expr, y_expr = _build_move_exprs(obj, start, dur)

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
            "-c:v", "libx264",
            "-t", str(self.duration),
            "-pix_fmt", "yuv420p",
            output_path,
        ])

        return cmd


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


def _build_effect_filters(obj, start, dur):
    """scale/fade等のeffectフィルタリストを生成（move以外）"""
    filters = []
    for e in obj.effects:
        if e.name == "scale":
            scale_expr = e.params.get("value", Const(1))
            u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
            ffmpeg_str = scale_expr.to_ffmpeg(u_expr)
            filters.append(
                f"scale=w='trunc(iw*({ffmpeg_str})/2)*2':h='trunc(ih*({ffmpeg_str})/2)*2':eval=frame"
            )
        elif e.name == "fade":
            alpha_expr = e.params.get("alpha", Const(1.0))
            u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
            ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
            filters.append("format=rgba")
            filters.append(
                f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({ffmpeg_str}\\,0\\,1)'"
            )
    return filters


def _build_move_exprs(obj, start, dur):
    """objのeffectsからmoveを探し、overlay用のx_expr/y_exprを返す"""
    move_effect = None
    for e in obj.effects:
        if e.name == "move":
            move_effect = e

    if move_effect is None:
        return "(W-w)/2", "(H-h)/2"

    p = move_effect.params
    anchor_val = p.get("anchor", "center")

    x_param = p.get("x", Const(0.5))
    y_param = p.get("y", Const(0.5))

    u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
    base_x = f"{x_param.to_ffmpeg(u_expr)}*W"
    base_y = f"{y_param.to_ffmpeg(u_expr)}*H"

    if anchor_val == "center":
        x_result = f"{base_x}-w/2"
        y_result = f"{base_y}-h/2"
    else:
        x_result = base_x
        y_result = base_y

    return x_result, y_result


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


class Object:
    def __init__(self, source):
        self.source = source
        self.transforms = []
        self.effects = []
        self.duration = None
        self.start_time = 0
        self.priority = 0
        self.media_type = _detect_media_type(source)
        self._until_anchor = None
        # 現在のProjectに自動登録
        if Project._current is not None:
            Project._current.objects.append(self)

    def time(self, duration):
        """表示時間を設定"""
        self.duration = duration
        return self

    def until(self, name):
        """durationをアンカー時刻まで伸長"""
        self._until_anchor = name
        return self

    def __le__(self, rhs):
        """<= 演算子: Transform/TransformChain/Effect/EffectChainを適用"""
        if isinstance(rhs, (_DisabledTransform, _DisabledEffect)):
            return self  # 無効化→スキップ
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(
                t for t in rhs.transforms if not isinstance(t, _DisabledTransform))
        elif isinstance(rhs, Effect):
            self.effects.append(rhs)
        elif isinstance(rhs, EffectChain):
            self.effects.extend(
                e for e in rhs.effects if not isinstance(e, _DisabledEffect))
        else:
            raise TypeError(f"Object <= に渡せるのは Transform/TransformChain/Effect/EffectChain のみ: {type(rhs)}")
        return self

    def _make_cached_object(self, path):
        """キャッシュObject（transforms/effectsなし）を生成してProjectに登録"""
        proj = Project._current
        cached = Object.__new__(Object)
        cached.source = path
        cached.transforms = []
        cached.effects = []
        cached.duration = self.duration
        cached.start_time = self.start_time
        cached.priority = self.priority
        cached.media_type = _detect_media_type(path)
        cached._until_anchor = self._until_anchor
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

    def __repr__(self):
        return f"Object({self.source}, transforms={self.transforms}, effects={self.effects})"


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
