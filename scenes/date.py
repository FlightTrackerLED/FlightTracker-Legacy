from datetime import datetime
import pytz
from config import LOCATION_HOME, TIMEZONE
from utilities.animator import Animator
from setup import colours, fonts, frames
from rgbmatrix import graphics

# Setup
DATE_COLOUR = colours.PINK_DARKER
DATE_FONT = fonts.small
DATE_POSITION = (1, 31)

class DateScene(object):
    def __init__(self):
        super().__init__()
        self._last_date = None
        self._time_zone = self.detect_timezone()

    def detect_timezone(self):
        # Read the TIMEZONE from the config file
        try:
            return pytz.timezone(TIMEZONE)
        except Exception:
            # Fallback to UTC if the timezone is invalid
            return pytz.UTC

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def date(self, count):
        if len(self._data):
            self._last_date = None
        else:
            # Get current time based on the detected time zone
            now = datetime.now(self._time_zone)
            current_date = now.strftime("%-m-%-d-%Y")
           # current_date = now.strftime("%-d-%-m-%Y")


            if self._last_date != current_date:
                if self._last_date is not None:
                    # Clear the previous date
                    _ = graphics.DrawText(
                        self.canvas,
                        DATE_FONT,
                        DATE_POSITION[0],
                        DATE_POSITION[1],
                        colours.BLACK,
                        self._last_date,
                    )
                self._last_date = current_date
                # Draw the new date
                _ = graphics.DrawText(
                    self.canvas,
                    DATE_FONT,
                    DATE_POSITION[0],
                    DATE_POSITION[1],
                    DATE_COLOUR,
                    current_date,
                )
