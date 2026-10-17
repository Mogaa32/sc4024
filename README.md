# Singapore MRT ridership: data pipeline (SC4024)

Data for our video on MRT/LRT ridership: which stations are busiest, how ridership changes by hour,
where people travel, and how weekdays differ from weekends.

The pipeline takes **one month** of LTA passenger data (currently **September 2026**), cleans it, and adds
station names, locations, lines and regions. Every step is a small Python script you can rerun.

## Teammates: start here

The cleaned data is already in the repo, so you can start making charts straight away. No API key needed.

```bash
git clone https://github.com/Mogaa32/sc4024.git
cd sc4024
pip install -r requirements.txt          # Python 3.10 or newer (on a Mac, use pip3 / python3)
```

1. Load the files in `data/clean/` (see [Output files](#output-files-dataclean) below), e.g.
   `pd.read_csv("data/clean/station_hourly.csv")`.
2. Join any table to `data/clean/stations.csv` on the station code to get names, map positions and regions.
3. Read [Things to know before making charts](#things-to-know-before-making-charts) first. Most importantly,
   compare weekdays and weekends with the `*_per_day` columns.
4. To open the EDA notebook (`eda.ipynb`), first run `python fetch_data.py --month 202609` once. It unzips the
   raw files the notebook reads (the extracted CSVs are too big for git).

## Rerunning the pipeline

```bash
pip install -r requirements.txt
```

Run the scripts in this order:

```bash
python fetch_data.py --month 202609   # 1. raw passenger data            -> data/raw/
python fetch_reference.py             # 2. station list, exits, regions  -> data/reference/
python build_stations.py              # 3. one row per station           -> data/clean/stations.csv
python clean_data.py                  # 4. tidy tables for charts        -> data/clean/*.csv
python validate.py                    # 5. checks                        -> data/clean/VALIDATION.md
```

Optional extras:
- `python inspect_raw.py` gives a quick look at the raw files (columns, codes, missing hours).
- `eda.ipynb` is the exploratory charts notebook (works on the raw data). Open it in VS Code and click Run All.

Every script uses the newest month in `data/raw/` by default and accepts `--month YYYYMM`.

### Do I need an API key?

Only to download data that isn't in the repo yet. The September 2026 ZIPs and the reference files are
committed, so steps 1–5 run without a key (step 1 just unzips). To download a new month:
copy `.env.example` to `.env` and put your LTA DataMall key in it (`LTA_API_KEY=...`). **Never commit `.env`.**

LTA only keeps the **last 3 months**. That's why the raw ZIPs are kept in git: September 2026 can't be
downloaded again after about January 2027. `python fetch_data.py` with no `--month` asks LTA for its newest
month, so always pass `--month 202609` to work on our month.

## Output files (`data/clean/`)

### `stations.csv`: one row per physical station (184 rows)

| column | meaning | example |
|---|---|---|
| station_code | Station ID; the same codes as the passenger data. Interchanges have one combined code. | `EW24/NS1` |
| station_name | Name from LTA | `Jurong East` |
| lines | Line name(s) | `East-West Line; North-South Line` |
| line_codes | Short line code(s); see `lines.csv` | `EW; NS` |
| station_type | `MRT`, `LRT`, or `MRT+LRT` (one station shared by both) | `MRT` |
| latitude, longitude | Location (WGS84) | `1.333209`, `103.742263` |
| region | URA planning region: Central, East, North, North-East, West | `West` |

### `station_hourly.csv`: taps per station per hour (7,360 rows = 184 stations × 2 day types × 20 hours)

| column | meaning |
|---|---|
| station_code | joins to `stations.csv` |
| day_type | `WEEKDAY` or `WEEKENDS/HOLIDAY` |
| hour | 0–23; `8` means 08:00–08:59. Hours 1–4 are not included (no trains). |
| tap_in, tap_out | people entering / leaving the station: **monthly totals** |
| net | `tap_in - tap_out`. Positive: more trips start here than end here. |
| tap_in_per_day, tap_out_per_day, net_per_day | the same, as an **average day** |

### `od_hourly.csv`: trips between station pairs (880,362 rows)

| column | meaning |
|---|---|
| origin_code, destination_code | where the trip started and ended (join to `stations.csv`) |
| day_type | `WEEKDAY` or `WEEKENDS/HOLIDAY` |
| hour | the hour the trip **started** (tap-in) |
| trips | monthly total |
| trips_per_day | average day |

A station pair/hour that isn't in the file had **0 trips**. Rows are not filled in because that would add over a million empty rows.

### `od_region.csv`: trips between regions (1,000 rows = 5 × 5 regions × 2 day types × 20 hours)

Columns: `origin_region, destination_region, day_type, hour, trips, trips_per_day` (same meanings as above).
Trips within a region (e.g. Central → Central) are included.

### Other files
- `lines.csv`: each line's code, name, **official colour** (e.g. North-South Line `#D62821`) and MRT/LRT type. Useful for chart colours.
- `stations_checks.csv`: how each station's location and region were checked (read by `validate.py`).
- `VALIDATION.md`: the validation report: matching, totals, busiest stations, missing values.

## Things to know before making charts

1. **LTA's numbers are monthly totals.** `WEEKDAY, hour 8` means all 08:00–08:59 taps added up over *every*
   weekday in the month. September 2026 had 22 weekdays but only 8 weekend days, so **use the `*_per_day`
   columns to compare weekdays with weekends**. Totals make weekdays look 3.5× busier; per day it's 1.27×.
2. **OD `hour` = when the trip started.** Don't compare it with tap-outs by hour.
3. **The two files agree closely.** OD trips are 98.7% of tap-ins. The OD file has no same-station trips, which explains most of the gap (details in `VALIDATION.md`).
4. **Always join on `station_code`**, never on station name.

## Decisions we made (and why)

| decision | why |
|---|---|
| Keep monthly totals and add `*_per_day` averages | Weekday and weekend totals cover different numbers of days |
| Merge Stevens `TE11` + `DT10` into one station, `DT10/TE11` | It's one interchange; LTA reports every other interchange under one code, and LTA's GTFS feed also treats Stevens as one |
| Drop the 333 Stevens → Stevens trips that merge creates | LTA's OD data has no same-station trips |
| Fill missing station/day-type/hour rows with 0 (24 rows) | A missing row means nobody tapped (e.g. Bukit Panjang LRT at midnight) |
| Keep LRT stations and mark them `LRT` / `MRT+LRT` | Choa Chu Kang, Bukit Panjang, Sengkang and Punggol combine MRT and LRT in LTA's data, and their numbers can't be split |
| Station locations from LTA's GTFS train feed | Official LTA data, same station codes as the passenger data (all 216 codes found), up to date |
| Cross-check locations against LTA's station exits | Every station is within 300 m of its exits (median 28 m) |
| Regions from URA Master Plan 2019 region boundaries | The official planning regions; exactly the five we need |

## Data sources

| data | publisher | used for |
|---|---|---|
| [Passenger Volume by Train Stations](https://datamall.lta.gov.sg) (`PV/Train`) | LTA DataMall | tap-ins and tap-outs |
| [Passenger Volume by Origin Destination Train Stations](https://datamall.lta.gov.sg) (`PV/ODTrain`) | LTA DataMall | trips between stations |
| [GTFS Schedule (Train)](https://datamall.lta.gov.sg) (`GTFSScheduleTrain`) | LTA DataMall | station names, locations, lines, line colours |
| [LTA MRT Station Exit (GeoJSON)](https://data.gov.sg/datasets/d_b39d3a0871985372d7e1637193335da5/view) | LTA via data.gov.sg | double-checking locations |
| [Master Plan 2019 Region Boundary (No Sea)](https://data.gov.sg/datasets/d_bf4d24df9129d5a8ff8cf82e20959ee0/view) | URA via data.gov.sg | regions |

API details (URLs, parameters, response fields) follow the
[LTA DataMall API User Guide](https://datamall.lta.gov.sg/content/dam/datamall/datasets/LTA_DataMall_API_User_Guide.pdf) v6.10.
Public holidays (for counting weekend/holiday days) are in `common.py` and come from MOM's 2026 list.

## Folder layout

```
fetch_data.py        download one month of passenger data (LTA DataMall)
fetch_reference.py   download station list, exits and region boundaries
inspect_raw.py       quick look at the raw files
build_stations.py    data/clean/stations.csv (+ lines.csv, stations_checks.csv)
clean_data.py        data/clean/station_hourly.csv, od_hourly.csv, od_region.csv
validate.py          data/clean/VALIDATION.md
common.py            shared paths and helpers (station code rules, day counts)
eda.ipynb            exploratory charts
data/raw/            LTA ZIPs (in git) and extracted CSVs (not in git)
data/reference/      station list, exits, regions (in git)
data/clean/          cleaned outputs
```

## Troubleshooting

- **`SSLCertVerificationError`**: some antivirus software (e.g. Norton) inspects HTTPS traffic. The scripts
  use `truststore` so Python trusts the same certificates as Windows; make sure it is installed.
- **`... has no data for YYYYMM`**: LTA only keeps the last 3 months.
- **HTTP 401**: the API key in `.env` is wrong.
- **data.gov.sg "slow down" messages**: normal; `fetch_reference.py` waits and retries by itself.
