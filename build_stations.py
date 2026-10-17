"""
build_stations.py - one row per physical station, with name, lines, location and region.

Output: data/clean/stations.csv
    station_code   station ID, the same codes as the passenger data (e.g. "EW24/NS1")
    station_name   e.g. "Jurong East"
    lines          e.g. "East-West Line; North-South Line"
    line_codes     e.g. "EW; NS"
    station_type   MRT, LRT, or MRT+LRT (one station shared by both)
    latitude, longitude
    region         Central, East, North, North-East or West

Also writes:
    data/clean/lines.csv            one row per line: code, name, official colour, MRT/LRT
    data/clean/stations_checks.csv  how each station's location and region were found (read by validate.py)

Sources (downloaded by fetch_reference.py):
    stations, names, coordinates: LTA GTFS train feed, stops.txt
    line names and colours:       LTA GTFS train feed, routes.txt
    location double-check:        LTA MRT Station Exit (data.gov.sg)
    regions:                      URA Master Plan 2019 Region Boundary (data.gov.sg)

Usage:
    python build_stations.py                 # stations in the newest month in data/raw/
    python build_stations.py --month 202608
"""

import argparse
import json
import math
import re

import pandas as pd
from matplotlib.path import Path as PolygonPath  # only used for the "is this point inside the region?" test

from common import (CLEAN_DIR, EXITS_GEOJSON, GTFS_DIR, REGIONS_GEOJSON, latest_raw_month,
                    load_od_raw, load_station_raw, normalise_code)

# Which line each station-code prefix belongs to. Line codes match GTFS routes.txt.
PREFIX_TO_LINE = {
    "NS": "NS", "EW": "EW", "NE": "NE", "CC": "CC", "DT": "DT", "TE": "TE",
    "CG": "EW",                            # Changi Airport branch of the East-West Line
    "BP": "BP",                            # Bukit Panjang LRT
    "SW": "SK", "SE": "SK", "STC": "SK",   # Sengkang LRT (west loop, east loop, Sengkang hub)
    "PW": "PG", "PE": "PG", "PTC": "PG",   # Punggol LRT (west loop, east loop, Punggol hub)
}
LRT_LINES = {"BP", "SK", "PG"}

EXIT_CHECK_LIMIT_M = 300  # flag a station if it's further than this from the centre of its exits


# ---------------------------------------------------------------------------
# 1. Which stations do we need?
# ---------------------------------------------------------------------------
def station_codes_for_month(month):
    """All station codes used in this month's passenger data (both files), normalised."""
    station = load_station_raw(month)
    od = load_od_raw(month)
    raw_codes = set(station["PT_CODE"]) | set(od["ORIGIN_PT_CODE"]) | set(od["DESTINATION_PT_CODE"])
    return sorted({normalise_code(c) for c in raw_codes})


# ---------------------------------------------------------------------------
# 2. Names and coordinates from LTA's GTFS feed
# ---------------------------------------------------------------------------
def load_gtfs():
    """Read GTFS stops.txt.

    GTFS has two kinds of rows that matter here:
      location_type 1 = a station, e.g. stop_id "EW24" (Jurong East), with lat/lon
      location_type 0 = a platform, e.g. stop_code "NS1", with parent_station "EW24"
    So every code (EW24 or NS1) can be traced to the station it belongs to.
    Returns (stations table indexed by station id, {code: station id}).
    """
    stops = pd.read_csv(GTFS_DIR / "stops.txt", dtype=str)
    stations = stops[stops["location_type"] == "1"].set_index("stop_id")
    stations = stations[["stop_name", "stop_lat", "stop_lon"]].astype({"stop_lat": float, "stop_lon": float})

    code_to_station = {sid: sid for sid in stations.index}
    platforms = stops[stops["location_type"] == "0"]
    for code, parent in zip(platforms["stop_code"], platforms["parent_station"]):
        code_to_station.setdefault(code, parent)
    return stations, code_to_station


