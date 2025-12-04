# AttendanceHub_GSheets.py
# إدارة الغيابات للمكوّنين + Google Sheets backend (كيف MegaCRM)

import json
import time
import uuid
import urllib.parse
from datetime import datetime, date, timedelta
import os

import pandas as pd
import streamlit as st
import gspread
import gspread.exceptions as gse
from google.oauth2.service_account import Credentials

# ================== إعداد الصفحة ==================
st.set_page_config(page_title="AttendanceHub - Mega Formation", layout="wide")

st.markdown(
    """
    <div style='text-align:center'>
      <h1>🕒 AttendanceHub - إدارة الغيابات</h1>
      <p>متكوّنين، مواد، غيابات، تنبيهات 10٪ - مع Google Sheets</p>
    </div>
    <hr/>
    """,
    unsafe_allow_html=True,
)

# ================== إعداد Google Sheets ==================
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

def make_client_and_sheet_id():
    # 1) نخدم من Streamlit secrets (بيئة الكلاود)
    if "gcp_service_account" in st.secrets:
        try:
            sa = st.secrets["gcp_service_account"]
            sa_info = dict(sa)
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPE)
            client = gspread.authorize(creds)

            if "SPREADSHEET_ID" not in st.secrets:
                st.error("⚠️ المفتاح SPREADSHEET_ID مش موجود في secrets.\nزيدو في Streamlit secrets.")
                st.stop()

            sheet_id = st.secrets["SPREADSHEET_ID"]
            return client, sheet_id
        except Exception as e:
            st.error(f"⚠️ خطأ في gcp_service_account داخل secrets: {e}")
            st.stop()

    # 2) لو تخدم لوكال وتنجم تستعمل ملف service_account.json
    elif os.path.exists("service_account.json"):
        try:
            creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPE)
            client = gspread.authorize(creds)
            sheet_id = "PUT_YOUR_SHEET_ID_HERE"  # بدّلها لو تخدم لوكال
            return client, sheet_id
        except Exception as e:
            st.error(f"⚠️ خطأ في قراءة service_account.json: {e}")
            st.stop()

    # 3) لا secrets لا ملف ⇒ نوقف ونفسّر
    else:
        st.error(
            "❌ لا وجدنا لا gcp_service_account في Streamlit secrets لا ملف service_account.json.\n\n"
            "▶ في Streamlit Cloud: زيد gcp_service_account و SPREADSHEET_ID في صفحة secrets.\n"
            "▶ لو تخدم لوكال: حط ملف service_account.json في نفس فولدر AttendanceHub_GSheets.py."
        )
        st.stop()

# استدعاء الدالة
client, SPREADSHEET_ID = make_client_and_sheet_id()

TRAINEES_SHEET = "Trainees"
SUBJECTS_SHEET = "Subjects"
ABSENCES_SHEET = "Absences"

TRAINEES_COLS = [
    "id", "nom", "telephone", "tel_parent",
    "branche", "specialite", "date_debut", "actif"
]

SUBJECTS_COLS = [
    "id", "nom_matiere", "branche",
    "specialites",  # قائمة تخصّصات مفصولة بفاصلة
    "heures_totales", "heures_semaine"
]

ABSENCES_COLS = [
    "id", "trainee_id", "subject_id",
    "date", "heures_absence",
    "justifie", "commentaire"
]

# ============= Utils Sheets =============
def get_spreadsheet():
    if st.session_state.get("sh_id") == SPREADSHEET_ID and "sh_obj" in st.session_state:
        return st.session_state["sh_obj"]
    last_err = None
    for i in range(5):
        try:
            sh = client.open_by_key(SPREADSHEET_ID)
            st.session_state["sh_obj"] = sh
            st.session_state["sh_id"] = SPREADSHEET_ID
            return sh
        except gse.APIError as e:
            last_err = e
            time.sleep(0.5 * (2 ** i))
    st.error("❌ فشل في فتح Google Sheet (ممكن الكوتا تعدّت).")
    raise last_err

def ensure_ws(title: str, columns: list[str]):
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="2000", cols=str(max(len(columns), 8)))
        ws.update("1:1", [columns])
        return ws
    header = ws.row_values(1)
    if not header or header[:len(columns)] != columns:
        ws.update("1:1", [columns])
    return ws

def append_record(sheet_name: str, cols: list[str], rec: dict):
    ws = ensure_ws(sheet_name, cols)
    row = [str(rec.get(c, "")) for c in cols]
    ws.append_row(row)
    st.cache_data.clear()

