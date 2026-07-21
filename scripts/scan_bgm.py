"""共有素材ライブラリの bgm/ をスキャンして catalog.json / catalog.md を生成する

楽曲を選ぶときの手がかり（尺・BPM・タグ）を一覧にする。BGM とカタログは
共有素材ライブラリ（環境変数 SCRIPTVEDIT_ASSETS 配下の bgm/）に置き、
リポジトリには入れない。

自動で集める情報:
  - 尺（ffprobe）
  - BPM（scriptvedit.beat のビート検出）
  - 曲名・タグ（ファイル名の nc番号 から ニコニ・コモンズを Playwright で取得）

タグはその曲がニコニコでどう使われてきたかを示す客観情報なので、
「どんな場面に合う曲か」を判断する材料になる。

使い方:
    python scripts/scan_bgm.py                # 全部（初回は commons 取得で時間がかかる）
    python scripts/scan_bgm.py --no-bpm       # BPM検出を省略（高速）
    python scripts/scan_bgm.py --no-commons   # commons 取得を省略（オフライン）
"""
import argparse
import json
import os
import re
import subprocess
import sys

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}


def _default_bgm_dir():
    """既定のBGMフォルダ

    BGM は共有素材ライブラリ側に置く（リポジトリには入れない。リポジトリ内への
    フォールバックは音源の誤 commit につながるため行わない）。
    環境変数 SCRIPTVEDIT_ASSETS（`;` 区切りの探索パス）の各ルート配下から bgm/ を探す。
    見つからなければ SystemExit（--dir で明示指定した場合はこの関数を通らない）。
    """
    env = os.environ.get("SCRIPTVEDIT_ASSETS", "")
    parts = [env]
    for sep in {os.pathsep, ";"}:   # 区切りは assets.py の library_dirs と同じ扱い
        parts = [piece for part in parts for piece in part.split(sep)]
    for root in [p.strip().strip('"') for p in parts if p.strip()]:
        cand = os.path.join(root, "bgm")
        if os.path.isdir(cand):
            return cand
    raise SystemExit(
        "BGMフォルダが見つかりません。共有素材ライブラリに bgm/ を作り、\n"
        "環境変数 SCRIPTVEDIT_ASSETS にライブラリのパスを設定してください\n"
        "（`;` 区切りで複数指定可）。特定のフォルダを使う場合は --dir で指定できます。"
    )