def load_lines():
    """One row per line from GTFS routes.txt: code, name, colour, MRT or LRT."""
    routes = pd.read_csv(GTFS_DIR / "routes.txt", dtype=str)
    lines = routes.drop_duplicates("route_short_name")[["route_short_name", "route_long_name", "route_color"]]
    lines.columns = ["line_code", "line_name", "line_colour"]
    # GTFS lists the Changi Airport branch (CG) as its own route; we count it as East-West Line
    lines = lines[lines["line_code"].isin(set(PREFIX_TO_LINE.values()))].copy()
    lines["line_colour"] = "#" + lines["line_colour"]
    lines["line_type"] = lines["line_code"].map(lambda c: "LRT" if c in LRT_LINES else "MRT")
    return lines.set_index("line_code")


def prefix(code_part):
    """'NS24' -> 'NS', 'STC' -> 'STC'"""
    return re.match(r"[A-Z]+", code_part).group()


def describe_station(station_code, gtfs_stations, code_to_station, lines):
    """Name, lines, type and coordinates for one station_code like 'NS24/NE6/CC1'."""
    parts = station_code.split("/")

    # GTFS station(s) this code covers. Usually one; two where the passenger data
    # combines stations GTFS keeps apart (e.g. Bukit Panjang LRT BP6 + MRT DT1).
    gtfs_ids = list(dict.fromkeys(code_to_station[p] for p in parts if p in code_to_station))
    missing_parts = [p for p in parts if p not in code_to_station]

    line_codes = list(dict.fromkeys(PREFIX_TO_LINE[prefix(p)] for p in parts))
    if all(lc in LRT_LINES for lc in line_codes):
        station_type = "LRT"
    elif any(lc in LRT_LINES for lc in line_codes):
        station_type = "MRT+LRT"
    else:
        station_type = "MRT"

    rows = gtfs_stations.loc[gtfs_ids]
    return {
        "station_code": station_code,
        "station_name": " / ".join(dict.fromkeys(rows["stop_name"])) if gtfs_ids else None,
        "lines": "; ".join(lines.loc[lc, "line_name"] for lc in line_codes),
        "line_codes": "; ".join(line_codes),
        "station_type": station_type,
        # Average if the code covers more than one GTFS station (they're ~100-200 m apart)
        "latitude": round(rows["stop_lat"].mean(), 6) if gtfs_ids else None,
        "longitude": round(rows["stop_lon"].mean(), 6) if gtfs_ids else None,
        "gtfs_station_ids": "; ".join(gtfs_ids),
        "missing_parts": "; ".join(missing_parts),
    }


# ---------------------------------------------------------------------------
# 3. Region from URA's region boundaries
# ---------------------------------------------------------------------------
def load_regions():
    """List of (region name, [(outer ring, [holes]), ...]) from the URA GeoJSON.

    GeoJSON coordinates are (longitude, latitude). Each region is a MultiPolygon:
    several pieces (mainland + islands), and a piece can have holes.
    """
    geo = json.loads(REGIONS_GEOJSON.read_text(encoding="utf-8"))
    regions = []
    for feature in geo["features"]:
        name = feature["properties"]["REGION_N"].replace(" REGION", "").title()  # "NORTH-EAST REGION" -> "North-East"
        geom = feature["geometry"]
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        pieces = [(PolygonPath(poly[0]), [PolygonPath(hole) for hole in poly[1:]]) for poly in polygons]
        regions.append((name, pieces))
    return regions


def find_region(lon, lat, regions):
    """Return (region, method). method is 'inside', or 'nearest' if the point
    lies just outside every region (e.g. a station on the waterfront)."""
    point = (lon, lat)
    for name, pieces in regions:
        for outer, holes in pieces:
            if outer.contains_point(point) and not any(h.contains_point(point) for h in holes):
                return name, "inside"

    # Not inside any region: take the region whose boundary is closest
    def distance_to_region(pieces):
        return min(math.dist(point, vertex) for outer, _ in pieces for vertex in outer.vertices)
    nearest = min(regions, key=lambda r: distance_to_region(r[1]))
    return nearest[0], "nearest"


