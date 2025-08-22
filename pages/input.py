from datetime import datetime, timedelta, timezone
import streamlit as st
import pandas as pd
from utils import calculate_sleep_duration, save_to_google_sheets, load_today_record, get_google_sheet, get_existing_data_row

st.title("セルフケア入力")

# デフォルト日付（today）
JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
st.write(f"今日の日付：{today}")

# --- UIのキー設定（ここはあなたの既存コードに合わせてください）---
SLEEP_KEY = "sleep_time"
WAKE_KEY = "wake_time"
MENTAL_KEY = "mental_demand"
PHYSICAL_KEY = "physical_demand"
TEMPORAL_KEY = "temporal_demand"
EFFORT_KEY = "effort"
PERFORMANCE_KEY = "performance"
FRUSTRATION_KEY = "frustration"
SIGN_KEY = "sign"
TASK_KEY = "task"
AWARENESS_KEY = "awareness"
ADVICE_KEY = "advice"

# --- 入力ウィジェット例 ---
sleep_time = st.time_input("就寝時刻", key=SLEEP_KEY)
wake_time = st.time_input("起床時刻", key=WAKE_KEY)
mental = st.slider("精神的要求（Mental Demand）", 0, 100, 50, key=MENTAL_KEY)
physical = st.slider("身体的要求（Physical Demand）", 0, 100, 50, key=PHYSICAL_KEY)
temporal = st.slider("時間的要求（Temporal Demand）", 0, 100, 50, key=TEMPORAL_KEY)
effort = st.slider("努力度（Effort）", 0, 100, 50, key=EFFORT_KEY)
performance = st.slider("成果満足度（Performance）", 0, 100, 50, key=PERFORMANCE_KEY)
frustration = st.slider("フラストレーション（Frustration）", 0, 100, 50, key=FRUSTRATION_KEY)
sign = st.text_input("体調サイン", key=SIGN_KEY)
task = st.text_area("取り組んだこと", key=TASK_KEY)
awareness = st.text_area("気づいたこと", key=AWARENESS_KEY)
advice = st.text_area("アドバイス", key=ADVICE_KEY)

# 就寝・起床時刻
col1, col2 = st.columns(2)
with col1:
    sleep_time = st.time_input("就寝時刻", value=datetime.strptime("23:00", "%H:%M").time())
with col2:
    wake_time = st.time_input("起床時刻", value=datetime.strptime("07:00", "%H:%M").time())

# 睡眠時間の計算
sleep_duration = calculate_sleep_duration(sleep_time, wake_time)
st.write(f"睡眠時間（推定）：{sleep_duration:.2f} 時間")

nasa_questions = [
    ("精神的要求（Mental Demand）", "精神的要求"),
    ("身体的要求（Physical Demand）", "身体的要求"),
    ("時間的要求（Temporal Demand）", "時間的要求"),
    ("努力度（Effort）", "努力"),
    ("成果満足度（Performance）", "成果満足"),
    ("フラストレーション（Frustration）", "フラストレーション")
]

# NASA-TLX スコア（1〜10）
nasa_scores = {}
st.subheader("NASA-TLX評価（0〜10）")
for question, label in nasa_questions:
    score = st.slider(question, 0, 10, 5)
    nasa_scores[label] = score

# サイン（メモ内にタグとして）
st.subheader("体調サイン・タグ付きメモ")
tagged_note = st.text_area("例：＜タグ：頭痛＞ 作業に集中できなかった")

# 自己成長メモ
st.subheader("内省ログ")
reflection1 = st.text_area("取り組んだこと")
reflection2 = st.text_area("気づいたこと・感想")

# GPTアドバイス（任意入力 or 自動挿入）
gpt_advice = st.text_area("GPTアドバイス（任意）")

# 保存ボタン
if st.button("保存する"):
    record = {
        "日付": today.isoformat(),
        "就寝時刻": sleep_time.strftime("%H:%M"),
        "起床時刻": wake_time.strftime("%H:%M"),
        "睡眠時間": round(sleep_duration, 2),
        "精神的要求（Mental Demand）": nasa_scores["精神的要求"],
        "身体的要求（Physical Demand）": nasa_scores["身体的要求"],
        "時間的要求（Temporal Demand）": nasa_scores["時間的要求"],
        "努力度（Effort）": nasa_scores["努力"],
        "成果満足度（Performance）": nasa_scores["成果満足"],
        "フラストレーション（Frustration）": nasa_scores["フラストレーション"],
        "体調サイン": tagged_note,
        "取り組んだこと": reflection1,
        "気づいたこと": reflection2,
        "アドバイス": gpt_advice
    }

    df = pd.DataFrame([record])  # ← ここで DataFrame を作成
    save_to_google_sheets(df, "care-log")
    st.success("保存しました！")

# --- 復元ボタン ---
if st.button("今日のデータを復元"):
    sheet = get_google_sheet()
    rec = get_existing_data_row(sheet)
    if rec:
        mapping = {
            "就寝時刻": SLEEP_KEY,
            "起床時刻": WAKE_KEY,
            "精神的要求（Mental Demand）": MENTAL_KEY,
            "身体的要求（Physical Demand）": PHYSICAL_KEY,
            "時間的要求（Temporal Demand）": TEMPORAL_KEY,
            "努力度（Effort）": EFFORT_KEY,
            "成果満足度（Performance）": PERFORMANCE_KEY,
            "フラストレーション（Frustration）": FRUSTRATION_KEY,
            "体調サイン": SIGN_KEY,
            "取り組んだこと": TASK_KEY,
            "気づいたこと": AWARENESS_KEY,
            "アドバイス": ADVICE_KEY,
        }
        for col, key in mapping.items():
            if col in rec and rec[col] not in ("", None):
                st.session_state[key] = rec[col]
        st.success("本日のデータを復元しました ✅")
        st.rerun()
    else:
        st.info("本日のデータはシートに存在しません。")