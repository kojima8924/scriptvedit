"""サンプルプラグイン: ネオングロー

split + 着色 + gblur + blend=screen の複合サブグラフ。
ctx["label"] で一意ラベルを作り、他エフェクトとラベル衝突しないようにする例。
strength は type="expr" なので lambda/Expr を渡すと live アニメーションになる。
"""
from scriptvedit import effect_plugin


@effect_plugin(
    "neon_glow",
    bakeable=True,
    category="視覚効果",
    params={
        "radius": {"type": "number", "default": 10, "min": 0.1, "max": 200,
                   "desc": "発光のぼかし半径(sigma)"},
        "color": {"type": "color", "default": "cyan", "desc": "発光色"},
        "strength": {"type": "expr", "default": 1.0, "min": 0, "max": 4,
                     "desc": "発光の強さ(Expr/lambda可 = liveアニメ)"},
    },
)
def build_neon_glow(params, ctx):
    """ネオン風グロー（発光色を乗せたソフトグローをscreen合成）"""
    r = params["radius"]
    cr, cg, cb = ctx["parse_color"](params["color"])
    # 強さは T 基準の u 式で毎フレーム評価（geq は T を使う）
    s = params["strength"].to_ffmpeg(ctx["u_T"])
    k = f"clip({s}\\,0\\,4)"
    p = ctx["label"]
    return [
        "format=rgba",
        # 複製 → 輝度で着色 → ぼかし → 強さを乗算 → 本体へ screen 合成
        f"split[{p}a][{p}b];"
        f"[{p}b]geq="
        f"r='{cr}*(r(X\\,Y)/255)':g='{cg}*(g(X\\,Y)/255)':b='{cb}*(b(X\\,Y)/255)'"
        f":a='alpha(X\\,Y)',"
        f"gblur=sigma={r},"
        f"geq=r='clip(r(X\\,Y)*{k}\\,0\\,255)':g='clip(g(X\\,Y)*{k}\\,0\\,255)'"
        f":b='clip(b(X\\,Y)*{k}\\,0\\,255)':a='alpha(X\\,Y)'[{p}g];"
        f"[{p}a][{p}g]blend=all_mode=screen:all_opacity=1",
    ]
