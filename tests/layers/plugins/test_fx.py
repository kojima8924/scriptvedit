"""テスト用プラグイン（test/plugins/ の自動読込を検証する）"""
from scriptvedit import effect_plugin


@effect_plugin(
    "tint_wash",
    bakeable=True,
    category="テスト",
    params={
        "color": {"type": "color", "default": "red", "desc": "着色する色"},
        "amount": {"type": "expr", "default": 0.5, "min": 0, "max": 1,
                   "desc": "着色の強さ(Expr可)"},
    },
)
def build_tint_wash(params, ctx):
    """指定色で画面を洗う（テスト用の単純な着色）"""
    cr, cg, cb = ctx["parse_color"](params["color"])
    a = params["amount"].to_ffmpeg(ctx["u_T"])
    k = f"clip({a}\\,0\\,1)"
    return [
        "format=rgba",
        f"geq=r='r(X\\,Y)*(1-{k})+{cr}*{k}':g='g(X\\,Y)*(1-{k})+{cg}*{k}'"
        f":b='b(X\\,Y)*(1-{k})+{cb}*{k}':a='alpha(X\\,Y)'",
    ]


@effect_plugin(
    "test_live_only",
    bakeable=False,
    category="テスト",
    params={
        "mode": {"type": "choice", "default": "soft",
                 "choices": ["soft", "hard"], "desc": "モード"},
        "gamma": {"type": "number", "default": 1.0, "min": 0.1, "max": 10,
                  "desc": "ガンマ"},
    },
)
def build_test_live_only(params, ctx):
    """bakeable=False のプラグイン（チェックポイント対象外）"""
    g = params["gamma"] if params["mode"] == "soft" else params["gamma"] * 2
    return [f"eq=gamma={g}"]
