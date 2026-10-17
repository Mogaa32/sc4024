"""
clean_data.py - turn the raw LTA files into tidy tables ready for charts.

Outputs (in data/clean/):
  station_hourly.csv  station_code, day_type, hour, tap_in, tap_out, net,
                      tap_in_per_day, tap_out_per_day, net_per_day
  od_hourly.csv       origin_code, destination_code, day_type, hour, trips, trips_per_day
  od_region.csv       origin_region, destination_region, day_type, hour, trips, trips_per_day

How to read the columns:
  - day_type: WEEKDAY or WEEKENDS/HOLIDAY (LTA's labels).
  - hour: hour of the day, 0-23. hour 8 = 08:00-08:59. In the OD files it is the
    hour the trip STARTED (when the passenger tapped in).
  - tap_in, tap_out, trips: LTA's numbers, which are TOTALS for the whole month
    (all weekdays, or all weekend/holiday days, added up).
  - *_per_day: the total divided by the number of days of that day type in the
    month, i.e. an average day. Use these to compare weekdays with weekends.
  - net = tap_in - tap_out. Positive: more people start trips here than end them.

Cleaning decisions (agreed with the team):
  1. Station codes are normalised (see common.normalise_code): Stevens' two
     codes TE11 and DT10 become one station, "DT10/TE11", and their numbers are added.
  2. station_hourly has a row for EVERY station x day type x operating hour.
     Where LTA has no row, nobody tapped, so we fill in 0. Operating hours are the
     hours that appear in the data (0 and 5-23); 1am-4am is left out because
     trains don't run.
  3. After merging Stevens, a trip between TE11 and DT10 would become
     Stevens -> Stevens. LTA's OD data has no same-station trips, so we drop these.
  4. od_hourly is NOT filled with zeros: that would add over a million empty
     rows. A station pair/hour that isn't in the file means 0 trips.
  5. od_region IS filled with zeros, since it's small (5 x 5 regions).

Usage:
    python clean_data.py                 # newest month in data/raw/
    python clean_data.py --month 202608
"""

import argparse

import pandas as pd

from common import (CLEAN_DIR, days_by_day_type, latest_raw_month, load_od_raw,
                    load_station_raw, normalise_code)


def add_per_day(df, columns, days, decimals):
    """Add '<column>_per_day' = monthly total / number of days of that day type."""
    n_days = df["day_type"].map(days)
    for col in columns:
        df[f"{col}_per_day"] = (df[col] / n_days).round(decimals)
    return df


def fill_missing_with_zero(df, keys):
    """Make sure every combination of the key columns has a row; new rows get 0."""
    all_combos = pd.MultiIndex.from_product([sorted(df[k].unique()) for k in keys], names=keys)
    filled = df.set_index(keys).reindex(all_combos, fill_value=0).reset_index()
    return filled, len(filled) - len(df)


def clean_station(month, days):
    raw = load_station_raw(month)
    df = pd.DataFrame({
        "station_code": raw["PT_CODE"].map(normalise_code),
        "day_type": raw["DAY_TYPE"],
        "hour": raw["TIME_PER_HOUR"],
        "tap_in": raw["TOTAL_TAP_IN_VOLUME"],
        "tap_out": raw["TOTAL_TAP_OUT_VOLUME"],
    })
    # Stevens' two codes now share one station_code, so add their rows together
    df = df.groupby(["station_code", "day_type", "hour"], as_index=False)[["tap_in", "tap_out"]].sum()

    df, n_filled = fill_missing_with_zero(df, ["station_code", "day_type", "hour"])
    print(f"  station_hourly: filled {n_filled} missing station/day-type/hour rows with 0")

    df["net"] = df["tap_in"] - df["tap_out"]
    return add_per_day(df, ["tap_in", "tap_out", "net"], days, decimals=2)


def clean_od(month, days):
    raw = load_od_raw(month)
    # Normalise each distinct code once (faster than once per row)
    codes = pd.concat([raw["ORIGIN_PT_CODE"], raw["DESTINATION_PT_CODE"]]).unique()
    code_map = {c: normalise_code(c) for c in codes}

    df = pd.DataFrame({
        "origin_code": raw["ORIGIN_PT_CODE"].map(code_map),
        "destination_code": raw["DESTINATION_PT_CODE"].map(code_map),
        "day_type": raw["DAY_TYPE"],
        "hour": raw["TIME_PER_HOUR"],
        "trips": raw["TOTAL_TRIPS"],
    })
    df = df.groupby(["origin_code", "destination_code", "day_type", "hour"], as_index=False)["trips"].sum()

    same_station = df["origin_code"] == df["destination_code"]
    print(f"  od_hourly: dropped {df.loc[same_station, 'trips'].sum():,} same-station trips "
          f"(created by merging Stevens)")
    df = df[~same_station].reset_index(drop=True)
    return add_per_day(df, ["trips"], days, decimals=3)


def build_od_region(od, days):
    stations = pd.read_csv(CLEAN_DIR / "stations.csv")
    region_of = stations.set_index("station_code")["region"]

    df = od.assign(origin_region=od["origin_code"].map(region_of),
                   destination_region=od["destination_code"].map(region_of))
    no_region = df["origin_region"].isna() | df["destination_region"].isna()
    if no_region.any():
        missing = sorted(set(df.loc[no_region, "origin_code"]) | set(df.loc[no_region, "destination_code"]))
        raise SystemExit(f"ERROR: stations without a region: {missing}. Run build_stations.py first.")

    keys = ["origin_region", "destination_region", "day_type", "hour"]
    df = df.groupby(keys, as_index=False)["trips"].sum()
    df, _ = fill_missing_with_zero(df, keys)
    return add_per_day(df, ["trips"], days, decimals=2)


def main():
    parser = argparse.ArgumentParser(description="Clean one month of LTA passenger data.")
    parser.add_argument("--month", help="YYYYMM. Default: newest month in data/raw/.")
    month = parser.parse_args().month or latest_raw_month()

    if not (CLEAN_DIR / "stations.csv").exists():
        raise SystemExit("ERROR: data/clean/stations.csv not found. Run build_stations.py first.")

    days = days_by_day_type(month)
    print(f"Month {month}, days per day type: {days}")

    station_hourly = clean_station(month, days)
    od_hourly = clean_od(month, days)
    od_region = build_od_region(od_hourly, days)

    for name, df in [("station_hourly", station_hourly), ("od_hourly", od_hourly), ("od_region", od_region)]:
        df.to_csv(CLEAN_DIR / f"{name}.csv", index=False)
        print(f"Saved {name}.csv: {len(df):,} rows")


if __name__ == "__main__":
    main()
