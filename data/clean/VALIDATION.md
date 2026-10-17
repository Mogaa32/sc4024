# Validation report: 2026-09

Days in the month: 22 weekdays, 8 weekend/holiday days. `*_per_day` columns = monthly total / these day counts.

## 1. Every station matched to coordinates and a region?

- 185 station codes in the passenger data -> 184 stations (Stevens' codes TE11 and DT10 merged into one).
- Codes without coordinates or region: **none** OK
- Station types: {'MRT': 142, 'LRT': 38, 'MRT+LRT': 4}
- Stations per region: {'Central': 88, 'North-East': 39, 'West': 30, 'East': 16, 'North': 11}
- Stations outside every URA region boundary (given the nearest region): none

## 2. Do station locations agree with LTA's station exits?

Each station's location (from LTA's GTFS feed) is compared with the centre of its exits (LTA MRT Station Exit dataset).

- Stations compared: 184 of 184; median distance 28 m, largest 178 m (Woodlands).
- Stations more than 300 m away: none OK

## 3. Total OD trips vs total tap-ins

| day type | tap-ins (station file) | trips (OD file) | gap | OD as % of tap-ins |
|---|---|---|---|---|
| WEEKDAY | 67,641,976 | 66,784,305 | 857,671 | 98.7 |
| WEEKENDS/HOLIDAY | 19,409,461 | 19,095,784 | 313,677 | 98.4 |
| TOTAL | 87,051,437 | 85,880,089 | 1,171,348 | 98.7 |

The two are very close: OD trips are 98.7% of tap-ins in the raw files. At 95% of stations, 97-100% of tap-ins appear as OD trips. Why the gap:

- **No same-station trips in the OD file.** It has 0 rows where origin = destination, so anyone who taps in and out at the same station (e.g. changes their mind) counts in the station file only.
- **Journeys without a valid exit** (e.g. a missing tap-out) can't be given a destination, so they likely can't appear in the OD file. LTA doesn't document this, so treat it as the likely reason, not a fact.
- **Our cleaning** dropped 333 Stevens -> Stevens trips after merging Stevens (decision 3 below).
- Every OD trip begins with a tap-in, so OD should never be above 100%. Highest station: 99.7% OK

Stations with the lowest share:

| code | station | tap_in | od_trips_starting_here | OD as % of tap-ins |
|---|---|---|---|---|
| NE17/PTC | Punggol | 1,320,734 | 1,215,323 | 92.0 |
| CC16 | Marymount | 217,427 | 200,377 | 92.2 |
| CC30 | Keppel | 4,983 | 4,681 | 93.9 |
| CC14 | Lorong Chuan | 234,621 | 223,139 | 95.1 |
| CC20 | Farrer Road | 161,049 | 154,725 | 96.1 |

Note: in the OD file, `hour` is when the trip **started**. Per station and hour (ignoring hours under 100 taps), OD trips by origin are 97%-100% of tap-ins (middle 80% of cases), while OD trips by destination are 69%-127% of tap-outs, because trips end in a later hour.

## 4. Did cleaning keep the totals?

| what | expected | in cleaned file | check |
|---|---|---|---|
| tap-ins | 87,051,437 | 87,051,437 | OK |
| tap-outs | 86,776,212 | 86,776,212 | OK |
| OD trips (raw minus Stevens -> Stevens) | 85,880,089 | 85,880,089 | OK |
| od_region trips vs od_hourly trips | 85,880,089 | 85,880,089 | OK |

- Duplicate rows (same key twice): {'station_hourly': 0, 'od_hourly': 0, 'od_region': 0} OK

## 5. Busiest 10 stations on weekdays

Busiest = tap-ins + tap-outs on an average weekday.

| rank | station_name | station_code | region | tap_in_per_day | tap_out_per_day | total_per_day |
|---|---|---|---|---|---|---|
| 1 | Jurong East | EW24/NS1 | West | 71,040 | 72,435 | 143,475 |
| 2 | Raffles Place | EW14/NS26 | Central | 65,608 | 64,933 | 130,541 |
| 3 | Woodlands | NS9/TE2 | North | 55,905 | 67,365 | 123,270 |
| 4 | Orchard | TE14/NS22 | Central | 58,183 | 61,903 | 120,086 |
| 5 | Serangoon | NE12/CC13 | North-East | 57,764 | 59,709 | 117,474 |
| 6 | Newton | NS21/DT11 | Central | 55,781 | 58,096 | 113,877 |
| 7 | Tampines | EW2/DT32 | East | 55,370 | 57,456 | 112,826 |
| 8 | Yishun | NS13 | North | 51,773 | 56,530 | 108,302 |
| 9 | Bugis | EW12/DT14 | Central | 53,127 | 54,598 | 107,724 |
| 10 | Boon Lay | EW27 | West | 45,898 | 55,997 | 101,895 |

## 6. Missing hours, zeros and negative values

- Hours never in the data: [1, 2, 3, 4] (no train service). They are left out of the cleaned files.
- Station/day-type/hour rows missing in the raw data and filled with 0: 24
    - 00:00, WEEKDAY: BP10, BP11, BP12, BP13, BP2, BP3, BP4, BP5, BP7, BP8, BP9
    - 00:00, WEEKENDS/HOLIDAY: BP10, BP11, BP12, BP13, BP2, BP3, BP4, BP5, BP7, BP8, BP9, CC31
    - 05:00, WEEKENDS/HOLIDAY: CC30
  All are at the edges of the operating day, so most likely the station had no service in that hour (e.g. the Bukit Panjang LRT appears to close before midnight).
- Raw rows with a 0 tap-in or tap-out: 34, at hour(s) [0, 5]. At the first and last trains this is expected (e.g. at midnight people arrive but nobody starts a trip), so they are kept as real values.
- Negative counts: {'raw tap-in': 0, 'raw tap-out': 0, 'raw OD trips': 0, 'clean tap_in/tap_out': 0, 'clean trips': 0} OK
  (`net` is often negative, and that's expected: it means more people ended trips there than started them.)

## Decisions applied in cleaning

1. Monthly totals are kept, and averages per day (`*_per_day`) are added for fair weekday/weekend comparisons.
2. Stevens (TE11 + DT10) is one station, `DT10/TE11`; LTA's GTFS feed also treats it as one.
3. Stevens -> Stevens trips created by that merge are dropped (LTA's OD data has no same-station trips).
4. Station/day-type/hour rows missing in the raw data are filled with 0; od_region too. od_hourly is not filled (a missing pair means 0 trips).
5. Interchanges keep LTA's combined codes (e.g. `NS24/NE6/CC1`). Choa Chu Kang (`NS4/BP1`) and Bukit Panjang (`BP6/DT1`) combine an MRT and an LRT station, as LTA reports them, so they are typed `MRT+LRT`.
6. Regions: the URA Master Plan 2019 region each station's location falls in.
