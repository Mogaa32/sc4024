"""Independent stdlib CSV recomputation of delivered tables and PNG properties.

Does not use shared.py or the chart aggregation functions. Writes only validation
artifacts inside the approved output folder; never changes input data.
"""
import argparse
import csv
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
from importlib.metadata import version
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
CLEAN=ROOT/"data/clean"
OUT=ROOT/"outputs/passenger_flows/202609"
DAYS={"WEEKDAY":22,"WEEKENDS/HOLIDAY":8}

def read(path):
    with path.open(encoding="utf-8",newline="") as f:
        yield from csv.DictReader(f)

def check(condition,message):
    if not condition: raise ValueError(message)

def close(a,b):
    return math.isclose(float(a),float(b),rel_tol=0,abs_tol=1e-7)

def probe_animation(path,expected_frames,expected_duration):
    ffprobe=shutil.which("ffprobe");ffmpeg=shutil.which("ffmpeg")
    check(ffprobe is not None and ffmpeg is not None,"FFmpeg tools available")
    result=subprocess.run([ffprobe,"-v","error","-count_frames","-show_streams",
        "-show_format","-of","json",str(path)],capture_output=True,text=True,check=True)
    metadata=json.loads(result.stdout);video=[s for s in metadata["streams"] if s["codec_type"]=="video"]
    check(len(video)==1 and not any(s["codec_type"]=="audio" for s in metadata["streams"]),
          f"{path.name} video-only stream")
    stream=video[0];num,den=map(int,stream["avg_frame_rate"].split("/"));fps=num/den
    frames=int(stream.get("nb_read_frames",stream.get("nb_frames",0)))
    duration=float(metadata["format"]["duration"])
    check(stream["codec_name"]=="h264",f"{path.name} H.264 codec")
    check(stream["pix_fmt"]=="yuv420p",f"{path.name} yuv420p pixel format")
    check((int(stream["width"]),int(stream["height"]))==(1280,720),f"{path.name} dimensions")
    check(close(fps,15),f"{path.name} frame rate")
    check(frames==expected_frames,f"{path.name} frame count")
    check(abs(duration-expected_duration)<.15,f"{path.name} duration")
    decoded=subprocess.run([ffmpeg,"-v","error","-i",str(path),"-f","null","-"],
                           capture_output=True,text=True)
    check(decoded.returncode==0,f"{path.name} full decode")
    return {"file":path.name,"width":1280,"height":720,"codec":"h264",
            "pixel_format":"yuv420p","fps":fps,"frames":frames,
            "duration_seconds":duration,"audio":False,"full_decode":True}

