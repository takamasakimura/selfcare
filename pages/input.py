from datetime import datetime, timedelta, timezone, time as _time
import streamlit as st
import pandas as pd
from utils import calculate_sleep_duration, save_to_google_sheets, load_today_record  # load_today_record は utils 側に実装済み想定

# ===== 基本設定 =====
JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
st.title("セルフケア入力")
st.caption(f"今日の日付 : {today.isoformat()}")

# ===== セッションキー（ウィジェットと復元の紐付けを一元管理）=====
K = {
    "就寝時刻": "sleep_time",
    "起床時刻": "wake_time",
    "精神的要求（Mental Demand）": "mental_demand",
    "身体的要求（Physical Demand）": "physical_demand",
    "時間的要求（Temporal Demand）": "temporal_demand",
    "努力度（Effort）": "effort",
    "成果満足度（Performance）": "performance",
    "フラストレーション（Frustration）": "frustration",
    "体調サイン": "sign",
    "取り組んだこと": "task",
    "気づいたこと": "awareness",
    "アドバイス": "advice",
}

# ===== 初期化（重複生成を防止）=====
def _init(k, v):
    if k not in st.session_state:
        st.session_state[k] = v

_init(K["就寝時刻"], datetime.strptime("23:00", "%H:%M").time())
_init(K["起床時刻"], datetime.strptime("07:00", "%H:%M").time())
_init(K["精神的要求（Mental Demand）"], 5)
_init(K["身体的要求（Physical Demand）"], 5)
_init(K["時間的要求（Temporal Demand）"], 5)
_init(K["努力度（Effort）"], 5)
_init(K["成果満足度（Performance）"], 5)
_init(K["フラストレーション（Frustration）"], 5)
_init(K["体調サイン"], "")
_init(K["取り組んだこと"], "")
_init(K["気づいたこと"], "")
_init(K["アドバイス"], "")

def _to_time(v):
    if isinstance(v, _time):
        return v
    if isinstance(v, str) and v.strip():
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(v.strip(), fmt).time()
            except ValueError:
                continue
    return None  # 不正なら None（代入スキップ）

def _to_int_0_10(v):
    try:
        n = int(float(v))
        return max(0, min(10, n))
    except Exception:
        return None

def _to_str(v):
    if v is None:
        return ""
    return str(v)

# ===== 入力ウィジェット =====
col1, col2 = st.columns(2)
with col1:
    sleep_time = st.time_input("就寝時刻", key=K["就寝時刻"])
with col2:
    wake_time = st.time_input("起床時刻", key=K["起床時刻"])

st.subheader("NASA-TLX（0〜10）")
mental = st.slider(
    "精神的要求（Mental Demand）",
    0, 10,
    st.session_state[K["精神的要求（Mental Demand）"]],
    key=K["精神的要求（Mental Demand）"]
)

physical = st.slider(
    "身体的要求（Physical Demand）",
    0, 10,
    st.session_state[K["身体的要求（Physical Demand）"]],
    key=K["身体的要求（Physical Demand）"]
)

temporal = st.slider(
    "時間的要求（Temporal Demand）",
    0, 10,
    st.session_state[K["時間的要求（Temporal Demand）"]],
    key=K["時間的要求（Temporal Demand）"]
)

effort = st.slider(
    "努力度（Effort）",
    0, 10,
    st.session_state[K["努力度（Effort）"]],
    key=K["努力度（Effort）"]
)

performance = st.slider(
    "成果満足度（Performance）",
    0, 10,
    st.session_state[K["成果満足度（Performance）"]],
    key=K["成果満足度（Performance）"]
)

frustration = st.slider(
    "フラストレーション（Frustration）",
    0, 10,
    st.session_state[K["フラストレーション（Frustration）"]],
    key=K["フラストレーション（Frustration）"]
)

st.subheader("体調サイン・メモ")
st.text_area("体調サイン（タグ可）", key=K["体調サイン"], placeholder="例：＜タグ：頭痛＞ 集中できなかった など")

st.subheader("内省ログ")
st.text_area("取り組んだこと", key=K["取り組んだこと"])
st.text_area("気づいたこと", key=K["気づいたこと"])

st.subheader("GPTアドバイス（任意）")
st.text_area("アドバイス", key=K["アドバイス"])

# ===== 洗い替え（睡眠時間の即時計算）=====
sleep_duration = calculate_sleep_duration(st.session_state[K["就寝時刻"]], st.session_state[K["起床時刻"]])
st.info(f"睡眠時間（推定）：{sleep_duration:.2f} 時間")

colA, colB = st.columns(2)

with colA:
    if st.button("本日のデータを復元"):
        restore_today()

