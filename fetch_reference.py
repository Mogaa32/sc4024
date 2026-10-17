"""
fetch_reference.py - download the reference data used to describe stations.

These files don't depend on the month, so they are downloaded once, saved in
data/reference/ and kept in git. Saving a copy matters: the sources only ever
give their CURRENT version, and station codes do change (e.g. Bayfront was
renumbered from CE1 to CC34 in July 2026).

Downloads (each one is skipped if the file already exists):
  1. LTA GTFS Schedule (Train), from LTA DataMall (needs the API key)
       -> gtfs_train/stops.txt     station codes, names, latitude/longitude
       -> gtfs_train/routes.txt    line names and official line colours
       -> gtfs_train/feed_info.txt which version of the feed this is
  2. LTA MRT Station Exit (GeoJSON), from data.gov.sg
       -> lta_mrt_station_exits.geojson   used to double-check station locations
  3. URA Master Plan 2019 Region Boundary (No Sea) (GeoJSON), from data.gov.sg
       -> ura_mp2019_region_boundary.geojson   the 5 planning regions

Usage:
    python fetch_reference.py
"""

import io
import time
import zipfile

import requests

from common import EXITS_GEOJSON, GTFS_DIR, REF_DIR, REGIONS_GEOJSON
from fetch_data import BASE_URL, load_api_key  # importing fetch_data also sets up HTTPS certificates

GTFS_FILES_TO_KEEP = ["stops.txt", "routes.txt", "feed_info.txt"]  # the other GTFS files are timetables we don't need

# data.gov.sg dataset IDs (from each dataset's page on data.gov.sg)
DATA_GOV_SG = {
    EXITS_GEOJSON: "d_b39d3a0871985372d7e1637193335da5",    # LTA MRT Station Exit (GEOJSON)
    REGIONS_GEOJSON: "d_bf4d24df9129d5a8ff8cf82e20959ee0",  # Master Plan 2019 Region Boundary (No Sea) (GEOJSON)
}


def fetch_gtfs():
    """Download LTA's GTFS train feed and keep only the files we need."""
    if all((GTFS_DIR / name).exists() for name in GTFS_FILES_TO_KEEP):
        print(f"[skip] {GTFS_DIR.name}/ already downloaded")
        return

    # Same pattern as the passenger volume APIs: the API returns a link to a ZIP.
    # (This API names the field "link" in lower case.)
    response = requests.get(f"{BASE_URL}/GTFSScheduleTrain",
                            headers={"AccountKey": load_api_key(), "accept": "application/json"},
                            timeout=30)
    response.raise_for_status()
    link = response.json()["value"][0]["link"]

    print("downloading LTA GTFS train feed ...")
    zip_bytes = requests.get(link, timeout=300).content
    GTFS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in GTFS_FILES_TO_KEEP:
            (GTFS_DIR / name).write_bytes(zf.read(name))
            print(f"  saved {GTFS_DIR.name}/{name}")


def fetch_data_gov_sg(out_path, dataset_id):
    """Download one dataset file from data.gov.sg."""
    if out_path.exists():
        print(f"[skip] {out_path.name} already downloaded")
        return

    # data.gov.sg also returns a temporary download link first. It allows only a
    # few requests per minute without a key, so if we are told to slow down
    # ("TOO_MANY_REQUESTS"), wait and try again.
    poll_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
    for _attempt in range(6):
        reply = requests.get(poll_url, timeout=30).json()
        if reply.get("code") == 0 and reply["data"].get("url"):
            break
        print("  data.gov.sg asked us to slow down, waiting 15 s ...")
        time.sleep(15)
    else:
        raise SystemExit(f"ERROR: could not get a download link for {dataset_id}")

    print(f"downloading {out_path.name} ...")
    response = requests.get(reply["data"]["url"], timeout=120)
    response.raise_for_status()
    out_path.write_bytes(response.content)
    time.sleep(5)  # be polite before the next data.gov.sg request


def main():
    REF_DIR.mkdir(parents=True, exist_ok=True)
    fetch_gtfs()
    for out_path, dataset_id in DATA_GOV_SG.items():
        fetch_data_gov_sg(out_path, dataset_id)
    print(f"Done. Reference files are in {REF_DIR}")


if __name__ == "__main__":
    main()
