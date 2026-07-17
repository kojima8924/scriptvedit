# -*- coding: utf-8 -*-
"""静的レビュー(issue #2)で見つかった asset/Web/cache/CLI の堅牢性テスト

対象:
  1. asset() のパストラバーサル拒否（..・絶対パス・ドライブレター）
  2. Web Object の短尺 duration（0フレーム化の防止）
  3. Web frames_dir の stale フレーム掃除
  4. キャッシュ生成一時パスのユニーク化（並列衝突防止）
  6. cache --clear/--gc の任意ディレクトリ削除ガード
  7. scriptvedit new --force の既存ファイル .bak 退避
"""
import os
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit.assets import asset  # noqa: E402
from scriptvedit.cache import cache_clear, cache_gc  # noqa: E402
from scriptvedit.cli import _main  # noqa: E402
from scriptvedit.ffmpeg import _run_ffmpeg_to_cache, _unique_tmp_path  # noqa: E402
from scriptvedit.filters.video import (  # noqa: E402
    _build_effect_filters, _try_native_fade,
)
from scriptvedit.objects import _web_frame_count  # noqa: E402
from scriptvedit.scaffold import new_project  # noqa: E402


# --- issue #9: native fade の線形判定 -------------------------------------

def test_native_fade_rejects_step_window():
    """矩形窓はランプへ近似せず、正確なgeq経路へフォールバックする"""
    from scriptvedit import Var, and_, gt, lt

    u = Var("u")
    alpha = and_(gt(u, 0.25), lt(u, 0.75))
    assert _try_native_fade(alpha, 0, 4) is None


def test_native_fade_keeps_linear_triangle():
    """真の区分線形ランプは従来どおりnative fadeを使う"""
    from scriptvedit import fade

    effect = fade(lambda u: 1 - abs(2 * u - 1))
    assert _try_native_fade(effect.params["alpha"], 0, 4) == [
        "fade=t=in:st=0:d=2.0:alpha=1",
        "fade=t=out:st=2.0:d=2.0:alpha=1",
    ]


def test_step_window_fade_real_render_has_no_alpha_leak(tmp_path):
    """実レンダ後の抽出フレームで矩形窓外のalphaが0になる"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg が無い環境")

    from scriptvedit import Var, and_, fade, gt, lt

    u = Var("u")
    effect = fade(lambda _u: and_(gt(u, 0.25), lt(u, 0.75)))
    obj = SimpleNamespace(effects=[effect])
    filters, _ = _build_effect_filters(obj, 0, 4)
    assert any(part.startswith("geq=") for part in filters)
    assert not any(part.startswith("fade=t=") for part in filters)

    rendered = tmp_path / "step-window.mkv"
    render_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=white:s=4x4:r=100:d=4",
        "-vf", ",".join(filters),
        "-c:v", "ffv1", "-pix_fmt", "yuva444p", str(rendered),
    ]
    subprocess.run(render_cmd, check=True, capture_output=True, timeout=30)

    def _alpha_at(u_value):
        extract_cmd = [
            "ffmpeg", "-v", "error", "-i", str(rendered),
            "-ss", str(u_value * 4), "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
        ]
        result = subprocess.run(
            extract_cmd, check=True, capture_output=True, timeout=30)
        assert len(result.stdout) == 4 * 4 * 4
        return result.stdout[3]

    assert [_alpha_at(u) for u in (0.10, 0.25, 0.75, 0.90)] == [0] * 4
    assert [_alpha_at(u) for u in (0.26, 0.50, 0.74)] == [255] * 3


# --- issue #13 P1-2: 音声のみプロジェクトの -map [0:v] --------------------

def _write_audio_only_layer(tmp_path, wav_path):
    layer = tmp_path / "audio_only_layer.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{wav_path}\")\n"
        "o.time(1) <= again(0.5)\n",
        encoding="utf-8")
    return layer


def test_audio_only_project_maps_raw_video_input(tmp_path):
    """音声Object+音声フィルタのみでも -map がグラフラベル扱いにならない"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg が無い環境")
    from scriptvedit import Project

    wav = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(wav)],
        check=True, capture_output=True, timeout=30)

    layer = _write_audio_only_layer(tmp_path, wav)
    p = Project()
    p.configure(width=320, height=180, fps=30)
    p.layer(str(layer))
    result = p.render(str(tmp_path / "out.mp4"), dry_run=True)
    cmd = result["main"] if isinstance(result, dict) else result
    assert "-filter_complex" in cmd, "音声フィルタでfilter_complexが作られる前提"
    map_targets = [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a == "-map"]
    assert "0:v" in map_targets, f"-map の対象が不正: {map_targets}"
    assert "[0:v]" not in map_targets, "生入力参照をグラフ出力ラベルとして-mapしている"


