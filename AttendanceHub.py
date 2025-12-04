# AttendanceHub_GSheets.py
# إدارة الغيابات للمكوّنين + Google Sheets backend (فرع MB/Bizerte)
# تنبيهات 10٪ + واتساب (فردي/جماعي) + حذف جماعي + Import من Excel/CSV

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
                st.error(
                    "⚠️ المفتاح SPREADSHEET_ID مش موجود في secrets.\nزيدو في Streamlit secrets."
                )
                st.stop()

            sheet_id = st.secrets["SPREADSHEET_ID"]
            return client, sheet_id
        except Exception as e:
            st.error(f"⚠️ خطأ في gcp_service_account داخل secrets: {e}")
            st.stop()

    # 2) لو تخدم لوكال وتنجم تستعمل ملف service_account.json
    elif os.path.exists("service_account.json"):
        try:
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=SCOPE
            )
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


client, SPREADSHEET_ID = make_client_and_sheet_id()

# أسماء الشيتات
TRAINEES_SHEET = "Trainees"
SUBJECTS_SHEET = "Subjects"
ABSENCES_SHEET = "Absences"

TRAINEES_COLS = [
    "id",
    "nom",
    "telephone",
    "tel_parent",
    "branche",
    "specialite",
    "date_debut",
    "actif",
]

SUBJECTS_COLS = [
    "id",
    "nom_matiere",
    "branche",
    "specialites",  # قائمة تخصّصات مفصولة بفاصلة
    "heures_totales",
    "heures_semaine",
]

