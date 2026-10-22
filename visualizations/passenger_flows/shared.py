"""Shared, read-only inputs; explicit aggregation, validation and 720p exports."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "outputs" / "passenger_flows" / "202609"
FIGURES, TABLES = OUT / "figures", OUT / "tables"
BG, BLUE, TEAL, AMBER = "#0E0E0E", "#7296B8", "#69A89F", "#D6A45D"
TEXT, MUTED, GRID = "#F4F7FB", "#A9BED3", "#383838"
DAYS = {"WEEKDAY": 22, "WEEKENDS/HOLIDAY": 8}
REGIONS = ["Central", "West", "North-East", "North", "East"]
# Region identity is conveyed by labels, not by inventing five categorical colors.
SOURCE = "Source: LTA DataMall; cleaned September 2026 data | Full MRT/LRT network"

def require(condition, message):
    if not bool(condition):
        raise ValueError(message)

def setup():
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ["Arial", "Liberation Sans", "DejaVu Sans"] if f in available), "DejaVu Sans")
    plt.rcParams.update({"font.family": font, "font.size": 12,
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": TEXT, "axes.labelcolor": TEXT, "xtick.color": MUTED,
        "ytick.color": TEXT, "axes.edgecolor": GRID, "axes.spines.top": False,
        "axes.spines.right": False, "axes.spines.left": False, "axes.spines.bottom": False})
    print(f"Font: {font}")
    return font

def frame():
    """Full-canvas chart without presentation titles or narrative text."""
    return plt.figure(figsize=(12.8, 7.2), dpi=100)


def export(fig, name):
    path = FIGURES / name
    fig.savefig(path, dpi=100, facecolor=BG, transparent=False)
    plt.close(fig)
    with Image.open(path) as im:
        require(im.size == (1280, 720), f"Wrong PNG dimensions: {path}")
        if im.mode == "RGBA":
            require(im.getchannel("A").getextrema() == (255, 255), "PNG must be opaque")
    print(path.relative_to(ROOT))

def save_table(df, name):
    df.to_csv(TABLES / name, index=False, float_format="%.8f")

def load_data():
    s = pd.read_csv(CLEAN / "stations.csv")
    od = pd.read_csv(CLEAN / "od_hourly.csv")
    sh = pd.read_csv(CLEAN / "station_hourly.csv")
    schemas = {"stations": (s, ["station_code", "station_name", "station_type", "latitude", "longitude", "region"]),
        "od": (od, ["origin_code", "destination_code", "day_type", "hour", "trips", "trips_per_day"]),
        "station": (sh, ["station_code", "day_type", "hour", "tap_in", "tap_out", "net"])}
    for name, (df, cols) in schemas.items():
        require(set(cols) <= set(df.columns), f"Missing {name} columns")
        require(not df[cols].isna().any().any(), f"Missing {name} values")
    require(len(s) == 184 and s.station_code.is_unique, "Expected 184 unique stations")
    require(not od.duplicated(["origin_code", "destination_code", "day_type", "hour"]).any(), "Duplicate OD keys")
    require(not sh.duplicated(["station_code", "day_type", "hour"]).any(), "Duplicate gate keys")
    for df in [od, sh]:
        require(set(df.day_type) == set(DAYS), "Unexpected day types")
        require(set(df.hour) == {0, *range(5, 24)}, "Unexpected hours")
    for df, cols in [(od, ["trips"]), (sh, ["tap_in", "tap_out"])]:
        require(all(pd.api.types.is_integer_dtype(df[c]) for c in cols), "Counts must be integers")
        require((df[cols] >= 0).all().all(), "Negative counts")
    require((od.origin_code != od.destination_code).all(), "Unexpected same-station OD")
    require(sh.station_code.isin(s.station_code).all(), "Unmatched station gate code")
    require((sh.net == sh.tap_in - sh.tap_out).all(), "Unexpected source net convention")
    require(np.allclose(od.trips / od.day_type.map(DAYS), od.trips_per_day, atol=.000501, rtol=0), "OD normalization mismatch")
    require(s.latitude.between(1.1, 1.6).all() and s.longitude.between(103.5, 104.2).all(), "Invalid Singapore coordinates")
    require(int(od.trips.sum()) == 85880089, "Unexpected September OD total")
    require(int(sh.tap_in.sum()) == 87051437 and int(sh.tap_out.sum()) == 86776212, "Unexpected gate totals")
    return s, od, sh

def join_od(od, stations):
    cols = ["station_code", "station_name", "region", "latitude", "longitude", "station_type"]
    joined = od
    for side in ["origin", "destination"]:
        lookup = stations[cols].rename(columns={c: (f"{side}_code" if c == "station_code" else f"{side}_{c}") for c in cols})
        joined = joined.merge(lookup, on=f"{side}_code", how="left", validate="many_to_one")
        require(not joined[f"{side}_region"].isna().any(), f"Unmatched {side}")
    require(len(joined) == len(od) and joined.trips.sum() == od.trips.sum(), "Join changed trips")
    return joined

def pair_totals(od, stations):
    p = od.groupby(["origin_code", "destination_code", "day_type"]).trips.sum().unstack(fill_value=0).reset_index()
    p["monthly_trips"] = p.WEEKDAY + p["WEEKENDS/HOLIDAY"]
    p["trips_per_calendar_day"] = p.monthly_trips / 30
    p["trips_per_weekday"] = p.WEEKDAY / 22
    p["trips_per_weekend_holiday"] = p["WEEKENDS/HOLIDAY"] / 8
    p = p.sort_values(["monthly_trips", "origin_code", "destination_code"], ascending=[False, True, True])
    return join_od(p.rename(columns={"monthly_trips": "trips"}), stations).rename(columns={"trips": "monthly_trips"})

def check_equal(label, expected, actual):
    expected, actual = int(expected), int(actual)
    require(expected == actual, f"{label}: {expected} != {actual}")
    return {"check": label, "expected_monthly_trips": expected, "actual_monthly_trips": actual,
            "difference": actual - expected, "passed": expected == actual}
