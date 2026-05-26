# OGFlightTracker

The original, Raspberry Pi based version of the **FlightTrackerLED** box — a
64×32 RGB LED matrix that shows live aircraft overhead, the local time, date,
and weather.

This is a **modified version of Colin Waddell's
[`its-a-plane-python`](https://github.com/ColinWaddell/its-a-plane-python)**
("RGB Matrix Flight Tracker"), released, like the original, under the
**GNU General Public License v3.0**. See [`NOTICE`](NOTICE) for full
attribution and a list of changes, and [`LICENSE`](LICENSE) for the license.

> This legacy Raspberry Pi version is different from Mach 2, which is
> independently written.

## Requirements

- Raspberry Pi connected to a 64x32 RGB LED matrix.
- Python 3 and the `rgbmatrix` library for driving the panel.
- A paid Flightradar24 API subscription token. This legacy build expects an
  FR24 key for the intended live aircraft feed behavior.
- Optional OpenWeather API key if you want the weather scene enabled.

## How it works

1. The Pi starts `its-a-plane.py`, which creates the LED matrix display and
   runs the scene loop.
2. `utilities/overhead.py` requests nearby aircraft from Flightradar24, then
   filters them by location, altitude, speed, and distance from the configured
   home position.
3. `utilities/fr24_client.py` attaches your `FR24_API_TOKEN` to the FR24 client
   when one is configured.
4. The files in `scenes/` turn the current aircraft, time, date, and weather
   state into display frames.
5. `display/` composites those scenes and writes them to the RGB matrix.
6. The optional Flask dashboard in `web_interface/` lets you change local
   settings from a browser on your LAN.

## What's in here

| Path | What it is |
| --- | --- |
| `its-a-plane.py` | Entry point — builds the `Display` and runs the matrix loop. |
| `display/` | The animated display loop and scene compositor. |
| `scenes/` | Individual screens: clock, date, weather, flight details, journey, plane details, loading. |
| `setup/`, `utilities/` | Matrix dimensions, fonts, colours, the animator, and the flight-data layer. |
| `utilities/overhead.py` | Pulls nearby aircraft from Flightradar24 and filters them by altitude / ground speed / distance. |
| `utilities/fr24_client.py` | Builds an **authenticated** Flightradar24 client from your API token. |
| `web_interface/` | Local Flask dashboard for configuring the box from a browser. |

## Secrets

**No keys, locations, or credentials are committed.** Everything sensitive
lives in `config.py`, which is git-ignored. Copy the template and fill in your
own values:

```bash
cp config.py.example config.py
```

- `FR24_API_TOKEN` — your paid Flightradar24 API token (or set the
  `FR24_API_TOKEN` environment variable). This is required for the intended
  live feed behavior. Left as the placeholder, the client falls back to
  anonymous, rate-limited feed access where available.
- `OPENWEATHER_API_KEY` — optional, from <https://openweathermap.org/price>.
- `ZONE_HOME` / `LOCATION_HOME` — your tracking box and home coordinates.

## Hardware setup

1. Assemble the RGB matrix, Raspberry Pi, and Adafruit RGB Matrix Bonnet per the
   [Adafruit guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview).
2. Install the `rgbmatrix` Python library
   ([hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)).
   It must run as root for stable timing.
3. Install the Python dependencies: `sudo pip3 install -r requirements.txt`.
4. Create your `config.py` (see above).
5. Run the display: `sudo python3 its-a-plane.py`.

## Local settings dashboard (optional)

```bash
python3 web_interface/app.py   # serves on http://<pi-ip>:5000
```

The dashboard reads and writes `config.py` and restarts the matrix service when
you save. Run it behind your LAN / a VPN — it is not meant to be exposed to the
public internet.

## License

GPL-3.0-or-later. This program is free software, distributed in the hope that
it will be useful, but **WITHOUT ANY WARRANTY**. See [`LICENSE`](LICENSE).
