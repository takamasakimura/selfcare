import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import sys
import os

# 親ディレクトリのutils.pyを読み込むためのパス追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import load_data

st.set_page_config(page_title="内省レポート", layout="wide")

# データ読み込み
df = load_data()

# 日付をdatetime型に変換
df["日付"] = pd.to_datetime(df["日付"])

# 最新の日付順にソートし、最新30件を抽出
filtered_df = df.sort_values(by="日付", ascending=False).head(30)

# タブで表示切り替え
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛏️ 睡眠傾向", "📊 TLX分析", "🔄 TLX×睡眠相関", "🏷️ タグ傾向", "📓 内省ログ"])

with tab1:
    st.subheader("睡眠傾向")
    sleep_chart = alt.Chart(filtered_df).transform_fold(
        ["睡眠時間"]
    ).mark_line(point=True).encode(
        x="日付:T",
        y="value:Q",
        color="key:N"
    ).properties(width=800, height=400)
    st.altair_chart(sleep_chart, use_container_width=True)

with tab2:
    st.subheader("NASA-TLX分析")
    tlx_items = [
        "精神的要求（Mental Demand）",
        "身体的要求（Physical Demand）",
        "時間的要求（Temporal Demand）",
        "努力度（Effort）",
        "成果満足度（Performance）",
        "フラストレーション（Frustration）"
    ]
    tlx_chart = alt.Chart(filtered_df).transform_fold(
        tlx_items
    ).mark_line(point=True).encode(
        x="日付:T",
        y="value:Q",
        color="key:N"
    ).properties(width=800, height=400)
    st.altair_chart(tlx_chart, use_container_width=True)

with tab3:
    st.subheader("TLX合計スコアと睡眠の相関")
    filtered_df["TLX合計"] = filtered_df[tlx_items].sum(axis=1)
    corr_chart = alt.Chart(filtered_df).mark_circle(size=100).encode(
        x="睡眠時間:Q",
        y="TLX合計:Q",
        tooltip=["日付", "睡眠時間", "TLX合計"]
    ).interactive().properties(width=700, height=400)
    st.altair_chart(corr_chart, use_container_width=True)

with tab4:
    st.subheader("タグ傾向（出現頻度）")
    tags = filtered_df["体調サイン"].str.extractall(r"＜タグ：(.*?)＞")[0]
    tag_counts = tags.value_counts().reset_index()
    tag_counts.columns = ["タグ", "件数"]
    tag_bar = alt.Chart(tag_counts).mark_bar().encode(
        x=alt.X("件数:Q"),
        y=alt.Y("タグ:N", sort='-x')
    ).properties(width=600, height=400)
    st.altair_chart(tag_bar, use_container_width=True)

with tab5:
    st.subheader("内省ログ")
    for _, row in filtered_df.iterrows():
        st.markdown(f"### {row['日付'].date()}")
        st.markdown(f"- **取り組んだこと**: {row['取り組んだこと']}")
        st.markdown(f"- **気づいたこと**: {row['気づいたこと']}")
        st.markdown(f"- **GPTアドバイス**: {row['アドバイス']}")
        st.markdown("---")