# ---------------------------------------------------------------------------
# 4. Double-check locations against LTA's station exits
# ---------------------------------------------------------------------------
def distance_m(lat1, lon1, lat2, lon2):
    """Straight-line distance in metres between two lat/lon points (haversine formula)."""
    r = 6_371_000  # Earth radius in metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_exits():
    """LTA exits as a table: exit station label, latitude, longitude.
    Labels are usually like 'JURONG EAST MRT STATION'; a few newer exits are
    labelled with just the station code, e.g. 'CC30'."""
    geo = json.loads(EXITS_GEOJSON.read_text(encoding="utf-8"))
    return pd.DataFrame([{"label": f["properties"]["STATION_NA"].strip().upper(),
                          "lon": f["geometry"]["coordinates"][0],
                          "lat": f["geometry"]["coordinates"][1]} for f in geo["features"]])


def exit_check(row, exits):
    """How far is our station point from the centre of its LTA exits?"""
    labels = set(row["station_code"].split("/"))
    for name in str(row["station_name"]).split(" / "):
        labels |= {f"{name.upper()} MRT STATION", f"{name.upper()} LRT STATION"}
    mine = exits[exits["label"].isin(labels)]
    if mine.empty:
        return 0, None
    d = distance_m(row["latitude"], row["longitude"], mine["lat"].mean(), mine["lon"].mean())
    return len(mine), round(d)


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build data/clean/stations.csv")
    parser.add_argument("--month", help="YYYYMM. Default: newest month in data/raw/.")
    month = parser.parse_args().month or latest_raw_month()

    codes = station_codes_for_month(month)
    gtfs_stations, code_to_station = load_gtfs()
    lines = load_lines()
    print(f"Month {month}: {len(codes)} stations in the passenger data")

    stations = pd.DataFrame([describe_station(c, gtfs_stations, code_to_station, lines) for c in codes])

    regions = load_regions()
    has_coords = stations["latitude"].notna()
    found = stations[has_coords].apply(lambda r: find_region(r["longitude"], r["latitude"], regions), axis=1)
    stations.loc[has_coords, "region"] = [region for region, _ in found]
    stations.loc[has_coords, "region_method"] = [method for _, method in found]

    exits = load_exits()
    checked = stations[has_coords].apply(lambda r: exit_check(r, exits), axis=1)
    stations.loc[has_coords, "n_exits"] = [n for n, _ in checked]
    stations.loc[has_coords, "exit_distance_m"] = [d for _, d in checked]

    # ---- Save ----
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    main_cols = ["station_code", "station_name", "lines", "line_codes", "station_type",
                 "latitude", "longitude", "region"]
    stations[main_cols].to_csv(CLEAN_DIR / "stations.csv", index=False)
    stations[["station_code", "station_name", "gtfs_station_ids", "missing_parts",
              "region_method", "n_exits", "exit_distance_m"]].to_csv(CLEAN_DIR / "stations_checks.csv", index=False)
    lines.reset_index().to_csv(CLEAN_DIR / "lines.csv", index=False)

    # ---- Short summary ----
    print(f"Saved {len(stations)} stations to {CLEAN_DIR / 'stations.csv'}")
    print("By type:  ", stations["station_type"].value_counts().to_dict())
    print("By region:", stations["region"].value_counts().to_dict())
    unmatched = stations[stations["missing_parts"] != ""]
    print(f"Codes not found in LTA GTFS: {unmatched['missing_parts'].tolist() or 'none'}")
    nearest = stations[stations["region_method"] == "nearest"]
    print(f"Stations just outside every region (given the nearest one): "
          f"{(nearest['station_name'] + ' -> ' + nearest['region']).tolist() or 'none'}")
    far = stations[stations["exit_distance_m"] > EXIT_CHECK_LIMIT_M]
    print(f"Stations more than {EXIT_CHECK_LIMIT_M} m from their LTA exits: "
          f"{far[['station_name', 'exit_distance_m']].values.tolist() or 'none'}")
    no_exits = stations[stations["n_exits"] == 0]
    print(f"Stations with no LTA exits to compare with: {no_exits['station_name'].tolist() or 'none'}")


if __name__ == "__main__":
    main()