def delete_record_by_id(sheet_name: str, cols: list[str], rec_id: str):
    ws = ensure_ws(sheet_name, cols)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return
    header = vals[0]
    if "id" in header:
        id_idx = header.index("id")
    else:
        id_idx = 0
    for i, r in enumerate(vals[1:], start=2):
        if len(r) > id_idx and r[id_idx] == rec_id:
            ws.delete_rows(i)
            st.cache_data.clear()
            break

def update_record_fields_by_id(sheet_name: str, cols: list[str], rec_id: str, updates: dict):
    ws = ensure_ws(sheet_name, cols)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return
    header = vals[0]
    if "id" not in header:
        return
    id_idx = header.index("id")
    row_idx = None
    for i, r in enumerate(vals[1:], start=2):
        if len(r) > id_idx and r[id_idx] == rec_id:
            row_idx = i
            break
    if not row_idx:
        return
    for field, value in updates.items():
        if field in header:
            col_idx = header.index(field) + 1
            ws.update_cell(row_idx, col_idx, str(value))
    st.cache_data.clear()

# ================== Helpers ==================
def normalize_phone(s: str) -> str:
    digits = "".join(c for c in str(s) if c.isdigit())
    if len(digits) == 8:
        return "216" + digits
    return digits

def wa_link(number: str, message: str) -> str:
    num = normalize_phone(number)
    if not num:
        return ""
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}"

def branch_password(branch: str) -> str:
    try:
        m = st.secrets["branch_passwords"]
        if "Menzel" in branch or branch == "MB":
            return str(m.get("MB", ""))
        if "Bizerte" in branch or branch == "BZ":
            return str(m.get("BZ", ""))
    except Exception:
        pass
    return ""

def as_float(x) -> float:
    try:
        return float(str(x).replace(",", ".").strip() or 0)
    except Exception:
        return 0.0

# ============= تحميل البيانات من Google Sheets =============
@st.cache_data(ttl=300)
def load_trainees():
    ws = ensure_ws(TRAINEES_SHEET, TRAINEES_COLS)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return pd.DataFrame(columns=TRAINEES_COLS)
    return pd.DataFrame(vals[1:], columns=vals[0])

@st.cache_data(ttl=300)
def load_subjects():
    ws = ensure_ws(SUBJECTS_SHEET, SUBJECTS_COLS)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return pd.DataFrame(columns=SUBJECTS_COLS)
    return pd.DataFrame(vals[1:], columns=vals[0])

@st.cache_data(ttl=300)
def load_absences():
    ws = ensure_ws(ABSENCES_SHEET, ABSENCES_COLS)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return pd.DataFrame(columns=ABSENCES_COLS)
    return pd.DataFrame(vals[1:], columns=vals[0])

# ================== Sidebar: اختيار الفرع + المودباس ==================
st.sidebar.markdown("## ⚙️ إعدادات الفرع")

branch = st.sidebar.selectbox("اختر الفرع", ["Menzel Bourguiba", "Bizerte"])

pw_need = branch_password(branch)
key_pw = f"branch_pw_ok::{branch}"

if pw_need:
    if key_pw not in st.session_state:
        st.session_state[key_pw] = False
    if not st.session_state[key_pw]:
        pw_try = st.sidebar.text_input("🔐 كلمة سرّ الفرع", type="password")
        if st.sidebar.button("دخول الفرع"):
            if pw_try == pw_need:
                st.session_state[key_pw] = True
                st.sidebar.success("تم الدخول ✅")
            else:
                st.sidebar.error("كلمة سرّ غير صحيحة ❌")
        st.stop()
else:
    st.sidebar.warning("⚠️ لم يتم ضبط كلمة المرور لهذا الفرع في secrets.branch_passwords")

st.sidebar.success(f"أنت الآن داخل فرع: **{branch}**")

tab1, tab2, tab3, tab4 = st.tabs(
    ["👤 المتكوّنون", "📚 المواد", "📅 الغيابات", "🚨 تنبيهات 10٪ + واتساب"]
)

