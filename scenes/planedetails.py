import json
import os
import time
from threading import Thread
from rgbmatrix import graphics

from utilities.animator import Animator
from setup import colours, fonts, screen

# ---- Optional master toggle from config.py (kept for convenience) ----
try:
    from config import SHOW_PLANE_DETAILS
except Exception:
    SHOW_PLANE_DETAILS = True

# ---- Settings file (edited by your Flask UI) ----
SETTINGS_FILE = "/home/pi/its-a-plane-python/settings/plane_details.json"
LIVE_MODE_FILE = "/home/pi/its-a-plane-python/settings/live_mode.json"

# Default set of fields if settings file is missing
# You can change this default, it’s only used the first time.
DEFAULT_FIELDS = ["plane", "route", "ground_speed", "heading"]

# All supported fields (must match keys in overhead.py data)
ALLOWED_FIELDS = {
    "plane",          # aircraft model/name (string)
    "plane_full_name",# aircraft full name from local feed.js code map (string)
    "route",          # "ORIGIN→DEST" using IATA codes (string)
    "callsign",       # callsign (string)
    "airline",        # airline name (string)
    "ground_speed",   # kts (number)
    "heading",        # degrees 0–359 (number)
    "altitude",       # feet (number)
    "vertical_speed", # fpm (number)
    "squawk",         # squawk code (string/number)
}

# Order to render on the display. We’ll include only the ones the user selected.
FIELD_ORDER = [
    "airline",
    "plane",
    "plane_full_name",
    "callsign",
    "route",
    "altitude",
    "ground_speed",
    "heading",
    "vertical_speed",
    "squawk",
]

# ---- Visual setup ----
PLANE_DETAILS_COLOUR = colours.PINK
PLANE_DISTANCE_FROM_TOP = 30
PLANE_TEXT_HEIGHT = 9
PLANE_FONT = fonts.regular
LIVE_MODE_TIMEOUT_SECONDS = 120
LIVE_MODE_COOLDOWN_SECONDS = 600
LIVE_MODE_FETCH_SECONDS = 2.0
LIVE_MODE_MISSING_LIMIT = 10
LIVE_PANEL_TOP = 13