with colB:
    if st.button("保存する"):
        record = {
            "日付": today.isoformat(),
            "就寝時刻": st.session_state[K["就寝時刻"]].strftime("%H:%M"),
            "起床時刻": st.session_state[K["起床時刻"]].strftime("%H:%M"),
            "睡眠時間": round(sleep_duration, 2),
            "精神的要求（Mental Demand）": int(st.session_state[K["精神的要求（Mental Demand）"]]),
            "身体的要求（Physical Demand）": int(st.session_state[K["身体的要求（Physical Demand）"]]),
            "時間的要求（Temporal Demand）": int(st.session_state[K["時間的要求（Temporal Demand）"]]),
            "努力度（Effort）": int(st.session_state[K["努力度（Effort）"]]),
            "成果満足度（Performance）": int(st.session_state[K["成果満足度（Performance）"]]),
            "フラストレーション（Frustration）": int(st.session_state[K["フラストレーション（Frustration）"]]),
            "体調サイン": st.session_state[K["体調サイン"]],
            "取り組んだこと": st.session_state[K["取り組んだこと"]],
            "気づいたこと": st.session_state[K["気づいたこと"]],
            "アドバイス": st.session_state[K["アドバイス"]],
        }
        df = pd.DataFrame([record])
        save_to_google_sheets(df, "care-log", "2025")
        st.success("保存しました！")

# ===== 保存ボタン =====
with colB:
    if st.button("保存する"):
        record = {
            "日付": today.isoformat(),
            "就寝時刻": st.session_state[K["就寝時刻"]].strftime("%H:%M"),
            "起床時刻": st.session_state[K["起床時刻"]].strftime("%H:%M"),
            "睡眠時間": round(sleep_duration, 2),
            "精神的要求（Mental Demand）": int(st.session_state[K["精神的要求（Mental Demand）"]]),
            "身体的要求（Physical Demand）": int(st.session_state[K["身体的要求（Physical Demand）"]]),
            "時間的要求（Temporal Demand）": int(st.session_state[K["時間的要求（Temporal Demand）"]]),
            "努力度（Effort）": int(st.session_state[K["努力度（Effort）"]]),
            "成果満足度（Performance）": int(st.session_state[K["成果満足度（Performance）"]]),
            "フラストレーション（Frustration）": int(st.session_state[K["フラストレーション（Frustration）"]]),
            "体調サイン": st.session_state[K["体調サイン"]],
            "取り組んだこと": st.session_state[K["取り組んだこと"]],
            "気づいたこと": st.session_state[K["気づいたこと"]],
            "アドバイス": st.session_state[K["アドバイス"]],
        }
        df = pd.DataFrame([record])
        save_to_google_sheets(df, "care-log", "2025")
        st.success("保存しました！")

def restore_today():
    rec = load_today_record("care-log", "2025")  # utils.load_today_record を呼ぶ
    if not rec:
        st.info("本日のデータはシートに見つかりませんでした。")
        return

    # 列名 → セッションキー
    mapping = {
        "就寝時刻": K["就寝時刻"],
        "起床時刻": K["起床時刻"],
        "精神的要求（Mental Demand）": K["精神的要求（Mental Demand）"],
        "身体的要求（Physical Demand）": K["身体的要求（Physical Demand）"],
        "時間的要求（Temporal Demand）": K["時間的要求（Temporal Demand）"],
        "努力度（Effort）": K["努力度（Effort）"],
        "成果満足度（Performance）": K["成果満足度（Performance）"],
        "フラストレーション（Frustration）": K["フラストレーション（Frustration）"],
        "体調サイン": K["体調サイン"],
        "取り組んだこと": K["取り組んだこと"],
        "気づいたこと": K["気づいたこと"],
        "アドバイス": K["アドバイス"],
    }

    # 期待型を指定（ここが肝）
    casters = {
        K["就寝時刻"]: _to_time,
        K["起床時刻"]: _to_time,
        K["精神的要求（Mental Demand）"]: _to_int_0_10,
        K["身体的要求（Physical Demand）"]: _to_int_0_10,
        K["時間的要求（Temporal Demand）"]: _to_int_0_10,
        K["努力度（Effort）"]: _to_int_0_10,
        K["成果満足度（Performance）"]: _to_int_0_10,
        K["フラストレーション（Frustration）"]: _to_int_0_10,
        K["体調サイン"]: _to_str,
        K["取り組んだこと"]: _to_str,
        K["気づいたこと"]: _to_str,
        K["アドバイス"]: _to_str,
    }

    # 値を型変換してから session_state に入れる
    updated = {}
    for col, key in mapping.items():
        if col not in rec:
            continue
        cast = casters.get(key, lambda x: x)
        val = cast(rec[col])
        # 型が合わない/変換失敗(None)はスキップして安全側に
        if val is not None:
            updated[key] = val

    # まとめて更新してから rerun
    st.session_state.update(updated)
    st.success("本日のデータを復元しました。")
    st.rerun()