"""Data-driven 720p animations for the passenger-flow presentation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.animation import FFMpegWriter, FuncAnimation
from matplotlib.patches import FancyArrowPatch, Patch, Polygon
from matplotlib.ticker import FuncFormatter

from .shared import (AMBER, BG, BLUE, GRID, MUTED, OUT, TEAL, TEXT, TABLES,
                     frame, load_data, pair_totals, require, setup)
from .flow_map import (LEGEND_Y, OFFSETS, arrow_dimensions, category_details,
                       draw_thickness_legend)
from .slopegraph import display_rank, separated_positions

FPS = 15
ANIMATIONS = OUT / "animations"
MAP_CATEGORY_FRAMES = 120       # 8 seconds
MAP_HIGHLIGHT_FRAMES = 90       # 6 seconds
DIVERGING_FRAMES = 120          # 8 seconds
SLOPEGRAPH_FRAMES = 120         # 8 seconds


def clamp01(value):
    return float(np.clip(value, 0.0, 1.0))


def ease(value):
    value = clamp01(value)
    return value * value * (3.0 - 2.0 * value)


def save_animation(fig, update, frame_count, filename):
    """Encode H.264/yuv420p without creating intermediate frame files."""
    ANIMATIONS.mkdir(parents=True, exist_ok=True)
    path = ANIMATIONS / filename
    animation = FuncAnimation(fig, update, frames=frame_count,
                              interval=1000 / FPS, blit=False, repeat=False)
    writer = FFMpegWriter(
        fps=FPS, codec="libx264", bitrate=-1,
        extra_args=["-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart"])
    animation.save(path, writer=writer, dpi=100)
    plt.close(fig)
    print(f"{path}: "
          f"{frame_count} frames, {frame_count / FPS:.1f} s at {FPS} fps")


def prepare_map_data():
    stations, od, _ = load_data()
    pairs = pair_totals(od, stations).head(15).copy()
    pairs.insert(0, "rank", range(1, 16))
    require(pairs["rank"].tolist() == list(range(1, 16)),
            "Expected deterministic top-15 ranks")
    require((pairs.iloc[0].origin_code, pairs.iloc[0].destination_code,
             int(pairs.iloc[0].monthly_trips)) == ("EW2/DT32", "EW1", 191047),
            "Highest-volume directed pair changed")
    categories = category_details(pairs)
    require({name: len(group) for name, group in categories.items()}
            == {"Higher": 5, "Medium": 5, "Lower": 5},
            "Expected five links in each volume category")
    selected = stations[stations.station_code.isin(
        set(pairs.origin_code) | set(pairs.destination_code))]
    geo = json.loads((Path(__file__).resolve().parents[2] /
                      "data/reference/ura_mp2019_region_boundary.geojson").read_text(
                          encoding="utf-8"))
    return stations, pairs, selected, geo


def map_scene(mode):
    """Build the fixed static geography and return independently animatable arrows."""
    stations, pairs, selected, geo = prepare_map_data()
    fig = frame()
    ax = fig.add_axes([.005, .015, .99, .96])
    for feature in geo["features"]:
        polygons = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            polygons = [polygons]
        for polygon in polygons:
            ax.add_patch(Polygon(polygon[0], facecolor="#1C242A", edgecolor="#424D55",
                                 linewidth=.6, zorder=0))
            for hole in polygon[1:]:
                ax.add_patch(Polygon(hole, facecolor=BG, edgecolor="none"))
    ax.scatter(stations.longitude, stations.latitude, s=5, color="#56616B",
               alpha=.65, zorder=1)

    category_for_rank = {**{rank: "Higher" for rank in range(1, 6)},
                         **{rank: "Medium" for rank in range(6, 11)},
                         **{rank: "Lower" for rank in range(11, 16)}}
    category_colors = {"Lower": BLUE, "Medium": TEAL, "Higher": AMBER}
    arrows = {}
    for row in pairs.iloc[::-1].itertuples():
        color = BLUE if mode == "highlight" else category_colors[category_for_rank[row.rank]]
        arrow = FancyArrowPatch(
            (row.origin_longitude, row.origin_latitude),
            (row.destination_longitude, row.destination_latitude),
            connectionstyle="arc3,rad=0.20", arrowstyle="-|>",
            **arrow_dimensions(row.trips_per_calendar_day), color=color,
            alpha=.92 if mode == "highlight" else 0.0,
            shrinkA=5, shrinkB=5, zorder=3)
        ax.add_patch(arrow)
        arrows[int(row.rank)] = arrow

    ax.scatter(selected.longitude, selected.latitude, s=32, color=TEXT,
               edgecolor=BG, linewidth=.8, zorder=4)
    for row in selected.itertuples():
        dx, dy = OFFSETS[row.station_code]
        ax.annotate(row.station_name, (row.longitude, row.latitude),
                    xytext=(dx, dy), textcoords="offset points", fontsize=13,
                    color=TEXT, zorder=5,
                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": .6},
                    bbox={"facecolor": BG, "edgecolor": "none", "alpha": .8,
                          "pad": 1.5})
    lon0, lon1 = selected.longitude.min(), selected.longitude.max()
    lat0, lat1 = selected.latitude.min(), selected.latitude.max()
    dx, dy = (lon1-lon0)*.08, (lat1-lat0)*.08
    ax.set_xlim(lon0-dx, lon1+dx)
    ax.set_ylim(lat0-dy, lat1+dy)
    ax.set_aspect(1/np.cos(np.deg2rad(selected.latitude.mean())))
    ax.axis("off")
    draw_thickness_legend(fig, pairs, mode)
    return fig, arrows, pairs


def animate_flow_map_categories():
    fig, arrows, _ = map_scene("categories")
    groups = [((11, 12, 13, 14, 15), .4, 2.1),
              ((6, 7, 8, 9, 10), 2.2, 3.9),
              ((1, 2, 3, 4, 5), 4.0, 5.7)]

    def update(frame_number):
        t = frame_number / FPS
        for ranks, start, end in groups:
            alpha = .92 * ease((t-start)/(end-start))
            for rank in ranks:
                arrows[rank].set_alpha(alpha)
        return list(arrows.values())

    save_animation(fig, update, MAP_CATEGORY_FRAMES, "flow_map_animated.mp4")


def animate_flow_map_highlight():
    fig, arrows, _ = map_scene("highlight")
    start_rgb = np.array(mcolors.to_rgb(BLUE))
    end_rgb = np.array(mcolors.to_rgb(AMBER))

    def update(frame_number):
        t = frame_number / FPS
        progress = ease((t-1.0)/2.0)
        arrows[1].set_color(tuple(start_rgb + (end_rgb-start_rgb)*progress))
        arrows[1].set_alpha(.92)
        return list(arrows.values())

    save_animation(fig, update, MAP_HIGHLIGHT_FRAMES,
                   "flow_map_highlight_animated.mp4")


def prepare_diverging_data():
    stations, _, hourly = load_data()
    names = stations.set_index("station_code").station_name
    periods = {"Morning": [7, 8, 9], "Evening": [17, 18, 19]}
    values = {}
    for period, hours in periods.items():
        grouped = (hourly[(hourly.day_type == "WEEKDAY") & hourly.hour.isin(hours)]
                   .groupby("station_code")[["tap_in", "tap_out"]].sum()
                   .reindex(stations.station_code))
        values[period] = (grouped.tap_out-grouped.tap_in)/22
    morning = values["Morning"]
    positive = (morning[morning > 0].rename("value").reset_index()
                .sort_values(["value", "station_code"], ascending=[False, True])
                .head(3).station_code.tolist())
    negative = (morning[morning < 0].rename("value").reset_index()
                .sort_values(["value", "station_code"], ascending=[True, True])
                .head(3).station_code.tolist())
    codes = positive + negative
    require(len(codes) == len(set(codes)) == 6, "Expected six distinct net-flow extremes")

    if (TABLES / "station_net_movement.csv").is_file():
        audit = pd.read_csv(TABLES / "station_net_movement.csv")
        for period in periods:
            expected = values[period].loc[codes].to_numpy()
            actual = (audit[audit.period == period].set_index("station_code")
                      .loc[codes].net_into_surroundings_per_weekday.to_numpy())
            require(np.allclose(expected, actual, atol=5e-9, rtol=0),
                    f"{period} animation values differ from validated static chart")
    return names, codes, values["Morning"].loc[codes].to_numpy(), \
        values["Evening"].loc[codes].to_numpy()


def animate_diverging_bar():
    names, codes, morning, evening = prepare_diverging_data()
    fig = frame()
    ax = fig.add_axes([.18, .16, .72, .74])
    y = np.arange(6)
    bars = ax.barh(y, np.zeros(6), height=.5,
                   color=[TEAL if value > 0 else AMBER for value in morning])
    ax.axvline(0, color=TEXT, lw=1)
    ax.set_xlim(-45000, 45000)
    ax.set_ylim(5.65, -.65)
    ax.set_yticks(y, [names[code] for code in codes])
    ax.tick_params(axis="y", length=0, labelsize=14)
    ax.set_xticks([-40000, -20000, 0, 20000, 40000])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value/1000:.0f}k"))
    ax.grid(axis="x", color=GRID, lw=.6)
    ax.set_axisbelow(True)
    period_label = ax.text(0, 1.025, "Morning (07:00\u201310:00)",
                           transform=ax.transAxes, fontsize=17, ha="left", va="bottom")
    ax.set_xlabel("Net gate movements / weekday", fontsize=12, labelpad=11)
    value_labels = [ax.text(0, row, "", va="center", fontsize=13, alpha=0)
                    for row in y]
    fig.legend(handles=[
        Patch(facecolor=TEAL, label="Net inflow (tap-outs > tap-ins)"),
        Patch(facecolor=AMBER, label="Net outflow (tap-ins > tap-outs)")],
        loc="lower center", bbox_to_anchor=(.54, .015), ncol=2,
        frameon=False, fontsize=13, labelcolor=TEXT, columnspacing=2.2)

    def update(frame_number):
        t = frame_number / FPS
        if t < 2.5:
            endpoint = morning * ease(t/2.5)
            show_values = False
            period_label.set_text("Morning (07:00\u201310:00)")
        elif t < 3.5:
            endpoint = morning
            show_values = True
            period_label.set_text("Morning (07:00\u201310:00)")
        elif t < 6.5:
            progress = ease((t-3.5)/3.0)
            endpoint = morning + (evening-morning)*progress
            show_values = False
            period_label.set_text("Evening (17:00\u201320:00)")
        else:
            endpoint = evening
            show_values = True
            period_label.set_text("Evening (17:00\u201320:00)")
        for row, (bar, label, value) in enumerate(zip(bars, value_labels, endpoint)):
            bar.set_width(value)
            bar.set_color(TEAL if value >= 0 else AMBER)
            if show_values:
                label.set_text(f"{value:+,.0f}")
                label.set_x(value + (1100 if value > 0 else -1100))
                label.set_ha("left" if value > 0 else "right")
                label.set_alpha(1)
            else:
                label.set_alpha(0)
        return [*bars, *value_labels, period_label]

    save_animation(fig, update, DIVERGING_FRAMES, "diverging_bar_animated.mp4")


def prepare_slopegraph_data():
    stations, _, hourly = load_data()
    totals = hourly.groupby(["station_code", "day_type"])[["tap_in", "tap_out"]].sum()
    volume = (totals.tap_in + totals.tap_out).unstack()
    data = (stations[["station_code", "station_name", "station_type"]]
            .set_index("station_code").join(volume))
    data["weekday_activity_per_day"] = data.WEEKDAY/22
    data["weekend_holiday_activity_per_day"] = data["WEEKENDS/HOLIDAY"]/8
    data["weekday_rank"] = data.weekday_activity_per_day.rank(
        method="min", ascending=False).astype(int)
    data["weekend_holiday_rank"] = data.weekend_holiday_activity_per_day.rank(
        method="min", ascending=False).astype(int)
    weekday_top = (data.reset_index().sort_values(
        ["weekday_activity_per_day", "station_code"], ascending=[False, True])
        .head(5).station_code.tolist())
    weekend_top = (data.reset_index().sort_values(
        ["weekend_holiday_activity_per_day", "station_code"], ascending=[False, True])
        .head(5).station_code.tolist())
    codes = list(dict.fromkeys(weekday_top + weekend_top))
    require(len(codes) == 8, "Expected eight-station top-five union")

    if (TABLES / "station_rank_changes.csv").is_file():
        audit = pd.read_csv(TABLES / "station_rank_changes.csv").set_index("station_code")
        require(set(codes) == set(audit.index), "Animation station selection differs from static chart")
        for code in codes:
            require((int(data.loc[code, "weekday_rank"]),
                     int(data.loc[code, "weekend_holiday_rank"])) ==
                    (int(audit.loc[code, "weekday_rank"]),
                     int(audit.loc[code, "weekend_holiday_rank"])),
                    "Animation rank differs from validated static chart")
    return data, codes


def animate_slopegraph():
    data, codes = prepare_slopegraph_data()
    fig = frame()
    ax = fig.add_axes([.04, .015, .92, .965])
    ax.set_xlim(-.65, 1.72)
    ax.set_ylim(19.9, -2)
    ax.axis("off")
    ax.text(.5, -1.65, "Station Activity Ranking (Average Daily Tap-ins + Tap-outs)",
            ha="center", fontsize=12, color=MUTED)
    ax.plot([0, 0], [1, 16], color=GRID, lw=1.5)
    ax.plot([1, 1], [1, 16.6], color=GRID, lw=1.5)
    ax.plot([1, 1], [17.6, 19], color=GRID, lw=1.5)
    for y in [16.95, 17.30]:
        ax.plot([.975, 1.025], [y+.13, y-.13], color=MUTED, lw=2.2, zorder=6)
    ax.text(1.075, 17.12, "//  17-47", fontsize=12, color=MUTED, va="center")
    ax.text(0, -.45, "WEEKDAY", ha="center", fontsize=13, color=BLUE, weight="bold")
    ax.text(1, -.45, "WEEKEND / HOLIDAY", ha="center", fontsize=13,
            color=BLUE, weight="bold")
    ax.text(1, .22, "Broken rank scale", ha="center", fontsize=11, color=MUTED)

    selected = data.loc[codes]
    left = separated_positions({code: display_rank(rank)
                                for code, rank in selected.weekday_rank.items()})
    right = separated_positions({code: display_rank(rank)
                                 for code, rank in selected.weekend_holiday_rank.items()})
    artists = []
    for code, row in selected.iterrows():
        color = AMBER if code == "EW14/NS26" else TEAL if code == "NS25/EW13" else BLUE
        weekday_rank = int(row.weekday_rank)
        weekend_rank = int(row.weekend_holiday_rank)
        y0, y1 = display_rank(weekday_rank), display_rank(weekend_rank)
        connection, = ax.plot([], [], color=color, lw=2.4, alpha=.9, zorder=2)
        left_point = ax.scatter([0], [y0], s=38, color=color, zorder=3, alpha=0)
        right_point = ax.scatter([1], [y1], s=38, color=color, zorder=3, alpha=0)
        left_leader, = ax.plot([-.06, 0], [left[code], y0], color=MUTED, lw=.7, alpha=0)
        right_leader, = ax.plot([1, 1.06], [y1, right[code]], color=MUTED, lw=.7, alpha=0)
        left_label = ax.text(-.075, left[code], f"{row.station_name}  #{weekday_rank}",
                             ha="right", va="center", fontsize=14, alpha=0)
        right_label = ax.text(1.075, right[code], f"#{weekend_rank}  {row.station_name}",
                              ha="left", va="center", fontsize=14, alpha=0)
        artists.append({"line": connection, "left_point": left_point,
                        "right_point": right_point, "left_leader": left_leader,
                        "right_leader": right_leader, "left_label": left_label,
                        "right_label": right_label, "y0": y0, "y1": y1})

    def update(frame_number):
        t = frame_number / FPS
        weekday_alpha = ease(t/1.3)
        line_progress = ease((t-1.5)/3.8)
        weekend_alpha = ease((t-5.4)/.9)
        returned = []
        for item in artists:
            item["left_point"].set_alpha(weekday_alpha)
            item["left_leader"].set_alpha(weekday_alpha)
            item["left_label"].set_alpha(weekday_alpha)
            item["line"].set_data([0, line_progress],
                                  [item["y0"], item["y0"] +
                                   (item["y1"]-item["y0"])*line_progress])
            item["right_point"].set_alpha(weekend_alpha)
            item["right_leader"].set_alpha(weekend_alpha)
            item["right_label"].set_alpha(weekend_alpha)
            returned.extend([item["line"], item["left_point"], item["right_point"],
                             item["left_leader"], item["right_leader"],
                             item["left_label"], item["right_label"]])
        return returned

    save_animation(fig, update, SLOPEGRAPH_FRAMES, "slopegraph_animated.mp4")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="write MP4s to an isolated directory")
    parser.add_argument("--all", action="store_true", help="render all four clips")
    parser.add_argument("--flow-map", action="store_true", help="render categorical map")
    parser.add_argument("--highlight-map", action="store_true", help="render highlight map")
    parser.add_argument("--diverging-bar", action="store_true", help="render net-flow bars")
    parser.add_argument("--slopegraph", action="store_true", help="render rank-change slopegraph")
    args = parser.parse_args()
    global ANIMATIONS
    if args.output_dir is not None:
        ANIMATIONS = args.output_dir.resolve()
    selected = {
        "flow": args.flow_map,
        "highlight": args.highlight_map,
        "diverging": args.diverging_bar,
        "slope": args.slopegraph,
    }
    if args.all:
        selected = {name: True for name in selected}
    require(any(selected.values()), "Choose --all or at least one animation")
    setup()
    if selected["flow"]:
        animate_flow_map_categories()
    if selected["highlight"]:
        animate_flow_map_highlight()
    if selected["diverging"]:
        animate_diverging_bar()
    if selected["slope"]:
        animate_slopegraph()


if __name__ == "__main__":
    main()