def ensure_settings_file():
    """Create default settings file on first run."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"fields": DEFAULT_FIELDS}, f)
    except Exception:
        # If this fails, we’ll just fall back to defaults at runtime.
        pass


def load_selected_fields():
    """Return list of enabled fields, filtered to allowed ones."""
    ensure_settings_file()
    try:
        with open(SETTINGS_FILE, "r") as f:
            obj = json.load(f)
        fields = obj.get("fields", DEFAULT_FIELDS)
        # sanitize
        fields = [x for x in fields if x in ALLOWED_FIELDS]
        if "plane" in fields and "plane_full_name" in fields:
            fields = [x for x in fields if x != "plane"]
        # if user somehow unchecked everything, fall back to defaults
        return fields or DEFAULT_FIELDS
    except Exception:
        return DEFAULT_FIELDS


def fmt_route(d):
    """Format origin→destination, handling blanks."""
    o = (d.get("origin") or "").strip()
    t = (d.get("destination") or "").strip()
    if o and t:
        return f"{o}→{t}"
    return o or t or ""


def fmt_num(val):
    """Turn None into '', keep ints/floats readable."""
    return "" if val is None else str(val)


def read_live_mode_enabled():
    try:
        with open(LIVE_MODE_FILE, "r") as f:
            return bool(json.load(f).get("enabled", False))
    except Exception:
        return False


def write_live_mode_enabled(enabled, reason=""):
    try:
        state = {"enabled": bool(enabled), "reason": reason, "updated_at": time.time()}
        if not enabled and reason == "timeout":
            state["cooldown_until"] = time.time() + LIVE_MODE_COOLDOWN_SECONDS
        os.makedirs(os.path.dirname(LIVE_MODE_FILE), exist_ok=True)
        with open(LIVE_MODE_FILE, "w") as f:
            json.dump(state, f)
        try:
            os.chmod(LIVE_MODE_FILE, 0o666)
        except Exception:
            pass
    except Exception:
        pass


def numeric(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def build_parts_for_fields(d, selected_fields):
    """Build a list of text parts in the FIELD_ORDER, only for selected fields."""
    parts = []

    for key in FIELD_ORDER:
        if key not in selected_fields:
            continue

        if key == "route":
            r = fmt_route(d)
            if r:
                parts.append(r)

        elif key == "plane":
            v = (d.get("plane") or "").strip()
            if v:
                parts.append(v)

        elif key == "plane_full_name":
            v = (d.get("plane_full_name") or "").strip()
            if v:
                parts.append(v)

        elif key == "callsign":
            v = (d.get("callsign") or "").strip()
            if v:
                parts.append(v)

        elif key == "airline":
            v = (d.get("airline") or "").strip()
            if v:
                parts.append(v)

        elif key == "ground_speed":
            v = d.get("ground_speed")
            if v is not None:
                parts.append(f"{fmt_num(v)} kts")

        elif key == "heading":
            v = d.get("heading")
            if v is not None:
                parts.append(f"HDG {fmt_num(v) or '—'}°")

        elif key == "altitude":
            v = d.get("altitude")
            if v is not None:
                parts.append(f"{fmt_num(v)} ft")

        elif key == "vertical_speed":
            v = d.get("vertical_speed")
            if v is not None:
                parts.append(f"{fmt_num(v)} fpm")

        elif key == "squawk":
            v = d.get("squawk")
            if v not in (None, "", "NONE"):
                parts.append(f"SQ {v}")

    return parts


class PlaneDetailsScene(object):
    def __init__(self):
        super().__init__()
        self.plane_position = screen.WIDTH
        self._data_all_looped = False
        self.scroll_speed = 1
        self._live_mode_locked = False
        self._live_target = None
        self._live_sample = None
        self._live_started_at = None
        self._live_last_fetch_at = 0
        self._live_misses = 0
        self._live_speed_display = None
        self._live_altitude_display = None
        self._live_last_render_at = None
        self._live_fetching = False
        self._live_pending_result = None
        self._live_pending_miss = False
        self._live_tracking_lost = False
        self._live_settings_checked_at = 0
        self._live_settings_enabled = False

    def _live_mode_enabled(self):
        now = time.time()
        if now - self._live_settings_checked_at > 0.25:
            self._live_settings_enabled = read_live_mode_enabled()
            self._live_settings_checked_at = now
        return self._live_settings_enabled

    def _reset_live_mode(self):
        self._live_mode_locked = False
        self._live_target = None
        self._live_sample = None
        self._live_started_at = None
        self._live_last_fetch_at = 0
        self._live_misses = 0
        self._live_speed_display = None
        self._live_altitude_display = None
        self._live_last_render_at = None
        self._live_fetching = False
        self._live_pending_result = None
        self._live_pending_miss = False
        self._live_tracking_lost = False

    def _stop_live_mode(self, reason):
        write_live_mode_enabled(False, reason)
        self._live_settings_enabled = False
        self._live_settings_checked_at = time.time()
        self._reset_live_mode()
        self.plane_position = screen.WIDTH
        self.draw_square(0, LIVE_PANEL_TOP, screen.WIDTH, screen.HEIGHT, colours.BLACK)
        self.reset_scene()

    def _lock_live_mode_plane(self):
        if len(self._data) == 0:
            return False

        self._live_target = dict(self._data[self._data_index])
        self._live_sample = dict(self._live_target)
        self._live_started_at = time.time()
        self._live_last_fetch_at = 0
        self._live_misses = 0
        self._live_speed_display = numeric(self._live_sample.get("ground_speed"))
        self._live_altitude_display = numeric(self._live_sample.get("altitude"))
        self._live_last_render_at = time.time()
        self._live_tracking_lost = False
        self._live_mode_locked = True
        self._data_all_looped = True
        return True

    def _live_fetch_worker(self, target):
        try:
            updated = self.overhead.find_live_flight(target)
        except Exception:
            updated = None

        if updated:
            self._live_pending_result = updated
        else:
            self._live_pending_miss = True
        self._live_fetching = False

    def _apply_live_fetch_result(self):
        if self._live_pending_result is not None:
            self._live_sample = self._live_pending_result
            self._live_target = self._live_pending_result
            self._live_pending_result = None
            self._live_pending_miss = False
            self._live_tracking_lost = False
            self._live_misses = 0
            return

        if self._live_pending_miss:
            self._live_pending_miss = False
            self._live_misses += 1
            if self._live_misses >= LIVE_MODE_MISSING_LIMIT:
                self._live_tracking_lost = True

    def _refresh_live_sample_if_due(self):
        now = time.time()
        if self._live_started_at and now - self._live_started_at > LIVE_MODE_TIMEOUT_SECONDS:
            self._stop_live_mode("timeout")
            return

        self._apply_live_fetch_result()
        if self._live_tracking_lost:
            return

        if self._live_fetching:
            return

        if now - self._live_last_fetch_at < LIVE_MODE_FETCH_SECONDS:
            return

        self._live_last_fetch_at = now
        self._live_fetching = True
        Thread(target=self._live_fetch_worker, args=(dict(self._live_target),), daemon=True).start()

    def _smooth_live_numbers(self):
        if not self._live_sample:
            return None, None

        target_speed = numeric(self._live_sample.get("ground_speed"))
        target_altitude = numeric(self._live_sample.get("altitude"))
        vertical_speed = numeric(self._live_sample.get("vertical_speed")) or 0
        now = time.time()
        elapsed = max(0, now - self._live_last_fetch_at)
        frame_elapsed = 0 if self._live_last_render_at is None else max(0, now - self._live_last_render_at)
        self._live_last_render_at = now

        if target_altitude is not None:
            predicted_altitude = target_altitude + (vertical_speed / 60.0 * elapsed)
            if self._live_altitude_display is None:
                self._live_altitude_display = predicted_altitude
            else:
                self._live_altitude_display += vertical_speed / 60.0 * frame_elapsed
                self._live_altitude_display += (predicted_altitude - self._live_altitude_display) * 0.35

        if target_speed is not None:
            if self._live_speed_display is None:
                self._live_speed_display = target_speed
            else:
                self._live_speed_display += (target_speed - self._live_speed_display) * 0.35

        return self._live_speed_display, self._live_altitude_display

    def _draw_live_waiting(self):
        self.draw_square(0, LIVE_PANEL_TOP, screen.WIDTH, screen.HEIGHT, colours.BLACK)
        graphics.DrawLine(self.canvas, 0, LIVE_PANEL_TOP, screen.WIDTH - 1, LIVE_PANEL_TOP, colours.RED)
        graphics.DrawText(self.canvas, fonts.small, 10, 28, colours.WHITE, "waiting")

    def _draw_live_panel(self):
        row = self._live_sample or self._live_target or {}
        speed, altitude = self._smooth_live_numbers()
        callsign = (row.get("callsign") or row.get("registration") or "PLANE").strip()
        aircraft_code = (row.get("plane") or "").strip()
        speed_text = "---" if speed is None else str(int(round(speed)))
        altitude_text = "-----" if altitude is None else str(int(round(altitude)))

        self.draw_square(0, LIVE_PANEL_TOP, screen.WIDTH, screen.HEIGHT, colours.BLACK)
        graphics.DrawLine(self.canvas, 0, LIVE_PANEL_TOP, screen.WIDTH - 1, LIVE_PANEL_TOP, colours.RED)
        graphics.DrawLine(self.canvas, 0, 31, screen.WIDTH - 1, 31, colours.RED)
        graphics.DrawLine(self.canvas, 0, LIVE_PANEL_TOP, 0, 31, colours.RED)
        graphics.DrawLine(self.canvas, screen.WIDTH - 1, LIVE_PANEL_TOP, screen.WIDTH - 1, 31, colours.RED)
        graphics.DrawText(self.canvas, fonts.extrasmall, 2, 20, colours.GREY, "kts")
        graphics.DrawText(self.canvas, fonts.extrasmall, 31, 20, colours.GREY, "ft")
        if aircraft_code:
            graphics.DrawText(self.canvas, fonts.extrasmall, 45, 20, colours.PINK, aircraft_code[:4])
        graphics.DrawText(self.canvas, fonts.regular, 2, 31, colours.WHITE, speed_text[-3:])
        graphics.DrawText(self.canvas, fonts.regular, 31, 31, colours.YELLOW, altitude_text[-5:])

    def _render_live_mode(self):
        if not self._live_mode_locked and not self._lock_live_mode_plane():
            if self._live_sample or self._live_target:
                self._draw_live_panel()
            else:
                self._draw_live_waiting()
            return

        self._refresh_live_sample_if_due()
        if self._live_mode_locked:
            self._draw_live_panel()

    @Animator.KeyFrame.add(1)
    def plane_details(self, count):
        # Optional global kill-switch
        if not SHOW_PLANE_DETAILS:
            self.draw_square(
                0,
                PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
                screen.WIDTH,
                screen.HEIGHT,
                colours.BLACK,
            )
            return

        # Guard against no data
        if len(self._data) == 0:
            if self._live_mode_enabled():
                self._render_live_mode()
            return

        if self._live_mode_enabled():
            self._render_live_mode()
            return

        if self._live_mode_locked:
            self._reset_live_mode()
            self.plane_position = screen.WIDTH
            self.draw_square(0, LIVE_PANEL_TOP, screen.WIDTH, screen.HEIGHT, colours.BLACK)
            self.reset_scene()
            return

        # Build line based on current settings
        selected = load_selected_fields()
        d = self._data[self._data_index]
        parts = build_parts_for_fields(d, selected)
        full_details = " - ".join([p for p in parts if p])

        # Draw background strip
        self.draw_square(
            0,
            PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
            screen.WIDTH,
            screen.HEIGHT,
            colours.BLACK,
        )

        # Draw text (empty string is fine; it just draws nothing)
        text_length = graphics.DrawText(
            self.canvas,
            PLANE_FONT,
            self.plane_position,
            PLANE_DISTANCE_FROM_TOP,
            PLANE_DETAILS_COLOUR,
            full_details,
        )

        # Scroll
        self.plane_position -= self.scroll_speed
        if self.plane_position + text_length < 0:
            self.plane_position = screen.WIDTH
            if len(self._data) > 1:
                self._data_index = (self._data_index + 1) % len(self._data)
                self._data_all_looped = (not self._data_index) or self._data_all_looped
                self.reset_scene()

    @Animator.KeyFrame.add(0)
    def reset_scrolling(self):
        self.plane_position = screen.WIDTH
