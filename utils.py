import streamlit as st
import pandas as pd
import base64
import gspread
from google.oauth2.service_account import Credentials
from zoneinfo import ZoneInfo
import numpy as np
from gspread.exceptions import WorksheetNotFound
from gspread.utils import rowcol_to_a1
from datetime import date, datetime, time, timedelta

JST = ZoneInfo("Asia/Tokyo")

# --- 想定ヘッダー定義 ---
EXPECTED_HEADERS = [
    "日付",
    "就寝時刻",
    "起床時刻",
    "睡眠時間",
    "精神的要求（Mental Demand）",
    "身体的要求（Physical Demand）",
    "時間的要求（Temporal Demand）",
    "努力度（Effort）",
    "成果満足度（Performance）",
    "フラストレーション（Frustration）",
    "体調サイン",
    "取り組んだこと",
    "気づいたこと",
    "アドバイス"
]


# --- Google Sheets連携 ---
@st.cache_resource
def get_google_sheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("care-log").worksheet("2025")
    return sheet

def calculate_sleep_duration(bed_time_val, wake_time_val) -> float:
    """
    "23:30" のような文字列 or datetime.time を受け取り、睡眠時間(h)を返す
    """
    from datetime import time as _time

    def _to_time(v):
        if isinstance(v, _time):
            return v
        if isinstance(v, str) and v:
            return datetime.strptime(v, "%H:%M").time()
        return None

    bed_time = _to_time(bed_time_val)
    wake_time = _to_time(wake_time_val)
    if not bed_time or not wake_time:
        return 0.0

    today = datetime.today().date()
    b = datetime.combine(today, bed_time)
    w = datetime.combine(today, wake_time)
    if w <= b:
        w += timedelta(days=1)
    return round((w - b).total_seconds() / 3600, 2)

def load_data():
    sheet = get_google_sheet()
    validate_headers(sheet, EXPECTED_HEADERS)  # 追加：読み込み時に検証
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

def get_existing_data_row(sheet):
    today = datetime.today().strftime("%Y-%m-%d")
    headers = sheet.row_values(1)
    all_data = sheet.get_all_records()
    for row in all_data:
        if str(row.get("日付", "")) == today:
            return row
    return None

def validate_headers(sheet, expected_headers, header_row=1):
    sheet_headers = sheet.row_values(header_row)
    if sheet_headers[:len(expected_headers)] != expected_headers:
        raise ValueError(
            f"Google Sheetsのヘッダーと定義が一致しません。\n"
            f"想定: {expected_headers}\n取得: {sheet_headers}"
        )

# --- NASA-TLX 関連 ---
@st.cache_data
def load_guide_column(item):
    df = pd.read_csv("nasa_tlx_guide.csv", usecols=["スコア", item])
    return df.dropna()

def render_nasa_tlx_slider(label, default):
    with st.expander(f"{label}（説明を見る）"):
        st.markdown(label)  # 説明は仮置き
        guide = load_guide_column(label)
        st.dataframe(guide, height=200)
    return st.slider(f"{label}（0〜10）", 0, 10, default, key=f"nasa_{label}")

# --- 睡眠時間関連 ---
def calc_sleep_hours(sleep, wake):
    dt_today = datetime.today()
    sleep_dt = datetime.combine(dt_today, sleep)
    wake_dt = datetime.combine(dt_today, wake)
    if wake_dt <= sleep_dt:
        wake_dt += timedelta(days=1)
    return round((wake_dt - sleep_dt).seconds / 3600, 2)

def parse_time(s):
    try:
        return datetime.strptime(s, "%H:%M").time() if s else None
    except:
        return None

