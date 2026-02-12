# エラーケーステスト: 各種エラー条件の自動検証
import sys, os, tempfile
sys.path.insert(0, "..")
from scriptvedit import (
    _resolve_param, Project, P, Object, VideoView, AudioView,
    again, move, fade, resize, rotate, rotate_to, morph_to, AudioEffect, AudioEffectChain,
    subtitle, subtitle_box, bubble, diagram, circle, label,
    crop, pad, blur, eq, wipe, zoom, color_shift, shake, scale,
    Transform, TransformChain, Effect, EffectChain,
    _checkpoint_cache_path, _file_fingerprint, _web_cache_path,
)


def test_math_sin_in_lambda():
    """lambda内でmath.sinを使用 → TypeErrorかつ案内メッセージ"""
    import math
    try:
        _resolve_param(lambda u: math.sin(u))
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "scriptvedit" in msg and "sin" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"


def test_undefined_anchor():
    """未定義アンカー参照 → RuntimeError"""
    layer_code = (
        'from scriptvedit import *\n'
        'pause.until("nonexistent")\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_err_undef.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp_path, priority=0)
        p.render("_tmp_err.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "nonexistent" in msg and "pause.until" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_same_anchor_different_files():
    """異ファイル間で同名アンカー定義 → RuntimeError"""
    layer1_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
        'anchor("my_anchor")\n'
    )
    layer2_code = (
        'from scriptvedit import *\n'
        'anchor("my_anchor")\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp1 = os.path.join(os.path.dirname(__file__), "_tmp_err_dup1.py")
    temp2 = os.path.join(os.path.dirname(__file__), "_tmp_err_dup2.py")
    try:
        with open(temp1, "w", encoding="utf-8") as f:
            f.write(layer1_code)
        with open(temp2, "w", encoding="utf-8") as f:
            f.write(layer2_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp1, priority=0)
        p.layer(temp2, priority=1)
        p.render("_tmp_err.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "my_anchor" in msg and "再定義は禁止" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"
    finally:
        for f in [temp1, temp2]:
            if os.path.exists(f):
                os.unlink(f)


def test_configure_typo():
    """configure()のtypo → ValueError"""
    p = Project()
    try:
        p.configure(widht=1280)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "widht" in msg and "width" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_percent_value():
    """50%P == 0.5 の確認"""
    result = 50%P
    if result == 0.5:
        return True, f"50%P = {result}"
    return False, f"50%P = {result} (期待: 0.5)"


def test_cache_invalid():
    """cache='invalid' → ValueError"""
    p = Project()
    try:
        p.layer("dummy.py", cache="invalid")
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "invalid" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_cache_use_no_file():
    """cache='use' でファイル不在 → FileNotFoundError"""
    p = Project()
    p.configure(width=320, height=240, fps=1, background_color="black")
    p.layer("nonexistent_layer.py", cache="use")
    try:
        p.render("_tmp.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except FileNotFoundError as e:
        msg = str(e)
        if "キャッシュファイルが見つかりません" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"


def test_image_length():
    """画像の length() → TypeError"""
    p = Project()
    obj = Object("../onigiri_tenmusu.png")
    try:
        obj.length()
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "画像" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_missing_file_length():
    """存在しないファイルの length() → FileNotFoundError"""
    p = Project()
    obj = Object("nonexistent_video.mp4")
    try:
        obj.length()
        return False, "例外が発生しませんでした"
    except FileNotFoundError as e:
        msg = str(e)
        if "メディアの長さを取得できません" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_view_time_forbidden():
    """VideoView.time() / AudioView.time() → TypeError"""
    p = Project()
    obj = Object("../onigiri_tenmusu.png")
    vv = VideoView(obj)
    try:
        vv.time(3)
        return False, "VideoView.time() 例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "禁止" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_view_until_forbidden():
    """VideoView.until() / AudioView.until() → TypeError"""
    p = Project()
    obj = Object("../Impact-38.mp3")
    av = AudioView(obj)
    try:
        av.until("test")
        return False, "AudioView.until() 例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "禁止" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_video_audio_effect_mismatch():
    """VideoView <= again() → TypeError"""
    p = Project()
    obj = Object("../onigiri_tenmusu.png")
    vv = VideoView(obj)
    try:
        vv <= again(0.5)
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "映像系のみ" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_audio_video_effect_mismatch():
    """AudioView <= move() → TypeError"""
    p = Project()
    obj = Object("../Impact-38.mp3")
    av = AudioView(obj)
    try:
        av <= move(x=0.5, y=0.5)
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "音声系のみ" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_web_kwargs_on_non_web():
    """画像にduration/sizeを渡す → TypeError"""
    p = Project()
    try:
        Object("../onigiri_tenmusu.png", duration=2.0, size=(640, 360))
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "web Object" in msg and ".html" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_web_unknown_kwarg():
    """HTMLに不明なkwarg → TypeError"""
    p = Project()
    try:
        Object("test.html", duration=2.0, size=(640, 360), unknown_param=True)
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "不明なキーワード引数" in msg and "unknown_param" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_web_no_duration():
    """HTMLにdurationなし → ValueError"""
    p = Project()
    try:
        Object("test.html", size=(640, 360))
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "duration" in msg and "必須" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_subtitle_no_project():
    """subtitle() でProject未設定 + size省略 → RuntimeError"""
    old = Project._current
    Project._current = None
    try:
        subtitle("テスト")
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "アクティブなProject" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"
    finally:
        Project._current = old


def test_diagram_no_project():
    """diagram() でProject未設定 + size省略 → RuntimeError"""
    old = Project._current
    Project._current = None
    try:
        diagram([circle(0.5, 0.5, 0.1)])
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "アクティブなProject" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"
    finally:
        Project._current = old


def test_subtitle_with_explicit_size():
    """subtitle() にsize明示 → Project不要で成功"""
    old = Project._current
    Project._current = None
    try:
        obj = subtitle("テスト", size=(640, 360))
        if obj.media_type == "web" and obj._web_size == (640, 360):
            return True, f"size=(640,360) で正常生成"
        return False, f"属性が不正: type={obj.media_type}, size={obj._web_size}"
    finally:
        Project._current = old


def test_neg_transform():
    """-resize() → policy='off' のTransformを返す"""
    result = -resize(sx=0.5, sy=0.5)
    if not isinstance(result, Transform):
        return False, f"型が不正: {type(result)}"
    if result.policy != "off":
        return False, f"policyが不正: {result.policy}"
    return True, f"policy={result.policy}"


def test_neg_effect():
    """-scale(0.5) → policy='off' のEffectを返す"""
    from scriptvedit import scale
    result = -scale(0.5)
    if not isinstance(result, Effect):
        return False, f"型が不正: {type(result)}"
    if result.policy != "off":
        return False, f"policyが不正: {result.policy}"
    return True, f"policy={result.policy}"


def test_chain_sugar():
    """~(tf1 | tf2) で全opがquality='fast'になる"""
    tf1 = resize(sx=0.5, sy=0.5)
    tf2 = resize(sx=0.3, sy=0.3)
    chain = tf1 | tf2
    result = ~chain
    if not isinstance(result, TransformChain):
        return False, f"型が不正: {type(result)}"
    # 全opがquality="fast"
    for i, t in enumerate(result.transforms):
        if not isinstance(t, Transform):
            return False, f"transforms[{i}]がTransformでない: {type(t)}"
        if t.quality != "fast":
            return False, f"transforms[{i}].quality={t.quality} (期待: fast)"
    return True, f"全{len(result.transforms)}opがquality=fast"


def test_force_operator():
    """+op で policy='force' 確認"""
    result = +resize(sx=0.5, sy=0.5)
    if not isinstance(result, Transform):
        return False, f"型が不正: {type(result)}"
    if result.policy != "force":
        return False, f"policyが不正: {result.policy}"
    return True, f"policy={result.policy}"


def test_off_operator():
    """-op で policy='off' 確認"""
    result = -resize(sx=0.5, sy=0.5)
    if not isinstance(result, Transform):
        return False, f"型が不正: {type(result)}"
    if result.policy != "off":
        return False, f"policyが不正: {result.policy}"
    return True, f"policy={result.policy}"


def test_fast_quality():
    """~op で quality='fast' 確認"""
    result = ~resize(sx=0.5, sy=0.5)
    if not isinstance(result, Transform):
        return False, f"型が不正: {type(result)}"
    if result.quality != "fast":
        return False, f"qualityが不正: {result.quality}"
    return True, f"quality={result.quality}"


def test_chain_force():
    """+chain で末尾policy='force' 確認"""
    tf1 = resize(sx=0.5, sy=0.5)
    tf2 = resize(sx=0.3, sy=0.3)
    chain = tf1 | tf2
    result = +chain
    if not isinstance(result, TransformChain):
        return False, f"型が不正: {type(result)}"
    last = result.transforms[-1]
    if last.policy != "force":
        return False, f"末尾policy={last.policy} (期待: force)"
    first = result.transforms[0]
    if first.policy != "auto":
        return False, f"先頭policy={first.policy} (期待: auto)"
    return True, f"末尾policy=force, 先頭policy=auto"


def test_ffp_change_detection():
    """ファイル変更でfingerprintが変わることを確認"""
    import time
    tmp = os.path.join(tempfile.gettempdir(), "_test_ffp_change.png")
    try:
        with open(tmp, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        ffp1 = _file_fingerprint(tmp)
        # わずかに待ってから内容変更
        time.sleep(0.05)
        with open(tmp, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\xFF" * 200)
        ffp2 = _file_fingerprint(tmp)
        if ffp1 == ffp2:
            return False, f"fingerprintが変わっていない: {ffp1}"
        return True, f"ffp1={ffp1[1:]}, ffp2={ffp2[1:]}"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_checkpoint_signature_uses_ffp():
    """checkpoint signatureにFFPが含まれることを確認"""
    import time
    tmp = os.path.join(tempfile.gettempdir(), "_test_cp_sig.png")
    try:
        with open(tmp, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        path1 = _checkpoint_cache_path(tmp, [])
        time.sleep(0.05)
        with open(tmp, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\xFF" * 200)
        path2 = _checkpoint_cache_path(tmp, [])
        if path1 == path2:
            return False, "ファイル変更後もキャッシュパスが同じ"
        return True, "ファイル変更でキャッシュパスが変化"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_web_deps_accepted():
    """web Objectにdeps引数が渡せることを確認"""
    old = Project._current
    try:
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        obj = subtitle("テスト", size=(320, 240), deps=["a.png", "b.png"])
        if obj._web_deps == ["a.png", "b.png"]:
            return True, f"deps={obj._web_deps}"
        return False, f"deps={obj._web_deps}"
    finally:
        Project._current = old


def test_video_no_time_checkpoint_has_duration():
    """video + transform-only + time未指定 → checkpointコマンドに-tが含まれる"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../fox_noaudio.mp4")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_vid_notime.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=1280, height=720, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        result = p.render("_tmp_vid_notime.mp4", dry_run=True)
        # resultはdict（cache付き）であるべき
        if not isinstance(result, dict):
            return False, f"dictでない: {type(result)}"
        cache = result.get("cache", {})
        if not cache:
            return False, "cacheが空"
        # cacheの各コマンドに-tが含まれ、値がNoneでないこと
        for path, cmd in cache.items():
            if not path.endswith(".webm"):
                return False, f"拡張子が.webmでない: {path}"
            if "-t" not in cmd:
                return False, f"-tがコマンドにない: {cmd}"
            t_idx = cmd.index("-t")
            t_val = cmd[t_idx + 1]
            if t_val == "None":
                return False, f"-tの値がNone"
            dur = float(t_val)
            if dur <= 0:
                return False, f"-tの値が不正: {dur}"
        return True, f"checkpoint .webm + -t={t_val}"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_video_with_time_uses_specified_duration():
    """video + time指定 → obj.time()の値がcheckpointのdurationに使われる"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../fox_noaudio.mp4")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2.5) <= move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_vid_time.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=1280, height=720, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        result = p.render("_tmp_vid_time.mp4", dry_run=True)
        if not isinstance(result, dict):
            return False, f"dictでない: {type(result)}"
        cache = result.get("cache", {})
        if not cache:
            return False, "cacheが空"
        for path, cmd in cache.items():
            if "-t" not in cmd:
                return False, f"-tがコマンドにない"
            t_idx = cmd.index("-t")
            t_val = float(cmd[t_idx + 1])
            if t_val != 2.5:
                return False, f"-tの値が2.5でない: {t_val}"
        return True, f"time指定=2.5が正しく使用される"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_morph_to_non_object():
    """morph_to に Object 以外 → TypeError"""
    p = Project()
    try:
        morph_to("not_an_object")
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "Object のみ" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_morph_to_not_last():
    """morph_to が bakeable ops の末尾でない → ValueError"""
    layer_code = (
        'from scriptvedit import *\n'
        'img1 = Object("../onigiri_tenmusu.png")\n'
        'img2 = Object("../figure_cafe.png")\n'
        'img1.time(3) <= morph_to(img2)\n'
        'img1 <= scale(0.5)\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_morph_order.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp_path, priority=0)
        p.render("_tmp_morph.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "morph_to" in msg and "末尾" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_rotate_no_args():
    """rotate() に deg/rad なし → ValueError"""
    try:
        rotate()
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "deg" in msg and "rad" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_rotate_to_no_args():
    """rotate_to() に deg/rad/from/to なし → ValueError"""
    try:
        rotate_to()
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "deg" in msg or "rad" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_rotate_to_preserves_move():
    """rotate_to(bakeable) + move(live) → checkpoint後もmoveが残る"""
    layer_code = (
        'from scriptvedit import *\n'
        'img = Object("../onigiri_tenmusu.png")\n'
        'img <= resize(sx=0.5, sy=0.5)\n'
        'img.time(2) <= rotate_to(from_deg=0, to_deg=90)\n'
        'img <= move(x=0.3, y=0.7, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_rotate_move.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp_path, priority=0)
        result = p.render("_tmp_rotate_move.mp4", dry_run=True)
        if not isinstance(result, dict):
            return False, f"dictでない: {type(result)}"
        # mainコマンドにoverlayがあること（moveが残っている）
        main_cmd = " ".join(result["main"])
        if "overlay" not in main_cmd:
            return False, "overlayがmainコマンドにない（moveが消えた）"
        return True, "rotate_to checkpoint後もmove保持"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_morph_to_hint_message():
    """morph_to末尾でないときエラーに「回避策」が含まれる"""
    layer_code = (
        'from scriptvedit import *\n'
        'img1 = Object("../onigiri_tenmusu.png")\n'
        'img2 = Object("../figure_cafe.png")\n'
        'img1.time(3) <= morph_to(img2)\n'
        'img1 <= scale(0.5)\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_morph_hint.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp_path, priority=0)
        p.render("_tmp_morph_hint.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "回避策" in msg and "除外" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージに回避策がない: {msg}"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_image_time_no_args():
    """画像に対する time() 省略は TypeError"""
    try:
        obj = Object("../onigiri_tenmusu.png")
        obj.time()
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "画像" in msg and "time()" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_probe_failure_has_audio_false():
    """probe不可時 has_audio=False"""
    old = Project._current
    try:
        Project._current = None
        obj = Object("nonexistent_media.mp4")
        result = obj.has_audio
        if result is False:
            return True, f"has_audio={result} (probe不可→False)"
        return False, f"has_audio={result} (期待: False)"
    finally:
        Project._current = old


def test_crop_no_size():
    """crop w/h未指定 → ValueError"""
    try:
        crop(x=0, y=0)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "w" in msg and "h" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_pad_no_size():
    """pad w/h未指定 → ValueError"""
    try:
        pad(x=0, y=0)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "w" in msg and "h" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_color_shift_no_args():
    """color_shift引数なし → ValueError"""
    try:
        color_shift()
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "hue" in msg or "saturation" in msg or "brightness" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_zoom_no_args():
    """zoom引数なし → ValueError"""
    try:
        zoom()
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "value" in msg or "to_value" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def _filter_found_in_cache(cmd_result, filter_str):
    """dry_run結果のcacheコマンドに指定フィルタ文字列が含まれるか検証"""
    if not isinstance(cmd_result, dict):
        return False, f"dictでない: {type(cmd_result)}"
    cache_cmds = cmd_result.get("cache", {})
    if not cache_cmds:
        return False, "cacheが空"
    for path, cmd in cache_cmds.items():
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if filter_str in cmd_str:
            return True, f"'{filter_str}' found"
    return False, f"'{filter_str}' NOT found in any cache cmd"


def _make_image_checkpoint_project(transforms_code, effects_code=""):
    """画像+Transform/Effect→dry_run結果を返すヘルパー"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        f'obj <= {transforms_code}\n'
        f'obj.time(1) <= move(x=0.5, y=0.5, anchor="center"){" & " + effects_code if effects_code else ""}\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_filter_test.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        return p.render("_tmp_filter.mp4", dry_run=True)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_crop_filter_in_checkpoint():
    """crop Transformがcheckpointのfiltergraphに出ること"""
    cmd = _make_image_checkpoint_project('crop(x=10, y=10, w=200, h=150)')
    return _filter_found_in_cache(cmd, "crop=200:150:10:10")


def test_pad_filter_in_checkpoint():
    """pad Transformがcheckpointのfiltergraphに出ること"""
    cmd = _make_image_checkpoint_project('pad(w=640, h=480)')
    return _filter_found_in_cache(cmd, "pad=640:480:")


def test_blur_filter_in_checkpoint():
    """blur Transformがcheckpointのfiltergraphに出ること"""
    cmd = _make_image_checkpoint_project('blur(radius=10)')
    return _filter_found_in_cache(cmd, "boxblur=10:10")


def test_eq_filter_in_checkpoint():
    """eq Transformがcheckpointのfiltergraphに出ること"""
    cmd = _make_image_checkpoint_project('eq(brightness=0.2, contrast=1.2)')
    return _filter_found_in_cache(cmd, "eq=brightness=0.2:contrast=1.2")


def test_wipe_filter_in_checkpoint():
    """wipe Effectがcheckpointのfiltergraphに出ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= wipe("left") & move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_wipe_test.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_wipe.mp4", dry_run=True)
        ok1, msg1 = _filter_found_in_cache(cmd, "geq=")
        if not ok1:
            return ok1, msg1
        return _filter_found_in_cache(cmd, "lte(X")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_zoom_filter_in_checkpoint():
    """zoom(scale) Effectがcheckpointのfiltergraphに出ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= zoom(lambda u: lerp(1, 2, u)) & move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_zoom_test.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_zoom.mp4", dry_run=True)
        ok1, msg1 = _filter_found_in_cache(cmd, "scale=w=")
        if not ok1:
            return ok1, msg1
        return _filter_found_in_cache(cmd, "eval=frame")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_color_shift_filter_in_checkpoint():
    """color_shift Effectがcheckpointのfiltergraphに出ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= color_shift(hue=90) & move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_cshift_test.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_cshift.mp4", dry_run=True)
        return _filter_found_in_cache(cmd, "hue=h=")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_rotate_to_filter_in_checkpoint():
    """rotate_to Effectがcheckpointのfiltergraphに出ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= rotate_to(from_deg=0, to_deg=90) & move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_rotto_test.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_rotto.mp4", dry_run=True)
        return _filter_found_in_cache(cmd, "rotate=angle=")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_move_survives_bakeable_checkpoint():
    """move(live) + wipe(bakeable) でcheckpoint後もmoveがoverlayに残ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= wipe("left") & move(from_x=0.2, from_y=0.5, to_x=0.8, to_y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_move_surv.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_move_surv.mp4", dry_run=True)
        if not isinstance(cmd, dict):
            return False, f"dictでない: {type(cmd)}"
        main_str = " ".join(cmd["main"])
        has_move = "0.2" in main_str and "0.8" in main_str
        if has_move:
            return True, "move preserved after bakeable checkpoint"
        return False, "move lost after checkpoint"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_shake_is_live():
    """shake(live)がcheckpointに焼かれずoverlayに残ること"""
    layer_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj <= resize(sx=0.5, sy=0.5)\n'
        'obj.time(2) <= shake(amplitude=0.05, frequency=8) & move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_shake_live.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        p.layer(temp_path, priority=0)
        cmd = p.render("_tmp_shake_live.mp4", dry_run=True)
        if isinstance(cmd, dict):
            main_str = " ".join(cmd["main"])
        else:
            main_str = " ".join(cmd)
        has_shake = "sin(" in main_str and "cos(" in main_str
        if has_shake:
            return True, "shake in overlay"
        return False, "shake NOT in overlay"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_web_deps_invalidation():
    """depsファイルのmtime変更でweb cache pathが変わること"""
    import time as _time
    with tempfile.NamedTemporaryFile(suffix=".css", delete=False, mode="w") as f:
        f.write("body{}")
        dep_path = f.name
    old = Project._current
    try:
        p = Project()
        p.configure(width=640, height=360, fps=30, background_color="black")
        obj1 = subtitle_box("test", deps=[dep_path])
        path1 = _web_cache_path(obj1, p)
        # mtimeを変更
        _time.sleep(0.05)
        os.utime(dep_path, None)
        obj2 = subtitle_box("test", deps=[dep_path])
        path2 = _web_cache_path(obj2, p)
        Project._current = old
        if path1 != path2:
            return True, f"cache path changed on dep touch"
        return False, f"cache path unchanged: {path1}"
    finally:
        os.unlink(dep_path)
        Project._current = old


ALL_TESTS = [
    ("math.sin in lambda", test_math_sin_in_lambda),
    ("未定義アンカー参照", test_undefined_anchor),
    ("同名アンカー異ファイル", test_same_anchor_different_files),
    ("configure typo", test_configure_typo),
    ("50%P == 0.5", test_percent_value),
    ("cache='invalid'", test_cache_invalid),
    ("cache='use' ファイル不在", test_cache_use_no_file),
    ("画像のlength()", test_image_length),
    ("存在しないファイルのlength()", test_missing_file_length),
    ("VideoView.time()禁止", test_view_time_forbidden),
    ("AudioView.until()禁止", test_view_until_forbidden),
    ("VideoView<=音声エフェクト", test_video_audio_effect_mismatch),
    ("AudioView<=映像エフェクト", test_audio_video_effect_mismatch),
    ("非webにkwargs", test_web_kwargs_on_non_web),
    ("web不明kwarg", test_web_unknown_kwarg),
    ("web duration未指定", test_web_no_duration),
    ("subtitle Project未設定", test_subtitle_no_project),
    ("diagram Project未設定", test_diagram_no_project),
    ("subtitle size明示", test_subtitle_with_explicit_size),
    ("-Transform", test_neg_transform),
    ("-Effect", test_neg_effect),
    ("~chain糖衣", test_chain_sugar),
    ("+force演算子", test_force_operator),
    ("-off演算子", test_off_operator),
    ("~fast品質", test_fast_quality),
    ("+chain force", test_chain_force),
    ("FFP変化検出", test_ffp_change_detection),
    ("checkpoint FFP署名", test_checkpoint_signature_uses_ffp),
    ("web deps引数", test_web_deps_accepted),
    ("video time未指定checkpoint", test_video_no_time_checkpoint_has_duration),
    ("video time指定checkpoint", test_video_with_time_uses_specified_duration),
    ("morph_to非Object", test_morph_to_non_object),
    ("morph_to末尾でない", test_morph_to_not_last),
    ("rotate引数なし", test_rotate_no_args),
    ("rotate_to引数なし", test_rotate_to_no_args),
    ("rotate_to move保持", test_rotate_to_preserves_move),
    ("morph_to回避策メッセージ", test_morph_to_hint_message),
    ("probe不可has_audio=False", test_probe_failure_has_audio_false),
    ("画像time()省略", test_image_time_no_args),
    ("crop w/h未指定", test_crop_no_size),
    ("pad w/h未指定", test_pad_no_size),
    ("color_shift引数なし", test_color_shift_no_args),
    ("zoom引数なし", test_zoom_no_args),
    ("crop filter in checkpoint", test_crop_filter_in_checkpoint),
    ("pad filter in checkpoint", test_pad_filter_in_checkpoint),
    ("blur filter in checkpoint", test_blur_filter_in_checkpoint),
    ("eq filter in checkpoint", test_eq_filter_in_checkpoint),
    ("wipe filter in checkpoint", test_wipe_filter_in_checkpoint),
    ("zoom filter in checkpoint", test_zoom_filter_in_checkpoint),
    ("color_shift filter in checkpoint", test_color_shift_filter_in_checkpoint),
    ("rotate_to filter in checkpoint", test_rotate_to_filter_in_checkpoint),
    ("move survives bakeable", test_move_survives_bakeable_checkpoint),
    ("shake is live", test_shake_is_live),
    ("web deps invalidation", test_web_deps_invalidation),
]


if __name__ == "__main__":
    print("エラーケーステスト")
    passed = 0
    failed = 0
    for name, fn in ALL_TESTS:
        ok, msg = fn()
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status} - {msg[:80]}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n結果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
