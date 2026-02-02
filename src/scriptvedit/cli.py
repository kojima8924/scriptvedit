"""
scriptvedit コマンドラインインターフェース

サブコマンド:
    render: プロジェクトJSONをレンダリング
    preview: プロジェクトの一部をプレビュー
    gui: GUIエディタを起動
"""

import argparse
import sys
from pathlib import Path


def cmd_render(args):
    """render サブコマンド: プロジェクトJSONをレンダリング"""
    from .project import Project
    from .renderer import render

    project_path = Path(args.project)
    if not project_path.exists():
        print(f"エラー: プロジェクトファイルが見つかりません: {project_path}", file=sys.stderr)
        sys.exit(1)

    if not project_path.suffix.lower() == ".json":
        print(f"警告: プロジェクトファイルは .json 拡張子が推奨されます", file=sys.stderr)

    try:
        project = Project.load(str(project_path))
    except Exception as e:
        print(f"エラー: プロジェクトの読み込みに失敗: {e}", file=sys.stderr)
        sys.exit(1)

    output = args.output
    if output is None:
        output = project_path.stem + ".mp4"

    print(f"レンダリング中: {project_path} -> {output}")
    print(f"  解像度: {project.timeline.width}x{project.timeline.height}")
    print(f"  FPS: {project.timeline.fps}")
    print(f"  総再生時間: {project.total_duration:.2f}秒")

    try:
        render(
            project.timeline,
            output,
            verbose=args.verbose,
            dump_graph=args.dump_graph
        )
        print(f"完了: {output}")
    except Exception as e:
        print(f"エラー: レンダリングに失敗: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_preview(args):
    """preview サブコマンド: プロジェクトの一部をプレビュー"""
    from .project import Project
    from .renderer import render_preview

    project_path = Path(args.project)
    if not project_path.exists():
        print(f"エラー: プロジェクトファイルが見つかりません: {project_path}", file=sys.stderr)
        sys.exit(1)

    try:
        project = Project.load(str(project_path))
    except Exception as e:
        print(f"エラー: プロジェクトの読み込みに失敗: {e}", file=sys.stderr)
        sys.exit(1)

    center = args.time
    if center is None:
        center = project.total_duration / 2

    output = args.output
    if output is None:
        output = project_path.stem + "_preview.mp4"

    pre = args.pre
    post = args.post
    width = args.width or 640
    height = args.height or 360
    fps = args.fps or 15

    print(f"プレビュー生成: {project_path}")
    print(f"  中心時刻: {center:.2f}秒 (前後 -{pre}秒 / +{post}秒)")
    print(f"  解像度: {width}x{height} @ {fps}fps")

    try:
        actual_start, actual_end = render_preview(
            project.timeline,
            output,
            center_time=center,
            pre=pre,
            post=post,
            out_width=width,
            out_height=height,
            out_fps=fps,
            verbose=args.verbose,
            dump_graph=args.dump_graph
        )
        print(f"完了: {output}")
        print(f"  実際の範囲: {actual_start:.2f}秒 - {actual_end:.2f}秒")
    except Exception as e:
        print(f"エラー: プレビュー生成に失敗: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_gui(args):
    """gui サブコマンド: GUIエディタを起動"""
    try:
        from .gui import main as gui_main
        project_path = args.project if args.project else None
        gui_main(project_path)
    except ImportError as e:
        print(f"エラー: GUI を起動できません: {e}", file=sys.stderr)
        print("ヒント: pip install PySide6 を実行してください", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"エラー: GUI の起動に失敗: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """CLI エントリポイント"""
    parser = argparse.ArgumentParser(
        prog="scriptvedit",
        description="scriptvedit - スクリプトベースの動画編集ツール"
    )
    subparsers = parser.add_subparsers(dest="command", help="サブコマンド")

    # render サブコマンド
    render_parser = subparsers.add_parser(
        "render",
        help="プロジェクトJSONをレンダリング"
    )
    render_parser.add_argument(
        "project",
        help="プロジェクトJSONファイル"
    )
    render_parser.add_argument(
        "-o", "--output",
        help="出力ファイル（省略時は project名.mp4）"
    )
    render_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細出力を表示"
    )
    render_parser.add_argument(
        "--dump-graph",
        metavar="FILE",
        help="FFmpegフィルターグラフを保存するファイル"
    )
    render_parser.set_defaults(func=cmd_render)

    # preview サブコマンド
    preview_parser = subparsers.add_parser(
        "preview",
        help="プロジェクトの一部をプレビュー"
    )
    preview_parser.add_argument(
        "project",
        help="プロジェクトJSONファイル"
    )
    preview_parser.add_argument(
        "-t", "--time",
        type=float,
        help="プレビュー中心時刻（秒）"
    )
    preview_parser.add_argument(
        "--pre",
        type=float,
        default=2.0,
        help="中心時刻の前（秒）（デフォルト: 2.0）"
    )
    preview_parser.add_argument(
        "--post",
        type=float,
        default=2.0,
        help="中心時刻の後（秒）（デフォルト: 2.0）"
    )
    preview_parser.add_argument(
        "-o", "--output",
        help="出力ファイル（省略時は project名_preview.mp4）"
    )
    preview_parser.add_argument(
        "-W", "--width",
        type=int,
        help="プレビュー幅（デフォルト: 640）"
    )
    preview_parser.add_argument(
        "-H", "--height",
        type=int,
        help="プレビュー高さ（デフォルト: 360）"
    )
    preview_parser.add_argument(
        "--fps",
        type=int,
        help="プレビューFPS（デフォルト: 15）"
    )
    preview_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細出力を表示"
    )
    preview_parser.add_argument(
        "--dump-graph",
        metavar="FILE",
        help="FFmpegフィルターグラフを保存するファイル"
    )
    preview_parser.set_defaults(func=cmd_preview)

    # gui サブコマンド
    gui_parser = subparsers.add_parser(
        "gui",
        help="GUIエディタを起動"
    )
    gui_parser.add_argument(
        "project",
        nargs="?",
        help="開くプロジェクトJSONファイル（省略可）"
    )
    gui_parser.set_defaults(func=cmd_gui)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
