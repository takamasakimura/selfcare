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
import re  # ← 追加

JST = ZoneInfo("Asia/Tokyo")

def _to_date_any(v):
    """Google Sheets由来の '日付' を最大公約数で date に正規化"""
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.date()
    if isinstance(v, date):
        return v
    # シリアル値（1899-12-30起点）
    if isinstance(v, (int, float)) and not pd.isna(v):
        try:
            ts = pd.Timestamp("1899-12-30") + pd.to_timedelta(float(v), unit="D")
            return ts.date()
        except Exception:
            pass
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        m = re.match(r"^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*$", s)
        if m:
            s = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        try:
            return pd.to_datetime(s, errors="raise").date()
        except Exception:
            try:
                return pd.to_datetime(s.split()[0], errors="raise").date()
            except Exception:
                return None
    return None

# --- 想定ヘッダー定義 ---
EXPECTED_HEADERS = [
    "日付","就寝時刻","起床時刻","睡眠時間",
    "精神的要求（Mental Demand）","身体的要求（Physical Demand）","時間的要求（Temporal Demand）",
    "努力度（Effort）","成果満足度（Performance）","フラストレーション（Frustration）",
    "体調サイン","取り組んだこと","ストレッサー",
    "シノアのコメント","桂花のコメント",
]

# --- Google Sheets連携 ---
@st.cache_resource
def get_google_sheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("care-log").worksheet("2025")
    return sheet

def calculate_sleep_duration(bed_time, wake_time) -> float:
    """
    datetime.time または "HH:MM" 文字列を受け取り、睡眠時間を計算する。
    翌日にまたがる睡眠にも対応。
    """
    try:
        # 型をそろえる
        if isinstance(bed_time, str):
            bed_time = datetime.strptime(bed_time, "%H:%M").time()
        if isinstance(wake_time, str):
            wake_time = datetime.strptime(wake_time, "%H:%M").time()

        dt_today = datetime.today()
        b = datetime.combine(dt_today, bed_time)
        w = datetime.combine(dt_today, wake_time)
        if w <= b:
            w += timedelta(days=1)

        return round((w - b).seconds / 3600, 2)
    except Exception:
        return 0.0

def load_data():
    sheet = get_google_sheet()
    validate_headers(sheet, EXPECTED_HEADERS)  # 追加：読み込み時に検証
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

def get_existing_data_row(sheet):
    today = datetime.now().date()  # datetime.date オブジェクト
    all_data = sheet.get_all_records()
    for row in all_data:
        try:
            row_date = pd.to_datetime(row.get("日付", ""), errors="coerce").date()
        except Exception:
            continue
        if row_date == today:
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

def load_tlx_guide():
    df = pd.read_csv("nasa_tlx_guide.csv")  # 列: item,label,text など想定
    # 列名が違う場合はここを合わせてください。例: '項目','説明'
    # return {行["項目"]: 行["説明"] for _, 行 in df.iterrows()}
    # ここでは 'item' と 'text' を想定：
    return {row["item"]: str(row["text"]) for _, row in df.iterrows()}

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

def _force_header(sheet):
    sheet.resize(rows=1000, cols=len(EXPECTED_HEADERS))
    sheet.update("A1", [EXPECTED_HEADERS], value_input_option="USER_ENTERED")

def _safe_get_all_records(sheet):
    try:
        return sheet.get_all_records(default_blank="")
    except Exception:
        # ヘッダー不正などで落ちたら矯正して空として扱う
        _force_header(sheet)
        return []

