# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from utils import load_data, hhmm_to_minutes, signed_circ_diff_minutes, require_passcode

JST = ZoneInfo("Asia/Tokyo")

st.set_page_config(page_title="睡眠ダッシュボード", page_icon="⏰", layout="wide")
st.title("⏰ 睡眠ダッシュボード")

# ---- パスコード（Secrets の APP_PASSCODE を使用） ----
require_passcode(page_name="graph")

# ---- 期間切替（共通） ----
opts = ["7日", "30日", "90日", "期間指定"]
sel = st.radio("期間", opts, index=1, horizontal=True)
start_override = end_override = None
if sel == "期間指定":
    today = datetime.now(JST).date()
    c1, c2 = st.columns(2)
    with c1:
        start_override = st.date_input("開始日", value=today - timedelta(days=29))
    with c2:
        end_override = st.date_input("終了日", value=today)

# ---- データ読込（年跨ぎ対応：直近2年を結合、無ければ現在年にフォールバック） ----
this_year = datetime.now(JST).year
dfs = []
for y in (this_year - 1, this_year):
    try:
        d = load_data("care-log", str(y))
        if not d.empty:
            dfs.append(d)
    except Exception:
        pass
df = pd.concat(dfs, ignore_index=True) if dfs else load_data("care-log", None)

if df is None or df.empty or "日付" not in df.columns:
    st.info("まだデータがありません。まずは入力ページから保存してください。")
    st.stop()

df = df.copy()
df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
df = df.dropna(subset=["日付"]).sort_values("日付")

# ---- 期間フィルタ ----
last_day = df["日付"].max().normalize()
if sel == "7日":
    start_day = last_day - timedelta(days=6)
elif sel == "30日":
    start_day = last_day - timedelta(days=29)
elif sel == "90日":
    start_day = last_day - timedelta(days=89)
else:
    start_day = pd.to_datetime(start_override) if start_override else last_day - timedelta(days=29)
    last_day  = pd.to_datetime(end_override) if end_override else last_day
recent = df[df["日付"].between(start_day, last_day)].reset_index(drop=True)

# ==================== Graph1: 就寝/起床のベースライン偏差 ====================
st.header("Graph1｜就寝・起床のベースラインからのズレ")
st.caption("ベースライン: 就寝21:00 / 起床04:00。縦軸は±3時間固定。空欄は自動で除外。")

BASE_SLEEP = 21 * 60  # 21:00
BASE_WAKE  = 4  * 60  # 04:00

