# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from utils import load_data, hhmm_to_minutes, signed_circ_diff_minutes, require_passcode

JST = ZoneInfo('Asia/Tokyo')

st.set_page_config(page_title='睡眠ダッシュボード', page_icon='⏰', layout='wide')
st.title('⏰ 睡眠ダッシュボード')

require_passcode(page_name='graph')

# 期間切替
opts = ['7日','30日','90日','期間指定']
sel = st.radio('期間', opts, index=1, horizontal=True)
start_override = end_override = None
if sel == '期間指定':
    today = datetime.now(JST).date()
    c1, c2 = st.columns(2)
    with c1: start_override = st.date_input('開始日', value=today - timedelta(days=29))
    with c2: end_override = st.date_input('終了日', value=today)

# データ読込（直近2年結合→なければ現在年）
this_year = datetime.now(JST).year
dfs = []
for y in (this_year-1, this_year):
    try:
        d = load_data('care-log', str(y))
        if not d.empty: dfs.append(d)
    except Exception: pass
df = pd.concat(dfs, ignore_index=True) if dfs else load_data('care-log', None)

if df is None or df.empty or '日付' not in df.columns:
    st.info('まだデータがありません。まずは入力ページから保存してください。'); st.stop()

df = df.copy()
df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
df = df.dropna(subset=['日付']).sort_values('日付')

last_day = df['日付'].max().normalize()
if sel=='7日': start_day = last_day - timedelta(days=6)
elif sel=='30日': start_day = last_day - timedelta(days=29)
elif sel=='90日': start_day = last_day - timedelta(days=89)
else:
    start_day = pd.to_datetime(start_override) if start_override else last_day - timedelta(days=29)
    last_day  = pd.to_datetime(end_override) if end_override else last_day
recent = df[df['日付'].between(start_day, last_day)].reset_index(drop=True)

# 関数
BASE_SLEEP, BASE_WAKE = 21*60, 4*60

def hourly_guides(ymin=-5, ymax=5):
    hours = [h for h in range(ymin, ymax+1) if h != 0]
    grid = alt.Chart(pd.DataFrame({'y': hours})).mark_rule(strokeDash=[2,3], opacity=0.35).encode(y='y:Q')
    zero = alt.Chart(pd.DataFrame({'y':[0]})).mark_rule(strokeDash=[6,4], opacity=0.7).encode(y='y:Q')
    return grid + zero


def make_sleep_dev(frame: pd.DataFrame, base_sleep=21*60, base_wake=4*60) -> pd.DataFrame:
    rows = []
    for _, r in frame.iterrows():
        s = hhmm_to_minutes(str(r.get('就寝時刻',''))) if '就寝時刻' in r else None
        w = hhmm_to_minutes(str(r.get('起床時刻',''))) if '起床時刻' in r else None
        sd = signed_circ_diff_minutes(s, base_sleep)
        wd = signed_circ_diff_minutes(w, base_wake)
        rows.append({
            '日付': r['日付'].date(),
            '日付_str': r['日付'].date().isoformat(),
            '就寝偏差(h)': sd/60 if sd is not None else None,
            '起床偏差(h)': wd/60 if wd is not None else None,
        })
    return pd.DataFrame(rows).dropna(how='all', subset=['就寝偏差(h)','起床偏差(h)'])


