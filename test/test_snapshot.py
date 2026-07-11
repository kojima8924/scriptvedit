# スナップショットテスト: dry_runで生成したffmpegコマンドをスナップショットと比較
import sys, os, json, shutil
sys.path.insert(0, "..")
from scriptvedit import *

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")


def normalize_cmd(cmd):
    """コマンドリスト/辞書をOS非依存に正規化"""
    if isinstance(cmd, dict):
        result = {}
        for k, v in cmd.items():
            nk = k.replace("\\", "/") if isinstance(k, str) else k
            result[nk] = normalize_cmd(v)
        return result
    if isinstance(cmd, list):
        return [c.replace("\\", "/") for c in cmd]
    return cmd


def load_snapshot(name):
    path = os.path.join(SNAPSHOT_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(name, cmd):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cmd, f, indent=2, ensure_ascii=False)


def run_test(name, setup_fn, update=False):
    """スナップショットテストを実行。update=Trueならスナップショットを更新"""
    cmd = normalize_cmd(setup_fn())
    expected = load_snapshot(name)
    if expected is None or update:
        save_snapshot(name, cmd)
        print(f"  {name}: スナップショット{'更新' if expected else '作成'}")
        return True
    if cmd != expected:
        print(f"  {name}: 不一致!")
        for i, (a, b) in enumerate(zip(cmd, expected)):
            if a != b:
                print(f"    [{i}] 期待: {b}")
                print(f"    [{i}] 実際: {a}")
        if len(cmd) != len(expected):
            print(f"    長さ: 期待={len(expected)}, 実際={len(cmd)}")
        return False
    print(f"  {name}: OK")
    return True


# --- テスト定義 ---

def setup_test01():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkred")
    p.layer("test01_bg.py", priority=0)
    p.layer("test01_oni.py", priority=1)
    return p.render("test01.mp4", dry_run=True)

def setup_test02():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test02_maku.py", priority=0)
    p.layer("test02_cafe.py", priority=1)
    return p.render("test02.mp4", dry_run=True)

def setup_test03():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test03_bg.py", priority=0)
    p.layer("test03_oni.py", priority=1)
    p.layer("test03_virus.py", priority=2)
    return p.render("test03.mp4", dry_run=True)

def setup_test04():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="white")
    p.layer("test04_maku.py", priority=0)
    p.layer("test04_cache_layer.py", priority=1)
    return p.render("test04.mp4", dry_run=True)

def setup_test05():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="green")
    p.layer("test05_bg.py", priority=0)
    p.layer("test05_pop.py", priority=1)
    return p.render("test05.mp4", dry_run=True)

def setup_test06():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="olive")
    p.layer("test06_oni.py", priority=0)
    return p.render("test06.mp4", dry_run=True)

def setup_test07():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="navy")
    p.layer("test07_oni.py", priority=0)
    p.layer("test07_cafe.py", priority=1)
    p.layer("test07_virus.py", priority=2)
    return p.render("test07.mp4", dry_run=True)

def setup_test08():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test08_bg.py", priority=0)
    p.layer("test08_pop.py", priority=1)
    return p.render("test08.mp4", dry_run=True)

def setup_test09():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test09_oni.py", priority=0)
    p.layer("test09_cafe.py", priority=1)
    p.layer("test09_virus.py", priority=2)
    p.layer("test09_pop.py", priority=3)
    return p.render("test09.mp4", dry_run=True)

def setup_test10():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="purple")
    p.layer("test10_maku.py", priority=0)
    p.layer("test10_cache_layer.py", priority=1)
    return p.render("test10.mp4", dry_run=True)

def setup_test11():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test11_maku.py", priority=0)
    p.layer("test11_oni.py", priority=1)
    return p.render("test11.mp4", dry_run=True)

def setup_test12():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test12_sin_fade.py", priority=0)
    p.layer("test12_lambda_scale.py", priority=1)
    p.layer("test12_lambda_move.py", priority=2)
    return p.render("test12.mp4", dry_run=True)


def setup_test13():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test13_percent.py", priority=0)
    return p.render("test13.mp4", dry_run=True)

def setup_test14():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test14_maku.py", priority=0, cache="make")
    p.layer("test14_oni.py", priority=1)
    result = p.render("test14.mp4", dry_run=True)
    return result

