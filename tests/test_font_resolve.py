# フォント解決のクロスプラットフォームテスト（issue #1）
#
# 実行OSに依存せず、monkeypatch で「非Windows環境」を模擬して
# 既定フォント候補・環境変数上書き・エラーメッセージを検証する。
import os
import sys

import pytest

from scriptvedit.text import (
    _FONT_CANDIDATES_BY_OS,
    _DEFAULT_FONT_CANDIDATES,
    _ordered_font_candidates,
    _platform_key,
    _resolve_font,
)

# issue #1 の報告者が Ubuntu 24.04 で実在を検証済みのパス
NOTO_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
HIRAGINO_PATH = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"


def _only_exists(monkeypatch, *paths):
    """os.path.exists を「指定パスのみ存在する」ように差し替える"""
    real = os.path.exists
    allowed = set(paths)
    monkeypatch.setattr(os.path, "exists", lambda p: p in allowed)
    return real


class TestCandidates:
    """既定フォント候補リストの内容と並び順"""

    def test_全OSの候補が含まれる(self):
        assert "C:/Windows/Fonts/meiryo.ttc" in _DEFAULT_FONT_CANDIDATES
        assert NOTO_PATH in _DEFAULT_FONT_CANDIDATES
        assert HIRAGINO_PATH in _DEFAULT_FONT_CANDIDATES

    def test_linux優先の並び順(self):
        cands = _ordered_font_candidates("linux")
        # Linux 候補群が先頭に来る（先頭は Noto CJK）
        assert cands[0] == NOTO_PATH
        n_linux = len(_FONT_CANDIDATES_BY_OS["linux"])
        assert cands[:n_linux] == _FONT_CANDIDATES_BY_OS["linux"]
        # 他OSの候補も後続に残る（コンテナ等での救済用）
        assert "C:/Windows/Fonts/meiryo.ttc" in cands[n_linux:]

    def test_darwin優先の並び順(self):
        cands = _ordered_font_candidates("darwin")
        assert cands[0] == HIRAGINO_PATH

    def test_windows優先の並び順(self):
        cands = _ordered_font_candidates("windows")
        assert cands[0] == "C:/Windows/Fonts/meiryo.ttc"

    def test_platform_key(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert _platform_key() == "linux"
        monkeypatch.setattr(sys, "platform", "darwin")
        assert _platform_key() == "darwin"
        monkeypatch.setattr(sys, "platform", "win32")
        assert _platform_key() == "windows"


class TestResolveNonWindows:
    """非Windows環境の模擬（os.path.exists 差し替え）"""

    def test_ubuntuではnoto_cjkが自動採用される(self, monkeypatch):
        monkeypatch.delenv("SCRIPTVEDIT_FONT", raising=False)
        _only_exists(monkeypatch, NOTO_PATH)
        assert _resolve_font(None) == NOTO_PATH

    def test_macosではヒラギノが自動採用される(self, monkeypatch):
        monkeypatch.delenv("SCRIPTVEDIT_FONT", raising=False)
        _only_exists(monkeypatch, HIRAGINO_PATH)
        assert _resolve_font(None) == HIRAGINO_PATH

    def test_全滅時はOS別の導入例つきエラー(self, monkeypatch):
        monkeypatch.delenv("SCRIPTVEDIT_FONT", raising=False)
        _only_exists(monkeypatch)  # 何も存在しない
        with pytest.raises(FileNotFoundError) as ei:
            _resolve_font(None)
        msg = str(ei.value)
        assert "apt install fonts-noto-cjk" in msg      # Linux導入例
        assert "meiryo.ttc" in msg                       # Windows案内
        assert "ヒラギノ" in msg                          # macOS案内
        assert "SCRIPTVEDIT_FONT" in msg                 # 環境変数の案内
        assert NOTO_PATH in msg                          # 探索候補の列挙


class TestEnvOverride:
    """環境変数 SCRIPTVEDIT_FONT による上書き"""

    def test_env指定が候補より優先される(self, monkeypatch):
        env_font = "/opt/fonts/MyFont.ttf"
        monkeypatch.setenv("SCRIPTVEDIT_FONT", env_font)
        _only_exists(monkeypatch, env_font, NOTO_PATH)
        assert _resolve_font(None) == env_font

    def test_env指定が不在ならエラー(self, monkeypatch):
        monkeypatch.setenv("SCRIPTVEDIT_FONT", "/no/such/font.ttf")
        _only_exists(monkeypatch, NOTO_PATH)
        with pytest.raises(FileNotFoundError) as ei:
            _resolve_font(None)
        assert "SCRIPTVEDIT_FONT" in str(ei.value)

    def test_font引数はenvより優先される(self, monkeypatch):
        env_font = "/opt/fonts/MyFont.ttf"
        explicit = "/opt/fonts/Explicit.ttf"
        monkeypatch.setenv("SCRIPTVEDIT_FONT", env_font)
        _only_exists(monkeypatch, env_font, explicit)
        assert _resolve_font(explicit) == explicit
