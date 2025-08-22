import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import base64
import gspread
from google.oauth2.service_account import Credentials

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

def calculate_sleep_duration(bed_time_str: str, wake_time_str: str) -> float:
    """
    時刻文字列（例: "23:30", "06:15"）から睡眠時間（時間）を計算する。
    翌日にまたがる睡眠にも対応。
    """
    try:
        bed_time = datetime.strptime(bed_time_str, "%H:%M")
        wake_time = datetime.strptime(wake_time_str, "%H:%M")

        if wake_time <= bed_time:
            wake_time += timedelta(days=1)

        duration = wake_time - bed_time
        return round(duration.total_seconds() / 3600, 2)
    except Exception:
        return 0.0

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
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)

    sheet = client.open(spreadsheet_name).worksheet(worksheet_name)
    existing_data = sheet.get_all_records()
    existing_df = pd.DataFrame(existing_data)

    if "日付" in existing_df.columns:
        existing_df["日付"] = pd.to_datetime(existing_df["日付"])

    new_row = df.iloc[0]
    new_date = pd.to_datetime(new_row["日付"])

    match_index = existing_df[existing_df["日付"] == new_date].index

    if len(match_index) > 0:
        row_number = match_index[0] + 2
        sheet.delete_rows(row_number)
        sheet.insert_rows([new_row.tolist()], row_number)
    else:
        sheet.append_row(new_row.tolist())

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