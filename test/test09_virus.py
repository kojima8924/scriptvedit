from scriptvedit import *

virus = Object("../virus_message_fuyoufukyu_gaisyutsu.png")
virus <= resize(sx=0.15, sy=0.15)
virus.time(4) <= move(from_x=0.1, from_y=0.9, to_x=0.5, to_y=0.5, anchor="center") & scale(lambda u: lerp(0.5, 1, u))
