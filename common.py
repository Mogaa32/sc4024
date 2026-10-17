"""
common.py - folder paths and small helpers shared by the pipeline scripts.
"""

import calendar
import re
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
REF_DIR = PROJECT_DIR / "data" / "reference"
CLEAN_DIR = PROJECT_DIR / "data" / "clean"

# File names of the CSVs inside LTA's ZIPs ({month} is YYYYMM)
STATION_CSV = "transport_node_train_{month}.csv"     # from PV/Train
OD_CSV = "origin_destination_train_{month}.csv"      # from PV/ODTrain

# Reference files saved by fetch_reference.py
GTFS_DIR = REF_DIR / "gtfs_train"                                  # LTA GTFS: stops.txt, routes.txt
EXITS_GEOJSON = REF_DIR / "lta_mrt_station_exits.geojson"          # LTA station exits
REGIONS_GEOJSON = REF_DIR / "ura_mp2019_region_boundary.geojson"   # URA planning regions


# ---------------------------------------------------------------------------
# Station codes
# ---------------------------------------------------------------------------
# LTA already gives most interchanges ONE combined code, e.g. "NS24/NE6/CC1" for
# Dhoby Ghaut. Stevens is the exception: LTA reports its two lines separately.
# The team decided to merge them into one station (LTA's GTFS feed also treats
# Stevens as one station).
MANUAL_MERGES = {
    "TE11": "DT10/TE11",
    "DT10": "DT10/TE11",
}


def normalise_code(raw_code):
    """Turn a station code from the LTA passenger data into our station_code.

    - LTA's API guide writes combined codes with "-" (EW14-NS26) while the data
      itself uses "/" (EW14/NS26). We always use "/".
    - Stevens' two codes become one (see MANUAL_MERGES).
    """
    code = raw_code.strip().replace("-", "/")
    return MANUAL_MERGES.get(code, code)


# Singapore public holidays (MOM). A holiday on a Sunday gives a day off on the
# Monday, so that Monday is listed too. LTA counts all of these as
# "WEEKENDS/HOLIDAY". Add the next year's dates here if you use later months.
PUBLIC_HOLIDAYS = {
    2026: ["2026-01-01", "2026-02-17", "2026-02-18", "2026-03-21", "2026-04-03",
           "2026-05-01", "2026-05-27", "2026-05-31", "2026-06-01", "2026-08-09",
           "2026-08-10", "2026-11-08", "2026-11-09", "2026-12-25"],
}


def days_by_day_type(month):
    """How many days of each LTA day type are in a month (YYYYMM).

    LTA's numbers are TOTALS over all days of that type in the month, so we
    need these counts to turn them into averages per day.
    E.g. '202609' -> {'WEEKDAY': 22, 'WEEKENDS/HOLIDAY': 8}
    """
    year, mon = int(month[:4]), int(month[4:])
    if year not in PUBLIC_HOLIDAYS:
        print(f"WARNING: no public holiday list for {year}; counting weekends only.")
    holidays = set(PUBLIC_HOLIDAYS.get(year, []))

    counts = {"WEEKDAY": 0, "WEEKENDS/HOLIDAY": 0}
    for day in range(1, calendar.monthrange(year, mon)[1] + 1):
        d = date(year, mon, day)
        if d.weekday() >= 5 or d.isoformat() in holidays:  # 5 = Sat, 6 = Sun
            counts["WEEKENDS/HOLIDAY"] += 1
        else:
            counts["WEEKDAY"] += 1
    return counts


def latest_raw_month():
    """The newest month (YYYYMM) that has a station CSV in data/raw/."""
    months = sorted(
        re.search(r"(\d{6})", f.name).group(1)
        for f in RAW_DIR.glob("transport_node_train_*.csv")
    )
    if not months:
        raise SystemExit("ERROR: no raw data in data/raw/. Run fetch_data.py first.")
    return months[-1]


def load_station_raw(month):
    """Raw tap-in/tap-out CSV for one month. Station codes are read as text."""
    return pd.read_csv(RAW_DIR / STATION_CSV.format(month=month), dtype={"PT_CODE": str})


def load_od_raw(month):
    """Raw origin-destination CSV for one month. Station codes are read as text."""
    return pd.read_csv(
        RAW_DIR / OD_CSV.format(month=month),
        dtype={"ORIGIN_PT_CODE": str, "DESTINATION_PT_CODE": str},
    )
