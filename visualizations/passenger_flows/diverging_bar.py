"""Morning-selected extremes; the same six are compared in the evening."""
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import Patch
import pandas as pd
try:
    from .shared import (AMBER, TEAL, TEXT, GRID, setup, load_data, require,
                        save_table, frame, export)
except ImportError:  # Direct script execution.
    from shared import (AMBER, TEAL, TEXT, GRID, setup, load_data, require,
                        save_table, frame, export)

PERIODS={"Morning":[7,8,9],"Evening":[17,18,19]}

def main():
    setup();s,_,sh=load_data();names=s.set_index("station_code").station_name
    rows=[]
    for period,hours in PERIODS.items():
        x=sh[(sh.day_type=="WEEKDAY") & sh.hour.isin(hours)].groupby("station_code")[["tap_in","tap_out"]].sum().reindex(s.station_code).reset_index()
        x["station_name"]=x.station_code.map(names);x["period"]=period;x["days"]=22
        x["net_into_surroundings_monthly"]=x.tap_out-x.tap_in
        x["net_into_surroundings_per_weekday"]=x.net_into_surroundings_monthly/22
        x=x.sort_values(["net_into_surroundings_monthly","station_code"],ascending=[False,True])
        x["period_rank"]=range(1,len(x)+1);rows.append(x)
    data=pd.concat(rows,ignore_index=True)
    morning=data[data.period=="Morning"].set_index("station_code")
    positive=morning[morning.net_into_surroundings_monthly>0].head(3).index.tolist()
    negative=morning[morning.net_into_surroundings_monthly<0].reset_index().sort_values(["net_into_surroundings_monthly","station_code"]).head(3).station_code.tolist()
    codes=positive+negative;require(len(set(codes))==6,"Expected six distinct extremes")
    evening=data[data.period=="Evening"].set_index("station_code")
    data["morning_rank"]=data.station_code.map(morning.period_rank)
    reversals=(morning.net_into_surroundings_monthly*evening.net_into_surroundings_monthly)<0
    data["evening_reverses_direction"]=data.station_code.map(reversals)
    data["selected_for_display"]=data.station_code.isin(codes)
    data["display_order"]=data.station_code.map({c:i+1 for i,c in enumerate(codes)}).astype("Int64")
    save_table(data,"all_station_net_flow_rankings.csv")
    selected=pd.concat([data[data.period==p].set_index("station_code").loc[codes].reset_index() for p in PERIODS],ignore_index=True)
    save_table(selected,"station_net_movement.csv")
    fig=frame()
    for i,(period,hours) in enumerate(PERIODS.items()):
        ax=fig.add_axes([.185+i*.405,.16,.35,.74]);x=selected[selected.period==period]
        vals=x.net_into_surroundings_per_weekday.to_numpy()
        ax.barh(range(6),vals,height=.5,color=[TEAL if v>0 else AMBER for v in vals])
        ax.axvline(0,color=TEXT,lw=1);ax.set_xlim(-45000,45000);ax.set_ylim(5.65,-.65)
        ax.set_yticks(range(6),[names[c] for c in codes] if i==0 else [""]*6)
        ax.tick_params(axis="y",length=0,labelsize=14)
        ax.set_xticks([-40000,-20000,0,20000,40000]);ax.xaxis.set_major_formatter(FuncFormatter(lambda v,p:f"{v/1000:.0f}k"))
        ax.grid(axis="x",color=GRID,lw=.6);ax.set_axisbelow(True)
        ax.set_title(f"{period} ({hours[0]:02}:00\u2013{hours[-1]+1:02}:00)",
                     fontsize=17,pad=16,loc="left")
        ax.set_xlabel("Net gate movements / weekday",fontsize=12,labelpad=11)
        for y,v in enumerate(vals):ax.text(v+(1100 if v>0 else -1100),y,f"{v:+,.0f}",ha="left" if v>0 else "right",va="center",fontsize=13)
    fig.legend(handles=[
        Patch(facecolor=TEAL,label="Net inflow (tap-outs > tap-ins)"),
        Patch(facecolor=AMBER,label="Net outflow (tap-ins > tap-outs)")],
        loc="lower center",bbox_to_anchor=(.55,.015),ncol=2,frameon=False,
        fontsize=13,labelcolor=TEXT,columnspacing=2.2)
    export(fig,"diverging_bar.png")
if __name__=="__main__":main()