def setup_test15():
    """cache='use' テスト: ダミーキャッシュからの読み込み"""
    from scriptvedit import _layer_cache_paths
    # まずProjectを作って正しいキャッシュパスを計算
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    dummy_webm, dummy_json = _layer_cache_paths("test14_maku.py", p)
    os.makedirs(os.path.dirname(dummy_webm), exist_ok=True)
    # ダミーwebmファイル（空でよい、dry_runなので実行されない）
    with open(dummy_webm, "wb") as f:
        f.write(b"\x00")
    # anchors.json
    with open(dummy_json, "w", encoding="utf-8") as f:
        json.dump({"duration": 3.0, "anchors": {"curtain_done": 3.0}}, f)
    try:
        p2 = Project()
        p2.configure(width=1280, height=720, fps=30, background_color="darkblue")
        p2.layer("test14_maku.py", priority=0, cache="use")
        p2.layer("test14_oni.py", priority=1)
        return p2.render("test15.mp4", dry_run=True)
    finally:
        # ダミーファイル削除
        if os.path.exists(dummy_webm):
            os.unlink(dummy_webm)
        if os.path.exists(dummy_json):
            os.unlink(dummy_json)
        # クリーンアップ
        parent = os.path.dirname(dummy_webm)
        if os.path.exists(parent) and not os.listdir(parent):
            os.rmdir(parent)


def setup_test16():
    """音声ミックステスト: BGM(mp3) + 画像+SE"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test16_bgm.py", priority=0)
    p.layer("test16_oni.py", priority=1)
    return p.render("test16.mp4", dry_run=True)

def setup_test17():
    """AV splitテスト: 音声なし動画 + 音声のみ"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test17_video_split.py", priority=0)
    p.layer("test17_audio.py", priority=1)
    return p.render("test17.mp4", dry_run=True)

def setup_test18():
    """length()テスト: ffprobeで取得した長さを使用"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test18_length.py", priority=0)
    return p.render("test18.mp4", dry_run=True)


def setup_test19():
    """webクリップテスト: HTML→透明webm→合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test19_web.py", priority=0)
    return p.render("test19.mp4", dry_run=True)


def setup_test20():
    """字幕/吹き出しテスト: subtitle+bubble+背景合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test20_bg.py", priority=0)
    p.layer("test20_subtitles.py", priority=1)
    p.layer("test20_bubble.py", priority=2)
    return p.render("test20.mp4", dry_run=True)


def setup_test21():
    """図解テスト: diagram SVG図形+from/toアニメ+画像合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test21_diagram.py", priority=0)
    p.layer("test21_overlay.py", priority=1)
    return p.render("test21.mp4", dry_run=True)


def setup_test22():
    """チェックポイントキャッシュテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test22_checkpoint.py", priority=0)
    return p.render("test22.mp4", dry_run=True)


def setup_test23():
    """move保存テスト: resize(force) + move + scaleでmoveが消えないことを確認"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test23_move_preserve.py", priority=0)
    return p.render("test23.mp4", dry_run=True)


def setup_test24():
    """video checkpointテスト: 動画のtransform-only → .webm拡張子"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test24_video_checkpoint.py", priority=0)
    return p.render("test24.mp4", dry_run=True)


def setup_test25():
    """time()省略 → auto duration（加工後長: trim(3)反映で duration=3）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test25_video_no_time.py", priority=0)
    return p.render("test25.mp4", dry_run=True)


def setup_test26():
    """morph_toテスト: 画像→画像のモーフィング"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test26_morph.py", priority=0)
    return p.render("test26.mp4", dry_run=True)


def setup_test27():
    """rotate Transformテスト: 画像を30度回転（静的）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test27_rotate.py", priority=0)
    return p.render("test27.mp4", dry_run=True)


def setup_test28():
    """rotate_to Effectテスト: 0→180度回転アニメーション + move保持"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test28_rotate_to.py", priority=0)
    return p.render("test28.mp4", dry_run=True)


def setup_test29():
    """web + bakeable (scale/fade) テスト: web変換後にcheckpointが正しく動作"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test29_web_bakeable.py", priority=0)
    return p.render("test29.mp4", dry_run=True)


def setup_test30():
    """sin scale中間最大padテスト: 11点サンプリングで正しいpadサイズ"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test30_sin_scale.py", priority=0)
    return p.render("test30.mp4", dry_run=True)


def setup_test31():
    """crop Transformテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test31_crop.py", priority=0)
    return p.render("test31.mp4", dry_run=True)


def setup_test32():
    """pad Transformテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test32_pad.py", priority=0)
    return p.render("test32.mp4", dry_run=True)


def setup_test33():
    """blur Transformテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test33_blur.py", priority=0)
    return p.render("test33.mp4", dry_run=True)


def setup_test34():
    """eq Transformテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test34_eq.py", priority=0)
    return p.render("test34.mp4", dry_run=True)


def setup_test35():
    """wipe Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test35_wipe.py", priority=0)
    return p.render("test35.mp4", dry_run=True)


def setup_test36():
    """zoom Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test36_zoom.py", priority=0)
    return p.render("test36.mp4", dry_run=True)


def setup_test37():
    """color_shift Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test37_color_shift.py", priority=0)
    return p.render("test37.mp4", dry_run=True)


