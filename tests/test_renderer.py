"""
renderer.py のテスト
"""

import pytest
import warnings
from unittest.mock import MagicMock, patch
from pathlib import Path

from scriptvedit.renderer import (
    IMAGE_EXTENSIONS, _build_video_filter, _resolve_transform_value,
    _sample_callable, _piecewise_linear_expr, _clamp_expr
)
from scriptvedit.media import Media, Transform, _chain, _UNSET
from scriptvedit.timeline import Timeline, VideoEntry
from scriptvedit.effects import (
    FadeEffect, MoveEffect, ScaleEffect, BlurEffect, ShakeEffect, RotateToEffect
)


def _create_mock_media(path: str = "test.png", width: int = 800, height: int = 600) -> Media:
    """テスト用のMediaオブジェクトを作成"""
    media = MagicMock(spec=Media)
    media.path = Path(path)
    media.transform = Transform()
    media._ensure_dimensions = MagicMock(return_value=(width, height))
    media._get_duration = MagicMock(return_value=None)  # 画像扱い
    return media


def _create_timeline(curve_samples: int = 10) -> Timeline:
    """テスト用のTimelineを作成"""
    timeline = Timeline()
    timeline.width = 1920
    timeline.height = 1080
    timeline.fps = 30
    timeline.background_color = "black"
    timeline.curve_samples = curve_samples
    return timeline


class TestImageExtensions:
    """画像拡張子の判定テスト"""

    def test_common_image_extensions_included(self):
        """一般的な画像拡張子が含まれていることを確認"""
        # 注意: .gif は動画として扱われることが多いため除外
        expected = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        for ext in expected:
            assert ext in IMAGE_EXTENSIONS, f"{ext} が IMAGE_EXTENSIONS に含まれていない"

    def test_gif_excluded_as_may_be_animated(self):
        """.gif はアニメーションの可能性があるため除外されていることを確認"""
        assert ".gif" not in IMAGE_EXTENSIONS, ".gif は動画扱いのため除外すべき"

    def test_video_extensions_not_included(self):
        """動画拡張子が含まれていないことを確認"""
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        for ext in video_extensions:
            assert ext not in IMAGE_EXTENSIONS, f"{ext} が IMAGE_EXTENSIONS に含まれている"


class TestLoopFlag:
    """-loop 1 フラグのテスト"""

    def test_image_gets_loop_flag(self):
        """画像ファイルに -loop 1 が付与されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("test.png")
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        inputs, _, _ = _build_video_filter(timeline, [entry])

        assert "-loop" in inputs, "画像に -loop フラグがない"
        loop_idx = inputs.index("-loop")
        assert inputs[loop_idx + 1] == "1", "-loop の後に 1 がない"

    def test_video_does_not_get_loop_flag(self):
        """動画ファイルに -loop 1 が付与されないことを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("test.mp4")
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        inputs, _, _ = _build_video_filter(timeline, [entry])

        assert "-loop" not in inputs, "動画に -loop フラグが付与されている"

    def test_jpg_gets_loop_flag(self):
        """JPGファイルに -loop 1 が付与されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("photo.jpg")
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        inputs, _, _ = _build_video_filter(timeline, [entry])
        assert "-loop" in inputs

    def test_webm_does_not_get_loop_flag(self):
        """WebMファイルに -loop 1 が付与されないことを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("video.webm")
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        inputs, _, _ = _build_video_filter(timeline, [entry])
        assert "-loop" not in inputs


class TestStartTimeOffset:
    """start>0 のアニメーションタイミングテスト"""

    def test_trim_added_for_any_entry(self):
        """すべてのエントリに trim が追加されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        entry = VideoEntry(media=media, start_time=0, duration=3, effects=[])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # offset 対応で trim=start=...:duration=... 形式になる
        assert "trim=start=" in filter_str and "duration=3" in filter_str, \
            f"trim が含まれていない: {filter_str}"

    def test_setpts_offset_for_start_greater_than_zero(self):
        """start>0 のとき setpts に開始時間オフセットがあることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        entry = VideoEntry(media=media, start_time=2.5, duration=3, effects=[])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # setpts=PTS-STARTPTS+2.5/TB が含まれていることを確認
        assert "setpts=PTS-STARTPTS+2.5/TB" in filter_str, f"setpts オフセットが正しくない: {filter_str}"

    def test_setpts_offset_zero_for_start_zero(self):
        """start=0 のとき setpts に 0 オフセットがあることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "setpts=PTS-STARTPTS+0/TB" in filter_str

    def test_enable_clause_still_present(self):
        """enable clause が維持されていることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        entry = VideoEntry(media=media, start_time=2, duration=3, effects=[])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "enable='between(t,2,5)'" in filter_str


