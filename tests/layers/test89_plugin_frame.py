from scriptvedit import *

# プラグインEffect: photo_frame は pad でキャンバスを広げ、
# ctx["expand_pad"] で overlay 中央配置基準(pad_size)を更新する。
# policy="off"(-op) でベイクさせず、本レンダの live 経路で pad_size を検証する
# （scale の pad サイズ + 枠の 2*width が overlay 位置に反映される）。
oni = Object(asset("images/shape_badge.png"))
oni.time(2) <= (-scale(lambda u: 0.5 + 0.1 * u)
                & -photo_frame(width=12, color="white")
                & move(x=0.5, y=0.5, anchor="center"))
