"""
validate.py - check the cleaned data. Prints a report and saves it as
data/clean/VALIDATION.md.

Checks:
  1. Is every station code in the passenger data matched to coordinates and a region?
  2. Do our station locations agree with LTA's station exits?
  3. Total OD trips vs total tap-ins: how close, and why they differ
  4. Did cleaning keep the totals (nothing lost or double counted)?
  5. Busiest 10 stations on weekdays (sanity check)
  6. Missing hours, zeros and negative values

Usage:
    python validate.py                 # newest month in data/raw/
    python validate.py --month 202608
"""

import argparse

import pandas as pd

from common import (CLEAN_DIR, MANUAL_MERGES, days_by_day_type, latest_raw_month,
                    load_od_raw, load_station_raw, normalise_code)

report = []  # the report is built up as a list of Markdown lines


def add(line=""):
    report.append(line)


def md_table(df):
    """A pandas table as Markdown text (numbers get thousands separators)."""
    def fmt(v):
        if isinstance(v, float):
            return f"{v:,.1f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.astype(object).itertuples(index=False)]
    return "\n".join(lines)


def ok(condition):
    return "OK" if condition else "**PROBLEM**"


def main():
    parser = argparse.ArgumentParser(description="Validate the cleaned data.")
    parser.add_argument("--month", help="YYYYMM. Default: newest month in data/raw/.")
    month = parser.parse_args().month or latest_raw_month()

    raw_station = load_station_raw(month)
    raw_od = load_od_raw(month)
    stations = pd.read_csv(CLEAN_DIR / "stations.csv")
    checks = pd.read_csv(CLEAN_DIR / "stations_checks.csv")
    station_hourly = pd.read_csv(CLEAN_DIR / "station_hourly.csv")
    od_hourly = pd.read_csv(CLEAN_DIR / "od_hourly.csv")
    od_region = pd.read_csv(CLEAN_DIR / "od_region.csv")
    days = days_by_day_type(month)
    names = stations.set_index("station_code")["station_name"]

    add(f"# Validation report: {month[:4]}-{month[4:]}")
    add()
    add(f"Days in the month: {days['WEEKDAY']} weekdays, {days['WEEKENDS/HOLIDAY']} weekend/holiday days. "
        "`*_per_day` columns = monthly total / these day counts.")

    # ------------------------------------------------------------------
    add()
    add("## 1. Every station matched to coordinates and a region?")
    add()
    raw_codes = set(raw_station["PT_CODE"]) | set(raw_od["ORIGIN_PT_CODE"]) | set(raw_od["DESTINATION_PT_CODE"])
    located = stations.dropna(subset=["latitude", "longitude", "region"])
    unmatched = sorted(c for c in raw_codes if normalise_code(c) not in set(located["station_code"]))
    add(f"- {len(raw_codes)} station codes in the passenger data -> {len(stations)} stations "
        f"(Stevens' codes {' and '.join(MANUAL_MERGES)} merged into one).")
    add(f"- Codes without coordinates or region: **{', '.join(unmatched) if unmatched else 'none'}** {ok(not unmatched)}")
    add(f"- Station types: {stations['station_type'].value_counts().to_dict()}")
    add(f"- Stations per region: {stations['region'].value_counts().to_dict()}")
    nearest = checks[checks["region_method"] == "nearest"]
    add(f"- Stations outside every URA region boundary (given the nearest region): "
        f"{', '.join(nearest['station_name']) if len(nearest) else 'none'}")

    # ------------------------------------------------------------------
    add()
    add("## 2. Do station locations agree with LTA's station exits?")
    add()
    add("Each station's location (from LTA's GTFS feed) is compared with the centre of its exits "
        "(LTA MRT Station Exit dataset).")
    add()
    d = checks["exit_distance_m"]
    far = checks[d > 300]
    add(f"- Stations compared: {d.notna().sum()} of {len(checks)}; median distance {d.median():.0f} m, "
        f"largest {d.max():.0f} m ({checks.loc[d.idxmax(), 'station_name']}).")
    add(f"- Stations more than 300 m away: {', '.join(far['station_name']) if len(far) else 'none'} {ok(far.empty)}")

    # ------------------------------------------------------------------
    add()
    add("## 3. Total OD trips vs total tap-ins")
    add()
    tap_in_raw = raw_station["TOTAL_TAP_IN_VOLUME"].sum()
    trips_raw = raw_od["TOTAL_TRIPS"].sum()
    by_day = pd.DataFrame({
        "tap-ins (station file)": station_hourly.groupby("day_type")["tap_in"].sum(),
        "trips (OD file)": od_hourly.groupby("day_type")["trips"].sum(),
    })
    by_day.loc["TOTAL"] = by_day.sum()
    by_day["gap"] = by_day["tap-ins (station file)"] - by_day["trips (OD file)"]
    by_day["OD as % of tap-ins"] = (100 * by_day["trips (OD file)"] / by_day["tap-ins (station file)"]).round(1)
    add(md_table(by_day.reset_index().rename(columns={"day_type": "day type"})))
    add()

    # Evidence for the explanation below
    same_station_raw = (raw_od["ORIGIN_PT_CODE"] == raw_od["DESTINATION_PT_CODE"]).sum()
    stevens_dropped = trips_raw - od_hourly["trips"].sum()
    per_station = pd.DataFrame({
        "tap_in": station_hourly.groupby("station_code")["tap_in"].sum(),
        "od_trips_starting_here": od_hourly.groupby("origin_code")["trips"].sum(),
    })
    per_station.index.name = "station_code"
    per_station["ratio"] = per_station["od_trips_starting_here"] / per_station["tap_in"]
    in_band = per_station["ratio"].between(0.97, 1.0).mean()

    add(f"The two are very close: OD trips are {trips_raw / tap_in_raw:.1%} of tap-ins in the raw files. "
        f"At {in_band:.0%} of stations, 97-100% of tap-ins appear as OD trips. Why the gap:")
    add()
    add(f"- **No same-station trips in the OD file.** It has {same_station_raw} rows where origin = destination, "
        "so anyone who taps in and out at the same station (e.g. changes their mind) counts in the station file only.")
    add("- **Journeys without a valid exit** (e.g. a missing tap-out) can't be given a destination, so they "
        "likely can't appear in the OD file. LTA doesn't document this, so treat it as the likely reason, not a fact.")
    add(f"- **Our cleaning** dropped {stevens_dropped:,} Stevens -> Stevens trips after merging Stevens (decision 3 below).")
    add(f"- Every OD trip begins with a tap-in, so OD should never be above 100%. "
        f"Highest station: {per_station['ratio'].max():.1%} {ok(per_station['ratio'].max() <= 1.005)}")
    add()
    add("Stations with the lowest share:")
    add()
    low = per_station.nsmallest(5, "ratio").reset_index()
    low.insert(1, "station", low["station_code"].map(names))
    low["ratio"] = (100 * low["ratio"]).round(1)
    add(md_table(low.rename(columns={"station_code": "code", "ratio": "OD as % of tap-ins"})))
    add()
    # Is the OD hour the start (tap-in) hour or the end (tap-out) hour? Compare per station and hour.
    keys = ["station_code", "day_type", "hour"]
    sh = station_hourly.set_index(keys)
    od_start = od_hourly.groupby(["origin_code", "day_type", "hour"])["trips"].sum().rename_axis(keys)
    od_end = od_hourly.groupby(["destination_code", "day_type", "hour"])["trips"].sum().rename_axis(keys)
    start_ratio = (od_start / sh["tap_in"][sh["tap_in"] > 100]).dropna()
    end_ratio = (od_end / sh["tap_out"][sh["tap_out"] > 100]).dropna()
    add(f"Note: in the OD file, `hour` is when the trip **started**. Per station and hour (ignoring hours under "
        f"100 taps), OD trips by origin are {start_ratio.quantile(0.1):.0%}-{start_ratio.quantile(0.9):.0%} of tap-ins "
        f"(middle 80% of cases), while OD trips by destination are {end_ratio.quantile(0.1):.0%}-"
        f"{end_ratio.quantile(0.9):.0%} of tap-outs, because trips end in a later hour.")

    # ------------------------------------------------------------------
    add()
    add("## 4. Did cleaning keep the totals?")
    add()
    rows = [
        ("tap-ins", tap_in_raw, station_hourly["tap_in"].sum()),
        ("tap-outs", raw_station["TOTAL_TAP_OUT_VOLUME"].sum(), station_hourly["tap_out"].sum()),
        ("OD trips (raw minus Stevens -> Stevens)", trips_raw - stevens_dropped, od_hourly["trips"].sum()),
        ("od_region trips vs od_hourly trips", od_hourly["trips"].sum(), od_region["trips"].sum()),
    ]
    totals = pd.DataFrame(rows, columns=["what", "expected", "in cleaned file"])
    totals["check"] = [ok(e == c) for e, c in zip(totals["expected"], totals["in cleaned file"])]
    add(md_table(totals))
    add()
    dupes = {
        "station_hourly": int(station_hourly.duplicated(["station_code", "day_type", "hour"]).sum()),
        "od_hourly": int(od_hourly.duplicated(["origin_code", "destination_code", "day_type", "hour"]).sum()),
        "od_region": int(od_region.duplicated(["origin_region", "destination_region", "day_type", "hour"]).sum()),
    }
    add(f"- Duplicate rows (same key twice): {dupes} {ok(sum(dupes.values()) == 0)}")

    # ------------------------------------------------------------------
    add()
    add("## 5. Busiest 10 stations on weekdays")
    add()
    add("Busiest = tap-ins + tap-outs on an average weekday.")
    add()
    wk = station_hourly[station_hourly["day_type"] == "WEEKDAY"]
    busy = wk.groupby("station_code")[["tap_in_per_day", "tap_out_per_day"]].sum()
    busy["total_per_day"] = busy["tap_in_per_day"] + busy["tap_out_per_day"]
    busy = busy.nlargest(10, "total_per_day").reset_index()
    busy = busy.merge(stations[["station_code", "station_name", "region"]], on="station_code")
    busy.insert(0, "rank", range(1, len(busy) + 1))
    busy = busy[["rank", "station_name", "station_code", "region", "tap_in_per_day", "tap_out_per_day", "total_per_day"]]
    busy = busy.round(0).astype({"tap_in_per_day": int, "tap_out_per_day": int, "total_per_day": int})
    add(md_table(busy))

    # ------------------------------------------------------------------
    add()
    add("## 6. Missing hours, zeros and negative values")
    add()
    hours = sorted(raw_station["TIME_PER_HOUR"].unique())
    no_service = sorted(set(range(24)) - set(hours))
    add(f"- Hours never in the data: {no_service} (no train service). They are left out of the cleaned files.")

    # Which station/day-type/hour rows were missing in the raw data (and filled with 0)?
    raw_keys = set(zip(raw_station["PT_CODE"].map(normalise_code), raw_station["DAY_TYPE"], raw_station["TIME_PER_HOUR"]))
    clean_keys = zip(station_hourly["station_code"], station_hourly["day_type"], station_hourly["hour"])
    filled = pd.DataFrame([k for k in clean_keys if k not in raw_keys], columns=["code", "day_type", "hour"])
    add(f"- Station/day-type/hour rows missing in the raw data and filled with 0: {len(filled)}")
    if len(filled):
        grouped = (filled.groupby(["hour", "day_type"])["code"]
                   .apply(lambda c: ", ".join(sorted(c))).reset_index())
        for _, g in grouped.iterrows():
            add(f"    - {g['hour']:02d}:00, {g['day_type']}: {g['code']}")
        add("  All are at the edges of the operating day, so most likely the station had no service "
            "in that hour (e.g. the Bukit Panjang LRT appears to close before midnight).")
    zero = raw_station[(raw_station["TOTAL_TAP_IN_VOLUME"] == 0) | (raw_station["TOTAL_TAP_OUT_VOLUME"] == 0)]
    add(f"- Raw rows with a 0 tap-in or tap-out: {len(zero)}, at hour(s) "
        f"{sorted(int(h) for h in zero['TIME_PER_HOUR'].unique())}. At the first and last trains this is "
        "expected (e.g. at midnight people arrive but nobody starts a trip), so they are kept as real values.")
    negatives = {
        "raw tap-in": int((raw_station["TOTAL_TAP_IN_VOLUME"] < 0).sum()),
        "raw tap-out": int((raw_station["TOTAL_TAP_OUT_VOLUME"] < 0).sum()),
        "raw OD trips": int((raw_od["TOTAL_TRIPS"] < 0).sum()),
        "clean tap_in/tap_out": int((station_hourly[["tap_in", "tap_out"]] < 0).sum().sum()),
        "clean trips": int((od_hourly["trips"] < 0).sum() + (od_region["trips"] < 0).sum()),
    }
    add(f"- Negative counts: {negatives} {ok(sum(negatives.values()) == 0)}")
    add("  (`net` is often negative, and that's expected: it means more people ended trips there than started them.)")

    # ------------------------------------------------------------------
    add()
    add("## Decisions applied in cleaning")
    add()
    add("1. Monthly totals are kept, and averages per day (`*_per_day`) are added for fair weekday/weekend comparisons.")
    add("2. Stevens (TE11 + DT10) is one station, `DT10/TE11`; LTA's GTFS feed also treats it as one.")
    add("3. Stevens -> Stevens trips created by that merge are dropped (LTA's OD data has no same-station trips).")
    add("4. Station/day-type/hour rows missing in the raw data are filled with 0; od_region too. "
        "od_hourly is not filled (a missing pair means 0 trips).")
    add("5. Interchanges keep LTA's combined codes (e.g. `NS24/NE6/CC1`). Choa Chu Kang (`NS4/BP1`) and "
        "Bukit Panjang (`BP6/DT1`) combine an MRT and an LRT station, as LTA reports them, so they are typed `MRT+LRT`.")
    add("6. Regions: the URA Master Plan 2019 region each station's location falls in.")

    text = "\n".join(report) + "\n"
    print(text)
    (CLEAN_DIR / "VALIDATION.md").write_text(text, encoding="utf-8")
    print(f"Saved {CLEAN_DIR / 'VALIDATION.md'}")


if __name__ == "__main__":
    main()
