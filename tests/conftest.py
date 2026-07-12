# -*- coding: utf-8 -*-
"""pytest 共通設定

- `tests/layers/` はレイヤー定義ファイル（testNN_*.py）とテスト用プラグインの置き場であり、
  pytest のテストモジュールではないため収集対象から外す。
- スナップショット再生成用のオプション `--snapshot-update` を提供する。
"""
import os

# レイヤー定義（DSLスクリプト）は pytest のテストではない
collect_ignore = ["layers"]


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update", action="store_true", default=False,
        help="スナップショット(tests/snapshots/*.json)を現在の出力で再生成する")


def pytest_configure(config):
    # 実行ディレクトリに依存せず、キャッシュ(__cache__)はリポジトリルートに置く
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
