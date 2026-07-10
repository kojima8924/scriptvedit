from scriptvedit import *

# chroma_key Effect: 緑色を透明化 + move
img = Object("../figure_cafe.png")
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= chroma_key(color="green", similarity=0.2, blend=0.1) & move(x=0.5, y=0.5, anchor="center")