def save_to_google_sheets(df: pd.DataFrame, spreadsheet_name: str, worksheet_name: str = "2025"):
    """
    指定されたスプレッドシートとシートに DataFrame を保存する。
    同じ日付のデータがあれば上書き、なければ追加（Upsert）。
    """

    # --- 0) 事前チェック ---
    if df is None or df.empty:
        st.warning("保存対象のデータフレームが空です。処理をスキップしました。")
        return
    if "日付" not in df.columns:
        st.error("DataFrame に『日付』列がありません。")
        return

    # --- 1) 認証（Secretsから） ---
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    except KeyError:
        st.error("Secrets に gcp_service_account が設定されていません。Settings → Secrets を確認してください。")
        st.stop()
    client = gspread.authorize(creds)

    # --- 2) ワークシート取得（無ければ作成・ヘッダー初期化） ---
    sh = client.open(spreadsheet_name)
    try:
        sheet = sh.worksheet(worksheet_name)
    except WorksheetNotFound:
        sheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=max(26, len(df.columns)))
        sheet.update("A1", [list(df.columns)], value_input_option="USER_ENTERED")

    # シートのヘッダー
    header = sheet.row_values(1)
    if not header:
        header = list(df.columns)
        sheet.update("A1", [header], value_input_option="USER_ENTERED")

    # --- 3) 既存レコード取得（辞書→DataFrame） ---
    records = sheet.get_all_records()  # 空なら []
    existing_df = pd.DataFrame(records)
    if existing_df.empty:
        existing_df = pd.DataFrame(columns=header)

    # --- 4) 新規行（1行想定）を取り出し ---
    new_row = df.iloc[0].copy()

    # --- 5) 日付を date 粒度で正規化し、Upsert対象を特定 ---
    def _to_date_scalar(v):
        if isinstance(v, (datetime, pd.Timestamp)):
            return v.date()
        if isinstance(v, date):
            return v
        # 文字列や他型は to_datetime で解釈
        try:
            return pd.to_datetime(v, errors="coerce").date()
        except Exception:
            return None

    new_date = _to_date_scalar(new_row.get("日付"))
    if new_date is None:
        st.error("『日付』の解釈に失敗しました。yyyy-mm-dd 形式などで指定してください。")
        return

    if "日付" in existing_df.columns and not existing_df.empty:
        existing_df["日付"] = pd.to_datetime(existing_df["日付"], errors="coerce").dt.date
        match_idx_list = existing_df.index[existing_df["日付"] == new_date].tolist()
    else:
        match_idx_list = []

    row_number = (match_idx_list[0] + 2) if match_idx_list else None  # ヘッダー1行ぶん+1

    # --- 6) JSON化できる値に正規化 ---
    def _to_jsonable(v):
        if v is None:
            return ""
        if isinstance(v, (pd.Timestamp, datetime, date, time)):
            return str(v)
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return ""
        if isinstance(v, (np.integer, np.floating)):
            return v.item()
        # NaN/NaT
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
        return v if isinstance(v, (str, int, float, bool)) else str(v)

    # シートのヘッダー順に並べ替え＆正規化
    ordered = [_to_jsonable(new_row.get(col, "")) for col in header]

    # --- 7) 上書き or 追加 ---
    if row_number:
        end_col = rowcol_to_a1(1, len(header))[:-1]  # 'D1' -> 'D'
        rng = f"A{row_number}:{end_col}{row_number}"
        sheet.update(rng, [ordered], value_input_option="USER_ENTERED")
    else:
        sheet.append_row(ordered, value_input_option="USER_ENTERED")

# --- アドバイス生成（仮） ---
def generate_advice(scores, nasa_scores):
    return "（アドバイス生成ロジックは後で定義）"

# --- GIF表示 ---
def display_base64_gif(file_path, width=600):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            base64_gif = f.read().replace("\n", "")
        st.markdown(
            f"""<img src="data:image/gif;base64,{base64_gif}" width="{width}" />""",
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.error("GIFの表示に失敗しました")
        st.exception(e)

def encode_gif_to_base64(gif_path, output_txt_path):
    try:
        with open(gif_path, "rb") as gif_file:
            encoded = base64.b64encode(gif_file.read()).decode("utf-8")
        with open(output_txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(encoded)
        print(f"✅ {output_txt_path} にエンコード済みデータを保存しました")
    except Exception as e:
        print("❌ Base64変換失敗:")
        print(e)

def _coerce_time_str_to_time(v):
    if isinstance(v, time):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.strptime(v, "%H:%M").time()
        except Exception:
            pass
    return None

def _coerce_num(v):
    if v is None: return None
    try:
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, str) and v.strip() == "":
            return None
        return float(v) if "." in str(v) else int(v)
    except Exception:
        return None

def load_today_record(spreadsheet_name: str, worksheet_name: str = "2025") -> dict | None:
    """JSTの今日に一致する最新行を dict で返す（なければ None）"""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)

    sh = client.open(spreadsheet_name)
    try:
        sheet = sh.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return None

    records = sheet.get_all_records()
    if not records:
        return None

    df = pd.DataFrame(records)
    if "日付" not in df.columns:
        return None

    # 日付を正規化
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce").dt.date
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    hit = df[df["日付"] == today]
    if hit.empty:
        return None

    row = hit.iloc[-1].to_dict()

    # 型の調整
    def _coerce_time(v):
        if isinstance(v, time):
            return v
        if isinstance(v, str) and v:
            try:
                return datetime.strptime(v, "%H:%M").time()
            except Exception:
                return None
        return None

    row["就寝時刻"] = _coerce_time(row.get("就寝時刻"))
    row["起床時刻"] = _coerce_time(row.get("起床時刻"))

    # 数値化（NASA-TLX系）
    for col in [
        "精神的要求（Mental Demand）",
        "身体的要求（Physical Demand）",
        "時間的要求（Temporal Demand）",
        "努力度（Effort）",
        "成果満足度（Performance）",
        "フラストレーション（Frustration）",
    ]:
        try:
            row[col] = int(row[col]) if row[col] != "" else None
        except Exception:
            row[col] = None

    return row