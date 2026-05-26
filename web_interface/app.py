from flask import Flask, request, render_template, jsonify
from geopy.geocoders import Nominatim
import pytz
import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify
import subprocess, datetime
import time

app = Flask(__name__)

CONFIG_FILE_PATH = "/home/pi/its-a-plane-python/config.py"


import json, os
from flask import Flask, render_template, request, redirect, url_for, jsonify

SETTINGS_FILE = "/home/pi/its-a-plane-python/settings/plane_details.json"
LIVE_MODE_FILE = "/home/pi/its-a-plane-python/settings/live_mode.json"

ALL_FIELDS = [
    ("plane", "Plane model/name"),
    ("plane_full_name", "Aircraft full name"),
    ("route", "Route (Origin→Destination)"),
    ("callsign", "Callsign"),
    ("airline", "Airline name"),
    ("ground_speed", "Ground speed"),
    ("heading", "Heading"),
    ("altitude", "Altitude"),
    ("vertical_speed", "Vertical speed"),
    ("squawk", "Squawk"),
]

PLANE_FIELD_EXAMPLES = {
    "plane": "A321",
    "plane_full_name": "Airbus A321",
    "route": "MSP→ATL",
    "callsign": "DAL1046",
    "airline": "DAL",
    "altitude": "34775 ft",
    "ground_speed": "516 kts",
    "heading": "HDG 156°",
    "vertical_speed": "832 fpm",
    "squawk": "SQ 1234",
}


def normalize_plane_detail_fields(fields):
    fields = [field for field in fields if field]
    if "plane" in fields and "plane_full_name" in fields:
        fields = [field for field in fields if field != "plane"]
    return fields


SYSTEMCTL = "/bin/systemctl" if os.path.exists("/bin/systemctl") else "/usr/bin/systemctl"
RESTART_LOG = "/home/pi/flask_restart.log"

def restart_service(unit_name: str):
    """Restart a systemd unit and return (ok, msg). Tries without sudo, then sudo -n."""
    cmds = [
        [SYSTEMCTL, "restart", "--no-block", unit_name],
        ["sudo", "-n", SYSTEMCTL, "restart", "--no-block", unit_name],
    ]
    last_err = ""
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
            if p.returncode == 0:
                return True, f"{' '.join(cmd)} OK"
            last_err = f"cmd={' '.join(cmd)} rc={p.returncode}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        except Exception as e:
            last_err = f"cmd={' '.join(cmd)} EXC: {e}"
    # log failure (non-fatal)
    try:
        with open(RESTART_LOG, "a") as lf:
            lf.write(f"[{datetime.datetime.now().isoformat()}] Restart failed:\n{last_err}\n")
    except Exception:
        pass
    return False, last_err



def read_plane_detail_fields():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return normalize_plane_detail_fields(json.load(f).get("fields", []))
    except Exception:
        return []

def write_plane_detail_fields(fields):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"fields": normalize_plane_detail_fields(fields)}, f)


def read_live_mode():
    try:
        with open(LIVE_MODE_FILE, "r") as f:
            obj = json.load(f)
    except Exception:
        obj = {}
    cooldown_until = obj.get("cooldown_until")
    try:
        cooldown_remaining = max(0, int(cooldown_until - time.time())) if cooldown_until else 0
    except Exception:
        cooldown_until = None
        cooldown_remaining = 0
    return {
        "enabled": bool(obj.get("enabled", False)),
        "reason": obj.get("reason", ""),
        "updated_at": obj.get("updated_at"),
        "cooldown_until": cooldown_until,
        "cooldown_remaining": cooldown_remaining,
        "cooldown_minutes": int((cooldown_remaining + 59) / 60),
    }


def set_live_mode(enabled):
    if enabled:
        current = read_live_mode()
        if current.get("cooldown_remaining", 0) > 0:
            return current

    os.makedirs(os.path.dirname(LIVE_MODE_FILE), exist_ok=True)
    with open(LIVE_MODE_FILE, "w") as f:
        json.dump(
            {
                "enabled": bool(enabled),
                "reason": "web_start" if enabled else "web_stop",
                "updated_at": datetime.datetime.now().timestamp(),
            },
            f,
        )
    os.chmod(LIVE_MODE_FILE, 0o666)
    return read_live_mode()



# Function to get current location from the config file
def get_current_location():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if "LOCATION_HOME" in line:
            location = lines[i + 1:i + 4]  # The next 3 lines contain the values
            return [float(loc.split(",")[0].split('#')[0].strip()) for loc in location if loc.strip()]