def _probe_duration(path):
    """ffprobe で尺（秒）を取得"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        return round(float(json.loads(r.stdout)["format"]["duration"]), 1)
    except Exception:
        return None


def _detect_bpm(path):
    """scriptvedit.beat でBPMを推定"""
    try:
        from scriptvedit.beat import detect_beats
    except ImportError:
        return None
    try:
        return round(detect_beats(path)["bpm"], 1)
    except Exception as e:
        print(f"    BPM検出失敗: {e}")
        return None


def _nc_id(filename):
    """ファイル名から ニコニ・コモンズのID（ncXXXXXX）を拾う"""
    m = re.search(r"(nc\d{4,})", filename, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _fetch_commons(nc_ids):
    """ニコニ・コモンズから曲名とタグを取得（Playwright でレンダリング）

    commons のページは JavaScript で描画されるため、素の HTTP 取得では中身が取れない。
    公開 API も無いので Chromium でレンダして DOM から拾う。
    """
    if not nc_ids:
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright が無いため commons 取得をスキップします "
              "(pip install playwright && playwright install chromium)")
        return {}

    out = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for i, nc in enumerate(nc_ids, 1):
            url = f"https://commons.nicovideo.jp/works/{nc}"
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                # SPA なので描画完了を待つ。曲名が入るまでポーリングする
                # （固定待ちだと取りこぼす。タグは付いていない曲もあるので待たない）
                page.wait_for_function(
                    "() => document.title && !/^ニコニ・コモンズ/.test(document.title)",
                    timeout=15000,
                )
                page.wait_for_timeout(800)
                info = page.evaluate("""() => {
                    const title = (document.title || '')
                        .replace(/ - ニコニ・コモンズ$/, '').trim();
                    const tags = Array.from(
                        document.querySelectorAll('a[href*="/search/tag"], [class*=tag] a')
                    ).map(e => e.innerText.trim()).filter(Boolean);
                    return {title, tags: [...new Set(tags)]};
                }""")
                out[nc] = info
                tags = "、".join(info["tags"]) if info["tags"] else "（タグなし）"
                print(f"  [{i}/{len(nc_ids)}] {nc}: {info['title']}")
                print(f"        {tags}")
            except Exception as e:
                print(f"  [{i}/{len(nc_ids)}] {nc}: 取得失敗 ({type(e).__name__})")
        browser.close()
    return out


def _license_note(track):
    """曲ごとの出典・利用条件の注記を返す

    ニコニ・コモンズID がファイル名にあり commons から情報が取れた曲だけ、
    出典（コモンズの作品ページ）を示す。それ以外の曲に特定レーベル固有の
    条件を推測で付けたりせず「未確認」と明記する。
    """
    if track.get("nc_id") and track.get("title"):
        return (f"ニコニ・コモンズ {track['nc_id']}"
                f"（利用条件は作品ページで確認: "
                f"https://commons.nicovideo.jp/works/{track['nc_id']}）")
    return "出典・利用条件: 未確認（各自で確認してください）"


def _write_markdown(md_path, tracks):
    """曲と特徴の一覧（人が読む用）"""
    lines = [
        "# BGM 一覧",
        "",
        "`python scripts/scan_bgm.py` で自動生成。",
        "`memo` 欄だけは手書きで、再生成しても消えない。",
        "",
        "タグはニコニ・コモンズに登録されている客観情報。その曲がどんな文脈で",
        "使われてきたかが分かるので、場面に合う曲を選ぶ手がかりになる。",
        "",
        "| 曲名 | ファイル | 尺 | BPM | タグ | 出典・利用条件 | memo |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for t in tracks:
        tags = "、".join(t["tags"]) if t["tags"] else ""
        dur = f"{t['duration']}s" if t["duration"] else "?"
        bpm = f"{t['bpm']}" if t["bpm"] else "?"
        lines.append(
            f"| {t['title'] or '-'} | `{t['file']}` | {dur} | {bpm} | {tags} "
            f"| {_license_note(t)} | {t['memo']} |"
        )
    lines += [
        "",
        "## 利用条件について",
        "",
        "- 「出典・利用条件」欄が **未確認** の曲は、使用前に必ず出典と利用条件を確認すること。",
        "- ニコニ・コモンズの曲は各作品ページの利用条件（利用範囲・親作品登録・"
        "クレジット表記等）に従うこと。",
        "",
    ]
    tmp = md_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines))
    os.replace(tmp, md_path)


def main():
    ap = argparse.ArgumentParser(description="BGMカタログを生成する")
    ap.add_argument("--dir", default=None,
                    help="BGMフォルダ（既定: 環境変数 SCRIPTVEDIT_ASSETS 配下の bgm/）")
    ap.add_argument("--no-bpm", action="store_true", help="BPM検出を省略")
    ap.add_argument("--no-commons", action="store_true", help="commons 取得を省略")
    ap.add_argument("--force", action="store_true",
                    help="取得済みの曲も全部やり直す（既定は増分更新）")
    args = ap.parse_args()

    bgm_dir = args.dir or _default_bgm_dir()
    json_path = os.path.join(bgm_dir, "catalog.json")
    md_path = os.path.join(bgm_dir, "catalog.md")
    if not os.path.isdir(bgm_dir):
        print(f"BGMフォルダがありません: {bgm_dir}")
        return 1

    # 既存カタログを読む（増分更新のため。200曲を毎回やり直すのは非現実的）
    old = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                for e in json.load(f).get("tracks", []):
                    old[e["file"]] = e
        except (OSError, json.JSONDecodeError):
            pass

    files = sorted(n for n in os.listdir(bgm_dir)
                   if os.path.splitext(n)[1].lower() in AUDIO_EXT)
    if not files:
        print(f"楽曲がありません: {bgm_dir}")
        print("ニコニ・コモンズ等からダウンロードして、このフォルダに置いてください。")
        return 0

    nc_map = {n: _nc_id(n) for n in files}

    # commons は「曲名がまだ取れていない曲」だけ取りに行く（--force で全件）
    commons = {}
    if not args.no_commons:
        need = sorted({
            nc_map[n] for n in files
            if nc_map[n] and (args.force or not old.get(n, {}).get("title"))
        })
        if need:
            print(f"ニコニ・コモンズから取得中（{len(need)}件）...")
            commons = _fetch_commons(need)
        else:
            print("commons: 全曲取得済み（スキップ）")

    tracks = []
    print("\n楽曲を解析中...")
    for name in files:
        path = os.path.join(bgm_dir, name)
        prev = old.get(name, {})
        nc = nc_map[name]
        info = commons.get(nc)

        # 取得済みの値は再計算しない（--force で全部やり直す）
        title = info["title"] if info else prev.get("title")
        tags = info["tags"] if info else prev.get("tags", [])
        duration = prev.get("duration") if not args.force else None
        if duration is None:
            duration = _probe_duration(path)
        bpm = prev.get("bpm") if not args.force else None
        if bpm is None and not args.no_bpm:
            print(f"  BPM検出: {name}")
            bpm = _detect_bpm(path)

        track = {
            "file": name,
            "nc_id": nc,
            "title": title,
            "duration": duration,
            "bpm": bpm,
            "tags": tags,
            "memo": prev.get("memo", ""),  # 手書き欄は必ず保持
        }
        track["license"] = _license_note(track)
        tracks.append(track)

    tmp = json_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump({"tracks": tracks}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, json_path)
    _write_markdown(md_path, tracks)

    print(f"\nカタログを更新しました（{len(tracks)}曲）")
    print(f"  {md_path}")
    print(f"  {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
