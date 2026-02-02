"""
scriptvedit コマンドラインインターフェース
"""

import argparse
import sys
import runpy


def main():
    """CLI エントリポイント"""
    parser = argparse.ArgumentParser(
        prog="scriptvedit",
        description="scriptvedit - スクリプトベースの動画編集ツール"
    )
    subparsers = parser.add_subparsers(dest="command", help="サブコマンド")

    # run サブコマンド
    run_parser = subparsers.add_parser(
        "run",
        help="Python スクリプトを実行"
    )
    run_parser.add_argument(
        "script",
        help="実行する Python スクリプト"
    )

    args = parser.parse_args()

    if args.command == "run":
        try:
            runpy.run_path(args.script, run_name="__main__")
        except FileNotFoundError:
            print(f"エラー: スクリプトが見つかりません: {args.script}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
