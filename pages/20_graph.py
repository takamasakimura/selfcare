# -*- coding: utf-8 -*-
import streamlit as st, pandas as pd, altair as alt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from utils import load_data, hhmm_to_minutes, signed_circ_diff_minutes, require_passcode

JST = ZoneInfo("Asia/Tokyo")

st.set_page_config(page_title="睡眠偏差グラフ", page_icon="⏰", layout="wide")
st.title("⏰ 睡眠偏差グラフ（就寝/起床のベースラインからのズレ）")

require_passcode(page_name="graph")

opts = ["7日","30日","90日","期間指定"]
sel = st.radio("期間", opts, index=1, horizontal=True)
start_override = end_override = None
if sel == "期間指定":
    today = datetime.now(JST).date()
    c1,c2 = st.columns(2)
    with c1: start_override = st.date_input("開始日", value=today - timedelta(days=29))
    with c2: end_override = st.date_input("終了日", value=today)

this_year = datetime.now(JST).year
dfs = []
for y in (this_year-1, this_year):
    try:
        d = load_data("care-log", str(y))
        if not d.empty: dfs.append(d)
    except Exception: pass
df = pd.concat(dfs, ignore_index=True) if dfs else load_data("care-log", None)

if df.empty or "日付" not in df.columns:
    st.info("まだデータがありません。入力ページから保存してください。"); st.stop()

df = df.copy().dropna(subset=["日付"]).sort_values("日付")
last_day = df["日付"].max().normalize()
if sel=="7日": start_day = last_day - timedelta(days=6)
elif sel=="30日": start_day = last_day - timedelta(days=29)
elif sel=="90日": start_day = last_day - timedelta(days=89)
else:
    start_day = pd.to_datetime(start_override) if start_override is not None else last_day - timedelta(days=29)
    last_day  = pd.to_datetime(end_override) if end_override is not None else last_day
recent = df[df["日付"].between(start_day, last_day)]

BASE_SLEEP, BASE_WAKE = 21*60, 4*60

def pick_sleep_minutes(row):
    s = hhmm_to_minutes(str(row.get("就寝時刻",""))) if "就寝時刻" in row else None
    w = hhmm_to_minutes(str(row.get("起床時刻",""))) if "起床時刻" in row else None
    if s is not None or w is not None: return s, w
    s_cands = [hhmm_to_minutes(str(row.get(f"就寝{i}",""))) for i in (1,2,3)]
    w_cands = [hhmm_to_minutes(str(row.get(f"起床{i}",""))) for i in (1,2,3)]
    s = next((x for x in s_cands if x is not None), None)
    w = max([x for x in w_cands if x is not None], default=None)
    return s, w

rows = []
for _, r in recent.iterrows():
    s, w = pick_sleep_minutes(r)
    sd = signed_circ_diff_minutes(s, BASE_SLEEP)
    wd = signed_circ_diff_minutes(w, BASE_WAKE)
    rows.append({"日付": r["日付"].date(), "就寝偏差(h)": sd/60 if sd is not None else None, "起床偏差(h)": wd/60 if wd is not None else None})
dev = pd.DataFrame(rows).dropna(how="all", subset=["就寝偏差(h)","起床偏差(h)"])

if not dev.empty:
    mdf = dev.melt(id_vars=["日付"], var_name="系列", value_name="偏差時間(h)")
    zero = alt.Chart(pd.DataFrame({"y":[0]})).mark_rule(strokeDash=[4,4]).encode(y="y:Q")
    line = alt.Chart(mdf).mark_line(point=True).encode(x="日付:T", y=alt.Y("偏差時間(h):Q", scale=alt.Scale(domain=[-3,3])), color="系列:N", tooltip=["日付:T","系列:N","偏差時間(h):Q"])
    st.altair_chart(zero + line, use_container_width=True)
else:
    st.caption("睡眠データが不足しています。")

with st.expander("データを表示"):
    st.dataframe(dev, use_container_width=True)
