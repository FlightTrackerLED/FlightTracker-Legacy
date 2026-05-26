from datetime import datetime
from config import TIME_FORMAT_24H, TIMEZONE
import pytz
from utilities.animator import Animator
from setup import colours, fonts, frames

from rgbmatrix import graphics

# Setup
CLOCK_FONT = fonts.regular
CLOCK_POSITION = (1, 8)
CLOCK_COLOUR = colours.BLUE_DARK


class ClockScene(object):
    def __init__(self):
        super().__init__()
        self._last_time = None

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def clock(self, count):
        if len(self._data):
            # Ensure redraw when there's new data
            self._last_time = None

        else:
            # If there's no data to display then draw a clock

            # --- NEW: use configured timezone ---
            try:
                tz = pytz.timezone(TIMEZONE) if TIMEZONE else None
            except Exception:
                tz = None
            now = datetime.now(tz) if tz else datetime.now()

            # --- NEW: 24h / 12h toggle from config ---
            if TIME_FORMAT_24H:
                # 24-hour format (e.g., 16:07)
                current_time = now.strftime("%H:%M")
            else:
                # 12-hour with AM/PM, keep your original style (strip leading zero)
                hour = now.strftime("%I")          # leading zero
                minute = now.strftime("%M %p")     # minute + AM/PM
                current_time = f"{int(hour)}:{minute}"

            # Only draw if time needs updated
            if self._last_time != current_time:
                # Undraw last time if different from current
                if self._last_time is not None:
                    _ = graphics.DrawText(
                        self.canvas,
                        CLOCK_FONT,
                        CLOCK_POSITION[0],
                        CLOCK_POSITION[1],
                        colours.BLACK,
                        self._last_time,
                    )
                self._last_time = current_time

                # Draw Time
                _ = graphics.DrawText(
                    self.canvas,
                    CLOCK_FONT,
                    CLOCK_POSITION[0],
                    CLOCK_POSITION[1],
                    CLOCK_COLOUR,
                    current_time,
                )
