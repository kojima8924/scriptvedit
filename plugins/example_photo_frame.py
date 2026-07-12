"""サンプルプラグイン: 写真フレーム風の縁取り

pad でキャンバスを広げるプラグインの書き方の例。
広げた分は必ず ctx["expand_pad"](dw, dh) で申告する
（overlay の中央配置基準 pad_size が更新され、位置ずれを防ぐ）。
"""
from scriptvedit import effect_plugin


@effect_plugin(
    "photo_frame",
    bakeable=True,
    category="装飾",
    params={
        "width": {"type": "int", "default": 20, "min": 1, "max": 500,
                  "desc": "枠の太さ(px)"},
        "color": {"type": "ffcolor", "default": "white", "desc": "枠の色"},
    },
)
def build_photo_frame(params, ctx):
    """写真フレーム風の枠を付ける（padでキャンバスを拡張）"""
    w = params["width"]
    color = params["color"]
    # pad で広げた分を overlay 中央配置基準へ反映（規約）
    ctx["expand_pad"](2 * w, 2 * w)
    return [
        "format=rgba",
        f"pad=iw+{2 * w}:ih+{2 * w}:{w}:{w}:color={color}",
    ]
