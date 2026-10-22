"""Conserving three-level ribbons using Matplotlib; no extra renderer needed.

Regional and station edges are separate representations of the SAME journeys.
The station table retains origin region, enabling audit without implying a
particular origin supplies a station based on ribbon ordering alone.
"""
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle
import pandas as pd
try:
    from .shared import (CLEAN, BG, BLUE, TEAL, AMBER, TEXT, MUTED, REGIONS, setup,
                        load_data, join_od, check_equal, require, save_table, frame, export)
except ImportError:  # Direct script execution.
    from shared import (CLEAN, BG, BLUE, TEAL, AMBER, TEXT, MUTED, REGIONS, setup,
                        load_data, join_od, check_equal, require, save_table, frame, export)


def prepare(s,od):
    j=join_od(od,s)
    rr=j.groupby(["origin_region","destination_region"],as_index=False).trips.sum()
    rr=rr.set_index(["origin_region","destination_region"]).reindex(pd.MultiIndex.from_product([REGIONS,REGIONS],names=["origin_region","destination_region"]),fill_value=0).reset_index()
    rr=rr.rename(columns={"trips":"monthly_trips"});rr["trips_per_calendar_day"]=rr.monthly_trips/30
    ds=j.groupby(["destination_region","destination_code","destination_station_name"],as_index=False).trips.sum()
    ds=ds.sort_values(["destination_region","trips","destination_code"],ascending=[True,False,True])
    top=ds.groupby("destination_region",sort=False).head(3)
    selected=set(top.destination_code)
    j["destination_bucket_code"]=j.destination_code.where(j.destination_code.isin(selected),"OTHER")
    j["destination_bucket_name"]=j.destination_station_name.where(j.destination_code.isin(selected),"Other stations")
    breakdown=j.groupby(["origin_region","destination_region","destination_bucket_code","destination_bucket_name"],as_index=False).trips.sum()
    breakdown=breakdown.rename(columns={"trips":"monthly_trips"});breakdown["trips_per_calendar_day"]=breakdown.monthly_trips/30
    totals=breakdown.groupby(["destination_region","destination_bucket_code","destination_bucket_name"],as_index=False).monthly_trips.sum()
    totals["trips_per_calendar_day"]=totals.monthly_trips/30
    rows=[check_equal("network to region edges",od.trips.sum(),rr.monthly_trips.sum()),check_equal("network to station buckets",od.trips.sum(),breakdown.monthly_trips.sum())]
    reference=pd.read_csv(CLEAN/"od_region.csv").groupby(["origin_region","destination_region"]).trips.sum()
    for row in rr.itertuples():
        rows.append(check_equal(f"reference {row.origin_region} -> {row.destination_region}",reference.loc[(row.origin_region,row.destination_region)],row.monthly_trips))
        b=breakdown[(breakdown.origin_region==row.origin_region)&(breakdown.destination_region==row.destination_region)]
        rows.append(check_equal(f"origin attribution {row.origin_region} -> {row.destination_region}",row.monthly_trips,b.monthly_trips.sum()))
    for region in REGIONS:
        incoming=rr.loc[rr.destination_region==region,"monthly_trips"].sum()
        rows.append(check_equal(f"destination node {region}",incoming,totals.loc[totals.destination_region==region,"monthly_trips"].sum()))
        rows.append(check_equal(f"origin node {region}",j.loc[j.origin_region==region,"trips"].sum(),rr.loc[rr.origin_region==region,"monthly_trips"].sum()))
    require(len(top)==15,"Expected three station selections per region")
    require(len(rr)==25 and len(totals)==20,"Sankey shape mismatch")
    require(int(rr[(rr.origin_region=="Central")&(rr.destination_region=="Central")].monthly_trips.iloc[0])==25117999,"Central flow changed")
    save_table(rr,"region_to_region_flows.csv");save_table(breakdown,"destination_station_breakdown.csv")
    save_table(totals,"destination_station_totals.csv");save_table(pd.DataFrame(rows),"sankey_conservation_checks.csv")
    return rr,totals

def ribbon(ax,x0,x1,y0,y1,h,color,alpha=.6):
    mid=(x0+x1)/2
    verts=[(x0,y0),(mid,y0),(mid,y1),(x1,y1),(x1,y1+h),(mid,y1+h),(mid,y0+h),(x0,y0+h),(x0,y0)]
    codes=[MplPath.MOVETO,MplPath.CURVE4,MplPath.CURVE4,MplPath.CURVE4,MplPath.LINETO,MplPath.CURVE4,MplPath.CURVE4,MplPath.CURVE4,MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(verts,codes),facecolor=color,edgecolor="none",alpha=alpha))

def stack(values,scale,gap=.043,top=.82):
    result={};y=top
    for key,val in values.items():
        h=val*scale;y-=h;result[key]=(y,h);y-=gap
    return result

