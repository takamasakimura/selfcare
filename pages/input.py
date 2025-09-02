from datetime import datetime, timedelta, timezone, time as _time
import streamlit as st
import pandas as pd
from utils import calculate_sleep_duration, save_to_google_sheets, load_today_record  # ← 追加

# ==== Debug/maintenance tools ====
st.sidebar.markdown("### 🔧 メンテ")
if st.sidebar.button("キャッシュ全クリア"): 
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    for k in list(st.session_state.keys()):
        try:
            del st.session_state[k]
        except Exception:
            pass
    st.success("Cleared. 再実行します")
    st.experimental_rerun()
st.write("input.py loaded:", __file__)


@st.cache_data
def load_tlx_guide():
    df = pd.read_csv("nasa_tlx_guide.csv")
    # 「スコア」列を見つける（念のため前後空白対応）
    score_col = next((c for c in df.columns if "スコア" in str(c)), None)
    if not score_col:
        raise ValueError(f"CSVに『スコア』列が見つかりません: {list(df.columns)}")

    guide = {}
    # 各TLX列をたどって、スコア→説明 のリストを作る
    for col in df.columns:
        if col == score_col:
            continue
        block = []
        # 当該列が NaN の行は無視（末尾のノイズ行も自然に除外される）
        for _, row in df[[score_col, col]].dropna(subset=[col]).iterrows():
            score = row[score_col]
            try:
                score = int(score)
            except Exception:
                # スコアが数字でない場合はそのまま
                pass
            text = str(row[col]).strip()
            if text:
                block.append(f"- **{score}**: {text}")

        # 一覧をMarkdown化（空なら登録しない）
        if block:
            md = "スコアごとの目安：\n\n" + "\n".join(block)
            guide[col] = md

    return guide

GUIDE = load_tlx_guide()

def g(name: str, default: str = ""):
    # ラベル一致で引く（必要なら正規化もここで噛ませられる）
    return GUIDE.get(name, default)

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
    "ストレッサー": "stressor",                # ← 置換
    "シノアのコメント": "comment_shinoa",        # ← 追加
    "桂花のコメント": "comment_keifa",           # ← 追加
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
    K["ストレッサー"]: str,               # ← 追加
    K["シノアのコメント"]: str,           # ← 追加
    K["桂花のコメント"]: str,              # ← 追加
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
for _k in ("体調サイン","取り組んだこと","ストレッサー","シノアのコメント","桂花のコメント"):
    _init(K[_k], "")

# ========= 基本 =========
st.title("セルフケア入力")
JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
st.write(f"今日の日付：{today}")

def slider_with_info(label, key, default, guide_text: str):
    gt = (guide_text or "").strip()  # 空対策
    c1, c2 = st.columns([1, 0.08])
    with c1:
        val = st.slider(label, 0, 10, default, key=key, help=gt or None)
    with c2:
        st.markdown(" ")  # 縦位置揃え
        if gt:
            if hasattr(st, "popover"):
                with st.popover("ℹ️"):
                    st.markdown(gt)
            else:
                st.caption("ℹ️ " + gt)
        else:
            # 中身が無いことを明示
            st.caption("ℹ️ ガイド未設定")
    return val

# ========= 入力UI（key を付けるのが肝）=========
col1, col2 = st.columns(2)
with col1:
    st.time_input("就寝時刻", key=K["就寝時刻"])
with col2:
    st.time_input("起床時刻", key=K["起床時刻"])

st.subheader("NASA-TLX評価（0〜10）")
mental = slider_with_info(
    "精神的要求（Mental Demand）",
    K["精神的要求（Mental Demand）"],
    st.session_state.get(K["精神的要求（Mental Demand）"], 5),
    g("精神的要求（Mental Demand）"),
)

physical = slider_with_info(
    "身体的要求（Physical Demand）",
    K["身体的要求（Physical Demand）"],
    st.session_state.get(K["身体的要求（Physical Demand）"], 5),
    g("身体的要求（Physical Demand）"),
)

temporal = slider_with_info(
    "時間的要求（Temporal Demand）",
    K["時間的要求（Temporal Demand）"],
    st.session_state.get(K["時間的要求（Temporal Demand）"], 5),
    g("時間的要求（Temporal Demand）"),
)

effort = slider_with_info(
    "努力度（Effort）",
    K["努力度（Effort）"],
    st.session_state.get(K["努力度（Effort）"], 5),
    g("努力度（Effort）"),
)

performance = slider_with_info(
    "成果満足度（Performance）",
    K["成果満足度（Performance）"],
    st.session_state.get(K["成果満足度（Performance）"], 5),
    g("成果満足度（Performance）"),
)

frustration = slider_with_info(
    "フラストレーション（Frustration）",
    K["フラストレーション（Frustration）"],
    st.session_state.get(K["フラストレーション（Frustration）"], 5),
    g("フラストレーション（Frustration）"),
)

st.subheader("体調サイン・タグ付きメモ")
st.text_area("例：＜タグ：頭痛＞ 作業に集中できなかった", key=K["体調サイン"])

