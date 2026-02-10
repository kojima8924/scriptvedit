import subprocess
import os
import builtins as _builtins


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

def log10(x):
    return _FuncCall("log", [_to_expr(x)]) / Const(2.302585092994046)

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


class Project:
    _current = None

    def __init__(self):
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.duration = None
        self.background_color = "black"
        self.objects = []
        self._layers = []  # [(start_idx, end_idx, priority)]
        self._anchors = {}  # anchor name → time
        Project._current = self

    def configure(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def layer(self, filename, priority=0):
        """レイヤーファイルを読み込み、Objectにpriorityを付与"""
        start_idx = len(self.objects)
        with open(filename, encoding="utf-8") as f:
            code = f.read()
        namespace = {}
        exec(compile(code, filename, "exec"), namespace)
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, priority))
        for obj in self.objects[start_idx:end_idx]:
            obj.priority = priority

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

    def _resolve_anchors(self):
        """反復走査でアンカーとuntilを解決（plan pass）"""
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
        # 未解決のuntilチェック
        for item in self.objects:
            until_name = getattr(item, '_until_anchor', None)
            if until_name and until_name not in self._anchors:
                raise RuntimeError(f"未定義のアンカー: '{until_name}'")

    def render(self, output_path):
        self._resolve_anchors()
        if self.duration is None:
            self.duration = self._calc_total_duration()
        cmd = self._build_ffmpeg_cmd(output_path)
        print(f"実行コマンド:")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        print()
        subprocess.run(cmd, check=True)
        print(f"\n完了: {output_path}")

    def render_object(self, obj, output_path, *, bg=None, fps=None):
        """単体Objectをレンダリングしてファイル出力"""
        bg = bg or self.background_color
        fps = fps or self.fps
        dur = obj.duration or 5
        is_image_out = _detect_media_type(output_path) == "image"

        if is_image_out:
            # 画像キャッシュ: 背景なし、Transformのみ適用して透過PNG出力
            cmd = self._build_image_cache_cmd(obj, output_path)
        else:
            # 動画キャッシュ: 背景あり、全Effect適用
            cmd = self._build_video_cache_cmd(obj, output_path, bg=bg, fps=fps, dur=dur)

        print(f"キャッシュ生成: {output_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        subprocess.run(cmd, check=True)
        print(f"  完了: {output_path}")

    def _build_image_cache_cmd(self, obj, output_path):
        """画像キャッシュ: 背景なし、Transformのみ適用して透過PNG出力"""
        filters = []
        for t in obj.transforms:
            if t.name == "resize":
                sx = t.params.get("sx", 1)
                sy = t.params.get("sy", 1)
                filters.append(f"scale=iw*{sx}:ih*{sy}")

        cmd = ["ffmpeg", "-y", "-i", obj.source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", output_path])
        return cmd

    def _build_video_cache_cmd(self, obj, output_path, *, bg, fps, dur):
        """動画キャッシュ: 背景あり、全Effect適用"""
        inputs = []
        filter_parts = []

        # [0] 背景色
        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c={bg}:s={self.width}x{self.height}:d={dur}:r={fps}",
        ])

        # [1] ソース入力
        if obj.media_type == "image":
            inputs.extend(["-loop", "1", "-i", obj.source])
        else:
            inputs.extend(["-i", obj.source])

        obj_filters = []

        # Transform処理
        for t in obj.transforms:
            if t.name == "resize":
                sx = t.params.get("sx", 1)
                sy = t.params.get("sy", 1)
                obj_filters.append(f"scale=iw*{sx}:ih*{sy}")

        # Effect処理（moveを除く）
        start = 0
        for e in obj.effects:
            if e.name == "scale":
                scale_expr = e.params.get("value", Const(1))
                u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
                ffmpeg_str = scale_expr.to_ffmpeg(u_expr)
                obj_filters.append(
                    f"scale=w='trunc(iw*({ffmpeg_str})/2)*2':h='trunc(ih*({ffmpeg_str})/2)*2':eval=frame"
                )
            elif e.name == "fade":
                alpha_expr = e.params.get("alpha", Const(1.0))
                u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
                ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
                obj_filters.append("format=rgba")
                obj_filters.append(
                    f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({ffmpeg_str}\\,0\\,1)'"
                )

        obj_label = "[obj1]"
        if obj_filters:
            filter_parts.append(f"[1:v]{','.join(obj_filters)}{obj_label}")
        else:
            obj_label = "[1:v]"

        # overlay位置（moveから取得）
        x_expr, y_expr = _build_move_exprs(obj, start, dur)

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

        # [0] 背景色
        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c={self.background_color}:s={self.width}x{self.height}:d={self.duration}:r={self.fps}",
        ])

        # タイミングは_resolve_anchorsで計算済み
        # z-order: priorityでソート（Pause/_AnchorMarkerを除外）
        renderable = [o for o in self.objects if isinstance(o, Object)]
        sorted_objects = sorted(renderable, key=lambda o: o.priority)

        current_base = "[0:v]"

        for i, obj in enumerate(sorted_objects):
            input_idx = i + 1

            # media_typeで入力分岐
            if obj.media_type == "image":
                inputs.extend(["-loop", "1", "-i", obj.source])
            else:
                inputs.extend(["-i", obj.source])

            # オブジェクトごとのフィルタチェーン構築
            obj_filters = []

            # Transform処理
            for t in obj.transforms:
                if t.name == "resize":
                    sx = t.params.get("sx", 1)
                    sy = t.params.get("sy", 1)
                    obj_filters.append(f"scale=iw*{sx}:ih*{sy}")

            # Effect処理（move以外）
            dur = obj.duration or 5
            start = obj.start_time
            for e in obj.effects:
                if e.name == "scale":
                    scale_expr = e.params.get("value", Const(1))
                    u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
                    ffmpeg_str = scale_expr.to_ffmpeg(u_expr)
                    obj_filters.append(
                        f"scale=w='trunc(iw*({ffmpeg_str})/2)*2':h='trunc(ih*({ffmpeg_str})/2)*2':eval=frame"
                    )
                elif e.name == "fade":
                    alpha_expr = e.params.get("alpha", Const(1.0))
                    u_expr = f"clip((T-{start})/{dur}\\,0\\,1)"
                    ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
                    obj_filters.append("format=rgba")
                    obj_filters.append(
                        f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({ffmpeg_str}\\,0\\,1)'"
                    )

            # フィルタがあればラベル付きで追加
            obj_label = f"[obj{input_idx}]"
            if obj_filters:
                filter_parts.append(
                    f"[{input_idx}:v]{','.join(obj_filters)}{obj_label}"
                )
            else:
                obj_label = f"[{input_idx}:v]"

            # overlay位置（moveから取得）
            x_expr, y_expr = _build_move_exprs(obj, start, dur)

            # 時間制御: enable='between(t,start,end)'
            enable_str = ""
            if obj.duration is not None:
                start = obj.start_time
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


