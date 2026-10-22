# Validation results: September 2026 passenger flows

PASS: independent CSV-based recomputation; chart aggregation helpers were not imported.

- 880,362 OD rows; 7,360 station-hour rows; 184 stations.
- OD monthly total: 85,880,089; tap-ins: 87,051,437; tap-outs: 86,776,212.
- Top 15 directions, monthly totals, weekday/weekend/calendar-day denominators, names and coordinates match source data.
- Both flow-map PNGs use the same verified top 15; ranked volume categories contain five links each and their data-derived ranges are recorded in validation_summary.json.
- All 25 regional flows match both station-level OD aggregation and committed od_region.csv.
- Top three destinations per region verified independently; all origin attribution retained.
- All 20 station buckets and all 62 integer conservation checks pass, with zero differences.
- All 12 selected and 368 full-network station-period net values verified directly from gate counts with tap_out - tap_in.
- All 184 station ranks and normalized daily volumes independently verified (competition ranks).
- Top-three positive/negative morning selection, code tie-breaks, evening reversals and all-station net ranks verified.
- Backup top-10 tables and original six ranks verified; main slopegraph is the independently verified eight-station top-five union.
- All 14 PNGs (including backups) are opaque 1280 x 720.
- All four MP4s are video-only H.264/yuv420p at 1280 x 720 and 15 fps; expected frame counts, durations and full-stream decoding pass.
- Input SHA-256 hashes and installed library versions are in validation_summary.json.

Visual review is documented in the implementation README; numerical checks do not replace visual inspection.
