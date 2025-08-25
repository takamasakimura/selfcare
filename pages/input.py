from datetime import datetime, timedelta, timezone, time as _time
import streamlit as st
import pandas as pd
from utils import calculate_sleep_duration, save_to_google_sheets, load_today_record  # ← 追加

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

# ★ここを追加：各セッションキーの“期待型”
EXPECT = {
    K["就寝時刻"]: _time,
    K["起床時刻"]: _time,
    K["精神的要求（Mental Demand）"]: int,
    K["身体的要求（Physical Demand）"]: int,
    K["時間的要求（Temporal Demand）"]: int,
    K["努力度（Effort）"]: int,
    K["成果満足度（Performance）"]: int,
    K["フラストレーション（Frustration）"]: int,
    K["体調サイン"]: str,
    K["取り組んだこと"]: str,
    K["気づいたこと"]: str,
    K["アドバイス"]: str,
}

# ========= 初期化（初回だけデフォルトを入れる）=========
def _init(k, v):
    if k not in st.session_state:
        st.session_state[k] = v

_init(K["就寝時刻"], datetime.strptime("23:00", "%H:%M").time())
_init(K["起床時刻"], datetime.strptime("07:00", "%H:%M").time())
for _k in ("精神的要求（Mental Demand）","身体的要求（Physical Demand）","時間的要求（Temporal Demand）",
           "努力度（Effort）","成果満足度（Performance）","フラストレーション（Frustration）"):
    _init(K[_k], 5)
for _k in ("体調サイン","取り組んだこと","気づいたこと","アドバイス"):
    _init(K[_k], "")

# ========= 基本 =========
st.title("セルフケア入力")
JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
st.write(f"今日の日付：{today}")

# ========= 入力UI（key を付けるのが肝）=========
col1, col2 = st.columns(2)
with col1:
    st.time_input("就寝時刻", key=K["就寝時刻"])
with col2:
    st.time_input("起床時刻", key=K["起床時刻"])

st.subheader("NASA-TLX評価（0〜10）")
st.slider("精神的要求（Mental Demand）", 0, 10, st.session_state[K["精神的要求（Mental Demand）"]], key=K["精神的要求（Mental Demand）"])
st.slider("身体的要求（Physical Demand）", 0, 10, st.session_state[K["身体的要求（Physical Demand）"]], key=K["身体的要求（Physical Demand）"])
st.slider("時間的要求（Temporal Demand）", 0, 10, st.session_state[K["時間的要求（Temporal Demand）"]], key=K["時間的要求（Temporal Demand）"])
st.slider("努力度（Effort）", 0, 10, st.session_state[K["努力度（Effort）"]], key=K["努力度（Effort）"])
st.slider("成果満足度（Performance）", 0, 10, st.session_state[K["成果満足度（Performance）"]], key=K["成果満足度（Performance）"])
st.slider("フラストレーション（Frustration）", 0, 10, st.session_state[K["フラストレーション（Frustration）"]], key=K["フラストレーション（Frustration）"])

st.subheader("体調サイン・タグ付きメモ")
st.text_area("例：＜タグ：頭痛＞ 作業に集中できなかった", key=K["体調サイン"])

st.subheader("内省ログ")
st.text_area("取り組んだこと", key=K["取り組んだこと"])
st.text_area("気づいたこと・感想", key=K["気づいたこと"])

st.subheader("GPTアドバイス（任意）")
st.text_area("GPTアドバイス（任意）", key=K["アドバイス"])

# ========= 計算表示 =========
def _calc_sleep():
    st_time = st.session_state[K["就寝時刻"]]
    wk_time = st.session_state[K["起床時刻"]]
    return calculate_sleep_duration(st_time, wk_time)

sleep_duration = _calc_sleep()
st.write(f"睡眠時間（推定）：{sleep_duration:.2f} 時間")

def _to_time(v):
    if isinstance(v, _time):
        return v
    if isinstance(v, str) and v.strip():
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(v.strip(), fmt).time()
            except ValueError:
                continue
    return None