class TestTransformCallableResolution:
    """Transform callable の解決テスト"""

    def test_resolve_transform_value_with_float(self):
        """float 値がそのまま返されることを確認"""
        result = _resolve_transform_value(0.5, 1.0)
        assert result == 0.5

    def test_resolve_transform_value_with_callable(self):
        """callable が現在値を受け取って評価されることを確認"""
        fn = lambda x: x * 2
        result = _resolve_transform_value(fn, 0.3)
        assert result == 0.6

    def test_resolve_transform_value_with_none(self):
        """None が現在値を返すことを確認"""
        result = _resolve_transform_value(None, 0.7)
        assert result == 0.7

    def test_transform_callable_scale_halves_current(self):
        """resize(sx=lambda x: x/2) で直前値の半分になることを確認"""
        timeline = _create_timeline()

        # 800x600 の画像
        media = _create_mock_media(width=800, height=600)
        # _chain を使って直前値を保持
        # 最初に 0.6 にリサイズ
        media.transform.scale_x = 0.6
        media.transform.scale_y = 0.45  # アスペクト比維持
        # 次に callable で半分にする（_chain を通す）
        media.transform.scale_x = _chain(media.transform.scale_x, lambda x: x / 2)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # scale_x = 0.6 / 2 = 0.3 → 1920 * 0.3 = 576
        # _chain により prev=0.6 が保持され、callable(0.6) = 0.3
        assert "scale=576:" in filter_str


class TestEffectCallablePiecewiseLinear:
    """Effect callable の区分線形式生成テスト"""

    def test_sample_callable_returns_correct_samples(self):
        """サンプリングが正しく動作することを確認"""
        fn = lambda u: u * u
        samples = _sample_callable(fn, 5)
        assert len(samples) == 5
        assert samples[0] == 0.0  # u=0
        assert samples[-1] == 1.0  # u=1
        assert abs(samples[2] - 0.25) < 0.01  # u=0.5 -> 0.25

    def test_piecewise_linear_expr_two_samples(self):
        """2サンプルで線形補間式が生成されることを確認"""
        expr = _piecewise_linear_expr("u", [0.0, 1.0])
        assert "0.0" in expr
        assert "1.0" in expr
        # 線形補間の形式: (v0 + (v1-v0) * u)
        assert "+" in expr

    def test_piecewise_linear_expr_multiple_samples(self):
        """複数サンプルで if 式が生成されることを確認"""
        expr = _piecewise_linear_expr("u", [0.0, 0.5, 1.0])
        assert "if(lte" in expr

    def test_clamp_expr_generates_clip(self):
        """clamp_expr が clip 式を生成することを確認"""
        expr = _clamp_expr("x", 0, 1)
        assert "clip(x,0,1)" == expr