def save_to_google_sheets(df, spreadsheet_name: str, worksheet_name: str):
    """
    1行の DataFrame を Google Sheets に Upsert（同日付があれば上書き、無ければ追記）。
    - ヘッダー（1行目）は常に新スキーマに強制整備
    - get_all_records() は例外安全で呼ぶ
    - 期待列順に並べて書き込む
    """
    # --- 依存を関数内でimport（他所の命名衝突を避ける） ---
    import re
    import numpy as np
    import pandas as pd
    import streamlit as st
    from datetime import datetime, date, time
    import gspread
    from gspread.exceptions import WorksheetNotFound
    from google.oauth2.service_account import Credentials

    # --- 期待ヘッダー（新スキーマ） ---
    EXPECTED_HEADERS = [
        "日付", "就寝時刻", "起床時刻", "睡眠時間",
        "精神的要求（Mental Demand）", "身体的要求（Physical Demand）", "時間的要求（Temporal Demand）",
        "努力度（Effort）", "成果満足度（Performance）", "フラストレーション（Frustration）",
        "体調サイン", "取り組んだこと", "ストレッサー",
        "シノアのコメント", "桂花のコメント",
    ]

    # --- 早期バリデーション ---
    if df is None or df.empty:
        st.warning("保存対象のDataFrameが空です。処理をスキップしました。")
        return
    if "日付" not in df.columns:
        st.error("DataFrameに『日付』列がありません。")
        return

    # --- 小さなユーティリティ ---
    def _normalize_row(vals):
        out = []
        for v in vals:
            s = str(v)
            s = s.replace("\u3000", " ").replace("　", " ")
            s = s.replace("（", "(").replace("）", ")")
            s = re.sub(r"\s+", " ", s).strip()
            out.append(s)
        return out

    def _force_header(sheet):
        sheet.resize(rows=1000, cols=len(EXPECTED_HEADERS))
        sheet.update("A1", [EXPECTED_HEADERS], value_input_option="USER_ENTERED")

    def _safe_get_all_records(sheet):
        try:
            return sheet.get_all_records(default_blank="")
        except Exception:
            _force_header(sheet)
            return []

    def _to_date_scalar(v):
        if isinstance(v, (datetime, pd.Timestamp)):
            return v.date()
        if isinstance(v, date):
            return v
        try:
            return pd.to_datetime(v, errors="coerce").date()
        except Exception:
            return None

    def _to_jsonable(v):
        if v is None:
            return ""
        if isinstance(v, (pd.Timestamp, datetime, date, time)):
            return str(v)
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return ""
        if isinstance(v, (np.integer, np.floating)):
            return v.item()
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
        return v if isinstance(v, (str, int, float, bool)) else str(v)

    # --- 認証（Secrets: gcp_service_account を使用） ---
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    except KeyError:
        st.error("Secrets に gcp_service_account がありません。Settings → Secrets を確認してください。")
        return
    client = gspread.authorize(creds)

    # --- Spreadsheet / Worksheet を取得（なければ作成） ---
    sh = client.open(spreadsheet_name)
    try:
        sheet = sh.worksheet(worksheet_name)
    except WorksheetNotFound:
        sheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(EXPECTED_HEADERS))
        _force_header(sheet)

    # --- 読む前に必ずヘッダーを矯正 ---
    values = sheet.get_all_values()
    if not values or not any(str(c).strip() for c in values[0]):
        _force_header(sheet)
        existing_records = []
    else:
        header_now = _normalize_row(values[0])
        header_exp = _normalize_row(EXPECTED_HEADERS)
        if header_now != header_exp:
            _force_header(sheet)
            existing_records = []
        else:
            existing_records = _safe_get_all_records(sheet)

    existing_df = pd.DataFrame(existing_records)
    if existing_df.empty:
        existing_df = pd.DataFrame(columns=EXPECTED_HEADERS)
    else:
        for c in EXPECTED_HEADERS:
            if c not in existing_df.columns:
                existing_df[c] = ""

    # --- 新規行（dfの先頭行）を準備 ---
    new_row = df.iloc[0].copy()

    # 日付で Upsert 対象の行番号を決める
    new_date = _to_date_scalar(new_row.get("日付"))
    if new_date is None:
        st.error("『日付』の解釈に失敗しました（yyyy-mm-dd 等）。")
        return

    if not existing_df.empty and "日付" in existing_df.columns:
        existing_df["日付"] = pd.to_datetime(existing_df["日付"], errors="coerce").dt.date
        match_idx_list = existing_df.index[existing_df["日付"] == new_date].tolist()
    else:
        match_idx_list = []

    # ヘッダー順に値を並べ替え
    ordered = [_to_jsonable(new_row.get(col, "")) for col in EXPECTED_HEADERS]

    # --- 上書き or 追記 ---
    if match_idx_list:
        # 上書き：ヘッダーが1行目なので +2 でシート行番号
        row_number = match_idx_list[0] + 2
        # 'A' から必要列数分の範囲を作る（A〜）
        # 例：15列なら 'O' まで
        start_col = 1
        end_col = len(EXPECTED_HEADERS)

        # 簡易的な列番号→列名（A1表記）変換
        def _col_to_a1(cn: int) -> str:
            s = ""
            while cn > 0:
                cn, r = divmod(cn - 1, 26)
                s = chr(65 + r) + s
            return s

        rng = f"A{row_number}:{_col_to_a1(end_col)}{row_number}"
        sheet.update(rng, [ordered], value_input_option="USER_ENTERED")
    else:
        # 追記
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

    try:
        sh = client.open(spreadsheet_name)
        sheet = sh.worksheet(worksheet_name)
    except WorksheetNotFound:
        return None

    records = sheet.get_all_records()  # [{列:値}, ...]
    if not records:
        return None

    today = datetime.now(JST).date()

    # 末尾（新しい方）から見て最初に一致した行を返す
    for row in reversed(records):
        d = _to_date_any(row.get("日付"))
        if d == today:
            return row
    return None