def _to_i010(v):
    try:
        # None/NaN対策
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        n = int(float(v))
        return max(0, min(10, n))
    except Exception:
        return None

def _to_str(v):
    if v is None:
        return ""
    s = str(v)
    return s

def _cast_for_key(key, v):
    et = EXPECT.get(key)
    if et is _time:
        return _to_time(v)
    if et is int:
        return _to_i010(v)
    if et is str:
        return _to_str(v)
    return v

def _safe_set_state(key, val):
    # None はスキップ
    if val is None:
        st.toast(f"復元スキップ: {key}（値が None）")
        return

    # 既存の型（ウィジェットが期待する型）を取得
    cur = st.session_state.get(key, None)

    # 既存があれば、その型に合わせて再キャストを試みる
    if cur is not None and (type(cur) is not type(val)):
        val2 = _cast_for_key(key, val)  # 期待型へ寄せる
        if (val2 is None) or (type(cur) is not type(val2)):
            st.toast(f"復元スキップ: {key}（型不一致: have={type(cur).__name__}, got={type(val).__name__}）")
            return
        val = val2

    # ここで最終代入。エラー内容を拾って見える化
    try:
        st.session_state[key] = val
    except Exception as e:
        st.toast(f"復元エラー: {key} → {type(val).__name__} / {e}")

def restore_today():
    """スプレッドの列名を正規化して、テキスト項目のみ復元する"""
    rec_raw = load_today_record("care-log", "2025")
    if not rec_raw:
        st.info("本日のデータはシートに見つかりませんでした。")
        return

    # 1) 列名を正規化（空白除去・全角括弧→半角・全角空白→半角 など）
    def _norm(s: str) -> str:
        if not isinstance(s, str):
            return s
        s = s.replace("\u3000", " ")        # 全角スペース→半角
        s = s.replace("（", "(").replace("）", ")")
        s = s.replace("　", " ")            # 別の全角スペース
        return "".join(s.split())           # すべての空白を除去

    # 2) 期待する列名（あなたのヘッダーを“正”として用意）
    expected = [
        "日付","就寝時刻","起床時刻","睡眠時間",
        "精神的要求（Mental Demand）","身体的要求（Physical Demand）",
        "時間的要求（Temporal Demand）","努力度（Effort）",
        "成果満足度（Performance）","フラストレーション（Frustration）",
        "体調サイン","取り組んだこと","気づいたこと","アドバイス",
    ]
    # 正規化→正名 の対応辞書
    alias = {_norm(name): name for name in expected}

    # 3) 行のキーを“正名”へマッピング
    rec = {}
    for k, v in rec_raw.items():
        nk = alias.get(_norm(k))
        if nk:  # 期待に含まれる場合のみ採用
            rec[nk] = v

    # デバッグ用（必要なら一時的に表示）
    # st.expander("復元デバッグ").write({"raw_keys": list(rec_raw.keys()), "mapped_keys": list(rec.keys())})

    # 4) テキスト項目だけ復元（※算出列「睡眠時間」は触らない）
    text_mapping = {
        "体調サイン": K["体調サイン"],
        "取り組んだこと": K["取り組んだこと"],
        "気づいたこと": K["気づいたこと"],
        "アドバイス": K["アドバイス"],
    }

    def _to_str(v):
        if v is None: return ""
        try:
            # NaN 対策
            import math
            if isinstance(v, float) and math.isnan(v):
                return ""
        except Exception:
            pass
        return str(v)

    any_update = False
    for col, key in text_mapping.items():
        if col in rec:
            val = _to_str(rec[col])
            cur = st.session_state.get(key, "")
            if isinstance(cur, str):
                try:
                    st.session_state[key] = val
                    any_update = True
                except Exception as e:
                    st.toast(f"復元エラー: {key} → {e}")
            else:
                st.toast(f"復元スキップ: {key}（ウィジェット型が str ではない）")

    if any_update:
        st.success("テキスト項目だけ復元しました。")
        st.rerun()
    else:
        st.info("復元対象のテキスト項目が見つかりませんでした。")

# ========= ボタン（横並び）=========
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