def main(mode="static", write_reports=True):
    stations={r["station_code"]:r for r in read(CLEAN/"stations.csv")}
    check(len(stations)==184,"Station count")
    pairs=Counter();by_type=Counter();regions=Counter();received=Counter();attributed=Counter();od_rows=0
    for r in read(CLEAN/"od_hourly.csv"):
        od_rows+=1;a,b=r["origin_code"],r["destination_code"];n=int(r["trips"])
        check(a in stations and b in stations,"OD join failed")
        ar,br=stations[a]["region"],stations[b]["region"]
        pairs[a,b]+=n;by_type[a,b,r["day_type"]]+=n;regions[ar,br]+=n
        received[br,b]+=n;attributed[ar,br,b]+=n
    total=sum(pairs.values());check(total==85880089,"OD total")
    top=sorted(pairs,key=lambda k:(-pairs[k],*k))[:15]
    exported=list(read(OUT/"tables/top15_od_pairs.csv"));check(len(exported)==15,"Top pairs count")
    for rank,(key,row) in enumerate(zip(top,exported),1):
        check((row["origin_code"],row["destination_code"])==key and int(row["rank"])==rank,"Top pairs order")
        check(int(row["monthly_trips"])==pairs[key],"Monthly pair trips")
        check(close(row["trips_per_calendar_day"],pairs[key]/30),"Calendar normalization")
        check(close(row["trips_per_weekday"],by_type[*key,"WEEKDAY"]/22),"Weekday normalization")
        check(close(row["trips_per_weekend_holiday"],by_type[*key,"WEEKENDS/HOLIDAY"]/8),"Weekend normalization")
        for side,code in zip(["origin","destination"],key):
            for field in ["station_name","region","station_type"]:
                check(row[f"{side}_{field}"]==stations[code][field],"Exported metadata mismatch")
            for field in ["latitude","longitude"]:
                check(close(row[f"{side}_{field}"],stations[code][field]),"Exported coordinate mismatch")
    category_keys={"Higher":top[:5],"Medium":top[5:10],"Lower":top[10:15]}
    check(all(len(keys)==5 for keys in category_keys.values()),"Five links per map category")
    category_ranges={name:{
        "minimum_trips_per_day":min(pairs[key]/30 for key in keys),
        "maximum_trips_per_day":max(pairs[key]/30 for key in keys),
        "link_count":len(keys)} for name,keys in category_keys.items()}
    check(category_ranges["Higher"]["minimum_trips_per_day"] > category_ranges["Medium"]["maximum_trips_per_day"]
          > category_ranges["Lower"]["maximum_trips_per_day"],"Ordered category ranges")
    actual={}
    for r in read(OUT/"tables/region_to_region_flows.csv"):
        key=(r["origin_region"],r["destination_region"]);actual[key]=int(r["monthly_trips"])
        check(close(r["trips_per_calendar_day"],actual[key]/30),"Regional normalization")
    check(actual==dict(regions) and len(actual)==25,"Regional table")
    reference=Counter()
    for r in read(CLEAN/"od_region.csv"):reference[r["origin_region"],r["destination_region"]]+=int(r["trips"])
    check(reference==regions,"Committed regional totals differ")
    region_names=sorted({s["region"] for s in stations.values()})
    top_codes=set()
    for region in region_names:
        ranked=sorted((key for key in received if key[0]==region),key=lambda key:(-received[key],key[1]))
        top_codes.update(key[1] for key in ranked[:3])
    buckets=Counter()
    for (a,b,code),n in attributed.items():buckets[a,b,code if code in top_codes else "OTHER"]+=n
    actual={}
    for r in read(OUT/"tables/destination_station_breakdown.csv"):
        key=(r["origin_region"],r["destination_region"],r["destination_bucket_code"])
        check(key not in actual,"Duplicate station bucket")
        actual[key]=int(r["monthly_trips"])
        check(close(r["trips_per_calendar_day"],actual[key]/30),"Station bucket normalization")
        check(r["destination_bucket_name"]==("Other stations" if key[2]=="OTHER" else stations[key[2]]["station_name"]),"Bucket name")
    check(actual==dict(buckets),"Station attribution/top-three selection")
    bucket_totals=Counter()
    for (a,b,c),n in buckets.items():bucket_totals[b,c]+=n
    rows=list(read(OUT/"tables/destination_station_totals.csv"))
    check(len(rows)==20,"Station totals count")
    for r in rows:
        key=(r["destination_region"],r["destination_bucket_code"])
        check(int(r["monthly_trips"])==bucket_totals[key],"Station totals")
        check(close(r["trips_per_calendar_day"],bucket_totals[key]/30),"Station total normalization")
    checks=list(read(OUT/"tables/sankey_conservation_checks.csv"))
    check(len(checks)==62 and all(r["passed"]=="True" and int(r["difference"])==0 for r in checks),"Conservation check report")
    activity=Counter();net=Counter();period_in=Counter();period_out=Counter();gate_totals=Counter();gate_rows=0
    for r in read(CLEAN/"station_hourly.csv"):
        gate_rows+=1;c,d,h=r["station_code"],r["day_type"],int(r["hour"]);ti,to=int(r["tap_in"]),int(r["tap_out"])
        check(int(r["net"])==ti-to,"Source net convention")
        activity[c,d]+=ti+to;gate_totals["tap_in"]+=ti;gate_totals["tap_out"]+=to
        if d=="WEEKDAY":
            for period,hours in [("Morning",[7,8,9]),("Evening",[17,18,19])]:
                if h in hours:net[c,period]+=to-ti;period_in[c,period]+=ti;period_out[c,period]+=to
    check(gate_totals=={"tap_in":87051437,"tap_out":86776212},"Gate totals")
    morning_order=sorted(stations,key=lambda c:(-net[c,"Morning"],c))
    evening_order=sorted(stations,key=lambda c:(-net[c,"Evening"],c))
    net_ranks={(c,p):i for p,order in [("Morning",morning_order),("Evening",evening_order)] for i,c in enumerate(order,1)}
    positive=[c for c in morning_order if net[c,"Morning"]>0][:3]
    negative=sorted([c for c in stations if net[c,"Morning"]<0],key=lambda c:(net[c,"Morning"],c))[:3]
    selected_codes=positive+negative
    for filename,expected_codes in [("station_net_movement.csv",selected_codes),("all_station_net_flow_rankings.csv",list(stations))]:
        rows=list(read(OUT/"tables"/filename));check(len(rows)==len(expected_codes)*2,"Net row count")
        check({(r["station_code"],r["period"]) for r in rows}=={(c,p) for c in expected_codes for p in ["Morning","Evening"]},"Net key coverage")
        for r in rows:
            c=r["station_code"];key=c,r["period"]
            check(r["station_name"]==stations[c]["station_name"] and int(r["days"])==22,"Net metadata")
            check(int(r["tap_in"])==period_in[key] and int(r["tap_out"])==period_out[key],"Period gate totals")
            check(int(r["net_into_surroundings_monthly"])==net[key],"Net sign/count")
            check(close(r["net_into_surroundings_per_weekday"],net[key]/22),"Net daily value")
            check(int(r["morning_rank"])==net_ranks[c,"Morning"] and int(r["period_rank"])==net_ranks[key],"Deterministic net ranks")
            check(r["evening_reverses_direction"]==str(net[c,"Morning"]*net[c,"Evening"]<0),"Evening reversal")
            check(r["selected_for_display"]==str(c in selected_codes),"Net selection flag")
            check(r["display_order"]==(str(selected_codes.index(c)+1) if c in selected_codes else ""),"Net display order")
        if filename=="station_net_movement.csv":
            for p in ["Morning","Evening"]:check([r["station_code"] for r in rows if r["period"]==p]==selected_codes,"Same station order in both panels")
    ranks={}
    for day in DAYS:
        ordered=sorted(stations,key=lambda c:(-activity[c,day],c));last=None
        for i,c in enumerate(ordered,1):
            if activity[c,day]!=last:rank=i
            ranks[c,day]=rank;last=activity[c,day]
    rows=list(read(OUT/"tables/all_station_activity_rankings.csv"));check(len(rows)==184,"Ranking population")
    for r in rows:
        c=r["station_code"];wd=activity[c,"WEEKDAY"]/22;we=activity[c,"WEEKENDS/HOLIDAY"]/8
        check(close(r["weekday_activity_per_day"],wd) and close(r["weekend_holiday_activity_per_day"],we),"Ranking normalization")
        check(int(r["weekday_rank"])==ranks[c,"WEEKDAY"] and int(r["weekend_holiday_rank"])==ranks[c,"WEEKENDS/HOLIDAY"],"Competition ranks")
        check(close(r["activity_change_pct"],(we/wd-1)*100),"Volume change")
    selected_slope={"TE14/NS22":(4,1),"NS25/EW13":(16,3),"NE1/CC29":(15,5),"CC34/DT16":(31,13),"EW12/DT14":(9,4),"EW14/NS26":(2,48)}
    for r in rows:
        c=r["station_code"]
        check(r["selected_original_six"]==str(c in selected_slope),"Original backup selection")
        check(int(r["rank_gain"])==ranks[c,"WEEKDAY"]-ranks[c,"WEEKENDS/HOLIDAY"],"Rank gain")
        if c in selected_slope:check((ranks[c,"WEEKDAY"],ranks[c,"WEEKENDS/HOLIDAY"])==selected_slope[c],"Preserved global ranks")
    union=set()
    for day in DAYS:union.update(sorted(stations,key=lambda c:(-activity[c,day],c))[:5])
    check(len(union)==8,"Eight-station top-five union")
    displayed=list(read(OUT/"tables/station_rank_changes.csv"))
    check(len(displayed)==8 and {r["station_code"] for r in displayed}==union,"Main slopegraph selection")
    full_by_code={r["station_code"]:r for r in rows}
    for r in rows:check(r["selected_for_display"]==str(r["station_code"] in union),"Union selection flag")
    for r in displayed:check(r==full_by_code[r["station_code"]],"Displayed ranks match full-network audit")
    top_rows=list(read(OUT/"tables/top10_station_rankings.csv"));check(len(top_rows)==20,"Top ten row count")
    for day,den in DAYS.items():
        expected_codes=sorted(stations,key=lambda c:(-activity[c,day],c))[:10]
        actual_rows=[r for r in top_rows if r["day_type"]==day]
        check([r["station_code"] for r in actual_rows]==expected_codes,"Global top ten selection and order")
        for r in actual_rows:
            c=r["station_code"]
            check(r["station_name"]==stations[c]["station_name"],"Top ten name")
            check(int(r["global_rank"])==ranks[c,day],"Top ten global rank")
            check(close(r["average_daily_activity"],activity[c,day]/den),"Top ten normalization")
    images=[]
    expected=["backup/top10_weekday","backup/top10_weekend","slopegraph_original_six",
              "flow_map","flow_map_volume_categories","diverging_bar","slopegraph",
              "sankey_regions","sankey_full"]+[f"sankey_focus_{r}" for r in ["central","west","northeast","north","east"]]
    for name in expected:
        path=OUT/"figures"/f"{name}.png"
        with Image.open(path) as im:
            check(im.size==(1280,720),f"{name} dimensions")
            check(im.mode in ["RGB","RGBA"],f"{name} color mode")
            if im.mode=="RGBA":check(im.getchannel("A").getextrema()==(255,255),f"{name} transparency")
            images.append({"file":str(path.relative_to(OUT/"figures")),"width":1280,"height":720,"opaque":True})
    animation_specs={"flow_map_animated.mp4":(120,8.0),
        "flow_map_highlight_animated.mp4":(90,6.0),
        "diverging_bar_animated.mp4":(120,8.0),
        "slopegraph_animated.mp4":(120,8.0)}
    animations=[probe_animation(OUT/"animations"/name,*spec)
                for name,spec in animation_specs.items()] if mode == "full" else []
    inputs=[CLEAN/f for f in ["stations.csv","od_hourly.csv","station_hourly.csv","od_region.csv"]]
    inputs.append(ROOT/"data/reference/ura_mp2019_region_boundary.geojson")
    manifest={"month":"202609","day_counts":DAYS,"calendar_days":30,"scope":"Full MRT/LRT network",
        "od_rows":od_rows,"station_hourly_rows":gate_rows,"od_monthly_trips":total,"station_gate_totals":dict(gate_totals),
        "top15_share":sum(pairs[k] for k in top)/total,"flow_map_category_ranges":category_ranges,
        "central_to_central_share":regions["Central","Central"]/total,
        "conservation_checks":len(checks),"images":images,"animations":animations,
        "all_checks_passed":True,"validation_mode":mode,
        "dependencies":{n:version(n) for n in ["pandas","numpy","matplotlib","Pillow"]},
        "input_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    if write_reports:
        (OUT/"validation_summary.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    animation_status = ("- All four MP4s are video-only H.264/yuv420p at 1280 x 720 and 15 fps; expected frame counts, durations and full-stream decoding pass."
                        if mode == "full" else "- Static mode: animation validation was not requested.")
    report=f"""# Validation results: September 2026 passenger flows

PASS: independent CSV-based recomputation; chart aggregation helpers were not imported.

- {od_rows:,} OD rows; {gate_rows:,} station-hour rows; 184 stations.
- OD monthly total: {total:,}; tap-ins: {gate_totals['tap_in']:,}; tap-outs: {gate_totals['tap_out']:,}.
- Top 15 directions, monthly totals, weekday/weekend/calendar-day denominators, names and coordinates match source data.
- Both flow-map PNGs use the same verified top 15; ranked volume categories contain five links each and their data-derived ranges are recorded in validation_summary.json.
- All 25 regional flows match both station-level OD aggregation and committed od_region.csv.
- Top three destinations per region verified independently; all origin attribution retained.
- All 20 station buckets and all {len(checks)} integer conservation checks pass, with zero differences.
- All 12 selected and 368 full-network station-period net values verified directly from gate counts with tap_out - tap_in.
- All 184 station ranks and normalized daily volumes independently verified (competition ranks).
- Top-three positive/negative morning selection, code tie-breaks, evening reversals and all-station net ranks verified.
- Backup top-10 tables and original six ranks verified; main slopegraph is the independently verified eight-station top-five union.
- All 14 PNGs (including backups) are opaque 1280 x 720.
{animation_status}
- Input SHA-256 hashes and installed library versions are in validation_summary.json.

Visual review is documented in the implementation README; numerical checks do not replace visual inspection.
"""
    if write_reports:
        (OUT/"VALIDATION.md").write_text(report,encoding="utf-8")
    print(report)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument("--static", action="store_const", dest="mode", const="static",
                       help="validate all static artifacts and numerical invariants (default)")
    modes.add_argument("--full", action="store_const", dest="mode", const="full",
                       help="also require and validate all four MP4s")
    parser.set_defaults(mode="static")
    parser.add_argument("--no-write", action="store_true", help="check without overwriting reports")
    args=parser.parse_args()
    main(args.mode, write_reports=not args.no_write)