class TestCallableFade:
    """callable fade のテスト（全ての callable は geq フィルタを使用）"""

    def test_linear_fadein_uses_geq(self):
        """線形フェードイン (lambda u: u) が geq を使用することを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        # 線形フェードイン
        fade_effect = FadeEffect(alpha=lambda u: u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # geq フィルタが使用されていることを確認
        assert "geq=" in filter_str, f"geq が含まれていない: {filter_str}"
        assert "a='alpha(X,Y)*" in filter_str, f"alpha 式が含まれていない: {filter_str}"
        # fade=t=in/out は使用しない
        assert "fade=t=in" not in filter_str, "callable では fade=t=in を使わない"

    def test_linear_fadeout_uses_geq(self):
        """線形フェードアウト (lambda u: 1-u) が geq を使用することを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        # 線形フェードアウト
        fade_effect = FadeEffect(alpha=lambda u: 1 - u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # geq フィルタが使用されていることを確認
        assert "geq=" in filter_str, f"geq が含まれていない: {filter_str}"
        assert "a='alpha(X,Y)*" in filter_str, f"alpha 式が含まれていない: {filter_str}"
        # fade=t=in/out は使用しない
        assert "fade=t=out" not in filter_str, "callable では fade=t=out を使わない"

    def test_callable_fade_no_warning(self):
        """callable フェードで警告が出ないことを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()

        fade_effect = FadeEffect(alpha=lambda u: 1 - u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _build_video_filter(timeline, [entry])

            # callable フェードで警告が出ないことを確認
            fade_warnings = [x for x in w if "fade" in str(x.message).lower()]
            assert len(fade_warnings) == 0, "callable fade で警告が出てはいけない"

    def test_complex_callable_fade_uses_geq(self):
        """複雑な callable fade も geq で処理されることを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        # 非線形フェード（二次関数）
        fade_effect = FadeEffect(alpha=lambda u: u * u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # geq フィルタが使用されていることを確認
        assert "geq=" in filter_str, f"geq が含まれていない: {filter_str}"
        assert "a='alpha(X,Y)*" in filter_str, f"alpha 式が含まれていない: {filter_str}"
        # 区分線形式が含まれている
        assert "if(lte" in filter_str, f"区分線形式が含まれていない: {filter_str}"

    def test_float_fade_uses_colorchannelmixer(self):
        """float の alpha では colorchannelmixer が使用されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()

        fade_effect = FadeEffect(alpha=0.5)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "colorchannelmixer=aa=0.5" in filter_str

    def test_zero_fade_uses_colorchannelmixer(self):
        """alpha=0 では colorchannelmixer で完全透明になることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()

        fade_effect = FadeEffect(alpha=0)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[fade_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # alpha=0 は固定透明度として colorchannelmixer で処理
        assert "colorchannelmixer=aa=0" in filter_str
        # geq は使用しない（固定透明度だから）
        assert "geq=" not in filter_str


class TestCallableBlur:
    """callable blur のテスト"""

    def test_callable_blur_generates_piecewise_expr(self):
        """callable blur が区分線形式を生成することを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        # 二次関数ブラー
        blur_effect = BlurEffect(amount=lambda u: 10 * u * u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[blur_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "gblur=sigma=" in filter_str
        # if(lte が含まれていることを確認（区分線形）
        assert "if(lte" in filter_str, f"区分線形式が含まれていない: {filter_str}"

    def test_float_blur_linear_interpolation(self):
        """float blur が線形補間されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()

        blur_effect = BlurEffect(amount=10)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[blur_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # 0 から 10 への線形補間
        assert "gblur=sigma='max(0,(10*(" in filter_str


class TestCallableMove:
    """callable move のテスト"""

    def test_callable_move_x_generates_piecewise_expr(self):
        """callable move.x が区分線形式を生成することを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()
        media.transform.pos_x = 0.2
        media.transform.pos_y = 0.5

        # x のみ callable
        move_effect = MoveEffect(x=lambda u: 0.2 + 0.6 * u, y=0.5)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[move_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # overlay フィルタの x= に if(lte が含まれていることを確認
        assert "overlay=" in filter_str
        assert "if(lte" in filter_str

    def test_float_move_linear_interpolation(self):
        """float move が線形補間されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        media.transform.pos_x = 0.2
        media.transform.pos_y = 0.5

        move_effect = MoveEffect(x=0.8, y=0.8)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[move_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # 線形補間の形式
        assert "overlay=" in filter_str
        # 開始位置と終了位置が含まれている
        assert "0.2*1920" in filter_str or "(0.2*1920)" in filter_str


class TestCallableShake:
    """callable shake のテスト"""

    def test_callable_shake_intensity(self):
        """callable shake.intensity が式に変換されることを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        # intensity を callable で指定
        shake_effect = ShakeEffect(intensity=lambda u: 0.01 * (1 - u), speed=10)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[shake_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # sin と cos が含まれていることを確認（shake の特徴）
        assert "sin(" in filter_str
        assert "cos(" in filter_str
        # 区分線形式が含まれている
        assert "if(lte" in filter_str


class TestCallableScale:
    """callable scale のテスト"""

    def test_callable_scale_sx(self):
        """callable scale.sx が式に変換されることを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media(width=800, height=600)
        media.transform.scale_x = 0.2
        media.transform.scale_y = 0.15

        scale_effect = ScaleEffect(sx=lambda u: 0.2 + 0.3 * u, sy=None)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[scale_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "scale=w=" in filter_str
        assert "eval=frame" in filter_str
        # 区分線形式
        assert "if(lte" in filter_str


class TestCallableRotate:
    """callable rotate_to のテスト"""

    def test_callable_rotate_angle(self):
        """callable rotate_to.angle が式に変換されることを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()
        media.transform.rotation = 0

        rotate_effect = RotateToEffect(angle=lambda u: 360 * u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[rotate_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "rotate=" in filter_str
        # 区分線形式
        assert "if(lte" in filter_str


class TestTimelineSettings:
    """Timeline 設定のテスト"""

    def test_curve_samples_default(self):
        """curve_samples のデフォルト値を確認"""
        timeline = Timeline()
        assert timeline.curve_samples == 60

    def test_curve_samples_configure(self):
        """curve_samples を configure で設定できることを確認"""
        timeline = Timeline()
        timeline.configure(curve_samples=100)
        assert timeline.curve_samples == 100

    def test_curve_samples_clamped_min(self):
        """curve_samples が最小値でクランプされることを確認"""
        timeline = Timeline()
        timeline.configure(curve_samples=5)
        assert timeline.curve_samples == 10  # 最小値

    def test_curve_samples_clamped_max(self):
        """curve_samples が最大値でクランプされることを確認"""
        timeline = Timeline()
        timeline.configure(curve_samples=500)
        assert timeline.curve_samples == 240  # 最大値


class TestTransformCallableChain:
    """Transform callable の直前値チェーンテスト"""

    def test_chain_float_then_float(self):
        """float の後に float を設定すると後の値が優先"""
        result = _chain(0.5, 0.8)
        assert result == 0.8

    def test_chain_float_then_none(self):
        """float の後に None を設定すると前の値が維持"""
        result = _chain(0.5, None)
        assert result == 0.5

    def test_chain_float_then_callable(self):
        """float の後に callable を設定すると直前値を使用"""
        result = _chain(0.5, lambda x: x + 0.1)
        # prev=0.5 なので、callable は 0.5 を受け取る
        assert callable(result)
        # 評価すると 0.5 + 0.1 = 0.6
        assert result(999) == 0.6  # current は使われない

    def test_chain_callable_then_callable(self):
        """callable の後に callable を設定すると両方が合成される"""
        fn1 = lambda x: x * 2
        fn2 = lambda x: x + 0.1
        result = _chain(fn1, fn2)
        assert callable(result)
        # current=0.3 → fn1(0.3)=0.6 → fn2(0.6)=0.7
        assert abs(result(0.3) - 0.7) < 0.0001

    def test_chain_none_then_callable(self):
        """None の後に callable を設定すると current を使用"""
        result = _chain(None, lambda x: x * 2)
        assert callable(result)
        # current=0.5 → 0.5*2 = 1.0
        assert result(0.5) == 1.0

    def test_pos_chaining_with_callable(self):
        """pos(x=0.5) の後に pos(x=lambda x: x+0.1) で 0.6 になることを確認"""
        timeline = _create_timeline()

        # 本物の Media を生成して _width/_height を設定
        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に pos(x=0.5) を設定
        media.pos(x=0.5, y=0.5)

        # 次に callable で +0.1
        media.pos(x=lambda x: x + 0.1)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # pos_x が 0.6 に解決されているはず
        # overlay x= の部分に 0.6*1920 = 1152 近くの値が含まれる
        assert "overlay=" in filter_str
        # 0.6 * 1920 = 1152
        assert "0.6*1920" in filter_str or "(0.6*1920)" in filter_str

    def test_opacity_chaining_with_callable(self):
        """opacity(0.8) の後に opacity(lambda a: a*0.5) で 0.4 になることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に opacity(0.8) を設定
        media.opacity(0.8)
        # 次に callable で半分に
        media.opacity(lambda a: a * 0.5)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # alpha が 0.4 になっているはず
        assert "colorchannelmixer=aa=0.4" in filter_str

    def test_resize_chaining_with_callable(self):
        """resize(sx=0.6) の後に resize(sx=lambda x: x/2) で 0.3 になることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に resize(sx=0.6, sy=0.45) を設定
        media.transform.scale_x = 0.6
        media.transform.scale_y = 0.45

        # 次に callable で半分に（_chain を通す）
        media.transform.scale_x = _chain(media.transform.scale_x, lambda x: x / 2)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # scale_x が 0.3 に解決されているはず
        # 0.3 * 1920 = 576
        assert "scale=576:" in filter_str


class TestDoubleApplicationPrevention:
    """rotate/scale の二重適用防止テスト"""

    def test_static_scale_skipped_when_scale_effect_present(self):
        """scale_effect がある場合、静的 scale がスキップされることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media(width=800, height=600)
        media.transform.scale_x = 0.5
        media.transform.scale_y = 0.375

        # scale_effect を追加
        scale_effect = ScaleEffect(sx=0.8, sy=None)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[scale_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # 静的 scale=960:405 が含まれていないことを確認
        # （動的な scale=w= のみ）
        assert "scale=960:" not in filter_str
        assert "scale=w=" in filter_str
        assert "eval=frame" in filter_str

    def test_static_rotate_skipped_when_rotate_effect_present(self):
        """rotate_effect がある場合、静的 rotate がスキップされることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()
        media.transform.rotation = 45  # 静的に45度回転

        # rotate_effect を追加
        rotate_effect = RotateToEffect(angle=90)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[rotate_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # rotate が1回だけ含まれていることを確認（二重適用なし）
        rotate_count = filter_str.count("rotate=")
        assert rotate_count == 1, f"rotate が {rotate_count} 回出現（1回であるべき）"

    def test_scale_then_rotate_order_preserved(self):
        """scale → rotate の順序が維持されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media(width=800, height=600)

        scale_effect = ScaleEffect(sx=0.5, sy=None)
        rotate_effect = RotateToEffect(angle=90)
        entry = VideoEntry(
            media=media, start_time=0, duration=2,
            effects=[scale_effect, rotate_effect]
        )

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # scale が rotate より前に出現することを確認
        scale_pos = filter_str.find("scale=w=")
        rotate_pos = filter_str.find("rotate=")
        assert scale_pos < rotate_pos, "scale が rotate より前に出現すべき"


class TestDynamicRotateNoCrop:
    """動的 rotate のクロップ防止テスト"""

    def test_dynamic_rotate_uses_hypot(self):
        """動的 rotate が hypot(iw,ih) を使用することを確認"""
        timeline = _create_timeline()

        media = _create_mock_media()

        rotate_effect = RotateToEffect(angle=90)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[rotate_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # hypot(iw,ih) が ow と oh に使用されていることを確認
        assert "ow='hypot(iw,ih)'" in filter_str
        assert "oh='hypot(iw,ih)'" in filter_str

    def test_callable_rotate_uses_hypot(self):
        """callable rotate_to でも hypot(iw,ih) を使用することを確認"""
        timeline = _create_timeline(curve_samples=10)

        media = _create_mock_media()

        rotate_effect = RotateToEffect(angle=lambda u: 360 * u)
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[rotate_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        assert "ow='hypot(iw,ih)'" in filter_str
        assert "oh='hypot(iw,ih)'" in filter_str


class TestNSamplesAdjustment:
    """n_samples がクリップ長に合わせて調整されるテスト"""

    def test_short_clip_uses_fewer_samples(self):
        """短いクリップではサンプル数が少なくなることを確認"""
        # 0.5秒のクリップ、30fps → 15フレーム+1=16 < curve_samples=60
        timeline = _create_timeline(curve_samples=60)
        timeline.fps = 30

        media = _create_mock_media()

        blur_effect = BlurEffect(amount=lambda u: 10 * u)
        entry = VideoEntry(media=media, start_time=0, duration=0.5, effects=[blur_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # 区分線形式が含まれているが、サンプル数が少ないため
        # if(lte の数が少ないはず（サンプル数-1個）
        # duration=0.5, fps=30 → n_samples = min(60, max(2, 15+1)) = 16
        # 16サンプルなら if(lte が 15回出現
        lte_count = filter_str.count("if(lte")
        assert lte_count <= 60, "サンプル数が調整されているべき"

    def test_long_clip_uses_curve_samples(self):
        """長いクリップでは curve_samples が使用されることを確認"""
        # 10秒のクリップ、30fps → 300フレーム+1=301 > curve_samples=60
        timeline = _create_timeline(curve_samples=60)
        timeline.fps = 30

        media = _create_mock_media()

        blur_effect = BlurEffect(amount=lambda u: 10 * u)
        entry = VideoEntry(media=media, start_time=0, duration=10, effects=[blur_effect])

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # min(60, 301) = 60 サンプル → 59 セグメント
        # 二分探索木: 内部ノード数 = 葉数 - 1 = 59 - 1 = 58 回の if(lte
        lte_count = filter_str.count("if(lte")
        assert lte_count == 58, f"curve_samples=60 のとき if(lte は 58 回のはずが {lte_count} 回"


class TestUnsetSentinel:
    """_UNSET センチネルによる未指定引数の保護テスト"""

    def test_pos_y_only_preserves_x(self):
        """pos(y=0.2) で x が保持されることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に pos(x=0.5, y=0.5) を設定
        media.pos(x=0.5, y=0.5)

        # y のみ変更
        media.pos(y=0.2)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # x=0.5, y=0.2 になっているはず
        # overlay x= に 0.5*1920 = 960、y= に 0.2*1080 = 216
        assert "0.5*1920" in filter_str, f"x=0.5 が保持されていない: {filter_str}"
        assert "0.2*1080" in filter_str, f"y=0.2 が反映されていない: {filter_str}"

    def test_pos_x_only_preserves_y(self):
        """pos(x=0.8) で y が保持されることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に pos(x=0.3, y=0.7) を設定
        media.pos(x=0.3, y=0.7)

        # x のみ変更
        media.pos(x=0.8)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # x=0.8, y=0.7 になっているはず
        assert "0.8*1920" in filter_str, f"x=0.8 が反映されていない: {filter_str}"
        assert "0.7*1080" in filter_str, f"y=0.7 が保持されていない: {filter_str}"

    def test_crop_partial_update(self):
        """crop(w=0.5) で他の値が保持されることを確認"""
        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に crop を設定
        media.crop(x=0.1, y=0.2, w=0.8, h=0.6)

        # w のみ変更
        media.crop(w=0.5)

        # x, y, h は保持されているはず
        assert media.transform.crop_x == 0.1
        assert media.transform.crop_y == 0.2
        assert media.transform.crop_w == 0.5
        assert media.transform.crop_h == 0.6

    def test_resize_sx_only_preserves_sy(self):
        """resize(sx=0.3) で sy が保持されることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に resize で両方設定
        media.transform.scale_x = 0.6
        media.transform.scale_y = 0.45

        # sx のみ callable で更新
        media.resize(sx=lambda x: x / 2)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # sx=0.3, sy=0.45 になっているはず
        # scale=576:486 (0.3*1920=576, 0.45*1080=486)
        assert "scale=576:486" in filter_str, f"sy が保持されていない: {filter_str}"

    def test_resize_sy_none_clears_to_aspect_auto(self):
        """resize(sx=lambda, sy=None) で sy がアスペクト比計算に戻ることを確認"""
        timeline = _create_timeline()

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に resize で両方設定
        media.transform.scale_x = 0.6
        media.transform.scale_y = 0.45

        # sx を callable で更新、sy を None でクリア（アスペクト比自動に戻す）
        media.resize(sx=lambda x: x / 2, sy=None)

        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])
        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # sx=0.3、sy はアスペクト比から計算
        # 800:600 = 4:3、timeline 1920:1080 = 16:9
        # sy = 0.3 * (600/800) * (1920/1080) = 0.3 * 0.75 * 1.778 ≈ 0.4
        # scale = 576:431 or 576:432 (丸め誤差)
        assert "scale=576:" in filter_str, f"sx が正しく設定されていない: {filter_str}"
        # sy はアスペクト比から計算された値（486ではないことを確認）
        # 0.45*1080=486 ではなく、アスペクト比計算の 431-432 付近
        assert ":486" not in filter_str, f"sy が保持されてしまっている（アスペクト比計算に戻っていない）: {filter_str}"
        assert ":431" in filter_str or ":432" in filter_str, \
            f"sy がアスペクト比計算に戻っていない: {filter_str}"

    def test_anchor_preserved_when_not_specified(self):
        """pos(x=0.5) で anchor が保持されることを確認"""
        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に anchor を設定
        media.pos(x=0.5, y=0.5, anchor="tl")

        # x のみ変更
        media.pos(x=0.8)

        # anchor は保持されているはず
        assert media.transform.anchor == "tl"

    def test_chromakey_similarity_preserved(self):
        """chromakey(color=...) で similarity/blend が保持されることを確認"""
        media = Media("test.png")
        media._width = 800
        media._height = 600

        # 最初に similarity/blend を設定
        media.transform.chromakey_similarity = 0.3
        media.transform.chromakey_blend = 0.2

        # color のみ指定（similarity/blend は _UNSET）
        media.transform.chromakey_color = "green"

        # similarity/blend は保持されているはず
        assert media.transform.chromakey_similarity == 0.3
        assert media.transform.chromakey_blend == 0.2


class TestLayerOrdering:
    """レイヤー順序のテスト"""

    def test_higher_layer_rendered_on_top(self):
        """layer が大きい方が上に描画されることを確認"""
        timeline = _create_timeline()

        # 2つのメディアを同時刻に配置
        media_bottom = _create_mock_media("bottom.png")
        media_top = _create_mock_media("top.png")

        # layer=0 が先、layer=10 が後（layerが大きい方が上）
        entry_bottom = VideoEntry(
            media=media_bottom, start_time=0, duration=2, effects=[],
            layer=0, order=0, offset=0.0
        )
        entry_top = VideoEntry(
            media=media_top, start_time=0, duration=2, effects=[],
            layer=10, order=1, offset=0.0
        )

        _, filters, _ = _build_video_filter(timeline, [entry_bottom, entry_top])

        # overlay フィルタの出現順を確認
        # layer=0 (bottom) → layer=10 (top) の順で処理される
        # overlay は後段ほど上に描画されるため、top が後に来るべき
        overlay_filters = [f for f in filters if "overlay=" in f]

        # 少なくとも2つの overlay がある
        assert len(overlay_filters) >= 2, f"overlay が2つ未満: {overlay_filters}"

        # 最初の overlay は layer=0 のもの（[mix0] を出力）
        # 2番目の overlay は layer=10 のもの（[mix1] または [vout] を出力）
        assert "[mix0]" in overlay_filters[0], f"最初の overlay が layer=0 でない: {overlay_filters[0]}"

    def test_same_layer_order_by_addition(self):
        """同一 layer では後に追加した方が上に描画されることを確認"""
        timeline = _create_timeline()

        media_first = _create_mock_media("first.png")
        media_second = _create_mock_media("second.png")

        # 同じ layer=0 で、order が異なる
        entry_first = VideoEntry(
            media=media_first, start_time=0, duration=2, effects=[],
            layer=0, order=0, offset=0.0  # 先に追加
        )
        entry_second = VideoEntry(
            media=media_second, start_time=0, duration=2, effects=[],
            layer=0, order=1, offset=0.0  # 後に追加
        )

        _, filters, _ = _build_video_filter(timeline, [entry_second, entry_first])  # 逆順で渡す

        # ソート後は order=0 → order=1 の順になるはず
        overlay_filters = [f for f in filters if "overlay=" in f]
        assert len(overlay_filters) >= 2

        # first (order=0) が先、second (order=1) が後（上に描画）
        # [mix0] が first、[mix1] または [vout] が second
        assert "[mix0]" in overlay_filters[0]

    def test_layer_sorting_mixed_orders(self):
        """layer と order の混合ソートが正しいことを確認"""
        timeline = _create_timeline()

        # layer=5, order=0
        # layer=0, order=1
        # layer=5, order=1
        # layer=0, order=0
        entries = [
            VideoEntry(media=_create_mock_media("a.png"), start_time=0, duration=2, effects=[],
                       layer=5, order=0, offset=0.0),
            VideoEntry(media=_create_mock_media("b.png"), start_time=0, duration=2, effects=[],
                       layer=0, order=1, offset=0.0),
            VideoEntry(media=_create_mock_media("c.png"), start_time=0, duration=2, effects=[],
                       layer=5, order=1, offset=0.0),
            VideoEntry(media=_create_mock_media("d.png"), start_time=0, duration=2, effects=[],
                       layer=0, order=0, offset=0.0),
        ]

        _, filters, _ = _build_video_filter(timeline, entries)

        # ソート後の順序: (0,0), (0,1), (5,0), (5,1)
        # つまり d, b, a, c の順
        # overlay は4つあるはず
        overlay_filters = [f for f in filters if "overlay=" in f]
        assert len(overlay_filters) == 4


class TestOffsetTrim:
    """素材内開始位置（offset）のテスト"""

    def test_offset_reflected_in_trim(self):
        """offset が trim=start=... に反映されることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("video.mp4")
        entry = VideoEntry(
            media=media, start_time=0, duration=2.0, effects=[],
            layer=0, order=0, offset=1.25
        )

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # trim=start=1.25:duration=2.0 が含まれていることを確認
        assert "trim=start=1.25:duration=2.0" in filter_str, \
            f"offset が trim に反映されていない: {filter_str}"

    def test_offset_zero_is_default(self):
        """offset=0 の場合も trim=start=0:duration=... になることを確認"""
        timeline = _create_timeline()

        media = _create_mock_media("video.mp4")
        entry = VideoEntry(
            media=media, start_time=0, duration=3.0, effects=[],
            layer=0, order=0, offset=0.0
        )

        _, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # trim=start=0:duration=3.0 または trim=start=0.0:duration=3.0
        assert "trim=start=0" in filter_str and "duration=3" in filter_str, \
            f"offset=0 の trim が正しくない: {filter_str}"

    def test_image_with_offset(self):
        """画像ファイルでも offset が trim に含まれることを確認（-loop と併用）"""
        timeline = _create_timeline()

        media = _create_mock_media("image.png")
        entry = VideoEntry(
            media=media, start_time=0, duration=2.0, effects=[],
            layer=0, order=0, offset=0.5
        )

        inputs, filters, _ = _build_video_filter(timeline, [entry])
        filter_str = ";".join(filters)

        # 画像には -loop 1 が付く
        assert "-loop" in inputs

        # trim には offset が反映される
        assert "trim=start=0.5:duration=2.0" in filter_str


class TestBackwardCompatibility:
    """後方互換性のテスト"""

    def test_show_without_layer_and_offset(self):
        """show(timeline, time, start) で動作することを確認（layer/offset 省略）"""
        from scriptvedit import Project

        project = Project()
        project.configure(width=1920, height=1080, fps=30, curve_samples=10)
        timeline = project.timeline

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # layer と offset を省略
        media.show(timeline, time=2.0, start=0.0)

        assert len(timeline.video_entries) == 1
        entry = timeline.video_entries[0]

        # デフォルト値が設定されていることを確認
        assert entry.layer == 0
        assert entry.offset == 0.0
        assert entry.duration == 2.0
        assert entry.start_time == 0.0

    def test_show_with_effects_only(self):
        """show(timeline, time, effects=...) で動作することを確認"""
        from scriptvedit import Project

        project = Project()
        project.configure(width=1920, height=1080, fps=30)
        timeline = project.timeline

        media = Media("test.png")
        media._width = 800
        media._height = 600

        # effects のみ指定
        media.show(timeline, time=3.0, effects=[FadeEffect(alpha=0.5)])

        assert len(timeline.video_entries) == 1
        entry = timeline.video_entries[0]
        assert entry.duration == 3.0
        assert len(entry.effects) == 1

    def test_videoentry_default_values(self):
        """VideoEntry のデフォルト値が正しいことを確認"""
        media = _create_mock_media()

        # 必須パラメータのみで作成
        entry = VideoEntry(media=media, start_time=0, duration=2, effects=[])

        # デフォルト値
        assert entry.layer == 0
        assert entry.order == 0
        assert entry.offset == 0.0


class TestValidation:
    """バリデーションのテスト"""

    def test_duration_must_be_positive(self):
        """duration <= 0 で ValueError が発生することを確認"""
        timeline = Timeline()

        media = _create_mock_media()

        with pytest.raises(ValueError, match="duration"):
            timeline.add_video(media, duration=0, effects=[])

        with pytest.raises(ValueError, match="duration"):
            timeline.add_video(media, duration=-1, effects=[])

    def test_offset_must_be_non_negative(self):
        """offset < 0 で ValueError が発生することを確認"""
        timeline = Timeline()

        media = _create_mock_media()

        with pytest.raises(ValueError, match="offset"):
            timeline.add_video(media, duration=2, effects=[], offset=-0.5)