def _build_move_exprs(obj, start, dur):
    """objのeffectsからmoveを探し、overlay用のx_expr/y_exprを返す"""
    # 最後のmoveを優先
    move_effect = None
    for e in obj.effects:
        if e.name == "move":
            move_effect = e

    if move_effect is None:
        return "(W-w)/2", "(H-h)/2"  # デフォルト中心

    p = move_effect.params
    anchor_val = p.get("anchor", "center")

    # x, y は Expr（_resolve_param済み）
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
        return NotImplemented

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

    def __repr__(self):
        return f"EffectChain({self.effects})"


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
        return NotImplemented

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
        return NotImplemented

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
        if Project._current is not None:
            Project._current.objects.append(self)

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
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(rhs.transforms)
        elif isinstance(rhs, Effect):
            self.effects.append(rhs)
        elif isinstance(rhs, EffectChain):
            self.effects.extend(rhs.effects)
        else:
            raise TypeError(f"Object <= に渡せるのは Transform/TransformChain/Effect/EffectChain のみ: {type(rhs)}")
        return self

    def cache(self, path, *, overwrite=True, bg=None, fps=None):
        """単体レンダしてキャッシュファイルを生成、そのファイルを sourceに持つ新Objectを返す"""
        proj = Project._current
        if proj is None:
            raise RuntimeError("cache()にはアクティブなProjectが必要です")
        if overwrite or not os.path.exists(path):
            proj.render_object(self, path, bg=bg, fps=fps)
        # キャッシュObjectを生成（Projectに自動登録される）
        # 元のObjectをProjectから除去し、キャッシュObjectで置き換える
        cached = Object.__new__(Object)
        cached.source = path
        cached.transforms = []
        cached.effects = []
        cached.duration = self.duration
        cached.start_time = self.start_time
        cached.priority = self.priority
        cached.media_type = _detect_media_type(path)
        cached._until_anchor = self._until_anchor
        # Projectのobjectsリストで自分をcachedに置換
        if proj is not None and self in proj.objects:
            idx = proj.objects.index(self)
            proj.objects[idx] = cached
        return cached

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
    marker = _AnchorMarker(name)
    proj.objects.append(marker)


class _PauseFactory:
    """pause.time(N) / pause.until(name) でPauseを生成するファクトリ"""
    def time(self, duration):
        p = Pause()
        p.duration = duration
        return p

    def until(self, name):
        p = Pause()
        p._until_anchor = name
        return p


pause = _PauseFactory()