# Update the home location in the config file
def update_location(latitude, longitude, altitude):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    
    # Update home location
    for i, line in enumerate(lines):
        if "LOCATION_HOME" in line:
            lines[i + 1] = f"    {latitude},  # Latitude (deg)\n"
            lines[i + 2] = f"    {longitude},  # Longitude (deg)\n"
            lines[i + 3] = f"    {altitude},  # Altitude (kilometers)\n"
            break

    # Reverse geocode to get the city name and update the weather location
    city_name = get_city_name(latitude, longitude)
    for i, line in enumerate(lines):
        if "WEATHER_LOCATION" in line:
            lines[i] = f'WEATHER_LOCATION = "{city_name}"\n'
            break

    # Write updates back to the config file
    with open(CONFIG_FILE_PATH, 'w') as file:
        file.writelines(lines)

    # Restart the service
    os.system('sudo systemctl restart itsaplane.service')


# Function to reverse geocode and get the city name from coordinates
def get_city_name(latitude, longitude):
    geolocator = Nominatim(user_agent="your-app")
    location = geolocator.reverse(f"{latitude}, {longitude}")
    if location:
        address = location.raw['address']
        # Try getting city, town, village, or hamlet
        city_name = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet')
        if city_name:
            return city_name
    return "Unknown City"

# Update the weather location manually
def update_weather_location(city_name):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        if "WEATHER_LOCATION" in line:
            lines[i] = f'WEATHER_LOCATION = "{city_name}"\n'
            break
    with open(CONFIG_FILE_PATH, 'w') as file:
        file.writelines(lines)
    os.system('sudo systemctl restart itsaplane.service')

# Function to get ZONE_HOME from the config file
def get_zone_home():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    zone_home = {}
    for i, line in enumerate(lines):
        if "ZONE_HOME" in line:
            zone_home["tl_y"] = float(lines[i + 1].split("#")[0].split(":")[1].replace(',', '').strip())
            zone_home["tl_x"] = float(lines[i + 2].split("#")[0].split(":")[1].replace(',', '').strip())
            zone_home["br_y"] = float(lines[i + 3].split("#")[0].split(":")[1].replace(',', '').strip())
            zone_home["br_x"] = float(lines[i + 4].split("#")[0].split(":")[1].replace(',', '').strip())
            break
    return zone_home

# Update ZONE_HOME in the config file
def update_zone_home(tl_y, tl_x, br_y, br_x):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        if "ZONE_HOME" in line:
            lines[i + 1] = f'    "tl_y": {tl_y},  # Top-Left Latitude (deg)\n'
            lines[i + 2] = f'    "tl_x": {tl_x},  # Top-Left Longitude (deg)\n'
            lines[i + 3] = f'    "br_y": {br_y},  # Bottom-Right Latitude (deg)\n'
            lines[i + 4] = f'    "br_x": {br_x},  # Bottom-Right Longitude (deg)\n'
            break
    with open(CONFIG_FILE_PATH, 'w') as file:
        file.writelines(lines)
    os.system('sudo systemctl restart itsaplane.service')

# Function to get current brightness from the config file
def get_brightness():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for line in lines:
        if "BRIGHTNESS" in line:
            return int(line.split('=')[1].strip())
    return 60  # Default brightness if not found

# Function to set the brightness and restart the service
def set_brightness(brightness_value):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    with open(CONFIG_FILE_PATH, 'w') as file:
        for line in lines:
            if "BRIGHTNESS" in line:
                file.write(f"BRIGHTNESS = {brightness_value}\n")
            else:
                file.write(line)
    os.system('sudo systemctl restart itsaplane.service')

# Function to get the current journey code from the config file
def get_journey_code():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for line in lines:
        if "JOURNEY_CODE_SELECTED" in line:
            return line.split('=')[1].strip().strip('"')
    return "ORD"  # Default airport code
# NEW — temperature units helpers
def get_temperature_units():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for line in lines:
        if "TEMPERATURE_UNITS" in line and "=" in line:
            return line.split('=')[1].strip().strip('"').strip("'")
    return "imperial"  # default

def set_temperature_units(units):
    units = units.lower()
    if units not in ("imperial", "metric"):
        return  # ignore invalid
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    with open(CONFIG_FILE_PATH, 'w') as file:
        for line in lines:
            if "TEMPERATURE_UNITS" in line and "=" in line:
                file.write(f'TEMPERATURE_UNITS = "{units}"\n')
            else:
                file.write(line)
    os.system('sudo systemctl restart itsaplane.service')