def test_audio_only_project_real_render(tmp_path):
    """音声のみプロジェクトの実レンダが成功し、映像+音声の両streamを持つ"""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe が無い環境")
    from scriptvedit import Project

    wav = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(wav)],
        check=True, capture_output=True, timeout=30)

    layer = _write_audio_only_layer(tmp_path, wav)
    out = tmp_path / "out.mp4"
    p = Project()
    p.configure(width=320, height=180, fps=30)
    p.layer(str(layer))
    p.render(str(out), timeout=120)

    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(out)],
        check=True, capture_output=True, text=True, timeout=30)
    kinds = sorted(probe.stdout.split())
    assert kinds == ["audio", "video"], f"stream構成が不正: {kinds}"


# --- issue #13 P1-3: レイヤーキャッシュ再利用時のalpha保持 -----------------

def test_layer_cache_paths_use_webm_extension():
    """レイヤーキャッシュはVP9+alphaのため.webm（デコーダ強制が効く拡張子）"""
    from scriptvedit import Project
    from scriptvedit.cache import _layer_cache_paths

    p = Project()
    video_path, json_path = _layer_cache_paths(__file__, p)
    assert video_path.endswith(".webm"), video_path
    assert json_path.endswith(".anchors.json"), json_path


def test_layer_cache_make_use_preserves_alpha(tmp_path):
    """cache='make'→'use' の往復で透過が保持され、背景色が透けて見える"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg が無い環境")
    from scriptvedit import Project
    from scriptvedit.cache import _layer_cache_paths

    # 中央に置く小さな赤画像（周囲はキャンバスの透過部分になる）
    png = tmp_path / "red.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=red:s=40x40:d=1", "-frames:v", "1", str(png)],
        check=True, capture_output=True, timeout=30)

    layer = tmp_path / "cached_layer.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{png}\")\n"
        "o.time(1) <= move(x=0.5, y=0.5, anchor=\"center\")\n",
        encoding="utf-8")

    def _render(cache_mode, out_name):
        p = Project()
        p.configure(width=160, height=90, fps=30, background_color="blue")
        p.layer(str(layer), cache=cache_mode)
        out = tmp_path / out_name
        p.render(str(out), timeout=120)
        return p, out

    p1, _ = _render("make", "out_make.mp4")
    cache_video, _ = _layer_cache_paths(str(layer), p1)
    assert os.path.exists(cache_video), "レイヤーキャッシュが生成されていない"
    try:
        _, out2 = _render("use", "out_use.mp4")

        # 左上隅（透過部分）のピクセル: alphaが保持されていれば背景の青、
        # alphaが落ちるとキャッシュの黒ベタが背景を覆う
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(out2),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            check=True, capture_output=True, timeout=30)
        r, g, b = result.stdout[0], result.stdout[1], result.stdout[2]
        assert b > 128 and r < 100, \
            f"透過部分に背景色(青)が見えない: RGB=({r},{g},{b})"
        # 中央ピクセルは赤画像
        w, h = 160, 90
        center = ((h // 2) * w + w // 2) * 3
        cr, cb = result.stdout[center], result.stdout[center + 2]
        assert cr > 128 and cb < 100, \
            f"中央に赤画像が見えない: R={cr}, B={cb}"
    finally:
        # グローバル__cache__を汚さない（このテスト専用鍵だが掃除しておく）
        for path in (cache_video,
                     _layer_cache_paths(str(layer), p1)[1]):
            try:
                os.remove(path)
            except OSError:
                pass


# --- 1. asset() のパストラバーサル拒否 -----------------------------------

@pytest.fixture
def fake_project(tmp_path, monkeypatch):
    """assets/ を持つ最小プロジェクトを作り、そこへ chdir する"""
    proj = tmp_path / "proj"
    (proj / "assets" / "images").mkdir(parents=True)
    (proj / "assets" / "images" / "a.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.chdir(proj)
    return proj


def test_asset_normal_resolution(fake_project):
    """正常系: assets/ 配下の素材は絶対パスで解決される"""
    p = asset("images/a.png")
    assert os.path.isabs(p) and os.path.exists(p)
    assert os.path.basename(p) == "a.png"


def test_asset_rejects_parent_traversal(fake_project):
    """`..` を含む指定は assets/ の外に出るため拒否される"""
    with pytest.raises(ValueError, match=r"'\.\.' を含むパスは指定できません"):
        asset("../secret.txt")
    with pytest.raises(ValueError, match=r"'\.\.' を含むパスは指定できません"):
        asset("images/../../secret.txt")
    with pytest.raises(ValueError, match=r"'\.\.' を含むパスは指定できません"):
        asset("images\\..\\..\\secret.txt")
    # must_exist=False でも拒否される（出力先組み立て経路の悪用防止）
    with pytest.raises(ValueError):
        asset("../secret.txt", must_exist=False)


def test_asset_rejects_absolute_and_drive_paths(fake_project, tmp_path):
    """絶対パス・ドライブレター付きパスは拒否される"""
    with pytest.raises(ValueError, match="絶対パス"):
        asset(str(tmp_path / "secret.txt"))
    with pytest.raises(ValueError, match="絶対パス"):
        asset("C:/Windows/win.ini")
    with pytest.raises(ValueError, match="絶対パス"):
        asset("C:relative_to_drive.txt")  # ドライブ相対も拒否
    with pytest.raises(ValueError, match="絶対パス"):
        asset("/etc/passwd")


def test_asset_rejects_empty(fake_project):
    """空・`.` のみの指定は拒否される"""
    with pytest.raises(ValueError, match="空です"):
        asset("")
    with pytest.raises(ValueError, match="空です"):
        asset("./.")


def test_asset_missing_gives_filenotfound(fake_project):
    """存在しない正当な相対パスは従来どおり FileNotFoundError（候補付き）"""
    with pytest.raises(FileNotFoundError):
        asset("images/nothing.png")


# --- 2. Web Object の短尺 duration ---------------------------------------

def test_web_frame_count_min_one():
    """duration < 1/fps でも最低1フレームを保証する（旧: int(dur*fps)=0）"""
    assert _web_frame_count(0.01, 30) == 1
    assert _web_frame_count(0.001, 30) == 1


def test_web_frame_count_ceil():
    """端数は切り上げて全尺をカバーする"""
    assert _web_frame_count(1.0, 30) == 30
    assert _web_frame_count(0.5, 30) == 15
    assert _web_frame_count(0.05, 30) == 2  # 1.5 → 2


def test_web_frame_count_rejects_nonpositive():
    """duration/fps が 0 以下・非数値は明確なエラー"""
    with pytest.raises(ValueError, match="duration"):
        _web_frame_count(0, 30)
    with pytest.raises(ValueError, match="duration"):
        _web_frame_count(-1, 30)
    with pytest.raises(ValueError, match="fps"):
        _web_frame_count(1.0, 0)


def test_web_object_rejects_nonpositive_duration(tmp_path, monkeypatch):
    """web Object 構築時に duration<=0 / 非数値を拒否する"""
    from scriptvedit.objects import Object
    html = tmp_path / "scene.html"
    html.write_text("<html></html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="duration は正の数値"):
        Object(str(html), duration=0, size=(320, 180))
    with pytest.raises(ValueError, match="duration は正の数値"):
        Object(str(html), duration=-2.0, size=(320, 180))
    with pytest.raises(ValueError, match="duration は正の数値"):
        Object(str(html), duration="3", size=(320, 180))


# --- 3. Web frames_dir の stale フレーム掃除 -------------------------------

def test_web_frames_dir_cleared_before_render(tmp_path, monkeypatch):
    """_render_web_frames は生成前に frames_dir を空にする（stale 混入防止）。

    Playwright 起動前に到達する検証: sync_playwright を差し替え、
    掃除後の frames_dir の状態を観測してから中断する。
    """
    from scriptvedit.objects import Object
    from scriptvedit.state import _CACHE_DIR

    html = tmp_path / "scene.html"
    html.write_text("<html><script>function renderFrame(s){}</script></html>",
                    encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    obj = Object.__new__(Object)
    obj._web_source = str(html)
    obj._web_size = (320, 180)
    obj._web_fps = 30
    obj._web_data = {}
    obj._web_name = "robustness_stale"
    obj._web_debug_frames = False
    obj._web_deps = []
    obj.duration = 0.5

    frames_dir = os.path.join(_CACHE_DIR, "webclip", "robustness_stale_frames")
    os.makedirs(frames_dir, exist_ok=True)
    stale = os.path.join(frames_dir, "frame_99999.png")
    with open(stale, "wb") as f:
        f.write(b"stale")

    observed = {}

    class _Stop(Exception):
        pass

    def fake_sync_playwright():
        # rmtree + makedirs の後に呼ばれる → この時点の中身を観測して中断
        observed["listing"] = os.listdir(frames_dir)
        raise _Stop()

    import types as _types
    fake_mod = _types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = fake_sync_playwright
    fake_pkg = _types.ModuleType("playwright")
    fake_pkg.sync_api = fake_mod
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

    class _FakeProject:
        fps = 30

    with pytest.raises(_Stop):
        obj._render_web_frames(_FakeProject())
    assert observed["listing"] == []  # stale フレームは掃除済み
    assert not os.path.exists(stale)
    # 後片付け
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)


# --- 4. キャッシュ生成一時パスのユニーク化 ---------------------------------

def test_unique_tmp_path_differs():
    """同じ最終パスから生成される一時パスは毎回異なり、拡張子は維持される"""
    p1 = _unique_tmp_path("out/final.webm")
    p2 = _unique_tmp_path("out/final.webm")
    assert p1 != p2
    assert p1.endswith(".webm") and p2.endswith(".webm")
    assert os.path.dirname(p1) == "out"  # 同一ディレクトリ（os.replace が原子的）


def test_run_ffmpeg_to_cache_parallel_no_collision(tmp_path, monkeypatch):
    """同じ cache_path へ並行到達しても一時パスが衝突しない"""
    import scriptvedit.ffmpeg as ffmpeg_mod
    cache_path = str(tmp_path / "clip.webm")
    tmp_paths = []
    lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=10)

    def fake_run(cmd, timeout=600):
        out = cmd[-1]
        barrier.wait()  # 2スレッドを同時に走らせて固定名なら衝突する状況を作る
        with lock:
            tmp_paths.append(out)
        with open(out, "wb") as f:
            f.write(b"webm")

    monkeypatch.setattr(ffmpeg_mod, "_run_ffmpeg", fake_run)
    cmd = ["ffmpeg", "-y", "-i", "in.png", cache_path]

    errors = []

    def worker():
        try:
            _run_ffmpeg_to_cache(list(cmd), cache_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(set(tmp_paths)) == 2  # 一時パスが互いに異なる
    assert os.path.exists(cache_path)
    # 一時ファイルの残骸が無い
    leftovers = [n for n in os.listdir(tmp_path) if ".tmp" in n]
    assert leftovers == []


def test_run_ffmpeg_to_cache_keeps_safety_valve(tmp_path):
    """既存の安全装置: cmd 内に cache_path が無ければ ValueError（維持されている）"""
    with pytest.raises(ValueError, match="cache_path"):
        _run_ffmpeg_to_cache(["ffmpeg", "-y", "-i", "in.png", "other.webm"],
                             str(tmp_path / "clip.webm"))


# --- 6. cache --clear/--gc の削除ガード ------------------------------------

def test_cache_clear_refuses_non_cache_dir(tmp_path):
    """__cache__ 配下でないディレクトリは既定で拒否される"""
    target = tmp_path / "not_cache"
    target.mkdir()
    (target / "important.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="__cache__"):
        cache_clear(str(target))
    assert (target / "important.txt").exists()  # 消えていない


def test_cache_gc_refuses_non_cache_dir(tmp_path):
    """--gc も同じガードが効く"""
    target = tmp_path / "not_cache2"
    target.mkdir()
    with pytest.raises(ValueError, match="__cache__"):
        cache_gc(0, str(target))


def test_cache_clear_allows_cache_dir(tmp_path):
    """__cache__ という名前のディレクトリは force なしで削除できる"""
    target = tmp_path / "__cache__"
    (target / "artifacts").mkdir(parents=True)
    (target / "artifacts" / "x.webm").write_bytes(b"x")
    cache_clear(str(target))
    assert not target.exists()


def test_cache_clear_force_allows_with_warning(tmp_path):
    """force=True なら __cache__ 外でも警告付きで削除できる（--yes 相当）"""
    target = tmp_path / "custom_cache"
    target.mkdir()
    (target / "a.bin").write_bytes(b"x")
    with pytest.warns(UserWarning, match="__cache__"):
        cache_clear(str(target), force=True)
    assert not target.exists()


def test_cli_cache_clear_guard(tmp_path, capsys):
    """CLI 経由: --dir が __cache__ 外なら rc=2 で中断、--yes で実行"""
    target = tmp_path / "victim"
    target.mkdir()
    (target / "keep.txt").write_text("x", encoding="utf-8")
    rc = _main(["cache", "--clear", "--dir", str(target)])
    assert rc == 2
    assert (target / "keep.txt").exists()
    err = capsys.readouterr().err
    assert "--yes" in err
    with pytest.warns(UserWarning):
        rc2 = _main(["cache", "--clear", "--dir", str(target), "--yes"])
    assert rc2 == 0
    assert not target.exists()


# --- 7. scriptvedit new --force の .bak 退避 --------------------------------

def test_new_project_force_backs_up_modified_files(tmp_path, capsys):
    """force=True の再生成で、編集済みファイルは .bak に退避される"""
    root = new_project(str(tmp_path / "proj"), quiet=True)
    main_py = os.path.join(root, "main.py")
    original = open(main_py, encoding="utf-8", newline="").read()
    edited = "# ユーザーの編集\n" + original
    with open(main_py, "w", encoding="utf-8", newline="") as f:
        f.write(edited)

    new_project(root, force=True)
    out = capsys.readouterr().out
    assert ".bak に退避" in out

    bak = main_py + ".bak"
    assert os.path.exists(bak)
    assert open(bak, encoding="utf-8", newline="").read() == edited  # 旧内容が残る
    assert open(main_py, encoding="utf-8", newline="").read() == original  # 雛形に戻る


def test_new_project_force_skips_identical_files(tmp_path):
    """内容が同一のファイルは .bak を作らずスキップする"""
    root = new_project(str(tmp_path / "proj2"), quiet=True)
    new_project(root, force=True, quiet=True)
    baks = []
    for dirpath, _dirs, files in os.walk(root):
        baks += [f for f in files if f.endswith(".bak")]
    assert baks == []
