# Passenger-flow animations

Use Python 3.11+, pandas, NumPy, Matplotlib, Pillow and Arial; see README.md for exact cleaned input paths. FFmpeg with libx264 must be on PATH; FFprobe is also needed for full validation. No generated output CSV is required for rendering.

~~~powershell
python -B -m visualizations.passenger_flows.animate --all
python -B -m visualizations.passenger_flows.validate_outputs --full --no-write
~~~

Full validation needs the static artifact set too. Use --static --no-write for static-only checks. Omit --no-write only when refreshing reports.

Individual flags: --flow-map, --highlight-map, --diverging-bar, --slopegraph. Use --output-dir <temporary-directory> for isolated exports. Default directory: outputs/passenger_flows/202609/animations/.

| File | Seconds | Frames at 15 fps | Motion |
|---|---:|---:|---|
| flow_map_animated.mp4 | 8 | 120 | Reveal ranks 11-15 blue, 6-10 teal, 1-5 amber; fixed daily-volume widths and geography. |
| flow_map_highlight_animated.mp4 | 6 | 90 | All blue initially; only Tampines to Pasir Ris fades to amber. |
| diverging_bar_animated.mp4 | 8 | 120 | Grow to morning values, hold, visually interpolate to evening; labels hidden during interpolation. |
| slopegraph_animated.mp4 | 8 | 120 | Reveal weekday ranks, draw static connections, reveal weekend ranks; axis break always visible. |

All clips are silent H.264/yuv420p at 1280 x 720. The bar animation uses a full-width single panel ending at the exact static evening values. Map curves do not represent physical train routes. Intermediate bar positions are presentation effects, not observed hours. No intermediate ranks or trip counts are invented.

Canva sequence: categorical map 3:00, highlight map 3:20, regional Sankey PNG 3:40, Central-focus PNG 4:15, diverging clip 4:40, slopegraph clip 5:15, conclusion 5:45. Hold final frames during narration instead of looping transitions.

Existing audit tables are compared if present but never required. The three historical PNGs and top-10 audit table remain preserved assets for full static validation; see README.md for reproduction order.
