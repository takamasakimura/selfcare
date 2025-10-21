# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta
from utils import load_data, hhmm_to_minutes, signed_circ_diff_minutes, require_passcode

st.set_page_config(page_title='セルフケア・レポート', page_icon='📊', layout='wide')
st.title('📊 セルフケア・レポート')

require_passcode(page_name='report')

opts = ['7日','30日','90日','期間指定']
sel = st.radio('期間', opts, index=1, horizontal=True)
start_override = end_override = None
if sel == '期間指定':
    c1, c2 = st.columns(2)
    with c1: start_override = st.date_input('開始日')
    with c2: end_override = st.date_input('終了日')

df = load_data('care-log', None)
if df is None or df.empty or '日付' not in df.columns:
    st.info('まだデータがありません。まずは入力ページから保存してください。')
    st.stop()

df = df.copy()
df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
df = df.dropna(subset=['日付']).sort_values('日付')

last_day = df['日付'].max().normalize()
if sel == '7日':
    start_day = last_day - timedelta(days=6)
elif sel == '30日':
    start_day = last_day - timedelta(days=29)
elif sel == '90日':
    start_day = last_day - timedelta(days=89)
else:
    start_day = pd.to_datetime(start_override) if start_override else last_day - timedelta(days=29)
    last_day  = pd.to_datetime(end_override) if end_override else last_day
recent = df[df['日付'].between(start_day, last_day)].reset_index(drop=True)

tab_sleep, tab_tlx = st.tabs(['睡眠偏差（±5h）','TLX'])

BASE_SLEEP, BASE_WAKE = 21*60, 4*60

def make_sleep_dev(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in frame.iterrows():
        s = hhmm_to_minutes(str(r.get('就寝時刻',''))) if '就寝時刻' in r else None
        w = hhmm_to_minutes(str(r.get('起床時刻',''))) if '起床時刻' in r else None
        sd = signed_circ_diff_minutes(s, BASE_SLEEP)
        wd = signed_circ_diff_minutes(w, BASE_WAKE)
        rows.append({
            '日付': r['日付'].date(),
            '日付_str': r['日付'].date().isoformat(),
            '就寝偏差(h)': sd/60 if sd is not None else None,
            '起床偏差(h)': wd/60 if wd is not None else None,
        })
    return pd.DataFrame(rows).dropna(how='all', subset=['就寝偏差(h)','起床偏差(h)'])

def hourly_guides(ymin=-5, ymax=5):
    hours = [h for h in range(ymin, ymax+1) if h != 0]
    grid = alt.Chart(pd.DataFrame({'y': hours})).mark_rule(strokeDash=[2,3], opacity=0.35).encode(y='y:Q')
    zero = alt.Chart(pd.DataFrame({'y':[0]})).mark_rule(strokeDash=[6,4], opacity=0.7).encode(y='y:Q')
    return grid + zero

with tab_sleep:
    st.caption('ベースライン: 就寝21:00 / 起床04:00。縦軸は±5時間固定。各1時間ごとに点線ガイド、0hは太めの点線で強調。')
    dev = make_sleep_dev(recent)
    if not dev.empty:
        mdf = dev.melt(id_vars=['日付','日付_str'], var_name='系列', value_name='偏差時間(h)')
        guides = hourly_guides(-5, 5)
        line = alt.Chart(mdf).mark_line(point=True).encode(
            x=alt.X('日付_str:N', sort=None, title='日付'),
            y=alt.Y('偏差時間(h):Q', scale=alt.Scale(domain=[-5,5]), title='基準からの偏差（時間）'),
            color=alt.Color('系列:N'),
            tooltip=['日付:T','系列:N','偏差時間(h):Q']
        )
        st.altair_chart(guides + line, use_container_width=True)
    else:
        st.caption('就寝時刻または起床時刻の有効値が不足しており、描画できませんでした。')

with tab_tlx:
    tlx_cols = [
        '精神的要求（Mental Demand）',
        '身体的要求（Physical Demand）',
        '時間的要求（Temporal Demand）',
        '努力度（Effort）',
        '成果満足度（Performance）',
        'フラストレーション（Frustration）',
    ]
    for c in tlx_cols:
        if c not in recent.columns: recent[c] = 0
    recent['NASA_TLX_平均'] = recent[tlx_cols].apply(pd.to_numeric, errors='coerce').mean(axis=1)

    c1, c2, c3 = st.columns(3)
    with c1: st.metric('対象データ件数', f'{len(recent)}')
    with c2: st.metric('最新日のTLX平均', f"{recent.iloc[-1]['NASA_TLX_平均']:.2f}" if len(recent)>0 else '—')
    with c3: st.metric('期間平均TLX', f"{recent['NASA_TLX_平均'].mean():.2f}" if len(recent)>0 else '—')

    line = alt.Chart(recent).mark_line(point=True).encode(
        x=alt.X('日付:T'), y=alt.Y('NASA_TLX_平均:Q'), tooltip=['日付:T','NASA_TLX_平均:Q']
    )
    st.altair_chart(line, use_container_width=True)

    avg_df = recent[tlx_cols].apply(pd.to_numeric, errors='coerce').mean().reset_index()
    avg_df.columns = ['ディメンション','平均']
    bar = alt.Chart(avg_df).mark_bar().encode(x='ディメンション:N', y='平均:Q', tooltip=['ディメンション','平均'])
    st.altair_chart(bar, use_container_width=True)
