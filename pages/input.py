# -*- coding: utf-8 -*-
from datetime import datetime
import streamlit as st
import pandas as pd
from streamlit_knobs import knob
from utils import (
    save_to_google_sheets,
    load_today_record,
    total_sleep_hours,
    minutes_to_hhmm,
    require_passcode,
)

st.set_page_config(
    page_title="セルフケア入力",
    page_icon="📝",
    layout="centered",
)

st.title("📝 セルフケア入力")

# -------- パスコード必須 --------
require_passcode(page_name="input")

# ============== TLXガイド読み込み（任意） ==============
@st.cache_data
def load_tlx_guide():
    try:
        df = pd.read_csv("nasa_tlx_guide.csv")
    except FileNotFoundError:
        return {}
    guide = {}
    if "スコア" in df.columns:
        for _, row in df.iterrows():
            try:
                score = int(row["スコア"])
            except Exception:
                continue
            guide[score] = {
                k: str(v) for k, v in row.items() if k != "スコア"
            }
    return guide

GUIDE = load_tlx_guide()

def tlx_help_text(dim: str, score: int) -> str:
    g = GUIDE.get(score, {})
    return g.get(dim, "")

# ============== 既存データの読込（本日分） ==============
today_record = load_today_record() or {}

# ============== 入力フォーム ==============
with st.form("care_form"):
    date_val = st.date_input("日付", value=today_record.get("日付", datetime.now().date()))

    st.markdown("### NASA-TLX（0〜10 の整数で評価）")
    dims = [
        "精神的要求（Mental Demand）",
        "身体的要求（Physical Demand）",
        "時間的要求（Temporal Demand）",
        "努力度（Effort）",
        "成果満足度（Performance）",
        "フラストレーション（Frustration）",
    ]
    tlx_vals = {}
    for dim in dims:
        default = 0
        try:
            default = int(today_record.get(dim, 0) or 0)
        except Exception:
            default = 0
        tlx_vals[dim] = st.slider(dim, 0, 10, default, help=tlx_help_text(dim, default))

    st.markdown("### 睡眠（円環ダイヤル・15分単位）")
    st.caption("＋ボタンで区間を追加できます（最大3つ）。時刻は0〜24hのダイヤルで設定。")

    if "sleep_segments" not in st.session_state:
        segs = []
        for i in range(1, 4):
            sj = today_record.get(f"就寝{i}", "")
            kj = today_record.get(f"起床{i}", "")
            segs.append([None, None])
            if isinstance(sj, str) and ":" in sj:
                h, m = sj.split(":"); segs[-1][0] = (int(h) % 24) * 60 + (int(m) % 60)
            if isinstance(kj, str) and ":" in kj:
                h, m = kj.split(":"); segs[-1][1] = (int(h) % 24) * 60 + (int(m) % 60)
        if all(v is None for v in segs[0]):
            segs[0] = [21*60, 4*60]  # 21:00 -> 04:00
        st.session_state.sleep_segments = segs
        st.session_state.sleep_count = 1 if any(v is None for v in segs[1]+segs[2]) else 3

    b1, b2 = st.columns(2)
    with b1:
        add = st.form_submit_button("➕ 区間を追加", use_container_width=True)
    with b2:
        rem = st.form_submit_button("➖ 最後の区間を削除", use_container_width=True)

    if add:
        st.session_state.sleep_count = min(3, st.session_state.sleep_count + 1)
    if rem:
        st.session_state.sleep_count = max(1, st.session_state.sleep_count - 1)
        idx = st.session_state.sleep_count
        st.session_state.sleep_segments[idx] = [None, None]

    total_rows = []
    for i in range(st.session_state.sleep_count):
        st.write(f"**区間{i+1}**")
        c1, c2 = st.columns(2)
        with c1:
            init_s = st.session_state.sleep_segments[i][0]
            val_s = knob(
                knob_type="2",
                title="就寝",
                min_value=0, max_value=1440, step=15,
                initial_value=init_s if init_s is not None else 21*60,
                key=f"knob_sleep_{i}_start"
            )
            st.session_state.sleep_segments[i][0] = int(val_s) if val_s is not None else None
            st.caption(f"就寝: {minutes_to_hhmm(st.session_state.sleep_segments[i][0])}")
        with c2:
            init_e = st.session_state.sleep_segments[i][1]
            val_e = knob(
                knob_type="2",
                title="起床",
                min_value=0, max_value=1440, step=15,
                initial_value=init_e if init_e is not None else 4*60,
                key=f"knob_sleep_{i}_end"
            )
            st.session_state.sleep_segments[i][1] = int(val_e) if val_e is not None else None
            st.caption(f"起床: {minutes_to_hhmm(st.session_state.sleep_segments[i][1])}")
        total_rows.append(tuple(st.session_state.sleep_segments[i]))

    tot = total_sleep_hours(total_rows)
    st.metric("総睡眠", f"{tot:.2f} 時間" if tot is not None else "—")

    st.markdown("### メモ")
    col1, col2 = st.columns(2)
    with col1:
        sign = st.text_area("体調サイン（タグは＜タグ:○○＞）", value=today_record.get("体調サイン", ""), height=100)
        effort = st.text_area("取り組んだこと", value=today_record.get("取り組んだこと", ""), height=100)
    with col2:
        stressor = st.text_area("ストレッサー", value=today_record.get("ストレッサー", ""), height=100)
        cmt_sinoa = st.text_area("シノアのコメント", value=today_record.get("シノアのコメント", ""), height=100)
        cmt_keika = st.text_area("桂花のコメント", value=today_record.get("桂花のコメント", ""), height=100)

    submitted = st.form_submit_button("保存", use_container_width=True)

if submitted:
    sj1, kj1 = st.session_state.sleep_segments[0]
    sj2, kj2 = st.session_state.sleep_segments[1]
    sj3, kj3 = st.session_state.sleep_segments[2]
    record = {
        "日付": date_val,
        **tlx_vals,
        "就寝1": minutes_to_hhmm(sj1),
        "起床1": minutes_to_hhmm(kj1),
        "就寝2": minutes_to_hhmm(sj2),
        "起床2": minutes_to_hhmm(kj2),
        "就寝3": minutes_to_hhmm(sj3),
        "起床3": minutes_to_hhmm(kj3),
        "総睡眠（時間）": total_sleep_hours([(sj1,kj1),(sj2,kj2),(sj3,kj3)]),
        "体調サイン": sign,
        "取り組んだこと": effort,
        "ストレッサー": stressor,
        "シノアのコメント": cmt_sinoa,
        "桂花のコメント": cmt_keika,
    }
    df = pd.DataFrame([record])
    save_to_google_sheets(df, "care-log", None)
    st.success("保存しました！")
    st.balloons()

st.caption("ヒント: 体調サインに **＜タグ:睡眠＞** のように書くと、レポートでタグ集計できます。")
