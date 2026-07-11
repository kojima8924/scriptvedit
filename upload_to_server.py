# scriptvedit 全ソースをロリポップFTPサーバーにアップロード
# export_project.py で結合したテキストを index_<commit>.html に埋め込む
#
# 使い方:
#   python upload_to_server.py
#
# 前提: 環境変数 LOLIPOP_FTP_PASS が設定済み
# pre-push hookから自動実行される
# 公開URL: http://kojima8924.main.jp/scriptvedit/
import ftplib
import html
import io
import os
import subprocess
import sys
import time

# --- 設定 ---
FTP_HOST = "ftp-1.lolipop.jp"
FTP_USER = "main.jp-kojima8924"
FTP_PASS = os.environ.get("LOLIPOP_FTP_PASS", "")
REMOTE_DIR = "scriptvedit"
PUBLIC_URL = "http://kojima8924.main.jp/scriptvedit"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXPORT_SCRIPT = "C:/code/export_project.py"


def git_cmd(*args):
    """gitコマンドを実行して出力を返す"""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def ftp_connect():
    """FTPS接続（explicit TLS、パッシブモード）"""
    ftp = ftplib.FTP_TLS()
    ftp.connect(FTP_HOST, 21, timeout=30)
    ftp.login(FTP_USER, FTP_PASS)  # login()が内部でAUTH TLSを実行
    ftp.prot_p()  # データチャネルも暗号化
    ftp.set_pasv(True)
    ftp.encoding = "utf-8"
    return ftp


def remote_dir_exists(ftp, path):
    """リモートディレクトリの存在確認

    ロリポップのFTPSは PWD に空文字を返すため、ftp.pwd() で現在位置を
    保存して戻す方式は使えない（cwd("") が元の位置に戻らず、path の中に
    入ったままになる）。呼び出し側は常にルート基準のため絶対パス "/" で戻す。
    """
    try:
        ftp.cwd(path)
        return True
    except ftplib.error_perm:
        return False
    finally:
        ftp.cwd("/")


def rmdir_recursive(ftp, path):
    """FTPディレクトリを再帰的に削除（MLSDのtypeでファイル/ディレクトリ判定）"""
    ftp.cwd(path)
    for name, facts in list(ftp.mlsd()):
        ftype = facts.get("type", "")
        if ftype in ("cdir", "pdir"):  # "." と ".."
            continue
        if ftype == "dir":
            rmdir_recursive(ftp, name)
        else:
            ftp.delete(name)
    ftp.cwd("..")
    ftp.rmd(path)


def main():
    if not FTP_PASS:
        print("エラー: 環境変数 LOLIPOP_FTP_PASS を設定してください")
        sys.exit(1)

    # --- export_project.py でソース結合 ---
    print("ソースファイル結合中...")
    r = subprocess.run(
        [sys.executable, EXPORT_SCRIPT, "scriptvedit"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        # 失敗時に古い scriptvedit-all.txt を公開しないよう中断
        print(f"エラー: export_project.py が失敗しました (exit={r.returncode})")
        if r.stderr.strip():
            print(r.stderr.strip())
        sys.exit(1)
    export_path = os.path.join(os.path.dirname(EXPORT_SCRIPT), "scriptvedit-all.txt")
    with open(export_path, "r", encoding="utf-8") as f:
        export_text = f.read()

    # --- git情報取得（失敗時は "unknown" にフォールバック） ---
    commit = git_cmd("rev-parse", "--short", "HEAD") or "unknown"
    branch = git_cmd("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    git_log = git_cmd("log", "--oneline", "--no-decorate", "-20")
    print(f"ブランチ: {branch}  コミット: {commit}")

    # --- index_<commit>.html 生成 ---
    filename = f"index_{commit}.html"
    index_html = (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset='utf-8'>\n"
        f"<title>scriptvedit source ({commit})</title>\n"
        "</head><body>\n"
        "<h1>scriptvedit 全ソース</h1>\n"
        f"<p>コミット: {commit} | ブランチ: {branch} | "
        f"更新: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>\n"
        "<h2>最近のコミット</h2>\n"
        f"<pre>{html.escape(git_log)}</pre>\n"
        "<hr>\n"
        "<h2>ソースコード</h2>\n"
        f"<pre>{html.escape(export_text)}</pre>\n"
        "</body></html>"
    )
    print(f"HTML生成: {filename} ({len(index_html) // 1024}KB)")

    # --- FTP接続 ---
    print(f"\n接続中: {FTP_HOST} ...")
    ftp = ftp_connect()
    print("接続完了")

    try:
        # --- 既存ディレクトリ削除 ---
        ftp.cwd("/")
        if remote_dir_exists(ftp, REMOTE_DIR):
            # 削除失敗は例外のまま中断（「存在しない」と誤報告しない）
            rmdir_recursive(ftp, REMOTE_DIR)
            print(f"{REMOTE_DIR}/ 削除完了")
        else:
            print(f"{REMOTE_DIR}/ は存在しない（スキップ）")

        # --- ディレクトリ作成 ---
        # 直前で削除済みのため「既に存在する」失敗は起きない。
        # 権限エラー等の本物の失敗は握りつぶさず伝播させる
        ftp.cwd("/")
        ftp.mkd(REMOTE_DIR)
        ftp.cwd(REMOTE_DIR)

        # --- .htaccess ---
        htaccess = "AddDefaultCharset UTF-8\n"
        ftp.storbinary("STOR .htaccess", io.BytesIO(htaccess.encode("utf-8")))
        print("  OK: .htaccess")

        # --- index_<commit>.html ---
        ftp.storbinary(f"STOR {filename}", io.BytesIO(index_html.encode("utf-8")))
        print(f"  OK: {filename}")

        # --- index.html (リダイレクト) ---
        redirect = f'<meta http-equiv="refresh" content="0;url={filename}">'
        ftp.storbinary("STOR index.html", io.BytesIO(redirect.encode("utf-8")))
        print("  OK: index.html (redirect)")
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    url = f"{PUBLIC_URL}/{filename}"
    print(f"\n完了: {url}")


if __name__ == "__main__":
    main()