def make_sleep_duration(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in frame.iterrows():
        s = hhmm_to_minutes(str(r.get('就寝時刻',''))) if '就寝時刻' in r else None
        w = hhmm_to_minutes(str(r.get('起床時刻',''))) if '起床時刻' in r else None
        dur_h = None
        if s is not None and w is not None:
            dur_h = ((w - s) % 1440) / 60.0  # 跨ぎ対応
        rows.append({
            '日付': r['日付'].date(),
            '日付_str': r['日付'].date().isoformat(),
            '睡眠時間(h)': dur_h,
        })
    return pd.DataFrame(rows).dropna(subset=['睡眠時間(h)'])


# タブ: Graph1 & Graph2
tab1, tab2 = st.tabs(['Graph1（偏差/時間）','Graph2（相関）'])

with tab1:
    sub1, sub2 = st.tabs(['偏差（就寝/起床）','睡眠時間'])
    with sub1:
        st.caption('ベースライン: 就寝21:00 / 起床04:00。縦軸は±5時間固定。各1時間ごとに点線ガイド、0hは太めの点線で強調。')
        dev = make_sleep_dev(recent, BASE_SLEEP, BASE_WAKE)
        if not dev.empty:
            mdf = dev.melt(id_vars=['日付','日付_str'], var_name='系列', value_name='偏差時間(h)')
            guides = hourly_guides(-5, 5)
            line = alt.Chart(mdf).mark_line(point=True).encode(
                x=alt.X('日付_str:N', sort=None, title='日付'),
                y=alt.Y('偏差時間(h):Q', scale=alt.Scale(domain=[-5,5]), title='基準からの偏差（時間）'),
                color=alt.Color('系列:N', scale=alt.Scale(domain=['就寝偏差(h)','起床偏差(h)'], range=['#1f77b4','#d62728'])),
                tooltip=['日付:T','系列:N','偏差時間(h):Q']
            )
            st.altair_chart(guides + line, use_container_width=True)
        else:
            st.caption('就寝時刻または起床時刻の有効値が不足しており、描画できませんでした。')
    with sub2:
        dur = make_sleep_duration(recent)
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

with tab2:
    st.caption('睡眠時間は1日の合計（一次＋二度寝等）。TLXの重みづけ方式をタブで切り替え、散布図＋回帰線と相関（r）を表示します。')
    TLX_COLS = ['精神的要求（Mental Demand）','身体的要求（Physical Demand）','時間的要求（Temporal Demand）','努力度（Effort）','成果満足度（Performance）','フラストレーション（Frustration）']
    work = recent.copy()
    work['睡眠時間'] = pd.to_numeric(work.get('睡眠時間'), errors='coerce')
    for c in TLX_COLS:
        if c not in work.columns: work[c] = pd.NA
        work[c] = pd.to_numeric(work[c], errors='coerce')
    tab_eq, tab_w = st.tabs(['等重み（Performance反転）','任意重み（調整可能）'])

    def corr_df(base: pd.DataFrame, score: pd.Series) -> pd.DataFrame:
        out = pd.DataFrame({
            '日付': base['日付'].dt.date,
            '睡眠時間[h]': base['睡眠時間'],
            '重み付きTLX': score
        }).dropna(subset=['睡眠時間[h]','重み付きTLX'])
        return out

    with tab_eq:
        perf_inv = 10 - work['成果満足度（Performance）']
        eq = pd.concat([
            work['精神的要求（Mental Demand）'],
            work['身体的要求（Physical Demand）'],
            work['時間的要求（Temporal Demand）'],
            work['努力度（Effort）'],
            perf_inv,
            work['フラストレーション（Frustration）'],
        ], axis=1).mean(axis=1, skipna=True)
        dfeq = corr_df(work, eq)
        c1, c2 = st.columns(2)
        with c1: st.metric('データ点', f'{len(dfeq)}')
        with c2:
            r = dfeq['睡眠時間[h]'].corr(dfeq['重み付きTLX']) if len(dfeq) > 1 else float('nan')
            st.metric('相関 r', f"{r:.3f}" if pd.notna(r) else '—')
        if not dfeq.empty and dfeq['睡眠時間[h]'].nunique() > 1:
            base = alt.Chart(dfeq)
            scatter = base.mark_circle(size=70).encode(
                x=alt.X('睡眠時間[h]:Q', title='合計睡眠時間 [h]'),
                y=alt.Y('重み付きTLX:Q', title='重み付きTLX（0–10）'),
                tooltip=['日付:T','睡眠時間[h]:Q','重み付きTLX:Q']
            )
            reg = base.transform_regression('睡眠時間[h]', '重み付きTLX').mark_line()
            st.altair_chart(scatter + reg, use_container_width=True)
        else:
            st.caption('相関を描くには有効なデータ点が不足しています。')

    with tab_w:
        st.write('重みを調整してください（0で無視）。Performanceは必要なら反転（10-値）。')
        c = st.columns(3)
        w_m = c[0].number_input('Mental',      min_value=0.0, value=1.0, step=0.1)
        w_p = c[0].number_input('Physical',    min_value=0.0, value=1.0, step=0.1, key='w_p')
        w_t = c[1].number_input('Temporal',    min_value=0.0, value=1.0, step=0.1)
        w_e = c[1].number_input('Effort',      min_value=0.0, value=1.0, step=0.1, key='w_e')
        invert_perf = c[2].checkbox('Performanceを反転（10-値）', value=True)
        w_f = c[2].number_input('Frustration', min_value=0.0, value=1.0, step=0.1)
        w_perf = c[2].number_input('Performanceの重み', min_value=0.0, value=1.0, step=0.1)
        comp = work.copy()
        comp['__perf__'] = (10 - comp['成果満足度（Performance）']) if invert_perf else comp['成果満足度（Performance）']
        num = (w_m*comp['精神的要求（Mental Demand）'] + w_p*comp['身体的要求（Physical Demand）'] + w_t*comp['時間的要求（Temporal Demand）'] + w_e*comp['努力度（Effort）'] + w_perf*comp['__perf__'] + w_f*comp['フラストレーション（Frustration）'])
        denom = (w_m + w_p + w_t + w_e + w_perf + w_f)
        weighted = num / denom if denom > 0 else pd.Series([pd.NA] * len(comp))
        dfw = corr_df(comp, weighted)
        c1, c2 = st.columns(2)
        with c1: st.metric('データ点', f'{len(dfw)}')
        with c2:
            r = dfw['睡眠時間[h]'].corr(dfw['重み付きTLX']) if len(dfw) > 1 else float('nan')
            st.metric('相関 r', f"{r:.3f}" if pd.notna(r) else '—')
        if not dfw.empty and dfw['睡眠時間[h]'].nunique() > 1:
            base = alt.Chart(dfw)
            scatter = base.mark_circle(size=70).encode(
                x=alt.X('睡眠時間[h]:Q', title='合計睡眠時間 [h]'),
                y=alt.Y('重み付きTLX:Q', title='重み付きTLX（0–10）'),
                tooltip=['日付:T','睡眠時間[h]:Q','重み付きTLX:Q']
            )
            reg = base.transform_regression('睡眠時間[h]', '重み付きTLX').mark_line()
            st.altair_chart(scatter + reg, use_container_width=True)
        else:
            st.caption('相関を描くには有効なデータ点が不足しています。')
