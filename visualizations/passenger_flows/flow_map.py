"""Top 15 directed connections; geography is not route geometry."""
import json
import numpy as np
from matplotlib.patches import Polygon, FancyArrowPatch
try:
    from .shared import (ROOT, BG, BLUE, TEAL, AMBER, TEXT, MUTED, setup, load_data,
                         pair_totals, save_table, require, frame, export)
except ImportError:  # Direct script execution from the repository root.
    from shared import (ROOT, BG, BLUE, TEAL, AMBER, TEXT, MUTED, setup, load_data,
                        pair_totals, save_table, require, frame, export)

# Hand-positioned labels for this fixed September selection; data locations remain exact.
OFFSETS = {"EW2/DT32": (-62,-28), "EW1": (-68,15), "EW24/NS1": (-18,-32),
 "EW27": (-52,14), "NS4/BP1": (-72,10), "NS2": (6,14), "EW23": (10,-13),
 "NS20": (20,2), "NS19": (18,19), "NS21/DT11": (-60,3), "TE14/NS22": (-53,-23),
 "NE17/PTC": (12,10), "NE16/STC": (12,-10)}

def arrow_dimensions(trips_per_day):
    """One linear point-size scale for links AND legend arrows.

    Shaft width = average calendar-day OD trips / 1000 (points).
    Head mutation scale = 3.5 times shaft width, preserving head proportions.
    """
    width = trips_per_day / 1000
    return {"linewidth": width, "mutation_scale": 3.5 * width}


LEGEND_Y = .889  # about 10-12 px above the aspect-correct map boundary


def category_details(pairs):
    categories = {
        "Higher": pairs[pairs["rank"].between(1,5)],
        "Medium": pairs[pairs["rank"].between(6,10)],
        "Lower": pairs[pairs["rank"].between(11,15)],
    }
    require(all(len(group) == 5 for group in categories.values()),
            "Each top-15 category must contain five links")
    return categories


def draw_thickness_legend(fig, pairs, mode):
    """Compact legend using the same continuous width encoding as the links."""
    if mode == "categories":
        categories = category_details(pairs)
        samples = [(4000, BLUE, "Lower"), (4500, TEAL, "Medium"),
                   (6000, AMBER, "Higher")]
        require(all(categories[name].trips_per_calendar_day.min() <= value
                    <= categories[name].trips_per_calendar_day.max()
                    for value, _, name in samples),
                "Category legend values must lie within their category ranges")
    else:
        samples = [(4000, BLUE, None), (5000, BLUE, None),
                   (6000, BLUE, None)]
    require(all(pairs.trips_per_calendar_day.min() <= value
                <= pairs.trips_per_calendar_day.max()
                for value, _, _ in samples),
            "Legend values must lie within the plotted data range")
    fig.text(.08, LEGEND_Y, "Average daily trips", ha="left", va="center",
             fontsize=13, color=TEXT)
    for x, (value, color, _) in zip([.39, .61, .83], samples):
        fig.add_artist(FancyArrowPatch(
            (x-.065, LEGEND_Y), (x+.005, LEGEND_Y), transform=fig.transFigure,
            arrowstyle="-|>", **arrow_dimensions(value), color=color, alpha=.92,
            shrinkA=5, shrinkB=5))
        fig.text(x+.020, LEGEND_Y, f"\u2248 {value:,}", ha="left", va="center",
                 fontsize=12, color=TEXT)


def draw_map(stations, pairs, geo, selected, mode, filename):
    fig = frame()
    ax = fig.add_axes([.005,.015,.99,.96])
    for feature in geo["features"]:
        polygons = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            polygons = [polygons]
        for polygon in polygons:
            ax.add_patch(Polygon(polygon[0], facecolor="#1C242A", edgecolor="#424D55",
                                 linewidth=.6, zorder=0))
            for hole in polygon[1:]:
                ax.add_patch(Polygon(hole, facecolor=BG, edgecolor="none"))
    ax.scatter(stations.longitude,stations.latitude,s=5,color="#56616B",alpha=.65,zorder=1)

    category_of_rank = {**{rank:"Higher" for rank in range(1,6)},
                        **{rank:"Medium" for rank in range(6,11)},
                        **{rank:"Lower" for rank in range(11,16)}}
    colors = {"Lower":BLUE, "Medium":TEAL, "Higher":AMBER}
    for row in pairs.iloc[::-1].itertuples():
        color = (AMBER if row.rank == 1 else BLUE) if mode == "highlight" else colors[category_of_rank[row.rank]]
        ax.add_patch(FancyArrowPatch(
            (row.origin_longitude,row.origin_latitude),
            (row.destination_longitude,row.destination_latitude),
            connectionstyle="arc3,rad=0.20",arrowstyle="-|>",
            **arrow_dimensions(row.trips_per_calendar_day),color=color,alpha=.92,
            shrinkA=5,shrinkB=5,zorder=3))

    ax.scatter(selected.longitude,selected.latitude,s=32,color=TEXT,edgecolor=BG,linewidth=.8,zorder=4)
    for row in selected.itertuples():
        dx,dy=OFFSETS[row.station_code]
        ax.annotate(row.station_name,(row.longitude,row.latitude),xytext=(dx,dy),textcoords="offset points",
            fontsize=13,color=TEXT,zorder=5,arrowprops={"arrowstyle":"-","color":MUTED,"lw":.6},
            bbox={"facecolor":BG,"edgecolor":"none","alpha":.8,"pad":1.5})
    lon0,lon1=selected.longitude.min(),selected.longitude.max()
    lat0,lat1=selected.latitude.min(),selected.latitude.max()
    dx,dy=(lon1-lon0)*.08,(lat1-lat0)*.08
    ax.set_xlim(lon0-dx,lon1+dx);ax.set_ylim(lat0-dy,lat1+dy)
    ax.set_aspect(1/np.cos(np.deg2rad(selected.latitude.mean())));ax.axis("off")

    if mode == "categories":
        categories = category_details(pairs)
        require({name:len(group) for name,group in categories.items()}
                == {"Higher":5,"Medium":5,"Lower":5},"Invalid category allocation")
    draw_thickness_legend(fig, pairs, mode)

    print(f"{filename} bounds: lon {lon0-dx:.6f} to {lon1+dx:.6f}; "
          f"lat {lat0-dy:.6f} to {lat1+dy:.6f}")
    export(fig,filename)


def main(modes=None):
    full_run = modes is None
    if modes is None:
        modes = ("highlight", "categories")
    setup()
    stations,od,_=load_data()
    pairs=pair_totals(od,stations).head(15).copy()
    pairs.insert(0,"rank",range(1,16))
    pairs["network_share"]=pairs.monthly_trips/od.trips.sum()
    require(len(pairs)==15 and pairs["rank"].tolist()==list(range(1,16)),
            "Expected deterministic top-15 ranks")
    require(pairs.iloc[0].origin_code=="EW2/DT32" and pairs.iloc[0].destination_code=="EW1",
            "Top pair changed")
    require(pairs.iloc[0].monthly_trips==191047,"Top pair count changed")
    if full_run:
        save_table(pairs,"top15_od_pairs.csv")
    selected=stations[stations.station_code.isin(set(pairs.origin_code)|set(pairs.destination_code))]
    geo=json.loads((ROOT/"data/reference/ura_mp2019_region_boundary.geojson").read_text(encoding="utf-8"))
    if "highlight" in modes:
        draw_map(stations,pairs,geo,selected,"highlight","flow_map.png")
    if "categories" in modes:
        draw_map(stations,pairs,geo,selected,"categories","flow_map_volume_categories.png")

if __name__ == "__main__": main()
