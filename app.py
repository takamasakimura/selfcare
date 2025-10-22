# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta
from utils import load_data, hhmm_to_minutes, signed_circ_diff_minutes, require_passcode

st.set_page_config(page_title='セルフケア・レポート', page_icon='📊', layout='wide')
st.title('📊 セルフケア・レポート')

require_passcode(page_name='report')

# 期間切替
opts = ['7日','30日','90日','期間指定']
sel = st.radio('期間', opts, index=1, horizontal=True)
start_override = end_override = None
if sel == '期間指定':
    c1, c2 = st.columns(2)
    with c1: start_override = st.date_input('開始日')
    with c2: end_override = st.date_input('終了日')

# データ読み込み
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

# ===== タブ切替 =====
tab_sleep, tab_tlx = st.tabs(['睡眠（偏差/時間）', 'TLX'])

# ---- 共通関数（睡眠偏差＋睡眠時間偏差[7h基準]） ----
BASE_SLEEP, BASE_WAKE = 21*60, 4*60
def make_sleep_deviation_df(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in frame.iterrows():
        s = hhmm_to_minutes(str(r.get('就寝時刻',''))) if '就寝時刻' in r else None
        w = hhmm_to_minutes(str(r.get('起床時刻',''))) if '起床時刻' in r else None
        sd = signed_circ_diff_minutes(s, BASE_SLEEP)
        wd = signed_circ_diff_minutes(w, BASE_WAKE)
        dur_dev = None
        if s is not None and w is not None:
            dur_h = ((w - s) % 1440) / 60.0
            dur_dev = dur_h - 7.0  # 7時間をベースライン
        rows.append({
            '日付': r['日付'].date(),
            '日付_str': r['日付'].date().isoformat(),  # カテゴリ軸で「有効日だけ」表示
            '就寝偏差(h)': sd/60 if sd is not None else None,
            '起床偏差(h)': wd/60 if wd is not None else None,
            '睡眠時間偏差(h)': dur_dev,
        })
    return pd.DataFrame(rows).dropna(how='all', subset=['就寝偏差(h)','起床偏差(h)','睡眠時間偏差(h)'])

def hourly_guides(ymin=-5, ymax=5):
    hours = [h for h in range(ymin, ymax+1) if h != 0]
    grid = alt.Chart(pd.DataFrame({'y': hours})).mark_rule(strokeDash=[2,3], opacity=0.35).encode(y='y:Q')
    zero = alt.Chart(pd.DataFrame({'y':[0]})).mark_rule(strokeDash=[6,4], opacity=0.8).encode(y='y:Q')
    return grid + zero

with tab_sleep:
    sub1, sub2 = st.tabs(['偏差（就寝/起床＋睡眠時間）','睡眠時間（参考）'])
    with sub1:
        st.caption('ベースライン: 就寝21:00 / 起床04:00 / 睡眠時間7:00。縦軸は±5時間固定。各1時間ごとに点線ガイド、0hは太めの点線で強調。')
        dev = make_sleep_deviation_df(recent)
        if not dev.empty:
            mdf = dev.melt(
                id_vars=['日付','日付_str'],
                value_vars=['就寝偏差(h)','起床偏差(h)','睡眠時間偏差(h)'],
                var_name='系列', value_name='偏差時間(h)'
            )
            guides = hourly_guides(-5, 5)
            line = alt.Chart(mdf).mark_line(point=True).encode(
                x=alt.X('日付_str:N', sort=None, title='日付'),
                y=alt.Y('偏差時間(h):Q', scale=alt.Scale(domain=[-5,5]), title='基準からの偏差（時間）'),
                color=alt.Color(
                    '系列:N',
                    scale=alt.Scale(
                        domain=['就寝偏差(h)','起床偏差(h)','睡眠時間偏差(h)'],
                        range=['#1f77b4','#d62728','#8c6d31']
                    ),
                    legend=alt.Legend(title='系列')
                ),
                tooltip=['日付:T','系列:N','偏差時間(h):Q']
            )
            st.altair_chart(guides + line, use_container_width=True)
        else:
            st.caption('有効な日が不足しており、描画できませんでした。')
    with sub2:
        # 参考用：純粋な睡眠時間（h）の折れ線（同じ計算式）
        rows = []
        for _, r in recent.iterrows():
            s = hhmm_to_minutes(str(r.get('就寝時刻',''))) if '就寝時刻' in r else None
            w = hhmm_to_minutes(str(r.get('起床時刻',''))) if '起床時刻' in r else None
            if s is not None and w is not None:
                rows.append({'日付_str': r['日付'].date().isoformat(), '日付': r['日付'].date(), '睡眠時間(h)': ((w - s) % 1440) / 60.0})
        dur = pd.DataFrame(rows)
        if not dur.empty:
            maxh = float(dur['睡眠時間(h)'].max())
            ymax = max(12.0, (int(maxh)+1))
            guides = alt.Chart(pd.DataFrame({'y': list(range(0, int(ymax)+1))})).mark_rule(strokeDash=[2,3], opacity=0.35).encode(y='y:Q')
            line = alt.Chart(dur).mark_line(point=True, color='#8c6d31').encode(
                x=alt.X('日付_str:N', sort=None, title='日付'),
                y=alt.Y('睡眠時間(h):Q', scale=alt.Scale(domain=[0, ymax]), title='睡眠時間（h）'),
                tooltip=['日付:T','睡眠時間(h):Q']
            )
            st.altair_chart(guides + line, use_container_width=True)
        else:
            st.caption('就寝/起床の両方が入っている日が不足しており、睡眠時間を描画できませんでした。')

with tab_tlx:
    tlx_cols = ['精神的要求（Mental Demand）','身体的要求（Physical Demand）','時間的要求（Temporal Demand）','努力度（Effort）','成果満足度（Performance）','フラストレーション（Frustration）']
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
    bar = alt.Chart(avg_df).mark_bar().encode(
        x='ディメンション:N', y='平均:Q', tooltip=['ディメンション','平均']
    )
    st.altair_chart(bar, use_container_width=True)
