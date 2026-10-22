"""Global activity ranks; primary display is the union of both top fives."""
try:
    from .shared import (BLUE, TEAL, AMBER, MUTED, GRID, setup, load_data, require,
                         save_table, frame, export)
except ImportError:  # Direct script execution from the repository root.
    from shared import (BLUE, TEAL, AMBER, MUTED, GRID, setup, load_data, require,
                        save_table, frame, export)
ORIGINAL_CODES=["TE14/NS22","NS25/EW13","NE1/CC29","CC34/DT16","EW12/DT14","EW14/NS26"]
ORIGINAL_EXPECTED=[(4,1),(16,3),(15,5),(31,13),(9,4),(2,48)]

def separated_positions(values, gap=1.15):
    """Only text is displaced; points retain exact rank positions with leaders."""
    out={};last=-100
    for code,value in sorted(values.items(),key=lambda kv:(kv[1],kv[0])):
        out[code]=max(value,last+gap);last=out[code]
    return out

def main():
    setup();s,_,sh=load_data()
    g=sh.groupby(["station_code","day_type"])[["tap_in","tap_out"]].sum()
    volume=(g.tap_in+g.tap_out).unstack()
    x=s[["station_code","station_name","station_type"]].set_index("station_code").join(volume)
    x["weekday_activity_per_day"]=x.WEEKDAY/22;x["weekend_holiday_activity_per_day"]=x["WEEKENDS/HOLIDAY"]/8
    for source,target in [("weekday_activity_per_day","weekday_rank"),("weekend_holiday_activity_per_day","weekend_holiday_rank")]:
        x[target]=x[source].rank(method="min",ascending=False).astype(int)
    x["rank_gain"]=x.weekday_rank-x.weekend_holiday_rank
    x["activity_change_pct"]=(x.weekend_holiday_activity_per_day/x.weekday_activity_per_day-1)*100
    weekday_top=x.reset_index().sort_values(["weekday_activity_per_day","station_code"],ascending=[False,True]).head(5).station_code.tolist()
    weekend_top=x.reset_index().sort_values(["weekend_holiday_activity_per_day","station_code"],ascending=[False,True]).head(5).station_code.tolist()
    codes=list(dict.fromkeys(weekday_top+weekend_top))
    require(len(codes)==8,"Expected eight stations in the top-five union")
    x["selected_for_display"]=x.index.isin(codes)
    x["selected_original_six"]=x.index.isin(ORIGINAL_CODES)
    require(list(zip(x.loc[ORIGINAL_CODES].weekday_rank,x.loc[ORIGINAL_CODES].weekend_holiday_rank))==ORIGINAL_EXPECTED,"Original global ranks changed")
    full=x.reset_index().sort_values(["weekday_rank","station_code"])
    save_table(full,"all_station_activity_rankings.csv")
    save_table(full[full.selected_for_display],"station_rank_changes.csv")
    draw(x,codes,"slopegraph.png")


def display_rank(rank):
    """Broken display: ranks 1-16 retain unit spacing; rank 48 maps to 19.

    No ranks 17-47 are displayed. The right axis has an explicit break;
    distances or angles spanning that break are not rank differences.
    """
    if 1 <= rank <= 16:
        return float(rank)
    require(rank == 48, "Unexpected rank outside the designed broken scale")
    return 19.0


def draw(x,codes,filename):
    fig=frame()
    ax=fig.add_axes([.04,.015,.92,.965]);ax.set_xlim(-.65,1.72);ax.set_ylim(19.9,-2);ax.axis("off")
    ax.text(.5,-1.65,"Station Activity Ranking (Average Daily Tap-ins + Tap-outs)",
            ha="center",fontsize=12,color=MUTED)
    ax.plot([0,0],[1,16],color=GRID,lw=1.5)
    # Explicit discontinuity before weekend rank 48; no implied proportional gap.
    ax.plot([1,1],[1,16.6],color=GRID,lw=1.5)
    ax.plot([1,1],[17.6,19],color=GRID,lw=1.5)
    for y in [16.95,17.30]:
        ax.plot([.975,1.025],[y+.13,y-.13],color=MUTED,lw=2.2,zorder=6)
    ax.text(1.075,17.12,"//  17-47",fontsize=12,color=MUTED,va="center")
    ax.text(0,-.45,"WEEKDAY",ha="center",fontsize=13,color=BLUE,weight="bold")
    ax.text(1,-.45,"WEEKEND / HOLIDAY",ha="center",fontsize=13,color=BLUE,weight="bold")
    ax.text(1,.22,"Broken rank scale",ha="center",fontsize=11,color=MUTED)
    selected=x.loc[codes]
    left=separated_positions({c:display_rank(r) for c,r in selected.weekday_rank.items()})
    right=separated_positions({c:display_rank(r) for c,r in selected.weekend_holiday_rank.items()})
    for code,row in selected.iterrows():
        color=AMBER if code=="EW14/NS26" else TEAL if code=="NS25/EW13" else BLUE
        a,b=int(row.weekday_rank),int(row.weekend_holiday_rank)
        ya,yb=display_rank(a),display_rank(b)
        ax.plot([0,1],[ya,yb],color=color,lw=2.4,alpha=.9,zorder=2)
        ax.scatter([0,1],[ya,yb],s=38,color=color,zorder=3)
        ax.plot([-.06,0],[left[code],ya],color=MUTED,lw=.7)
        ax.plot([1,1.06],[yb,right[code]],color=MUTED,lw=.7)
        ax.text(-.075,left[code],f"{row.station_name}  #{a}",ha="right",va="center",fontsize=14)
        ax.text(1.075,right[code],f"#{b}  {row.station_name}",ha="left",va="center",fontsize=14)
    export(fig,filename)
if __name__ == "__main__": main()