ABSENCES_COLS = [
    "id",
    "trainee_id",
    "subject_id",
    "date",
    "heures_absence",
    "justifie",
    "commentaire",
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
    if not header or header[: len(columns)] != columns:
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


def update_record_fields_by_id(
    sheet_name: str, cols: list[str], rec_id: str, updates: dict
):
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


# دالة مساعدة: تجهيز رسالة واتساب لمتربّص معيّن و فترة معيّنة
def build_whatsapp_message_for_trainee(
    tr_row, df_abs_all, df_sub_all, branch_name, d_from: date, d_to: date, period_label: str
) -> tuple[str, list[str]]:
    """
    ترجع (message_text, info_lines)  — info_lines لو تحب تعرضها في الواجهة.
    """
    trainee_id = tr_row["id"]
    df_abs_t = df_abs_all[df_abs_all["trainee_id"] == trainee_id].copy()

    if df_abs_t.empty:
        return "", ["لا توجد غيابات لهذا المتكوّن في أي فترة."]

    df_abs_t["date_dt"] = pd.to_datetime(df_abs_t["date"], errors="coerce")
    mask_period = (df_abs_t["date_dt"].dt.date >= d_from) & (
        df_abs_t["date_dt"].dt.date <= d_to
    )
    df_abs_period = df_abs_t[mask_period].copy()

    if df_abs_period.empty:
        return "", ["لا توجد غيابات في هذه الفترة."]

    df_abs_period = df_abs_period.merge(
        df_sub_all[["id", "nom_matiere", "heures_totales"]],
        left_on="subject_id",
        right_on="id",
        how="left",
        suffixes=("", "_sub"),
    )

    lines = []
    for _, r in df_abs_period.iterrows():
        if pd.notna(r["date_dt"]):
            dstr = r["date_dt"].strftime("%Y-%m-%d")
        else:
            dstr = str(r["date"])
        subj = str(r.get("nom_matiere", ""))
        h = as_float(r.get("heures_absence", 0))
        just = "مبرر" if str(r.get("justifie", "")).strip() == "Oui" else "غير مبرر"
        lines.append(f"- {dstr} | {subj} | {h}h ({just})")

    # غيابات غير مبررة فقط لحساب 10٪
    df_eff_t = df_abs_period[df_abs_period["justifie"] != "Oui"].copy()
    df_eff_t["heures_absence_f"] = df_eff_t["heures_absence"].apply(as_float)
    df_eff_t["heures_totales_f"] = df_eff_t["heures_totales"].apply(as_float)

    elim_lines = []
    stats_lines = []

    if not df_eff_t.empty:
        grp_t = df_eff_t.groupby("nom_matiere", as_index=False).agg(
            total_abs=("heures_absence_f", "sum"),
            heures_tot=("heures_totales_f", "first"),
        )
        grp_t["limit_10"] = grp_t["heures_tot"] * 0.10
        grp_t["remaining"] = grp_t["limit_10"] - grp_t["total_abs"]

        for _, g in grp_t.iterrows():
            stats_lines.append(
                f"- {g['nom_matiere']}: مجموع غياب غير مبرر {g['total_abs']:.2f}h / حد 10٪ = {g['limit_10']:.2f}h (الباقي قبل 10٪ = {g['remaining']:.2f}h)"
            )
        elim = grp_t[grp_t["total_abs"] >= grp_t["limit_10"]]
        for _, g in elim.iterrows():
            elim_lines.append(
                f"- {g['nom_matiere']} (مجموع غياب غير مبرر {g['total_abs']:.2f}h ≥ حد 10٪ {g['limit_10']:.2f}h)"
            )

    msg_lines = []
    msg_lines.append("مرحبا بيك، إدارة هيكل التكوين تعلمك أنو:")
    msg_lines.append("")
    msg_lines.append(f"📌 المتكوّن: {tr_row['nom']}")
    msg_lines.append(f"🏫 الفرع: {branch_name}")
    msg_lines.append(f"🔧 التخصّص: {tr_row.get('specialite', '')}")
    msg_lines.append(f"🕒 الفترة: {period_label}")
    msg_lines.append("")

    msg_lines.append("تفاصيل الغيابات المسجّلة في هذه الفترة:")
    msg_lines.extend(lines)

    if stats_lines:
        msg_lines.append("")
        msg_lines.append("إحصائيات 10٪ للمواد (غيابات غير مبررة فقط):")
        msg_lines.extend(stats_lines)

    if elim_lines:
        msg_lines.append("")
        msg_lines.append(
            "⚠️ المواد اللي تنجم تطيح فيهم élimination (تجاوز 10٪ غيابات غير مبررة):"
        )
        msg_lines.extend(elim_lines)

    msg_lines.append("")
    msg_lines.append("شكراً لتفهمك، ومرحبا بيك في أي وقت في إدارة هيكل التكوين.")

    msg = "\n".join(msg_lines)
    info_debug = [
        f"Found {len(df_abs_period)} absences in this period.",
        f"Unjustified rows used for 10% calc: {len(df_eff_t)}",
    ]
    return msg, info_debug


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
    st.sidebar.warning(
        "⚠️ لم يتم ضبط كلمة المرور لهذا الفرع في secrets.branch_passwords"
    )

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
            df_tr[
                [
                    "id",
                    "nom",
                    "telephone",
                    "tel_parent",
                    "specialite",
                    "date_debut",
                    "actif",
                ]
            ],
            use_container_width=True,
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
            heures_tot = st.number_input(
                "إجمالي الساعات (للمادة)", min_value=0.0, step=1.0
            )
        with col3:
            heures_week = st.number_input(
                "عدد الساعات في الأسبوع", min_value=0.0, step=1.0
            )

        spec_choices = st.multiselect(
            "🔧 التخصّصات المرتبطة بهذه المادة (يمكن أكثر من تخصّص)", specs_all
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
            df_show[
                ["id", "nom_matiere", "specialites", "heures_totales", "heures_semaine"]
            ],
            use_container_width=True,
        )

        st.markdown("### ✏️ تعديل مادة")
        opts_edit = [
            f"[{i}] {r['nom_matiere']} — {r['specialites']} ({r['heures_totales']}h)"
            for i, (_, r) in enumerate(df_sub.iterrows())
        ]
        if opts_edit:
            pick_edit = st.selectbox("اختر مادة للتعديل", opts_edit)
            idx_edit = int(pick_edit.split("]")[0].replace("[", "").strip())
            row_edit = df_sub.iloc[idx_edit]

            with st.form("edit_subject_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_name = st.text_input(
                        "اسم المادة", value=row_edit["nom_matiere"]
                    )
                with col2:
                    new_tot = st.number_input(
                        "إجمالي الساعات",
                        value=as_float(row_edit["heures_totales"]),
                        step=1.0,
                    )
                with col3:
                    new_week = st.number_input(
                        "ساعات في الأسبوع",
                        value=as_float(row_edit["heures_semaine"]),
                        step=1.0,
                    )
                current_specs = [s for s in str(row_edit["specialites"]).split(",") if s]
                new_specs = st.multiselect(
                    "التخصّصات", specs_all, default=current_specs
                )
                sub_ok = st.form_submit_button("💾 حفظ التعديلات")

            if sub_ok:
                try:
                    sid = row_edit["id"]
                    updates = {
                        "nom_matiere": new_name.strip(),
                        "heures_totales": str(new_tot),
                        "heures_semaine": str(new_week),
                        "specialites": ",".join(new_specs),
                    }
                    update_record_fields_by_id(
                        SUBJECTS_SHEET, SUBJECTS_COLS, sid, updates
                    )
                    st.success("✅ تم تعديل المادة.")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ أثناء تعديل المادة: {e}")

        st.markdown("### 🗑️ حذف مادة")
        opts_del = [
            f"[{i}] {r['nom_matiere']} — {r['specialites']}"
            for i, (_, r) in enumerate(df_sub.iterrows())
        ]
        if opts_del:
            pick_del = st.selectbox(
                "اختر مادة للحذف", opts_del, key="del_subject_pick"
            )
            if st.button("❗ حذف المادة"):
                try:
                    idxd = int(pick_del.split("]")[0].replace("[", "").strip())
                    sid = df_sub.iloc[idxd]["id"]
                    delete_record_by_id(SUBJECTS_SHEET, SUBJECTS_COLS, sid)
                    st.success("✅ تم الحذف.")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ أثناء الحذف: {e}")

# ----------------- تبويب 3: الغيابات -----------------
with tab3:
    st.subheader("📅 تسجيل و تعديل و حذف الغيابات")

    df_tr_all = load_trainees()
    df_tr_b = df_tr_all[df_tr_all["branche"] == branch].copy()

    df_sub_all = load_subjects()
    df_sub_b = df_sub_all[df_sub_all["branche"] == branch].copy()

    df_abs_all = load_absences()

    if df_tr_b.empty:
        st.info("لا يوجد متكوّنون في هذا الفرع.")
    elif df_sub_b.empty:
        st.info("لا توجد مواد مضبوطة في هذا الفرع.")
    else:
        specs_in_branch = sorted([s for s in df_tr_b["specialite"].dropna().unique() if s])
        spec_choice = st.selectbox(
            "🔧 اختر التخصّص (لإظهار المتكوّنين)",
            ["(الكل)"] + specs_in_branch,
        )
        if spec_choice != "(الكل)":
            df_tr_b = df_tr_b[df_tr_b["specialite"] == spec_choice].copy()

        if df_tr_b.empty:
            st.info("لا يوجد متكوّنون بهذا التخصّص في هذا الفرع.")
        else:
            # ---- إضافة غياب جديد ----
            st.markdown("### ➕ إضافة غياب")

            options_tr = [
                f"[{i}] {r['nom']} — {r['specialite']} ({r['telephone']})"
                for i, (_, r) in enumerate(df_tr_b.iterrows())
            ]
            tr_pick = st.selectbox("اختر المتكوّن", options_tr)
            idx_tr = int(tr_pick.split("]")[0].replace("[", "").strip())
            row_tr = df_tr_b.iloc[idx_tr]

            spec_tr = str(row_tr["specialite"])
            df_sub_for_tr = df_sub_b[
                df_sub_b["specialites"].fillna("").str.contains(spec_tr)
            ].copy()

            if df_sub_for_tr.empty:
                st.warning(
                    "لا توجد مواد مربوطة بهذا التخصّص. اضبط المواد في تبويب المواد."
                )
            else:
                opts_sub = [
                    f"[{i}] {r['nom_matiere']} ({r['heures_totales']}h)"
                    for i, (_, r) in enumerate(df_sub_for_tr.iterrows())
                ]
                sub_pick = st.selectbox("اختر المادة", opts_sub)
                idx_sub = int(sub_pick.split("]")[0].replace("[", "").strip())
                row_sub = df_sub_for_tr.iloc[idx_sub]

                with st.form("add_abs_form"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        abs_date = st.date_input("تاريخ الغياب", value=date.today())
                    with col2:
                        h_abs = st.number_input(
                            "عدد ساعات الغياب", min_value=0.0, step=0.5
                        )
                    with col3:
                        is_justified = st.checkbox(
                            "غياب مبرر (شهادة طبية؟)", value=False
                        )

                    comment = st.text_area("ملاحظة (اختياري)")
                    submit_abs = st.form_submit_button("📥 حفظ الغياب")

                if submit_abs:
                    if h_abs <= 0:
                        st.error("❌ عدد ساعات الغياب يجب أن يكون > 0.")
                    else:
                        new_id = uuid.uuid4().hex[:10]
                        rec = {
                            "id": new_id,
                            "trainee_id": row_tr["id"],
                            "subject_id": row_sub["id"],
                            "date": abs_date.strftime("%Y-%m-%d"),
                            "heures_absence": str(h_abs),
                            "justifie": "Oui" if is_justified else "Non",
                            "commentaire": comment.strip(),
                        }
                        try:
                            append_record(ABSENCES_SHEET, ABSENCES_COLS, rec)
                            st.success("✅ تم تسجيل الغياب.")
                        except Exception as e:
                            st.error(f"خطأ أثناء تسجيل الغياب: {e}")

            # ---- تعديل / حذف غياب واحد ----
            st.markdown("---")
            st.markdown("### ✏️ تعديل / 🗑️ حذف غياب مفرد")

            df_abs_all = load_absences()
            if df_abs_all.empty:
                st.info("لا توجد غيابات مسجلة بعد.")
            else:
                df_abs = df_abs_all.copy()
                df_abs["heures_absence_f"] = df_abs["heures_absence"].apply(as_float)

                df_abs = df_abs.merge(
                    df_tr_all[
                        ["id", "nom", "branche", "specialite", "telephone"]
                    ],
                    left_on="trainee_id",
                    right_on="id",
                    how="left",
                    suffixes=("", "_tr"),
                )
                df_abs = df_abs.merge(
                    df_sub_all[["id", "nom_matiere"]],
                    left_on="subject_id",
                    right_on="id",
                    how="left",
                    suffixes=("", "_sub"),
                )

                df_abs = df_abs[df_abs["branche"] == branch].copy()
                if df_abs.empty:
                    st.info("لا توجد غيابات في هذا الفرع.")
                else:
                    df_abs["date_dt"] = pd.to_datetime(
                        df_abs["date"], errors="coerce"
                    )
                    df_abs = df_abs.sort_values(
                        "date_dt", ascending=False
                    ).reset_index(drop=True)

                    options_abs_edit = [
                        f"[{i}] {r['nom']} — {r['nom_matiere']} — {r['date']} — {r['heures_absence_f']}h — مبرر: {r['justifie']}"
                        for i, (_, r) in enumerate(df_abs.iterrows())
                    ]
                    pick_abs = st.selectbox(
                        "اختر الغياب للتعديل / الحذف", options_abs_edit
                    )

                    if pick_abs:
                        idx_abs = int(pick_abs.split("]")[0].replace("[", "").strip())
                        row_a = df_abs.iloc[idx_abs]

                        with st.form("edit_abs_form"):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                base_date = (
                                    row_a["date_dt"].date()
                                    if pd.notna(row_a["date_dt"])
                                    else date.today()
                                )
                                new_date = st.date_input(
                                    "تاريخ الغياب", value=base_date
                                )
                            with col2:
                                new_hours = st.number_input(
                                    "ساعات الغياب",
                                    value=float(row_a["heures_absence_f"]),
                                    step=0.5,
                                )
                            with col3:
                                new_just = st.selectbox(
                                    "مبرر؟",
                                    ["Non", "Oui"],
                                    index=(
                                        1
                                        if str(row_a["justifie"]).strip() == "Oui"
                                        else 0
                                    ),
                                )
                            new_comment = st.text_area(
                                "ملاحظة", value=str(row_a.get("commentaire", ""))
                            )
                            cols_btn = st.columns(2)
                            with cols_btn[0]:
                                submit_edit_abs = st.form_submit_button(
                                    "💾 حفظ التعديل"
                                )
                            with cols_btn[1]:
                                delete_abs = st.form_submit_button("🗑️ حذف هذا الغياب")

                        if submit_edit_abs:
                            try:
                                aid = row_a["id_x"] if "id_x" in row_a else row_a["id"]
                                updates = {
                                    "date": new_date.strftime("%Y-%m-%d"),
                                    "heures_absence": str(new_hours),
                                    "justifie": new_just,
                                    "commentaire": new_comment.strip(),
                                }
                                update_record_fields_by_id(
                                    ABSENCES_SHEET, ABSENCES_COLS, aid, updates
                                )
                                st.success("✅ تم تعديل الغياب.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"خطأ أثناء تعديل الغياب: {e}")

                        if delete_abs:
                            try:
                                aid = row_a["id_x"] if "id_x" in row_a else row_a["id"]
                                delete_record_by_id(
                                    ABSENCES_SHEET, ABSENCES_COLS, aid
                                )
                                st.success("✅ تم حذف الغياب.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"خطأ أثناء حذف الغياب: {e}")

            # ---- حذف جماعي (Bulk) ----
            st.markdown("---")
            st.markdown("### 🗑️ حذف مجموعة غيابات (Bulk)")

            df_abs_all = load_absences()
            if df_abs_all.empty:
                st.info("لا توجد غيابات للحذف.")
            else:
                specs_bulk = sorted(
                    [s for s in df_tr_b["specialite"].dropna().unique() if s]
                )
                spec_bulk = st.selectbox(
                    "🔧 التخصّص (للحذف الجماعي)", ["(الكل)"] + specs_bulk
                )
                df_tr_bulk = df_tr_b.copy()
                if spec_bulk != "(الكل)":
                    df_tr_bulk = df_tr_bulk[df_tr_bulk["specialite"] == spec_bulk]

                if df_tr_bulk.empty:
                    st.info("لا يوجد متكوّنون بهذا التخصّص.")
                else:
                    labels_map_bulk = {
                        f"{r['nom']} — {r['specialite']} ({r['telephone']})": r["id"]
                        for _, r in df_tr_bulk.iterrows()
                    }
                    label_tr_bulk = st.selectbox(
                        "👤 اختر المتكوّن", list(labels_map_bulk.keys())
                    )
                    trainee_id_bulk = labels_map_bulk[label_tr_bulk]

                    df_abs_t_bulk = df_abs_all[
                        df_abs_all["trainee_id"] == trainee_id_bulk
                    ].copy()
                    if df_abs_t_bulk.empty:
                        st.info("لا توجد غيابات لهذا المتكوّن.")
                    else:
                        df_abs_t_bulk = df_abs_t_bulk.merge(
                            df_sub_all[["id", "nom_matiere"]],
                            left_on="subject_id",
                            right_on="id",
                            how="left",
                            suffixes=("", "_sub"),
                        )

                        sub_choices_bulk = sorted(
                            df_abs_t_bulk["nom_matiere"].dropna().unique()
                        )
                        sub_bulk = st.selectbox(
                            "📚 المادة (اختياري)", ["(الكل)"] + sub_choices_bulk
                        )

                        colb1, colb2 = st.columns(2)
                        with colb1:
                            d_from_bulk = st.date_input(
                                "من تاريخ", value=date.today() - timedelta(days=7)
                            )
                        with colb2:
                            d_to_bulk = st.date_input("إلى تاريخ", value=date.today())

                        if d_to_bulk < d_from_bulk:
                            st.error("❌ تاريخ النهاية لازم يكون بعد البداية.")
                        else:
                            if st.button("🗑️ حذف كل الغيابات في هذه الفترة"):
                                try:
                                    df_abs_t_bulk["date_dt"] = pd.to_datetime(
                                        df_abs_t_bulk["date"], errors="coerce"
                                    )
                                    mask = (df_abs_t_bulk["date_dt"].dt.date >= d_from_bulk) & (
                                        df_abs_t_bulk["date_dt"].dt.date <= d_to_bulk
                                    )
                                    if sub_bulk != "(الكل)":
                                        mask &= df_abs_t_bulk[
                                            "nom_matiere"
                                        ] == sub_bulk
                                    to_del = df_abs_t_bulk[mask]
                                    if to_del.empty:
                                        st.info("لا توجد غيابات مطابقة للحذف.")
                                    else:
                                        for _, rdel in to_del.iterrows():
                                            delete_record_by_id(
                                                ABSENCES_SHEET,
                                                ABSENCES_COLS,
                                                rdel["id"],
                                            )
                                        st.success(
                                            f"✅ تم حذف {len(to_del)} غياب(ات)."
                                        )
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"خطأ أثناء الحذف الجماعي: {e}")

            # ---- Import من Excel/CSV ----
            st.markdown("---")
            st.markdown("### 📥 استيراد غيابات من ملف Excel/CSV")

            st.info(
                "الملف لازم يحتوي الأعمدة التالية على الأقل:\n"
                "- trainee_id (من جدول المتكوّنين)\n"
                "- subject_id (من جدول المواد)\n"
                "- date (صيغة YYYY-MM-DD)\n"
                "- heures_absence (عدد الساعات)\n"
                "إختياري: justifie (Oui/Non)، commentaire.\n"
            )

            # نموذج فارغ للتحميل
            template_df = pd.DataFrame(
                {
                    "trainee_id": [],
                    "subject_id": [],
                    "date": [],
                    "heures_absence": [],
                    "justifie": [],
                    "commentaire": [],
                }
            )
            tmpl_csv = template_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ تحميل نموذج CSV فارغ",
                data=tmpl_csv,
                file_name="absences_template.csv",
                mime="text/csv",
            )

            uploaded = st.file_uploader(
                "حمّل ملف الغيابات (CSV أو Excel)", type=["csv", "xlsx"]
            )
            if uploaded is not None:
                try:
                    if uploaded.name.lower().endswith(".xlsx"):
                        df_up = pd.read_excel(uploaded)
                    else:
                        df_up = pd.read_csv(uploaded)

                    req_cols = {"trainee_id", "subject_id", "date", "heures_absence"}
                    if not req_cols.issubset(set(df_up.columns)):
                        st.error(
                            f"❌ الملف لازم يحتوي الأعمدة: {', '.join(req_cols)}"
                        )
                    else:
                        count_ok = 0
                        for _, r in df_up.iterrows():
                            try:
                                rec = {
                                    "id": uuid.uuid4().hex[:10],
                                    "trainee_id": str(r["trainee_id"]).strip(),
                                    "subject_id": str(r["subject_id"]).strip(),
                                    "date": str(r["date"]).split()[0],
                                    "heures_absence": str(r["heures_absence"]),
                                    "justifie": "Oui"
                                    if str(r.get("justifie", "Non")).strip() == "Oui"
                                    else "Non",
                                    "commentaire": str(
                                        r.get("commentaire", "")
                                    ).strip(),
                                }
                                append_record(ABSENCES_SHEET, ABSENCES_COLS, rec)
                                count_ok += 1
                            except Exception:
                                continue
                        st.success(f"✅ تم استيراد {count_ok} غياب(ات) من الملف.")
                except Exception as e:
                    st.error(f"❌ خطأ أثناء قراءة الملف: {e}")

# ----------------- تبويب 4: تنبيهات 10٪ + واتساب -----------------
with tab4:
    st.subheader("🚨 تنبيهات اقتراب 10٪ غيابات + 💬 رسائل واتساب (فردي/جماعي)")

    df_tr_all = load_trainees()
    df_tr_b = df_tr_all[df_tr_all["branche"] == branch].copy()
    df_sub_all = load_subjects()
    df_sub_b = df_sub_all[df_sub_all["branche"] == branch].copy()
    df_abs_all = load_absences()

    if df_tr_b.empty or df_sub_b.empty or df_abs_all.empty:
        st.info("يلزم يكون فما متكوّنين + مواد + غيابات باش تظهر التنبيهات.")
    else:
        # --------- جزء التنبيهات (قريبين من 10٪) ----------
        df_abs = df_abs_all.merge(
            df_tr_b[["id", "nom", "specialite"]],
            left_on="trainee_id",
            right_on="id",
            how="inner",
            suffixes=("", "_tr"),
        )
        df_abs = df_abs.merge(
            df_sub_b[["id", "nom_matiere", "heures_totales"]],
            left_on="subject_id",
            right_on="id",
            how="inner",
            suffixes=("", "_sub"),
        )

        if df_abs.empty:
            st.info("لا توجد غيابات لهذا الفرع.")
        else:
            df_abs["heures_absence_f"] = df_abs["heures_absence"].apply(as_float)
            df_abs["heures_totales_f"] = df_abs["heures_totales"].apply(as_float)

            df_eff = df_abs[df_abs["justifie"] != "Oui"].copy()

            if df_eff.empty:
                st.info("كل الغيابات مبررة، ما فماش تنبيهات 10٪.")
            else:
                X = st.number_input(
                    "أرني المتكوّنين اللي بقايلهم أقل من X ساعات قبل بلوغ 10٪ غيابات (غير مبررة)",
                    min_value=0.0,
                    value=2.0,
                    step=0.5,
                )

                grp = df_eff.groupby(["trainee_id", "subject_id"], as_index=False).agg(
                    total_abs=("heures_absence_f", "sum"),
                    nom=("nom", "first"),
                    matiere=("nom_matiere", "first"),
                    spec=("specialite", "first"),
                    heures_tot=("heures_totales_f", "first"),
                )

                grp["limit_10"] = grp["heures_tot"] * 0.10
                grp["remaining_before_10"] = grp["limit_10"] - grp["total_abs"]
                grp = grp[grp["heures_tot"] > 0]

                alerts = grp[
                    (grp["remaining_before_10"] > 0)
                    & (grp["remaining_before_10"] <= X)
                ].copy()

                if alerts.empty:
                    st.success("💚 لا يوجد متكوّنين قريبين من 10٪ حسب الشرط الحالي.")
                else:
                    alerts["total_abs"] = alerts["total_abs"].round(2)
                    alerts["limit_10"] = alerts["limit_10"].round(2)
                    alerts["remaining_before_10"] = alerts[
                        "remaining_before_10"
                    ].round(2)
                    alerts = alerts.sort_values("remaining_before_10")

                    st.markdown("### قائمة المتكوّنين القريبين من بلوغ 10٪")
                    st.dataframe(
                        alerts[
                            [
                                "nom",
                                "spec",
                                "matiere",
                                "total_abs",
                                "limit_10",
                                "remaining_before_10",
                            ]
                        ].rename(
                            columns={
                                "nom": "المتكوّن",
                                "spec": "التخصّص",
                                "matiere": "المادة",
                                "total_abs": "مجموع الغياب غير المبرر",
                                "limit_10": "حد 10٪",
                                "remaining_before_10": "الباقي قبل 10٪",
                            }
                        ),
                        use_container_width=True,
                    )

        st.markdown("---")
        st.markdown("### 💬 رسالة واتساب مفصّلة حسب الفترة (فردي)")

        # اختيار الاختصاص ثم المتربّص (باش يسهل الاختيار)
        specs_branch = sorted(
            [s for s in df_tr_b["specialite"].dropna().unique() if s]
        )
        spec_filter = st.selectbox(
            "🔧 اختر التخصّص", ["(الكل)"] + specs_branch, key="wa_spec_single"
        )
        df_tr_wa = df_tr_b.copy()
        if spec_filter != "(الكل)":
            df_tr_wa = df_tr_wa[df_tr_wa["specialite"] == spec_filter]

        if df_tr_wa.empty:
            st.info("لا يوجد متكوّنون بهذا التخصّص.")
        else:
            labels_map_wa = {
                f"{r['nom']} — {r['specialite']} ({r['telephone']})": r["id"]
                for _, r in df_tr_wa.iterrows()
            }
            label_tr_wa = st.selectbox(
                "👤 اختر المتكوّن للرسالة", list(labels_map_wa.keys()), key="wa_trainee_single"
            )
            trainee_id_wa = labels_map_wa[label_tr_wa]
            tr_row = df_tr_all[df_tr_all["id"] == trainee_id_wa].iloc[0]

            target_wa = st.radio(
                "المرسل إليه", ["المتكوّن", "الولي"], horizontal=True, key="wa_target_single"
            )
            phone_target = tr_row["telephone"] if target_wa == "المتكوّن" else tr_row["tel_parent"]
            phone_target = normalize_phone(phone_target)

            st.markdown("#### 🕒 اختر الفترة")
            period_type = st.radio(
                "نوع الفترة", ["يوم", "أسبوع", "شهر", "مخصص"], horizontal=True, key="wa_period_single"
            )
            today = date.today()

            if period_type == "يوم":
                d_single = st.date_input("اليوم", value=today, key="wa_day_single")
                d_from = d_single
                d_to = d_single
                period_label = f"بتاريخ {d_single.strftime('%Y-%m-%d')}"
            elif period_type == "أسبوع":
                week_start = st.date_input(
                    "بداية الأسبوع", value=today, key="wa_week_start_single"
                )
                d_from = week_start
                d_to = week_start + timedelta(days=6)
                period_label = (
                    f"من {d_from.strftime('%Y-%m-%d')} إلى {d_to.strftime('%Y-%m-%d')}"
                )
            elif period_type == "شهر":
                any_day = st.date_input(
                    "أي يوم من الشهر المطلوب", value=today, key="wa_month_day_single"
                )
                first = any_day.replace(day=1)
                if first.month == 12:
                    next_first = first.replace(year=first.year + 1, month=1)
                else:
                    next_first = first.replace(month=first.month + 1)
                last = next_first - timedelta(days=1)
                d_from = first
                d_to = last
                period_label = (
                    f"من {d_from.strftime('%Y-%m-%d')} إلى {d_to.strftime('%Y-%m-%d')} (شهر كامل)"
                )
            else:
                colp1, colp2 = st.columns(2)
                with colp1:
                    d_from = st.date_input(
                        "من تاريخ", value=today - timedelta(days=7), key="wa_from_single"
                    )
                with colp2:
                    d_to = st.date_input(
                        "إلى تاريخ", value=today, key="wa_to_single"
                    )
                if d_to < d_from:
                    st.error("❌ تاريخ النهاية لازم يكون بعد البداية.")
                    d_from, d_to = d_to, d_from
                period_label = (
                    f"من {d_from.strftime('%Y-%m-%d')} إلى {d_to.strftime('%Y-%m-%d')}"
                )

            if st.button("📲 جهّز رسالة الواتساب (فردي)"):
                if not phone_target:
                    st.error("❌ ما فماش رقم هاتف مضبوط للمتكوّن/الولي.")
                else:
                    msg, info_debug = build_whatsapp_message_for_trainee(
                        tr_row, df_abs_all, df_sub_all, branch, d_from, d_to, period_label
                    )
                    if not msg:
                        st.info("لا توجد غيابات في هذه الفترة لهذا المتكوّن.")
                    else:
                        st.caption("معلومة تقنية: " + " | ".join(info_debug))
                        st.text_area(
                            "نص الرسالة (يمكنك تعديله قبل الإرسال)", value=msg, height=250
                        )
                        link = wa_link(phone_target, msg)
                        st.markdown(f"[📲 افتح رسالة الواتساب الجاهزة]({link})")

        # -------- WhatsApp جماعي --------
        st.markdown("---")
        st.markdown("### 💬 رسائل واتساب جماعية (عدة متكوّنين في نفس الفترة)")

        spec_batch = st.selectbox(
            "🔧 اختر التخصّص (لإرسال جماعي)", ["(الكل)"] + specs_branch, key="wa_spec_batch"
        )
        df_tr_batch = df_tr_b.copy()
        if spec_batch != "(الكل)":
            df_tr_batch = df_tr_batch[df_tr_batch["specialite"] == spec_batch]

        if df_tr_batch.empty:
            st.info("لا يوجد متكوّنون لهذا الشرط.")
        else:
            st.markdown("#### 🕒 اختر الفترة المشتركة")
            period_type_b = st.radio(
                "نوع الفترة", ["يوم", "أسبوع", "شهر", "مخصص"], horizontal=True, key="wa_period_batch"
            )
            today_b = date.today()

            if period_type_b == "يوم":
                d_single_b = st.date_input(
                    "اليوم", value=today_b, key="wa_day_batch"
                )
                d_from_b = d_single_b
                d_to_b = d_single_b
                period_label_b = f"بتاريخ {d_single_b.strftime('%Y-%m-%d')}"
            elif period_type_b == "أسبوع":
                week_start_b = st.date_input(
                    "بداية الأسبوع", value=today_b, key="wa_week_start_batch"
                )
                d_from_b = week_start_b
                d_to_b = week_start_b + timedelta(days=6)
                period_label_b = (
                    f"من {d_from_b.strftime('%Y-%m-%d')} إلى {d_to_b.strftime('%Y-%m-%d')}"
                )
            elif period_type_b == "شهر":
                any_day_b = st.date_input(
                    "أي يوم من الشهر المطلوب", value=today_b, key="wa_month_day_batch"
                )
                first_b = any_day_b.replace(day=1)
                if first_b.month == 12:
                    next_first_b = first_b.replace(year=first_b.year + 1, month=1)
                else:
                    next_first_b = first_b.replace(month=first_b.month + 1)
                last_b = next_first_b - timedelta(days=1)
                d_from_b = first_b
                d_to_b = last_b
                period_label_b = (
                    f"من {d_from_b.strftime('%Y-%m-%d')} إلى {d_to_b.strftime('%Y-%m-%d')} (شهر كامل)"
                )
            else:
                colpb1, colpb2 = st.columns(2)
                with colpb1:
                    d_from_b = st.date_input(
                        "من تاريخ", value=today_b - timedelta(days=7), key="wa_from_batch"
                    )
                with colpb2:
                    d_to_b = st.date_input(
                        "إلى تاريخ", value=today_b, key="wa_to_batch"
                    )
                if d_to_b < d_from_b:
                    st.error("❌ تاريخ النهاية لازم يكون بعد البداية.")
                    d_from_b, d_to_b = d_to_b, d_from_b
                period_label_b = (
                    f"من {d_from_b.strftime('%Y-%m-%d')} إلى {d_to_b.strftime('%Y-%m-%d')}"
                )

            target_batch = st.radio(
                "المرسل إليه في الجماعي",
                ["المتكوّن", "الولي"],
                horizontal=True,
                key="wa_target_batch",
            )

            if st.button("📲 توليد روابط الواتساب لكل المتكوّنين (جماعي)"):
                rows_out = []
                for _, tr in df_tr_batch.iterrows():
                    phone_t = tr["telephone"] if target_batch == "المتكوّن" else tr["tel_parent"]
                    phone_t = normalize_phone(phone_t)
                    if not phone_t:
                        continue
                    msg_t, _ = build_whatsapp_message_for_trainee(
                        tr, df_abs_all, df_sub_all, branch, d_from_b, d_to_b, period_label_b
                    )
                    if not msg_t:
                        continue
                    link_t = wa_link(phone_t, msg_t)
                    rows_out.append(
                        {
                            "المتكوّن": tr["nom"],
                            "التخصّص": tr.get("specialite", ""),
                            "الهاتف": phone_t,
                            "رابط الواتساب": link_t,
                        }
                    )
                if not rows_out:
                    st.info(
                        "لا يوجد متكوّنون لديهم غيابات في هذه الفترة حسب الشروط."
                    )
                else:
                    df_links = pd.DataFrame(rows_out)
                    st.dataframe(
                        df_links[
                            ["المتكوّن", "التخصّص", "الهاتف", "رابط الواتساب"]
                        ],
                        use_container_width=True,
                    )
                    st.caption(
                        "إضغط على كل رابط لفتح رسالة واتساب في نافذة جديدة."
                    )