# ----------------- تبويب 1: المتكوّنون -----------------
with tab1:
    st.subheader("👤 إدارة المتكوّنين")

    df_tr = load_trainees()
    df_tr = df_tr[df_tr["branche"] == branch].copy()

    specialites_exist = sorted([s for s in df_tr["specialite"].dropna().unique() if s])

    st.markdown("### ➕ إضافة متكوّن جديد")
    with st.form("add_trainee_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            nom = st.text_input("الاسم واللقب")
            tel = st.text_input("📞 هاتف المتكوّن")
        with col2:
            tel_parent = st.text_input("📞 هاتف الولي (اختياري)")
            spec = st.text_input("🔧 التخصّص (مثال: Anglais A2)")
        with col3:
            dt_deb = st.date_input("📅 تاريخ بداية التكوين", value=date.today())
        submitted_tr = st.form_submit_button("📥 حفظ المتكوّن")

    if submitted_tr:
        if not nom.strip() or not tel.strip() or not spec.strip():
            st.error("❌ الاسم، الهاتف، والتخصّص إجباريين.")
        else:
            new_id = uuid.uuid4().hex[:10]
            new_row = {
                "id": new_id,
                "nom": nom.strip(),
                "telephone": normalize_phone(tel),
                "tel_parent": normalize_phone(tel_parent),
                "branche": branch,
                "specialite": spec.strip(),
                "date_debut": dt_deb.strftime("%Y-%m-%d"),
                "actif": "1",
            }
            try:
                append_record(TRAINEES_SHEET, TRAINEES_COLS, new_row)
                st.success("✅ تم إضافة المتكوّن.")
                st.rerun()
            except Exception as e:
                st.error(f"خطأ أثناء إضافة المتكوّن: {e}")

    st.markdown("### 📋 قائمة المتكوّنين في هذا الفرع")
    if df_tr.empty:
        st.info("لا يوجد متكوّنون بعد في هذا الفرع.")
    else:
        st.dataframe(
            df_tr[["id", "nom", "telephone", "tel_parent", "specialite", "date_debut", "actif"]],
            use_container_width=True
        )

        st.markdown("### 🗑️ حذف متكوّن")
        options_tr_del = [
            f"[{i}] {r['nom']} — {r['specialite']} ({r['telephone']})"
            for i, (_, r) in enumerate(df_tr.iterrows())
        ]
        if options_tr_del:
            pick_tr_del = st.selectbox("اختر المتكوّن للحذف", options_tr_del)
            if st.button("❗ حذف المتكوّن نهائيًا"):
                try:
                    idx = int(pick_tr_del.split("]")[0].replace("[", "").strip())
                    tr_id = df_tr.iloc[idx]["id"]
                    delete_record_by_id(TRAINEES_SHEET, TRAINEES_COLS, tr_id)
                    st.success("✅ تم الحذف.")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ أثناء الحذف: {e}")

# ----------------- تبويب 2: المواد -----------------
with tab2:
    st.subheader("📚 إدارة المواد")

    df_sub = load_subjects()
    df_sub = df_sub[df_sub["branche"] == branch].copy()

    df_tr_all = load_trainees()
    specs_all = sorted([s for s in df_tr_all["specialite"].dropna().unique() if s])

    st.markdown("### ➕ إضافة مادة جديدة")
    with st.form("add_subject_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            mat_nom = st.text_input("اسم المادة")
        with col2:
            heures_tot = st.number_input("إجمالي الساعات (للمادة)", min_value=0.0, step=1.0)
        with col3:
            heures_week = st.number_input("عدد الساعات في الأسبوع", min_value=0.0, step=1.0)

        spec_choices = st.multiselect(
            "🔧 التخصّصات المرتبطة بهذه المادة (يمكن أكثر من تخصّص)",
            specs_all
        )

        sub_submit = st.form_submit_button("📥 حفظ المادة")

    if sub_submit:
        if not mat_nom.strip():
            st.error("❌ اسم المادة إجباري.")
        elif not spec_choices:
            st.error("❌ اختر على الأقل تخصّص واحد للمادة.")
        else:
            new_id = uuid.uuid4().hex[:10]
            rec = {
                "id": new_id,
                "nom_matiere": mat_nom.strip(),
                "branche": branch,
                "specialites": ",".join(spec_choices),
                "heures_totales": str(heures_tot),
                "heures_semaine": str(heures_week),
            }
            try:
                append_record(SUBJECTS_SHEET, SUBJECTS_COLS, rec)
                st.success("✅ تم إضافة المادة.")
                st.rerun()
            except Exception as e:
                st.error(f"خطأ أثناء إضافة المادة: {e}")

    st.markdown("### 📋 قائمة المواد في هذا الفرع")
    if df_sub.empty:
        st.info("لا توجد مواد بعد.")
    else:
        df_show = df_sub.copy()
        df_show["specialites"] = df_show["specialites"].fillna("")
        st.dataframe(
            df_show[["id", "nom_matiere", "specialites", "heures_totales", "heures_semaine"]],
