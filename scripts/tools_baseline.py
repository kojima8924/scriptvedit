"""再編前後の等価性検証ツール

スナップショット(ffmpegコマンド)から素材パス・キャッシュパスをトークン化して
正規化し、構造再編の前後で「パス以外は1バイトも変わっていない」ことを検証する。

使い方:
    python tools_baseline.py capture -o baseline.json   # 再編前に実行
    python tools_baseline.py verify baseline.json       # 再編後に実行(差分を報告)
"""
import argparse
import json
import os
import re
import sys

SNAP_DIRS = ["test/snapshots", "tests/snapshots"]


def _find_snapshot_dir():
    # scripts/ から見たリポジトリルート配下を探す
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in SNAP_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            return p
    raise SystemExit("スナップショットディレクトリが見つかりません")


def normalize(text):
    """パス依存の差異をトークン化して正規化する

    - 素材ファイル名(拡張子付き)は basename だけ残す（ディレクトリ移動を吸収）
    - キャッシュのハッシュ(16進16桁など)は <HASH> に置換
    - 一時ファイルパスは <TMP> に置換
    """
    s = text
    # Windows/Posix 混在パス区切りを統一
    s = s.replace("\\", "/")
    # キャッシュ配下のハッシュ付きパス → ディレクトリ構造を無視して種別+ハッシュ長のみ残す
    s = re.sub(r"[A-Za-z0-9_./:-]*__cache__/[A-Za-z0-9_./-]*", "<CACHE>", s)
    # 16進ハッシュ(12桁以上)
    s = re.sub(r"\b[0-9a-f]{12,}\b", "<HASH>", s)
    # 素材パス: ディレクトリを剥がして basename のみ（assets/ 移動を吸収）
    # ディレクトリ部は任意（再編前の「ディレクトリ無し=cwd相対」表記も同じトークンに畳む）
    s = re.sub(
        r"(?:[A-Za-z]:)?(?:[\w./-]*/)?([\w　-鿿-]+\.(?:png|jpg|jpeg|mp4|mp3|wav|webm|mkv|srt|ass|cube|html|ttf|otf))",
        r"<ASSET:\1>", s)
    # 一時ファイル
    s = re.sub(r"[\w./:-]*(?:Temp|tmp)[\w./-]*", "<TMP>", s)
    return s


def _canon(data):
    """正規化してから並べ替える（キーがキャッシュハッシュの場合の順序ゆれを吸収）

    dict のキーはキャッシュパス（ハッシュ）であり、正規化前のキーで sort すると
    パスが変わっただけで並び順が変わってしまう。正規化後の [key, value] ペアを
    ソートしたリストにすることで「中身は同じだが順序だけ違う」を同一とみなす。
    フィルタ文字列の実質的な変化は従来どおり検出できる。
    """
    if isinstance(data, dict):
        return sorted([[_canon(k), _canon(v)] for k, v in data.items()],
                      key=lambda kv: json.dumps(kv, ensure_ascii=False))
    if isinstance(data, list):
        return [_canon(v) for v in data]
    if isinstance(data, str):
        return normalize(data)
    return data


def _load_snapshots(snap_dir):
    out = {}
    for name in sorted(os.listdir(snap_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(snap_dir, name), "r", encoding="utf-8") as f:
            data = json.load(f)
        out[name] = json.dumps(_canon(data), ensure_ascii=False)
    return out


def cmd_capture(args):
    snap_dir = args.dir or _find_snapshot_dir()
    snaps = _load_snapshots(snap_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snaps, f, ensure_ascii=False, indent=1)
    print(f"ベースライン保存: {args.out} ({len(snaps)}件, 元: {snap_dir})")


def cmd_verify(args):
    snap_dir = _find_snapshot_dir()
    with open(args.baseline, "r", encoding="utf-8") as f:
        base = json.load(f)
    cur = _load_snapshots(snap_dir)

    missing = sorted(set(base) - set(cur))
    added = sorted(set(cur) - set(base))
    changed = [k for k in sorted(set(base) & set(cur)) if base[k] != cur[k]]

    print(f"ベースライン {len(base)}件 / 現在 {len(cur)}件 (元: {snap_dir})")
    if missing:
        print(f"  消えたスナップショット({len(missing)}): {missing}")
    if added:
        print(f"  増えたスナップショット({len(added)}): {added}")
    if changed:
        print(f"  ★正規化後も差分あり({len(changed)}件) — パス以外が変わっている疑い:")
        for k in changed:
            print(f"    - {k}")
            b, c = base[k], cur[k]
            # 最初の相違箇所を表示
            for i, (x, y) in enumerate(zip(b, c)):
                if x != y:
                    print(f"        base: ...{b[max(0,i-60):i+60]}...")
                    print(f"        cur : ...{c[max(0,i-60):i+60]}...")
                    break
            else:
                print(f"        長さ違い: base={len(b)} cur={len(c)}")
    if not missing and not added and not changed:
        print("  ✅ 正規化後は完全一致 — パス以外の挙動変化なし")
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser(description="構造再編の等価性検証")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture", help="現在のスナップショットを正規化して保存")
    c.add_argument("-o", "--out", default="baseline_snapshots.json")
    c.add_argument("--dir", default=None,
                   help="スナップショットディレクトリ（再編前の状態を git から取り出して指定できる）")
    c.set_defaults(func=cmd_capture)
    v = sub.add_parser("verify", help="ベースラインと比較")
    v.add_argument("baseline")
    v.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
