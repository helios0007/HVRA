"""
EPW climate file loader — Stage 2 prerequisite.

Reads the Barcelona TMYx EPW and extracts the July 15–21 design heatwave week
(168 hours). Falls back to a synthetic Barcelona July profile if the file is absent,
so the pipeline runs in tests without the real file.

EPW source: climate.onebuilding.org — Spain → Cataluña →
  ESP_CT_Barcelona.081810_TMYx.epw
Place the file at: backend/config/barcelona/barcelona.epw
"""

import os
import csv
import math
from dataclasses import dataclass
from typing import List


HEATWAVE_MONTH = 7
HEATWAVE_DAYS = list(range(15, 22))  # July 15–21 inclusive, 7 × 24 = 168 h

# EPW column indices (0-based, after the 8-line header)
_COL = {
    "month": 1, "day": 2, "hour": 3,
    "dry_bulb": 6, "dew_point": 7, "rh": 8, "pressure": 9,
    "global_horiz": 13, "direct_normal": 14, "diffuse_horiz": 15,
}


@dataclass
class HourlyClimate:
    month: int
    day: int
    hour: int          # 1–24 (EPW convention)
    dry_bulb_c: float
    dew_point_c: float
    relative_humidity_pct: float
    atm_pressure_pa: float
    global_horiz_wh_m2: float    # GHI
    direct_normal_wh_m2: float   # DNI
    diffuse_horiz_wh_m2: float   # DHI


def load_epw(epw_path: str) -> List[HourlyClimate]:
    """
    Parse EPW file and return 168 HourlyClimate records for July 15–21.
    Raises FileNotFoundError with download instructions if file is missing.
    """
    if not os.path.exists(epw_path):
        raise FileNotFoundError(
            f"EPW file not found: {epw_path}\n"
            "Download the Barcelona TMYx EPW from:\n"
            "  https://climate.onebuilding.org → Spain → Cataluña →\n"
            "  ESP_CT_Barcelona.081810_TMYx.epw\n"
            "Save it to: backend/config/barcelona/barcelona.epw\n"
            "Or the pipeline will use synthetic Barcelona fallback data."
        )

    records: List[HourlyClimate] = []
    with open(epw_path, encoding="latin-1", newline="") as fh:
        reader = csv.reader(fh)
        for _ in range(8):          # skip 8 EPW header lines
            next(reader)
        for row in reader:
            if len(row) < 16:
                continue
            try:
                month = int(row[_COL["month"]])
                day = int(row[_COL["day"]])
            except ValueError:
                continue
            if month != HEATWAVE_MONTH or day not in HEATWAVE_DAYS:
                continue
            records.append(HourlyClimate(
                month=month,
                day=day,
                hour=int(row[_COL["hour"]]),
                dry_bulb_c=float(row[_COL["dry_bulb"]]),
                dew_point_c=float(row[_COL["dew_point"]]),
                relative_humidity_pct=float(row[_COL["rh"]]),
                atm_pressure_pa=float(row[_COL["pressure"]]),
                global_horiz_wh_m2=max(0.0, float(row[_COL["global_horiz"]])),
                direct_normal_wh_m2=max(0.0, float(row[_COL["direct_normal"]])),
                diffuse_horiz_wh_m2=max(0.0, float(row[_COL["diffuse_horiz"]])),
            ))

    if not records:
        raise ValueError(
            "No July 15–21 records found in EPW file. "
            "Verify the file is a full annual 8760-hour EPW."
        )
    return records


def prevailing_wind_direction(epw_path: str) -> float | None:
    """
    Prevailing daytime wind direction for July, in compass degrees
    (direction the wind comes FROM, 0=N 90=E 180=S 270=W).

    Speed-weighted vector average of EPW wind records (fields 21/22),
    July, 10:00–19:00 — the window when cross-ventilation protocols apply.
    Returns None if the EPW is missing or has no usable wind data.
    """
    if not os.path.exists(epw_path):
        return None
    sum_x = sum_y = 0.0
    try:
        with open(epw_path, encoding="latin-1", newline="") as fh:
            reader = csv.reader(fh)
            for _ in range(8):
                next(reader)
            for row in reader:
                if len(row) < 22:
                    continue
                try:
                    month = int(row[1])
                    hour = int(row[3])
                    wdir = float(row[20])
                    wspd = float(row[21])
                except ValueError:
                    continue
                if month != HEATWAVE_MONTH or not (10 <= hour <= 19):
                    continue
                if wspd <= 0 or wspd > 40 or not (0 <= wdir <= 360):
                    continue
                rad = math.radians(wdir)
                sum_x += math.sin(rad) * wspd
                sum_y += math.cos(rad) * wspd
    except Exception:
        return None
    if abs(sum_x) < 1e-9 and abs(sum_y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(sum_x, sum_y)) % 360, 1)