# Function to set the journey code in the config file
def set_journey_code(journey_code):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    with open(CONFIG_FILE_PATH, 'w') as file:
        for line in lines:
            if "JOURNEY_CODE_SELECTED" in line:
                file.write(f'JOURNEY_CODE_SELECTED = "{journey_code}"\n')
            else:
                file.write(line)
    os.system('sudo systemctl restart itsaplane.service')


# Function to get Min and Max Altitude from the config file (in feet)
# Function to get Min and Max Altitude from the config file (in feet)
def get_altitudes():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    min_altitude = max_altitude = 0
    for line in lines:
        if "MIN_ALTITUDE" in line:
            min_altitude = int(line.split('=')[1].split('#')[0].strip())  # Strip out the comment and convert to int
        elif "MAX_ALTITUDE" in line:
            max_altitude = int(line.split('=')[1].split('#')[0].strip())  # Strip out the comment and convert to int
    return min_altitude, max_altitude


# Function to update Min and Max Altitude in the config file
def update_altitudes(min_altitude, max_altitude):
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        if "MIN_ALTITUDE" in line:
            lines[i] = f"MIN_ALTITUDE = {min_altitude}\n"  # Save in feet
        elif "MAX_ALTITUDE" in line:
            lines[i] = f"MAX_ALTITUDE = {max_altitude}\n"  # Save in feet
    with open(CONFIG_FILE_PATH, 'w') as file:
        file.writelines(lines)
    # Restart the box
    os.system('sudo systemctl restart itsaplane.service')


# --- Ground speed (kts) helpers ---
def get_groundspeeds():
    with open(CONFIG_FILE_PATH, 'r') as f:
        lines = f.readlines()
    min_gs = None
    max_gs = None
    for line in lines:
        if "MIN_GROUNDSPEED" in line and "=" in line:
            val = line.split('=')[1].split('#')[0].strip()
            min_gs = None if val.startswith("None") else int(val)
        elif "MAX_GROUNDSPEED" in line and "=" in line:
            val = line.split('=')[1].split('#')[0].strip()
            max_gs = None if val.startswith("None") else int(val)
    return min_gs, max_gs


def update_groundspeeds(min_gs, max_gs):
    with open(CONFIG_FILE_PATH, 'r') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if "MIN_GROUNDSPEED" in line and "=" in line:
            lines[i] = f"MIN_GROUNDSPEED = {min_gs if min_gs is not None else 'None'}\n"
        elif "MAX_GROUNDSPEED" in line and "=" in line:
            lines[i] = f"MAX_GROUNDSPEED = {max_gs if max_gs is not None else 'None'}\n"

    with open(CONFIG_FILE_PATH, 'w') as f:
        f.writelines(lines)

    ok, msg = restart_service("itsaplane.service")
    return ok, msg


# Function to get current weather location from the config file
def get_current_weather_location():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for line in lines:
        if "WEATHER_LOCATION" in line:
            return line.split('=')[1].strip().strip('"')
    return "Unknown"

# Function to update the timezone in the config file and system timezone
def update_timezone(timezone):
    # Update the config file
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    with open(CONFIG_FILE_PATH, 'w') as file:
        for line in lines:
            if "TIMEZONE" in line:
                file.write(f'TIMEZONE = "{timezone}"\n')
            else:
                file.write(line)

    # Update system timezone using timedatectl
    os.system(f'sudo timedatectl set-timezone "{timezone}"')

    # Restart the service if needed
    os.system('sudo systemctl restart itsaplane.service')

# Function to get the current timezone from the config file
def get_timezone():
    with open(CONFIG_FILE_PATH, 'r') as file:
        lines = file.readlines()
    for line in lines:
        if "TIMEZONE" in line:
            return line.split('=')[1].strip().strip('"')
    return "UTC"  # Default timezone

def get_time_format_24h():
    """
    Returns True for 24-hour, False for 12-hour.
    Defaults to False (12-hour) if the key isn't present.
    """
    with open(CONFIG_FILE_PATH, 'r') as f:
        lines = f.readlines()
    for line in lines:
        if "TIME_FORMAT_24H" in line and "=" in line:
            val = line.split('=')[1].strip()
            return val.startswith("True") or val.startswith("true")
    return False  # default to 12-hour if not found


def set_time_format_24h(flag: bool):
    """
    Writes TIME_FORMAT_24H = True/False to config.py and restarts the matrix service.
    """
    with open(CONFIG_FILE_PATH, 'r') as f:
        lines = f.readlines()
    with open(CONFIG_FILE_PATH, 'w') as f:
        wrote = False
        for line in lines:
            if "TIME_FORMAT_24H" in line and "=" in line:
                f.write(f"TIME_FORMAT_24H = {bool(flag)}\n")
                wrote = True
            else:
                f.write(line)
        if not wrote:
            # If the key didn't exist, append it
            f.write(f"\nTIME_FORMAT_24H = {bool(flag)}\n")
    os.system('sudo systemctl restart itsaplane.service')
    
