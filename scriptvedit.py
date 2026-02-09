import subprocess
import os


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
            for obj in self.objects[start_idx:end_idx]:
                if obj.duration is not None:
                    layer_dur += obj.duration
            max_dur = max(max_dur, layer_dur)
        return max_dur if max_dur > 0 else 5

    def render(self, output_path):
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
                v = e.params.get("value", 1)
                expr = f"{v}+(1-{v})*(t-{start})/{dur}"
                obj_filters.append(
                    f"scale=w='trunc(iw*({expr})/2)*2':h='trunc(ih*({expr})/2)*2':eval=frame"
                )
            elif e.name == "fade":
                alpha = e.params.get("alpha", 1.0)
                expr = f"{alpha}+(1-{alpha})*(T-{start})/{dur}"
                obj_filters.append("format=rgba")
                obj_filters.append(
                    f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({expr}\\,0\\,1)'"
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

        # タイミング計算（レイヤーごとに独立、各レイヤーは0秒から開始）
        for start_idx, end_idx, _ in self._layers:
            current_time = 0
            for obj in self.objects[start_idx:end_idx]:
                obj.start_time = current_time
                if obj.duration is not None:
                    current_time += obj.duration

        # z-order: priorityでソート（小さい=奥、大きい=手前）
        sorted_objects = sorted(self.objects, key=lambda o: o.priority)

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

            # Effect処理（move以外、float引数はstart_time〜start_time+durationで値→1.0にアニメーション）
            dur = obj.duration or 5
            start = obj.start_time
            for e in obj.effects:
                if e.name == "scale":
                    v = e.params.get("value", 1)
                    expr = f"{v}+(1-{v})*(t-{start})/{dur}"
                    obj_filters.append(
                        f"scale=w='trunc(iw*({expr})/2)*2':h='trunc(ih*({expr})/2)*2':eval=frame"
                    )
                elif e.name == "fade":
                    alpha = e.params.get("alpha", 1.0)
                    expr = f"{alpha}+(1-{alpha})*(T-{start})/{dur}"
                    obj_filters.append("format=rgba")
                    obj_filters.append(
                        f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*clip({expr}\\,0\\,1)'"
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
    anchor = p.get("anchor", "center")

    # from/to アニメーション対応
    has_anim = "from_x" in p or "from_y" in p or "to_x" in p or "to_y" in p

    if has_anim:
        fx = p.get("from_x", p.get("x", 0.5))
        fy = p.get("from_y", p.get("y", 0.5))
        tx = p.get("to_x", p.get("x", 0.5))
        ty = p.get("to_y", p.get("y", 0.5))
        # p_expr = clip((t-start)/dur, 0, 1)
        p_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
        base_x = f"({fx}+({tx}-{fx})*{p_expr})*W"
        base_y = f"({fy}+({ty}-{fy})*{p_expr})*H"
    else:
        x = p.get("x", 0.5)
        y = p.get("y", 0.5)
        base_x = f"W*{x}"
        base_y = f"H*{y}"

    if anchor == "center":
        x_expr = f"{base_x}-w/2"
        y_expr = f"{base_y}-h/2"
    else:
        x_expr = base_x
        y_expr = base_y

    return x_expr, y_expr


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


class Object:
    def __init__(self, source):
        self.source = source
        self.transforms = []
        self.effects = []
        self.duration = None
        self.start_time = 0
        self.priority = 0
        self.media_type = _detect_media_type(source)
        # 現在のProjectに自動登録
        if Project._current is not None:
            Project._current.objects.append(self)

    def time(self, duration):
        """表示時間を設定"""
        self.duration = duration
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

def scale(value):
    return Effect("scale", value=value)


def fade(**kwargs):
    return Effect("fade", **kwargs)


def move(**kwargs):
    return Effect("move", **kwargs)
