from utilities.fr24_client import build_api
from threading import Thread, Lock
from time import sleep
import math
import logging

from requests.exceptions import ConnectionError
from urllib3.exceptions import NewConnectionError
from urllib3.exceptions import MaxRetryError

# Configure logging to output to a file
logging.basicConfig(
    filename="/home/pi/overhead_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# Load MIN_ALTITUDE and MAX_ALTITUDE from config.py
try:
    from config import MIN_ALTITUDE, MAX_ALTITUDE
    logging.info(f"Loaded from config: MIN_ALTITUDE = {MIN_ALTITUDE}, MAX_ALTITUDE = {MAX_ALTITUDE}")
except (ModuleNotFoundError, NameError, ImportError):
    # Fallback if the values are not in config.py
    MIN_ALTITUDE = 950  # feet
    MAX_ALTITUDE = 10000  # feet
    logging.info(f"Using fallback: MIN_ALTITUDE = {MIN_ALTITUDE}, MAX_ALTITUDE = {MAX_ALTITUDE}")


RETRIES = 3
RATE_LIMIT_DELAY = 1
MAX_FLIGHT_LOOKUP = 5
#MAX_ALTITUDE = 10000  # feet
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]
AIRCRAFT_FULL_NAMES = {
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A20N": "Airbus A320neo",
    "A321": "Airbus A321",
    "A21N": "Airbus A321neo",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A359": "Airbus A350-900",
    "B37M": "Boeing 737 MAX 7",
    "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9",
    "B737": "Boeing 737-700",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B752": "Boeing 757-200",
    "B753": "Boeing 757-300",
    "B763": "Boeing 767-300",
    "B772": "Boeing 777-200",
    "B77W": "Boeing 777-300ER",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "CRJ2": "Bombardier CRJ-200",
    "CRJ7": "Bombardier CRJ-700",
    "CRJ9": "Bombardier CRJ-900",
    "E170": "Embraer 170",
    "E175": "Embraer 175",
    "E190": "Embraer 190",
    "C172": "Cessna 172",
    "C25A": "Cessna Citation CJ2",
    "C25B": "Cessna Citation CJ3",
    "C25C": "Cessna Citation CJ4",
    "C525": "Cessna CitationJet CJ1",
    "C560": "Cessna Citation V",
    "C56X": "Cessna Citation Excel/XLS",
    "C68A": "Cessna Citation Latitude",
    "C700": "Cessna Citation Longitude",
    "C750": "Cessna Citation X",
    "CL30": "Bombardier Challenger 300",
    "CL35": "Bombardier Challenger 350",
    "E550": "Embraer Legacy 500",
    "E55P": "Embraer Phenom 300",
    "FA8X": "Dassault Falcon 8X",
    "GA5C": "Gulfstream G500",
    "GLF5": "Gulfstream G-V",
    "GLF6": "Gulfstream G650",
    "LJ40": "Learjet 40",
    "P28A": "Piper PA-28",
    "SR22": "Cirrus SR22",
}


def aircraft_full_name(code):
    code = clean_text(code).upper()
    return AIRCRAFT_FULL_NAMES.get(code, code)


def clean_text(value):
    value = "" if value is None else str(value).strip()
    return "" if value.upper() in BLANK_FIELDS else value


def flight_to_data_row(flight):
    aircraft_code = clean_text(getattr(flight, "aircraft_code", ""))
    return {
        "fr24_id": clean_text(getattr(flight, "id", "")),
        "registration": clean_text(getattr(flight, "registration", "")),
        "plane": aircraft_code,
        "plane_full_name": aircraft_full_name(aircraft_code),
        "origin": clean_text(getattr(flight, "origin_airport_iata", "")),
        "destination": clean_text(getattr(flight, "destination_airport_iata", "")),
        "vertical_speed": getattr(flight, "vertical_speed", None),
        "altitude": getattr(flight, "altitude", None),
        "heading": getattr(flight, "heading", None),
        "callsign": clean_text(getattr(flight, "callsign", "")),
        "ground_speed": getattr(flight, "ground_speed", None),
        "airline": clean_text(getattr(flight, "airline_icao", "")),
        "squawk": clean_text(getattr(flight, "squawk", "")),
    }

try:
    # Attempt to load config data
    from config import ZONE_HOME, LOCATION_HOME

    ZONE_DEFAULT = ZONE_HOME
    LOCATION_DEFAULT = LOCATION_HOME

except (ModuleNotFoundError, NameError, ImportError):
    # If there's no config data
    # Generic placeholder area — override with your own ZONE_HOME/LOCATION_HOME
    # in config.py (see config.py.example).
    ZONE_DEFAULT = {"tl_y": 0.02, "tl_x": -0.02, "br_y": -0.02, "br_x": 0.02}
    LOCATION_DEFAULT = [0.0, 0.0, EARTH_RADIUS_KM]