def synthetic_barcelona_july() -> List[HourlyClimate]:
    """
    Generate 168 hours of synthetic Barcelona July climate data for testing.

    Values are representative of Barcelona July TMYx statistics:
    T_peak ≈ 31°C (14:00), T_night_min ≈ 22°C (04:00), RH ≈ 60–70%.
    SOURCE: Climatological norms, Barcelona El Prat station, AEMET 1991–2020.
    PROXY: Synthetic sinusoidal approximation — not EPW data. Use real EPW for production.
    """
    records: List[HourlyClimate] = []
    T_mean = 26.5       # °C — July mean dry bulb
    T_amplitude = 4.5   # °C — half diurnal swing
    RH_mean = 65.0      # %
    RH_amplitude = 10.0
    DNI_peak = 750.0    # W/m² — typical peak direct normal for Barcelona July
    GHI_peak = 650.0    # W/m²
    DHI_fraction = 0.18 # DHI / GHI at peak

    day_num = 0
    for day in HEATWAVE_DAYS:
        day_num += 1
        for hour in range(1, 25):   # EPW hours 1–24
            # Solar hour angle: hour 13–14 = solar noon
            hour_angle = (hour - 13.5) * 15.0  # degrees
            cos_solar = max(0.0, math.cos(math.radians(hour_angle)))

            T_db = T_mean - T_amplitude * math.cos(math.pi * (hour - 14) / 12)
            rh = RH_mean + RH_amplitude * math.cos(math.pi * (hour - 6) / 12)
            rh = max(30.0, min(100.0, rh))
            T_dp = T_db - ((100 - rh) / 5.0)  # Magnus approximation

            ghi = GHI_peak * cos_solar
            dni = DNI_peak * cos_solar if cos_solar > 0.05 else 0.0
            dhi = DHI_fraction * ghi

            records.append(HourlyClimate(
                month=7,
                day=day,
                hour=hour,
                dry_bulb_c=round(T_db, 2),
                dew_point_c=round(T_dp, 2),
                relative_humidity_pct=round(rh, 1),
                atm_pressure_pa=101325.0,
                global_horiz_wh_m2=round(ghi, 1),
                direct_normal_wh_m2=round(dni, 1),
                diffuse_horiz_wh_m2=round(dhi, 1),
            ))
    return records


def load_epw_or_synthetic(epw_path: str) -> tuple[List[HourlyClimate], bool]:
    """
    Try to load EPW file; if absent, fall back to synthetic Barcelona data.
    Returns (records, is_synthetic).
    """
    try:
        return load_epw(epw_path), False
    except FileNotFoundError:
        return synthetic_barcelona_july(), True


def overnight_min_temp(climate_hours: List[HourlyClimate]) -> float:
    """
    Return the minimum dry-bulb temperature across all 3am–5am hours in the
    heatwave week. Used for nocturnal recovery and night purge eligibility.
    SOURCE: Blondeau et al. (1997), Solar Energy — night purge eligibility condition.
    """
    night_temps = [
        h.dry_bulb_c for h in climate_hours if h.hour in (3, 4, 5)
    ]
    return min(night_temps) if night_temps else 20.0


def peak_conditions(climate_hours: List[HourlyClimate]) -> dict:
    """Return the single worst-case hour (highest dry-bulb) for design calculations."""
    peak = max(climate_hours, key=lambda h: h.dry_bulb_c)
    return {
        "T_peak_db": peak.dry_bulb_c,
        "RH_at_peak": peak.relative_humidity_pct,
        "DNI_at_peak": peak.direct_normal_wh_m2,
        "DHI_at_peak": peak.diffuse_horiz_wh_m2,
        "GHI_at_peak": peak.global_horiz_wh_m2,
        "hour": peak.hour,
        "day": peak.day,
    }
