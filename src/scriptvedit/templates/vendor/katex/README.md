# 同梱 KaTeX (vendored)

- 由来: npm パッケージ `katex@0.17.0` の `dist/`
- 同梱物: `katex.min.css` / `katex.min.js` / `fonts/*.woff2`
  （woff2 のみ。Chromium は woff2 を読むため woff/ttf は不要）
- 用途: `formula()` / `formula_lines()` が Playwright(Chromium) でこの HTML/JS を
  レンダリングして数式の透過 PNG を生成する。**CDN は参照しない（オフライン動作）**。
- 更新手順: npm の tarball から上記ファイルを差し替え、
  `src/scriptvedit/formula.py` の `_FORMULA_VER` を上げる（キャッシュ無効化のため）。

## ライセンス（KaTeX / MIT）

```
The MIT License (MIT)

Copyright (c) 2013-2020 Khan Academy and other contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
