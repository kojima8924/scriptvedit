# -*- coding: utf-8 -*-
"""svtts — VOICEVOX による日本語ナレーション音声生成モジュール

ローカルで起動している VOICEVOX エンジン (http://127.0.0.1:50021) の REST API を
呼び出して日本語テキストから wav を合成し、scriptvedit の素材として使える
ファイルパスを返す。

使い方（Python から）:
    from svtts import tts, tts_duration, speakers

    wav = tts("こんにちは、ずんだもんなのだ", speaker=3)
    dur = tts_duration(wav)   # 字幕同期用の実長（秒）

使い方（CLI から）:
    python svtts.py "こんにちは" --speaker 1 -o out.wav
    python svtts.py --list-speakers

依存は標準ライブラリのみ（urllib.request / wave / hashlib など）。
生成結果は text+speaker+speed+pitch の sha256 を鍵に __cache__/tts/ へ
キャッシュされ、2回目以降は API を呼ばずに即座にパスを返す。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 50021
_DEFAULT_CACHE_DIR = "__cache__/tts"

_CONNECT_TIMEOUT = 5   # audio_query / speakers 用（接続確認を兼ねる）
_SYNTH_TIMEOUT = 60    # synthesis 用（長文の合成に時間がかかるため長め）


def _base_url(host, port):
    """VOICEVOX エンジンのベースURLを返す"""
    return f"http://{host}:{port}"


def _not_running_error(host, port):
    """VOICEVOX 未起動時に投げる ConnectionError を生成する"""
    return ConnectionError(
        f"VOICEVOX が起動していません({_base_url(host, port)})。"
        "https://voicevox.hiroshiba.jp/ からインストールして起動してください")


def _request(url, *, host, port, method="GET", data=None, headers=None,
             timeout=_CONNECT_TIMEOUT):
    """VOICEVOX API へ HTTP リクエストを送り、レスポンスボディ(bytes)を返す

    接続不可（未起動・ポート違い等）は明確なメッセージの ConnectionError、
    タイムアウトは TimeoutError、API 側のエラー応答は RuntimeError にする。
    """
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        # サーバーは起動しているが API がエラーを返した（パラメータ不正など）
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"VOICEVOX API エラー ({e.code} {e.reason}): {url}\n{body}") from e
    except TimeoutError as e:
        raise TimeoutError(
            f"VOICEVOX API がタイムアウトしました({timeout}秒): {url}") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise TimeoutError(
                f"VOICEVOX API がタイムアウトしました({timeout}秒): {url}") from e
        raise _not_running_error(host, port) from e
    except OSError as e:
        # ConnectionRefusedError 等が直接漏れてくるケース
        raise _not_running_error(host, port) from e


def _cache_path(text, speaker, speed, pitch, cache_dir):
    """キャッシュファイルのパスを決定する（text+speaker+speed+pitch の sha256）"""
    sig = f"{text}||speaker={int(speaker)}||speed={float(speed):g}||pitch={float(pitch):g}"
    key = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, f"{key}.wav")


def tts(text, *, speaker=1, speed=1.0, pitch=0.0, cache_dir=_DEFAULT_CACHE_DIR,
        host=_DEFAULT_HOST, port=_DEFAULT_PORT):
    """日本語テキストを VOICEVOX で音声合成し、wav ファイルのパスを返す

    Args:
        text:      読み上げるテキスト
        speaker:   話者スタイルID（speakers() や --list-speakers で確認できる）
        speed:     話速（speedScale、1.0 が標準）
        pitch:     音高（pitchScale、0.0 が標準）
        cache_dir: キャッシュディレクトリ
        host/port: VOICEVOX エンジンのアドレス

    Returns:
        生成された wav ファイルのパス（キャッシュ済みなら API を呼ばず即返す）

    Raises:
        ConnectionError: VOICEVOX エンジンが起動していない場合
    """
    if not text:
        raise ValueError("tts: text が空です")
    cache_path = _cache_path(text, speaker, speed, pitch, cache_dir)
    if os.path.exists(cache_path):
        return cache_path

    base = _base_url(host, port)

    # 1) audio_query: テキストから合成用クエリ(JSON)を生成
    #    （接続確認を兼ねるため短いタイムアウト）
    query_qs = urllib.parse.urlencode({"text": text, "speaker": int(speaker)})
    raw = _request(f"{base}/audio_query?{query_qs}", host=host, port=port,
                   method="POST", timeout=_CONNECT_TIMEOUT)
    query = json.loads(raw)

    # 2) 話速・音高を調整
    query["speedScale"] = float(speed)
    query["pitchScale"] = float(pitch)

    # 3) synthesis: クエリを渡して wav を取得
    wav_bytes = _request(
        f"{base}/synthesis?speaker={int(speaker)}", host=host, port=port,
        method="POST", data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
        timeout=_SYNTH_TIMEOUT)

    # 4) 一時パスへ書き込み → os.replace で確定（アトミック書き込み）
    #    途中失敗で壊れた部分ファイルがキャッシュとして残るのを防ぐ
    os.makedirs(cache_dir, exist_ok=True)
    base_path, ext = os.path.splitext(cache_path)
    tmp_path = f"{base_path}.tmp{ext}"
    try:
        with open(tmp_path, "wb") as f:
            f.write(wav_bytes)
        os.replace(tmp_path, cache_path)
    finally:
        # 失敗時に残った一時ファイルを削除（成功時は os.replace 済みで存在しない）
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return cache_path


def speakers(host=_DEFAULT_HOST, port=_DEFAULT_PORT):
    """VOICEVOX の話者一覧を取得して整形して返す

    Returns:
        [{"id": スタイルID, "name": 話者名, "style": スタイル名}, ...]（ID昇順）
    """
    raw = _request(f"{_base_url(host, port)}/speakers", host=host, port=port,
                   timeout=_CONNECT_TIMEOUT)
    result = []
    for sp in json.loads(raw):
        for style in sp.get("styles", []):
            result.append({
                "id": style["id"],
                "name": sp["name"],
                "style": style["name"],
            })
    result.sort(key=lambda s: s["id"])
    return result


def tts_duration(wav_path):
    """wav ファイルの実長（秒）を返す（字幕・タイムライン同期用）"""
    with wave.open(wav_path, "rb") as w:
        rate = w.getframerate()
        if rate <= 0:
            raise ValueError(f"tts_duration: サンプルレートが不正です: {wav_path}")
        nframes = w.getnframes()
        if nframes <= 0:
            raise ValueError(f"tts_duration: フレーム数が 0 です(空の wav): {wav_path}")
        return nframes / float(rate)


def _main(argv=None):
    """CLI エントリポイント"""
    parser = argparse.ArgumentParser(
        description="VOICEVOX で日本語テキストから wav を生成する")
    parser.add_argument("text", nargs="?", help="読み上げるテキスト")
    parser.add_argument("--speaker", type=int, default=1, help="話者スタイルID（既定: 1）")
    parser.add_argument("--speed", type=float, default=1.0, help="話速（既定: 1.0）")
    parser.add_argument("--pitch", type=float, default=0.0, help="音高（既定: 0.0）")
    parser.add_argument("-o", "--output", help="出力先 wav パス（省略時はキャッシュパスを表示）")
    parser.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR,
                        help=f"キャッシュディレクトリ（既定: {_DEFAULT_CACHE_DIR}）")
    parser.add_argument("--host", default=_DEFAULT_HOST, help="VOICEVOX ホスト")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="VOICEVOX ポート")
    parser.add_argument("--list-speakers", action="store_true", help="話者一覧を表示して終了")
    args = parser.parse_args(argv)

    try:
        if args.list_speakers:
            for sp in speakers(host=args.host, port=args.port):
                print(f"{sp['id']:4d}  {sp['name']} ({sp['style']})")
            return 0

        if not args.text:
            parser.error("text を指定してください（話者一覧は --list-speakers）")

        path = tts(args.text, speaker=args.speaker, speed=args.speed,
                   pitch=args.pitch, cache_dir=args.cache_dir,
                   host=args.host, port=args.port)
        if args.output:
            shutil.copyfile(path, args.output)
            path = args.output
        print(f"{path} ({tts_duration(path):.2f}秒)")
        return 0
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