def sleep_dev_df(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in frame.iterrows():
        s = hhmm_to_minutes(str(r.get("就寝時刻", ""))) if "就寝時刻" in r else None
        w = hhmm_to_minutes(str(r.get("起床時刻", ""))) if "起床時刻" in r else None
        sd = signed_circ_diff_minutes(s, BASE_SLEEP)
        wd = signed_circ_diff_minutes(w, BASE_WAKE)
        rows.append({
            "日付": r["日付"].date(),
            "就寝偏差(h)": sd/60 if sd is not None else None,
            "起床偏差(h)": wd/60 if wd is not None else None,
        })
    out = pd.DataFrame(rows).dropna(how="all", subset=["就寝偏差(h)", "起床偏差(h)"])
    return out

g1 = sleep_dev_df(recent)
if not g1.empty:
    mdf = g1.melt(id_vars=["日付"], var_name="系列", value_name="偏差時間(h)")
    zero = alt.Chart(pd.DataFrame({"y":[0]})).mark_rule(strokeDash=[4,4]).encode(y="y:Q")
    line = alt.Chart(mdf).mark_line(point=True).encode(
        x=alt.X("日付:T"),
        y=alt.Y("偏差時間(h):Q", scale=alt.Scale(domain=[-3, 3])),
        color=alt.Color("系列:N"),
        tooltip=["日付:T","系列:N","偏差時間(h):Q"]
    )
    st.altair_chart(zero + line, use_container_width=True)
else:
    st.caption("就寝時刻または起床時刻が未入力の日が多く、描画できませんでした。")

st.markdown("---")

# ==================== Graph2: 合計睡眠 × 重み付きTLX の相関 ====================
st.header("Graph2｜合計睡眠時間 × 重み付き TLX の相関")
st.caption("睡眠時間は1日の合計（一次＋二度寝等）。TLXの重みづけ方式をタブで切り替え、散布図＋回帰線と相関（r）を表示します。")

# TLX 列名
TLX_COLS = [
    "精神的要求（Mental Demand）",
    "身体的要求（Physical Demand）",
    "時間的要求（Temporal Demand）",
    "努力度（Effort）",
    "成果満足度（Performance）",  # 反転候補
    "フラストレーション（Frustration）",
]

# 入力の正規化
work = recent.copy()
# 睡眠時間（時間）を数値化
if "睡眠時間" in work.columns:
    work["睡眠時間"] = pd.to_numeric(work["睡眠時間"], errors="coerce")
else:
    work["睡眠時間"] = pd.NA

# TLX 数値化
for c in TLX_COLS:
    if c not in work.columns:
        work[c] = pd.NA
    work[c] = pd.to_numeric(work[c], errors="coerce")

tab_a, tab_b = st.tabs(["等重み（Performance反転）", "任意重み（調整可能）"])

def build_corr_df(base: pd.DataFrame, score_series: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame({
        "日付": base["日付"].dt.date,
        "睡眠時間[h]": base["睡眠時間"],
        "重み付きTLX": score_series
    })
    out = out.dropna(subset=["睡眠時間[h]", "重み付きTLX"])
    return out

with tab_a:
    perf_inv = 10 - work["成果満足度（Performance）"]
    eq_scores = pd.concat([
        work["精神的要求（Mental Demand）"],
        work["身体的要求（Physical Demand）"],
        work["時間的要求（Temporal Demand）"],
        work["努力度（Effort）"],
        perf_inv,
        work["フラストレーション（Frustration）"],
    ], axis=1).mean(axis=1, skipna=True)

    corr_a = build_corr_df(work, eq_scores)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("データ点", f"{len(corr_a)}")
    with c2:
        r = corr_a["睡眠時間[h]"].corr(corr_a["重み付きTLX"]) if len(corr_a) > 1 else float('nan')
        st.metric("ピアソン相関 r", f"{r:.3f}" if pd.notna(r) else "—")

    if not corr_a.empty and corr_a["睡眠時間[h]"].nunique() > 1:
        base = alt.Chart(corr_a)
        scatter = base.mark_circle(size=70).encode(
            x=alt.X("睡眠時間[h]:Q"),
            y=alt.Y("重み付きTLX:Q"),
            tooltip=["日付:T","睡眠時間[h]:Q","重み付きTLX:Q"]
        )
        reg = base.transform_regression("睡眠時間[h]", "重み付きTLX").mark_line()
        st.altair_chart(scatter + reg, use_container_width=True)
    else:
        st.caption("相関を描くには有効なデータ点が不足しています。")

with tab_b:
    st.write("重みを調整してください（合計は任意、0で無視）。Performanceは必要なら反転します。")
    cols = st.columns(3)
    w = {}
    with cols[0]:
        w["精神的要求（Mental Demand）"] = st.number_input("Mental", min_value=0.0, value=1.0, step=0.1, key="w_m")
        w["身体的要求（Physical Demand）"] = st.number_input("Physical", min_value=0.0, value=1.0, step=0.1, key="w_p")
    with cols[1]:
        w["時間的要求（Temporal Demand）"] = st.number_input("Temporal", min_value=0.0, value=1.0, step=0.1, key="w_t")
        w["努力度（Effort）"] = st.number_input("Effort", min_value=0.0, value=1.0, step=0.1, key="w_e")
    with cols[2]:
        invert_perf = st.checkbox("成果満足度（Performance）を反転（10-値）", value=True, key="inv_perf")
        w["フラストレーション（Frustration）"] = st.number_input("Frustration", min_value=0.0, value=1.0, step=0.1, key="w_f")
        w_perf = st.number_input("Performance の重み", min_value=0.0, value=1.0, step=0.1, key="w_perf")

    comp = work.copy()
    comp["__perf_adj__"] = (10 - comp["成果満足度（Performance）"]) if invert_perf else comp["成果満足度（Performance）"]

    weighted_sum = (
        w["精神的要求（Mental Demand）"] * comp["精神的要求（Mental Demand）"] +
        w["身体的要求（Physical Demand）"] * comp["身体的要求（Physical Demand）"] +
        w["時間的要求（Temporal Demand）"] * comp["時間的要求（Temporal Demand）"] +
        w["努力度（Effort）"] * comp["努力度（Effort）"] +
        w_perf * comp["__perf_adj__"] +
        w["フラストレーション（Frustration）"] * comp["フラストレーション（Frustration）"]
    )

    total_w = (
        w["精神的要求（Mental Demand）"] +
        w["身体的要求（Physical Demand）"] +
        w["時間的要求（Temporal Demand）"] +
        w["努力度（Effort）"] +
        w_perf +
        w["フラストレーション（Frustration）"]
    )

    weighted = weighted_sum / total_w if total_w > 0 else pd.Series([pd.NA] * len(comp))

    corr_b = build_corr_df(comp, weighted)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("データ点", f"{len(corr_b)}")
    with c2:
        r = corr_b["睡眠時間[h]"].corr(corr_b["重み付きTLX"]) if len(corr_b) > 1 else float('nan')
        st.metric("ピアソン相関 r", f"{r:.3f}" if pd.notna(r) else "—")

    if not corr_b.empty and corr_b["睡眠時間[h]"].nunique() > 1:
        base = alt.Chart(corr_b)
        scatter = base.mark_circle(size=70).encode(
            x=alt.X("睡眠時間[h]:Q"),
            y=alt.Y("重み付きTLX:Q"),
            tooltip=["日付:T","睡眠時間[h]:Q","重み付きTLX:Q"]
        )
        reg = base.transform_regression("睡眠時間[h]", "重み付きTLX").mark_line()
        st.altair_chart(scatter + reg, use_container_width=True)
    else:
        st.caption("相関を描くには有効なデータ点が不足しています。")