# Update the index route in app.py to handle Min/Max Altitude POST request
@app.route('/', methods=['GET', 'POST'])
def index():
    current_location = get_current_location()
    brightness = get_brightness()
    city_name = get_city_name(current_location[0], current_location[1])
    zone_home = get_zone_home()
    journey_code = get_journey_code()
    min_altitude, max_altitude = get_altitudes()
    min_groundspeed, max_groundspeed = get_groundspeeds()
    current_weather_location = get_current_weather_location()
    current_timezone = get_timezone()
    temperature_units = get_temperature_units()
    time_format_24h = get_time_format_24h()
    live_mode = read_live_mode()



    if request.method == 'POST':
        # 🔹 FIRST: handle plane fields (so nothing else catches the POST)
        if 'live_mode_action' in request.form:
            live_mode = set_live_mode(request.form.get('live_mode_action') == 'start')

        elif 'plane_fields_form' in request.form or 'plane_fields' in request.form:
            fields = request.form.getlist('plane_fields')
            write_plane_detail_fields(fields)

        elif 'latitude' in request.form and 'longitude' in request.form and 'altitude' in request.form:
            latitude = request.form['latitude']
            longitude = request.form['longitude']
            altitude = float(request.form['altitude']) * 0.0003048  # feet -> km
            update_location(latitude, longitude, altitude)
            city_name = get_city_name(latitude, longitude)
            update_weather_location(city_name)
            current_location = [latitude, longitude, altitude]

        elif 'tl_y' in request.form and 'tl_x' in request.form and 'br_y' in request.form and 'br_x' in request.form:
            tl_y = request.form['tl_y']; tl_x = request.form['tl_x']
            br_y = request.form['br_y']; br_x = request.form['br_x']
            update_zone_home(tl_y, tl_x, br_y, br_x)

        elif 'brightness' in request.form:
            brightness = request.form['brightness']
            set_brightness(brightness)

        elif 'journey_code' in request.form:
            journey_code = request.form['journey_code']
            set_journey_code(journey_code)

        elif 'min_altitude' in request.form and 'max_altitude' in request.form:
            min_altitude = int(request.form['min_altitude'])
            max_altitude = int(request.form['max_altitude'])
            update_altitudes(min_altitude, max_altitude)

        elif ('min_groundspeed' in request.form or 'min_gs_none' in request.form
              or 'max_groundspeed' in request.form or 'max_gs_none' in request.form):
            # If the override checkboxes are checked, set to None, otherwise use slider values
            min_gs = None if request.form.get('min_gs_none') == 'on' else int(request.form.get('min_groundspeed', 0))
            max_gs = None if request.form.get('max_gs_none') == 'on' else int(request.form.get('max_groundspeed', 0))
            update_groundspeeds(min_gs, max_gs)
            # refresh local values so the template shows what we just saved
            min_groundspeed, max_groundspeed = get_groundspeeds()

        elif 'weather_location' in request.form:
            city_name = request.form['weather_location']
            update_weather_location(city_name)

        elif 'temperature_units' in request.form:
            set_temperature_units(request.form['temperature_units'])
            temperature_units = get_temperature_units()  # refresh

        elif 'timezone' in request.form:
            timezone = request.form['timezone']
            update_timezone(timezone)
            current_timezone = timezone

        elif 'time_format_24h' in request.form:
            time_format_24h = request.form['time_format_24h'].lower() == 'true'
            set_time_format_24h(time_format_24h)
            time_format_24h = get_time_format_24h()  # refresh

    # Read current selection AFTER handling POST so the page shows the latest
    selected_plane_fields = set(read_plane_detail_fields())

    return render_template(
        'index.html',
        current_location=current_location,
        brightness=brightness,
        weather_location=city_name,
        current_weather_location=current_weather_location,
        zone_home=zone_home,
        journey_code=journey_code,
        min_altitude=min_altitude,
        max_altitude=max_altitude,
        current_timezone=current_timezone,
        timezones=pytz.all_timezones,
        temperature_units=temperature_units,
        time_format_24h=time_format_24h,
        selected_plane_fields=selected_plane_fields,   # ✅ pass to template
        plane_field_examples=PLANE_FIELD_EXAMPLES,
        live_mode=live_mode,
        min_groundspeed=min_groundspeed,
        max_groundspeed=max_groundspeed,
    )


@app.route('/api/live-mode')
def api_live_mode():
    return jsonify(read_live_mode())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
