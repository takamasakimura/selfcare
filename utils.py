# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound
from gspread.utils import rowcol_to_a1
from datetime import datetime, date, time as _time
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

EXPECTED_HEADERS = [
    "日付","就寝時刻","起床時刻","睡眠時間",
    "精神的要求（Mental Demand）","身体的要求（Physical Demand）","時間的要求（Temporal Demand）",
    "努力度（Effort）","成果満足度（Performance）","フラストレーション（Frustration）",
    "体調サイン","取り組んだこと","ストレッサー","シノアのコメント","桂花のコメント",
]

@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    info = st.secrets.get("gcp_service_account")
    if not info:
        raise RuntimeError("Secretsに gcp_service_account がありません。")
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def _force_header(ws):
    ws.resize(rows=2, cols=len(EXPECTED_HEADERS))
    ws.update("A1", [EXPECTED_HEADERS])

def _ensure_ws(sh, title):
    try:
        ws = sh.worksheet(title)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=len(EXPECTED_HEADERS))
        _force_header(ws); return ws
    if ws.row_values(1) != EXPECTED_HEADERS:
        _force_header(ws)
    return ws

def get_sheet(spreadsheet_name="care-log", worksheet_name=None):
    client = get_gspread_client()
    sh = client.open(spreadsheet_name)
    if worksheet_name is None:
        worksheet_name = str(datetime.now(JST).year)
    return _ensure_ws(sh, worksheet_name)

def hhmm_to_minutes(s):
    if not s or not isinstance(s, str): return None
    try:
        h, m = s.strip().split(":")[:2]
        return (int(h)%24)*60 + (int(m)%60)
    except Exception: return None

def minutes_to_hhmm(m):
    if m is None: return ""
    m = int(m)%1440; h, mm = divmod(m, 60); return f"{h:02d}:{mm:02d}"

def signed_circ_diff_minutes(actual_min, baseline_min):
    if actual_min is None: return None
    d = (actual_min - baseline_min) % 1440
    if d >= 720: d -= 1440
    return d

def calculate_sleep_duration(sleep_time: _time, wake_time: _time) -> float:
    if not isinstance(sleep_time, _time) or not isinstance(wake_time, _time): return 0.0
    s = sleep_time.hour*60 + sleep_time.minute
    w = wake_time.hour*60 + wake_time.minute
    return round(((w - s) % 1440) / 60.0, 2)

@st.cache_data(show_spinner=False)
def load_data(spreadsheet_name="care-log", worksheet_name=None):
    ws = get_sheet(spreadsheet_name, worksheet_name)
    recs = ws.get_all_records()
    df = pd.DataFrame(recs)
    if df.empty: df = pd.DataFrame(columns=EXPECTED_HEADERS)
    for c in EXPECTED_HEADERS:
        if c not in df.columns: df[c] = ""
    if "日付" in df.columns:
        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    return df

def save_to_google_sheets(df, spreadsheet_name="care-log", worksheet_name=None):
    if df is None or df.empty: return
    ws = get_sheet(spreadsheet_name, worksheet_name)
    for c in EXPECTED_HEADERS:
        if c not in df.columns: df[c] = ""
    df = df[EXPECTED_HEADERS]
    def norm(col, v):
        if col == "日付":
            try: return pd.to_datetime(v).date().isoformat()
            except Exception: return ""
        if col in ("就寝時刻","起床時刻"):
            if isinstance(v, str): return v
            if isinstance(v, _time): return f"{v.hour:02d}:{v.minute:02d}"
            return ""
        return "" if v is None else v
    values = [[norm(c, v) for c, v in zip(df.columns, row)] for row in df.itertuples(index=False, name=None)]
    ws.append_rows(values, value_input_option="USER_ENTERED")

def load_today_record(spreadsheet_name="care-log", worksheet_name=None):
    df = load_data(spreadsheet_name, worksheet_name)
    if df.empty: return None
    today = datetime.now(JST).date()
    dff = df[df["日付"].dt.date == today]
    if dff.empty: return None
    return dff.iloc[-1].to_dict()

def require_passcode(secret_key="APP_PASSCODE", page_name="page"):
    want = st.secrets.get(secret_key)
    if not want: return True
    ok_key = f"auth_ok_{page_name}"
    if st.session_state.get(ok_key): return True
    with st.sidebar:
        st.markdown("### 🔒 認証")
        code = st.text_input("パスコード", type="password")
        if st.button("Unlock"):
            if code == want:
                st.session_state[ok_key] = True
                st.rerun()
            else:
                st.error("パスコードが違います")
    st.stop()
