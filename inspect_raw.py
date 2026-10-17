"""
inspect_raw.py - quick look at the two raw CSVs before cleaning them.

Prints, for each file: columns, row count, station codes, day types,
hours covered, and checks for missing values, duplicates and negatives.
Then compares the two files with each other.

Usage:
    python inspect_raw.py                # newest month in data/raw/
    python inspect_raw.py --month 202608
"""

import argparse

from common import latest_raw_month, load_od_raw, load_station_raw

ALL_HOURS = set(range(24))


def describe_basics(name, df, key_cols, value_cols):
    """Print the checks that apply to both files."""
    print(f"\n===== {name} =====")
    print(f"Columns: {list(df.columns)}")
    print(f"Rows: {len(df):,}")
    print(f"YEAR_MONTH values: {sorted(df['YEAR_MONTH'].unique())}")
    print(f"PT_TYPE values:    {sorted(df['PT_TYPE'].unique())}")
    print(f"DAY_TYPE values:   {df['DAY_TYPE'].value_counts().to_dict()}")

    hours = set(df["TIME_PER_HOUR"].unique())
    print(f"TIME_PER_HOUR: min {min(hours)}, max {max(hours)}, "
          f"hours never present: {sorted(ALL_HOURS - hours)}")

    print(f"Missing values: {int(df.isna().sum().sum())}")
    print(f"Duplicate rows (same {key_cols}): {df.duplicated(key_cols).sum()}")
    for col in value_cols:
        print(f"{col}: total {df[col].sum():,}, "
              f"negative {(df[col] < 0).sum()}, zero {(df[col] == 0).sum()}")


def main():
    parser = argparse.ArgumentParser(description="Inspect the raw LTA CSVs for one month.")
    parser.add_argument("--month", help="YYYYMM. Default: newest month in data/raw/.")
    month = parser.parse_args().month or latest_raw_month()
    print(f"Month: {month}")

    station = load_station_raw(month)
    od = load_od_raw(month)

    # ---- Station file (tap in / tap out) ----
    describe_basics("STATION (PV/Train)", station,
                    ["DAY_TYPE", "TIME_PER_HOUR", "PT_CODE"],
                    ["TOTAL_TAP_IN_VOLUME", "TOTAL_TAP_OUT_VOLUME"])
    codes = set(station["PT_CODE"])
    combined = sorted(c for c in codes if "/" in c or "-" in c)
    print(f"Unique station codes: {len(codes)}")
    print(f"Combined interchange codes ({len(combined)}): {combined}")

    # Which station / day type combinations are missing some operating hours?
    operating_hours = set(station["TIME_PER_HOUR"].unique())
    hours_seen = station.groupby(["PT_CODE", "DAY_TYPE"])["TIME_PER_HOUR"].apply(set)
    gaps = hours_seen.apply(lambda h: sorted(int(x) for x in operating_hours - h))
    gaps = gaps[gaps.str.len() > 0]
    print(f"Station/day-type combos missing an hour ({len(gaps)}):")
    for (code, day_type), missing in gaps.items():
        print(f"    {code:<10} {day_type:<17} missing hour(s) {missing}")

    # ---- OD file (trips between stations) ----
    describe_basics("ORIGIN-DESTINATION (PV/ODTrain)", od,
                    ["DAY_TYPE", "TIME_PER_HOUR", "ORIGIN_PT_CODE", "DESTINATION_PT_CODE"],
                    ["TOTAL_TRIPS"])
    od_codes = set(od["ORIGIN_PT_CODE"]) | set(od["DESTINATION_PT_CODE"])
    print(f"Unique station codes (origin or destination): {len(od_codes)}")
    same = od["ORIGIN_PT_CODE"] == od["DESTINATION_PT_CODE"]
    print(f"Rows where origin == destination: {same.sum()}")
    print(f"Station pairs with any trips: "
          f"{od[['ORIGIN_PT_CODE', 'DESTINATION_PT_CODE']].drop_duplicates().shape[0]:,}")

    # ---- Compare the two files ----
    print("\n===== COMPARISON =====")
    print(f"Codes only in station file: {sorted(codes - od_codes)}")
    print(f"Codes only in OD file:      {sorted(od_codes - codes)}")
    tap_in = station["TOTAL_TAP_IN_VOLUME"].sum()
    trips = od["TOTAL_TRIPS"].sum()
    print(f"Total tap-ins {tap_in:,} vs total OD trips {trips:,} "
          f"-> OD is {trips / tap_in:.1%} of tap-ins")


if __name__ == "__main__":
    main()