# Optional ground-speed filter (raw units, confirmed as knots)
try:
    from config import MIN_GROUNDSPEED, MAX_GROUNDSPEED  # e.g. 120 / 560 (None disables)
except Exception:
    MIN_GROUNDSPEED = None
    MAX_GROUNDSPEED = None


def distance_from_flight_to_home(flight, home=LOCATION_DEFAULT):
    def polar_to_cartesian(lat, long, alt):
        DEG2RAD = math.pi / 180
        return [
            alt * math.cos(DEG2RAD * lat) * math.sin(DEG2RAD * long),
            alt * math.sin(DEG2RAD * lat),
            alt * math.cos(DEG2RAD * lat) * math.cos(DEG2RAD * long),
        ]

    def feet_to_meters_plus_earth(altitude_ft):
        altitude_km = 0.0003048 * altitude_ft
        return altitude_km + EARTH_RADIUS_KM

    try:
        (x0, y0, z0) = polar_to_cartesian(
            flight.latitude,
            flight.longitude,
            feet_to_meters_plus_earth(flight.altitude),
        )

        (x1, y1, z1) = polar_to_cartesian(*home)

        dist = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)

        return dist

    except AttributeError:
        # on error say it's far away
        return 1e6


class Overhead:
    def __init__(self):
        self._api = build_api()
        self._lock = Lock()
        self._data = []
        self._new_data = False
        self._processing = False

    def grab_data(self):
        Thread(target=self._grab_data, daemon=True).start()


    def _grab_data(self):
        # Mark data as old
        with self._lock:
            self._new_data = False
            self._processing = True

        data = []

        # Grab flight details
        try:
            bounds = self._api.get_bounds(ZONE_DEFAULT)
            flights = self._api.get_flights(bounds=bounds)

            # Sort flights by closest first
            def _speed_ok_raw(f):
                """
                Use ground_speed as-is (API returns knots).
                If MIN/MAX_GROUNDSPEED are None, the check is disabled.
                """
                try:
                    v = getattr(f, "ground_speed", None)
                    if v is None:
                        return True  # keep if unknown; change to False to be strict
                    if MIN_GROUNDSPEED is not None and v < MIN_GROUNDSPEED:
                        return False
                    if MAX_GROUNDSPEED is not None and v > MAX_GROUNDSPEED:
                        return False
                    return True
                except Exception:
                    return True

            # Altitude + optional speed filter, then nearest-first
            flights = [
                f for f in flights
                if (getattr(f, "altitude", 0) > MIN_ALTITUDE and getattr(f, "altitude", 0) < MAX_ALTITUDE) and _speed_ok_raw(f)
            ]
            flights = sorted(flights, key=lambda f: distance_from_flight_to_home(f))


            for flight in flights[:MAX_FLIGHT_LOOKUP]:
                # FR24's old clickhandler detail endpoint is now Cloudflare-blocked.
                # The feed.js payload still contains the fields the display needs.
                data.append(flight_to_data_row(flight))

            with self._lock:
                self._new_data = True
                self._processing = False
                self._data = data

        except (ConnectionError, NewConnectionError, MaxRetryError):
            self._new_data = False
            self._processing = False

    def find_live_flight(self, target):
        bounds = self._api.get_bounds(ZONE_DEFAULT)
        flights = self._api.get_flights(bounds=bounds)

        target_fr24_id = clean_text(target.get("fr24_id", ""))
        target_registration = clean_text(target.get("registration", "")).upper()
        target_callsign = clean_text(target.get("callsign", "")).upper()
        rows = [flight_to_data_row(flight) for flight in flights]

        if target_fr24_id:
            for row in rows:
                if clean_text(row.get("fr24_id", "")) == target_fr24_id:
                    return row

        if target_registration:
            for row in rows:
                if clean_text(row.get("registration", "")).upper() == target_registration:
                    return row

        if target_callsign:
            for row in rows:
                if clean_text(row.get("callsign", "")).upper() == target_callsign:
                    return row

        return None

    @property
    def new_data(self):
        with self._lock:
            return self._new_data

    @property
    def processing(self):
        with self._lock:
            return self._processing

    @property
    def data(self):
        with self._lock:
            self._new_data = False
            return self._data

    @property
    def data_is_empty(self):
        return len(self._data) == 0


# Main function
if __name__ == "__main__":

    o = Overhead()
    o.grab_data()
    while not o.new_data:
        print("processing...")
        sleep(1)

    print(o.data)
