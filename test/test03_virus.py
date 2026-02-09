from scriptvedit import *

virus = Object("../virus_message_fuyoufukyu_gaisyutsu.png")
virus <= resize(sx=0.25, sy=0.25)
virus.time(5) <= move(from_x=1.0, from_y=0.3, to_x=0.0, to_y=0.7, anchor="center") & fade(alpha=0)
