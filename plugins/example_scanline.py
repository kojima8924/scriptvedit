"""サンプルプラグイン: 走査線（CRT風）

geq のみのシンプル構成。darkness は type="expr" なので
scanline(darkness=lambda u: u) のように live アニメーションできる。
"""
from scriptvedit import effect_plugin


@effect_plugin(
    "scanline",
    bakeable=True,
    category="視覚効果",
    params={
        "spacing": {"type": "int", "default": 4, "min": 2, "max": 256,
                    "desc": "走査線の周期(px)"},
        "darkness": {"type": "expr", "default": 0.35, "min": 0, "max": 1,
                     "desc": "暗くする強さ 0〜1(Expr/lambda可 = liveアニメ)"},
        "speed": {"type": "number", "default": 0.0, "min": -2000, "max": 2000,
                  "desc": "走査線が流れる速度(px/秒)"},
    },
)
def build_scanline(params, ctx):
    """CRT風の走査線（周期・濃さ・流れる速度を指定、濃さはliveアニメ可）"""
    sp = params["spacing"]
    d = params["darkness"].to_ffmpeg(ctx["u_T"])
    speed = params["speed"]
    # 走査線の位置（speed!=0 なら経過時間で流れる）
    offset = f"+{speed}*(T-{ctx['start']})" if speed else ""
    line = f"mod(Y{offset}\\,{sp})"
    # 周期の前半だけ暗くする係数
    k = f"(1-clip({d}\\,0\\,1)*lt({line}\\,{sp}/2))"
    return [
        "format=rgba",
        f"geq=r='r(X\\,Y)*{k}':g='g(X\\,Y)*{k}':b='b(X\\,Y)*{k}':a='alpha(X\\,Y)'",
    ]