def draw(rr,totals,focus=None,full=False):
    total=int(rr.monthly_trips.sum());scale=.49/total
    origins=rr.groupby("origin_region").monthly_trips.sum().reindex(REGIONS)
    dests=rr.groupby("destination_region").monthly_trips.sum().reindex(REGIONS)
    a=stack(origins.to_dict(),scale);b=stack(dests.to_dict(),scale)
    detail=focus is not None or full
    fig=frame();ax=fig.add_axes([.025,.02,.95,.96]);ax.set_xlim(0,1);ax.set_ylim(.10,.98);ax.axis("off")
    ax.text(.98,.11,"Trips / calendar day",ha="right",fontsize=11,color=MUTED)
    x0,x1,x2=(.08,.43,.74) if detail else (.16,.72,.94)
    width=.012
    ax.text(x0,.94,"ORIGIN REGION",fontsize=11,color=MUTED)
    ax.text(x1,.94,"DESTINATION REGION",fontsize=11,color=MUTED)
    if detail:ax.text(x2,.94,"DESTINATION STATIONS",fontsize=11,color=MUTED)
    cursor_a={r:a[r][0]+a[r][1] for r in REGIONS};cursor_b={r:b[r][0]+b[r][1] for r in REGIONS}
    for origin in REGIONS:
        for dest in REGIONS:
            val=int(rr[(rr.origin_region==origin)&(rr.destination_region==dest)].monthly_trips.iloc[0]);h=val*scale
            cursor_a[origin]-=h;cursor_b[dest]-=h
            active=focus is None or dest==focus
            color=AMBER if (focus and dest==focus) or (not focus and origin==dest=="Central") else BLUE
            ribbon(ax,x0+width,x1,cursor_a[origin],cursor_b[dest],h,color,.64 if active else .10)
    for side,nodes,values in [(x0,a,origins),(x1,b,dests)]:
        for region,(y,h) in nodes.items():
            active=focus is None or side==x0 or region==focus
            ax.add_patch(Rectangle((side,y),width,h,facecolor=AMBER if region==focus else TEAL,alpha=1 if active else .3))
            # Text above the node avoids crossing the narrowest node.
            ax.text(side,y+h+.009,f"{region}  {values[region]/30/1000:,.0f}k",fontsize=12 if detail else 15,
                    color=TEXT if active else MUTED,va="bottom",
                    bbox={"facecolor": BG, "edgecolor": "none", "alpha": .90, "pad": .8}, zorder=10)
    if detail:
        groups={}
        for region in REGIONS:
            group=totals[totals.destination_region==region].copy()
            group["is_other"]=group.destination_bucket_code=="OTHER"
            groups[region]=group.sort_values(["is_other","monthly_trips","destination_bucket_code"],ascending=[True,False,True])
        if focus:
            group=groups[focus];values={row.destination_bucket_code:int(row.monthly_trips) for row in group.itertuples()}
            c=stack(values,scale,gap=.035,top=.73)
            cursor=b[focus][0]+b[focus][1]
            label_y=[.80,.65,.50,.33]
            for i,row in enumerate(group.itertuples()):
                y,h=c[row.destination_bucket_code];cursor-=h
                ribbon(ax,x1+width,x2,cursor,y,h,TEAL,.75)
                ax.add_patch(Rectangle((x2,y),width,h,facecolor=TEAL))
                ly=label_y[i]
                ax.plot([x2+width,x2+.035],[y+h/2,ly],color=MUTED,lw=.7)
                ax.text(x2+.04,ly,f"{row.destination_bucket_name}\n{row.monthly_trips/30:,.0f} / day",fontsize=12,va="center",linespacing=1.5)
        else:
            y=.83;label_y=.85
            for region in REGIONS:
                cursor=b[region][0]+b[region][1]
                for row in groups[region].itertuples():
                    h=row.monthly_trips*scale;y-=h;cursor-=h
                    ribbon(ax,x1+width,x2,cursor,y,h,TEAL,.65)
                    ax.add_patch(Rectangle((x2,y),width,h,facecolor=TEAL))
                    ax.plot([x2+width,x2+.03],[y+h/2,label_y],color=MUTED,lw=.4)
                    label=row.destination_bucket_name if row.destination_bucket_code!="OTHER" else f"Other ({region})"
                    ax.text(x2+.035,label_y,f"{label} \u00b7 {row.monthly_trips/30/1000:.1f}k",fontsize=10.5,va="center")
                    label_y-=.037;y-=.006
                y-=.015
    filename="sankey_full.png" if full else f"sankey_focus_{focus.lower().replace('-','')}.png" if focus else "sankey_regions.png"
    export(fig,filename)

def main():
    setup();s,od,_=load_data();rr,totals=prepare(s,od)
    draw(rr,totals)
    draw(rr,totals,full=True)
    for region in REGIONS:draw(rr,totals,focus=region)
if __name__ == "__main__":main()