st.subheader("内省ログ")
st.text_area("取り組んだこと", key=K["取り組んだこと"])
st.text_area("ストレッサー", key=K["ストレッサー"])

st.subheader("コメント")
st.text_area("コメント", key=K["シノアのコメント"])
st.text_area("コメント2", key=K["桂花のコメント"])

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
    """列名を正規化し、テキスト＋スライダー＋時刻（time_input）を復元する"""
    rec_raw = load_today_record("care-log", "2025")
    if not isinstance(rec_raw, dict) or not rec_raw:
        st.info("本日のデータはシートに見つかりませんでした。")
        st.expander("debug: load_today_record result").write(rec_raw)
        return

    W = {
        # テキスト
        "体調サイン": {"key": K["体調サイン"], "kind": "text"},
        "取り組んだこと": {"key": K["取り組んだこと"], "kind": "text"},
        "ストレッサー": {"key": K["ストレッサー"], "kind": "text"},
        "シノアのコメント": {"key": K["シノアのコメント"], "kind": "text"},
        "桂花のコメント": {"key": K["桂花のコメント"], "kind": "text"},

        # スライダー（0〜10）
        "精神的要求（Mental Demand）": {"key": K["精神的要求（Mental Demand）"], "kind": "slider", "min": 0, "max": 10},
        "身体的要求（Physical Demand）": {"key": K["身体的要求（Physical Demand）"], "kind": "slider", "min": 0, "max": 10},
        "時間的要求（Temporal Demand）": {"key": K["時間的要求（Temporal Demand）"], "kind": "slider", "min": 0, "max": 10},
        "努力度（Effort）": {"key": K["努力度（Effort）"], "kind": "slider", "min": 0, "max": 10},
        "成果満足度（Performance）": {"key": K["成果満足度（Performance）"], "kind": "slider", "min": 0, "max": 10},
        "フラストレーション（Frustration）": {"key": K["フラストレーション（Frustration）"], "kind": "slider", "min": 0,
                                            "max": 10},

        # 時刻（time_input）
        "就寝時刻": {"key": K["就寝時刻"], "kind": "time"},
        "起床時刻": {"key": K["起床時刻"], "kind": "time"},

        # ※「睡眠時間」は算出列なので触らない
    }

    # 1) そもそもレコードが無い（= 今日の行が無い）時は即終了
    if not isinstance(rec_raw, dict) or not rec_raw:
        st.info("本日のデータはシートに見つかりませんでした。")
        # デバッグ表示（必要ならコメントアウト）
        st.expander("debug: load_today_record result").write(rec_raw)
        return

    # 2) 列名を正規化（空白や全角括弧の差異を吸収）
    def _norm(s: str) -> str:
        if not isinstance(s, str): return s
        s = s.replace("\u3000", " ").replace("　", " ")
        s = s.replace("（", "(").replace("）", ")")
        return "".join(s.split())

    expected = list(W.keys()) + ["日付", "睡眠時間"]
    alias = {_norm(name): name for name in expected}

    # 正式名へ写し替え
    rec = {}
    for k, v in rec_raw.items():
        nk = alias.get(_norm(k))
        if nk:
            rec[nk] = v

    st.expander("debug: keys mapping").write({
        "raw_keys": list(rec_raw.keys()),
        "mapped_keys": list(rec.keys()),
    })

    updated_any = False
    for col, spec in W.items():
        if col not in rec:
            continue
        key, kind = spec["key"], spec["kind"]
        cur = st.session_state.get(key, None)
        try:
            if kind == "text":
                val = _to_str(rec[col])
                if isinstance(cur, str):
                    _safe_set_state(key, val); updated_any = True

            elif kind == "slider":
                val = _to_i010(rec[col])
                if (val is not None) and isinstance(cur, int):
                    # 範囲で丸める
                    lo, hi = spec.get("min", 0), spec.get("max", 10)
                    val = max(lo, min(hi, val))
                    _safe_set_state(key, val); updated_any = True

            elif kind == "time":
                val = _to_time(rec[col])
                if (val is not None) and isinstance(cur, _time):
                    _safe_set_state(key, val); updated_any = True

        except Exception as e:
            st.toast(f"復元スキップ: {col} → {e}")

    if updated_any:
        st.success("本日のデータを復元しました。")
        # on_click コールバックなら rerun 不要。ifで呼ぶ方式なら st.rerun() を付けてOK
    else:
        st.info("復元対象に一致する項目がありませんでした。")

# ========= ボタン（横並び）=========
colA, colB = st.columns(2)
with colA:
    st.button("本日のデータを復元", on_click=restore_today)

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
            "ストレッサー": st.session_state[K["ストレッサー"]],
            "シノアのコメント": st.session_state[K["シノアのコメント"]],
            "桂花のコメント": st.session_state[K["桂花のコメント"]],
        }
        df = pd.DataFrame([record])
        save_to_google_sheets(df, "care-log", "2025")
        st.success("保存しました！")