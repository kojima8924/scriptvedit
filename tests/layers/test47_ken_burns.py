from scriptvedit import *

# ken_burns Effect: 矩形間パン&ズーム（crop+scale、イージング付き）
img = Object(asset("images/bg_pattern_tiles.jpg"))
img.time(3) <= ken_burns((0, 0, 800, 450), (200, 150, 400, 225), easing=ease_in_out_quad) & move(x=0.5, y=0.5, anchor="center")