def setup_test38():
    """subtitle_box Webテンプレートテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test38_subtitle_box.py", priority=0)
    return p.render("test38.mp4", dry_run=True)


def setup_test39():
    """chroma_key Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test39_chroma_key.py", priority=0)
    return p.render("test39.mp4", dry_run=True)


def setup_test40():
    """vignette Effectテスト（strength=Expr → eval=frame）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test40_vignette.py", priority=0)
    return p.render("test40.mp4", dry_run=True)


def setup_test41():
    """pixelize Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test41_pixelize.py", priority=0)
    return p.render("test41.mp4", dry_run=True)


def setup_test42():
    """glow Effectテスト（split→gblur→blend=screen）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test42_glow.py", priority=0)
    return p.render("test42.mp4", dry_run=True)


def setup_test43():
    """lut Effectテスト（lut3d + LUTファイル）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test43_lut.py", priority=0)
    return p.render("test43.mp4", dry_run=True)


def setup_test44():
    """glitch Effectテスト（rgbashift+noise、間欠enable）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test44_glitch.py", priority=0)
    return p.render("test44.mp4", dry_run=True)


def setup_test45():
    """perspective_warp Effectテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test45_perspective.py", priority=0)
    return p.render("test45.mp4", dry_run=True)


def setup_test46():
    """lens Effectテスト（lenscorrection）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test46_lens.py", priority=0)
    return p.render("test46.mp4", dry_run=True)


def setup_test47():
    """ken_burns Effectテスト（動的scale+crop）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test47_ken_burns.py", priority=0)
    return p.render("test47.mp4", dry_run=True)


def setup_test48():
    """drop_shadow Effectテスト（split→色付け+gblur→overlay）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test48_drop_shadow.py", priority=0)
    return p.render("test48.mp4", dry_run=True)


def setup_test49():
    """outline Effectテスト（dilationベースの縁取り）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test49_outline.py", priority=0)
    return p.render("test49.mp4", dry_run=True)


def setup_test50():
    """slideshowテスト（xfade連結の合成Object）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test50_slideshow.py", priority=0)
    return p.render("test50.mp4", dry_run=True)


def setup_test51():
    """transitionテスト（2Objectのxfade合成）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test51_transition.py", priority=0)
    return p.render("test51.mp4", dry_run=True)


def setup_test52():
    """text Effect: drawtextエスケープ + x/y/size/alphaアニメ + box"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test52_text.py", priority=0)
    return p.render("test52.mp4", dry_run=True)


def setup_test53():
    """typewriter: 1文字ずつdrawtext + enable"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test53_typewriter.py", priority=0)
    return p.render("test53.mp4", dry_run=True)


def setup_test54():
    """counter: %{eif}数値カウントアップ + format"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test54_counter.py", priority=0)
    return p.render("test54.mp4", dry_run=True)


def setup_test55():
    """subtitles: SRT字幕 + force_style"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test55_subtitles.py", priority=0)
    return p.render("test55.mp4", dry_run=True)


def setup_test56():
    """audio_viz: showwaves可視化（キャッシュ生成物）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test56_audio_viz.py", priority=0)
    return p.render("test56.mp4", dry_run=True)


def setup_test57():
    """audio_sequence + sfx（キャッシュ生成物） + normalize_audio(loudnorm)"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.normalize_audio(-14)
    p.layer("test57_audio_bake.py", priority=0)
    return p.render("test57.mp4", dry_run=True)


def setup_test58():
    """loop(aloop) + duck_under(sidechaincompress)"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test58_audio_fx.py", priority=0)
    return p.render("test58.mp4", dry_run=True)


def setup_test59():
    """move_along / path_bezier / throw / look_at のパスアニメ"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test59_paths.py", priority=0)
    return p.render("test59.mp4", dry_run=True)


def setup_test60():
    """explode_to: 粒子飛散（morph同機構でmkvキャッシュ生成物）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test60_explode.py", priority=0)
    return p.render("test60.mp4", dry_run=True)


def setup_test61():
    """assemble_from: 粒子集合（source消費+mkvキャッシュ生成物）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test61_assemble.py", priority=0)
    return p.render("test61.mp4", dry_run=True)


def setup_test62():
    """group（一括適用）+ grid/tile（グリッド複製）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test62_group_grid.py", priority=0)
    return p.render("test62.mp4", dry_run=True)


def setup_test63():
    """scene: シーンの順次配置（シーン相対時刻）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test63_scene.py", priority=0)
    return p.render("test63.mp4", dry_run=True)


