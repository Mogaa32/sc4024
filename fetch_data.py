"""
fetch_data.py - Step 1 of the pipeline: download the raw data.

Downloads ONE month of LTA DataMall train passenger volume data:
  1. PV/Train   -> tap-in / tap-out volume per station, per hour
  2. PV/ODTrain -> number of trips between each pair of stations, per hour

How the LTA API works (checked against the LTA DataMall API User Guide v6.10):
  - GET https://datamall2.mytransport.sg/ltaodataservice/PV/Train  (or PV/ODTrain)
  - The API key goes in a request header called "AccountKey".
  - Optional parameter Date=YYYYMM. Only the last 3 months are kept;
    asking for any other month returns HTTP 404.
  - The response does not contain the data. It is a small JSON like
        {"value": [{"Link": "https://...zip"}]}
    The Link is a ZIP file (with one CSV inside) and expires after 15 minutes.

Usage:
    python fetch_data.py                 # most recent month available for BOTH datasets
    python fetch_data.py --month 202608  # a specific month (YYYYMM)

Output (in data/raw/):
    transport_node_train_YYYYMM.zip      and the CSV inside it
    origin_destination_train_YYYYMM.zip  and the CSV inside it
"""

import argparse
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import requests
import truststore
from dotenv import load_dotenv

from common import PROJECT_DIR, RAW_DIR

# Use the operating system's certificate store for HTTPS instead of Python's
# own bundled list. This is needed on laptops where antivirus software
# (e.g. Norton) inspects HTTPS traffic with its own certificate. It is
# harmless on other machines, and certificate checking stays switched on.
truststore.inject_into_ssl()

BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice"

# API endpoint -> the file name prefix LTA uses for that dataset's ZIP
DATASETS = {
    "PV/Train": "transport_node_train",
    "PV/ODTrain": "origin_destination_train",
}


def load_api_key():
    """Read the API key from the .env file. The key is never printed."""
    load_dotenv(PROJECT_DIR / ".env")
    key = os.getenv("LTA_API_KEY")
    if not key:
        sys.exit("ERROR: LTA_API_KEY not found. Create a .env file (see .env.example).")
    return key


def get_download_link(endpoint, month, api_key):
    """Ask the API for the ZIP download link of one dataset for one month.
    Returns the link, or None if that month is not available (HTTP 404)."""
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={"AccountKey": api_key, "accept": "application/json"},
        params={"Date": month},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()  # stop on any other error, e.g. 401 = bad key
    return response.json()["value"][0]["Link"]


def previous_months(n):
    """The n calendar months before the current one, newest first, as YYYYMM.
    E.g. on 2026-10-12 with n=3 -> ['202609', '202608', '202607']."""
    months = []
    year, month = date.today().year, date.today().month
    for _ in range(n):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        months.append(f"{year}{month:02d}")
    return months


def find_latest_month(api_key):
    """Find the most recent month for which BOTH datasets are available.

    LTA only publishes a month after it has ended (by the 10th of the next
    month), so any month it returns is complete. The current month is never
    available, so we start from last month and go back up to 3 months."""
    for month in previous_months(3):
        if all(get_download_link(endpoint, month, api_key) for endpoint in DATASETS):
            return month
    sys.exit("ERROR: could not find a month where both datasets are available.")


def download_zip(endpoint, prefix, month):
    """Download one dataset's ZIP into data/raw/. Skipped if it already exists
    (the ZIPs are kept in git, so a teammate doesn't need an API key for them)."""
    zip_path = RAW_DIR / f"{prefix}_{month}.zip"
    if zip_path.exists():
        print(f"  [skip] {zip_path.name} already downloaded")
        return zip_path

    link = get_download_link(endpoint, month, load_api_key())
    if link is None:
        sys.exit(f"ERROR: {endpoint} has no data for {month} "
                 "(LTA only keeps the last 3 months).")

    print(f"  downloading {zip_path.name} ...")
    response = requests.get(link, timeout=300)
    response.raise_for_status()

    # Write to a temporary name first, then rename. This way a download that
    # fails halfway never leaves a file behind that looks finished.
    tmp_path = zip_path.with_name(zip_path.name + ".part")
    tmp_path.write_bytes(response.content)
    tmp_path.replace(zip_path)
    return zip_path


def extract_csv(zip_path):
    """Extract the CSV file(s) in the ZIP into data/raw/. Skipped if already extracted."""
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith("/"):  # a folder entry, nothing to extract
                continue
            out_path = RAW_DIR / Path(name).name  # ignore any folders inside the ZIP
            if out_path.exists():
                print(f"  [skip] {out_path.name} already extracted")
                continue
            print(f"  extracting {out_path.name}")
            out_path.write_bytes(zf.read(name))


def main():
    parser = argparse.ArgumentParser(description="Download one month of LTA train passenger volume data.")
    parser.add_argument("--month", help="Month as YYYYMM, e.g. 202608. Default: most recent available.")
    args = parser.parse_args()

    if args.month and not re.fullmatch(r"\d{6}", args.month):
        sys.exit("ERROR: --month must look like YYYYMM, e.g. 202608")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    month = args.month or find_latest_month(load_api_key())
    print(f"Month: {month}")

    for endpoint, prefix in DATASETS.items():
        print(f"{endpoint}:")
        zip_path = download_zip(endpoint, prefix, month)
        extract_csv(zip_path)

    print(f"Done. Raw files are in {RAW_DIR}")


if __name__ == "__main__":
    main()