def setup_test64():
    """perlin ノイズによる手ブレ風 move"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test64_perlin.py", priority=0)
    return p.render("test64.mp4", dry_run=True)


def setup_test65():
    """marker + チャプター（FFMETADATA埋め込み）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.marker(0, "イントロ")
    p.marker(2.0, "本編")
    p.marker(4.5, "まとめ")
    p.layer("test65_chapters.py", priority=0)
    return p.render("test65.mp4", dry_run=True)


def setup_test66():
    """部分レンダ（時間窓 start=1.5, end=4.0）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test66_window.py", priority=0)
    return p.render("test66.mp4", dry_run=True, start=1.5, end=4.0)


def setup_test67():
    """GIF出力（palettegen/paletteuse を1グラフで実行、音声なし）"""
    p = Project()
    p.configure(width=640, height=360, fps=15, background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test67.gif", dry_run=True)


def setup_test68():
    """ドラフトレンダ（解像度半分・ultrafast・crf28）"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test68.mp4", dry_run=True, draft=True)


def setup_test69():
    """プリセット square（1080x1080）"""
    p = Project()
    p.configure(preset="square", background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test69.mp4", dry_run=True)


def setup_test70():
    """透過webm出力（libvpx-vp9 yuva420p + 透明背景）"""
    p = Project()
    p.configure(width=640, height=360, fps=30, background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test70.webm", dry_run=True, alpha=True)


def setup_test71():
    """連番PNG出力（out_%05d.png / png rgba）"""
    p = Project()
    p.configure(width=640, height=360, fps=15, background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test71.png", dry_run=True)


def setup_test72():
    """アニメーションWebP出力"""
    p = Project()
    p.configure(width=640, height=360, fps=15, background_color="black")
    p.layer("test67_layer.py", priority=0)
    return p.render("test72.webp", dry_run=True)


def setup_test73():
    """プリセット + 個別上書き（shorts の後に fps=24 で上書き）"""
    p = Project()
    p.configure(preset="shorts", fps=24, background_color="navy")
    p.layer("test67_layer.py", priority=0)
    return p.render("test73.mp4", dry_run=True)


ALL_TESTS = [
    ("test01", setup_test01),
    ("test02", setup_test02),
    ("test03", setup_test03),
    ("test04", setup_test04),
    ("test05", setup_test05),
    ("test06", setup_test06),
    ("test07", setup_test07),
    ("test08", setup_test08),
    ("test09", setup_test09),
    ("test10", setup_test10),
    ("test11", setup_test11),
    ("test12", setup_test12),
    ("test13", setup_test13),
    ("test14", setup_test14),
    ("test15", setup_test15),
    ("test16", setup_test16),
    ("test17", setup_test17),
    ("test18", setup_test18),
    ("test19", setup_test19),
    ("test20", setup_test20),
    ("test21", setup_test21),
    ("test22", setup_test22),
    ("test23", setup_test23),
    ("test24", setup_test24),
    ("test25", setup_test25),
    ("test26", setup_test26),
    ("test27", setup_test27),
    ("test28", setup_test28),
    ("test29", setup_test29),
    ("test30", setup_test30),
    ("test31", setup_test31),
    ("test32", setup_test32),
    ("test33", setup_test33),
    ("test34", setup_test34),
    ("test35", setup_test35),
    ("test36", setup_test36),
    ("test37", setup_test37),
    ("test38", setup_test38),
    ("test39", setup_test39),
    ("test40", setup_test40),
    ("test41", setup_test41),
    ("test42", setup_test42),
    ("test43", setup_test43),
    ("test44", setup_test44),
    ("test45", setup_test45),
    ("test46", setup_test46),
    ("test47", setup_test47),
    ("test48", setup_test48),
    ("test49", setup_test49),
    ("test50", setup_test50),
    ("test51", setup_test51),
    ("test52", setup_test52),
    ("test53", setup_test53),
    ("test54", setup_test54),
    ("test55", setup_test55),
    ("test56", setup_test56),
    ("test57", setup_test57),
    ("test58", setup_test58),
    ("test59", setup_test59),
    ("test60", setup_test60),
    ("test61", setup_test61),
    ("test62", setup_test62),
    ("test63", setup_test63),
    ("test64", setup_test64),
    ("test65", setup_test65),
    ("test66", setup_test66),
    ("test67", setup_test67),
    ("test68", setup_test68),
    ("test69", setup_test69),
    ("test70", setup_test70),
    ("test71", setup_test71),
    ("test72", setup_test72),
    ("test73", setup_test73),
]


if __name__ == "__main__":
    update = "--update" in sys.argv
    print("スナップショットテスト" + (" (更新モード)" if update else ""))
    passed = 0
    failed = 0
    for name, fn in ALL_TESTS:
        if run_test(name, fn, update=update):
            passed += 1
        else:
            failed += 1
    print(f"\n結果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
