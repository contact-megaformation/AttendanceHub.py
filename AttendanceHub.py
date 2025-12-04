# ==========================================
# AttendanceHub.py - نسخة مصلّحة ومستقرة
# إدارة الغيابات + التنبيهات + واتساب + حذف غيابات
# ==========================================

import json, time, uuid, urllib.parse, os
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

# ================== إعداد الصفحة ==================
st.set_page_config(page_title="AttendanceHub - Mega Formation", layout="wide")

st.markdown(
    """
    <div style='text-align:center'>
      <h1>🕒 AttendanceHub - إدارة الغيابات</h1>
      <p>متكوّنين، مواد، غيابات، تنبيهات 10٪ + رسائل واتساب</p>
    </div>
    <hr/>
    """,
    unsafe_allow_html=True,
)

# ================== Google Sheets ==================
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

def make_client_and_sheet_id():
    # 1) من Streamlit secrets
    if "gcp_service_account" in st.secrets:
        sa_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPE)
        client = gspread.authorize(creds)
        if "SPREADSHEET_ID" not in st.secrets:
            st.error("⚠️ SPREADSHEET_ID مفقود في secrets.")
            st.stop()
        return client, st.secrets["SPREADSHEET_ID"]

    # 2) لوكال عبر ملف service_account.json
    elif os.path.exists("service_account.json"):
        creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPE)
        client = gspread.authorize(creds)
        sheet_id = "PUT_YOUR_SHEET_ID_HERE"  # ✳️ بدّلها لو تخدم لوكال
        return client, sheet_id

    # 3) ما فما حتى طريقة
    else:
        st.error(
            "❌ لا gcp_service_account في secrets ولا service_account.json في المشروع.\n"
            "ضبط واحد منهم ضروري لربط Google Sheets."
        )
        st.stop()

client, SPREADSHEET_ID = make_client_and_sheet_id()

# ================== أسماء الشيتات والأعمدة ==================
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

# ================== Utils عامة ==================
def normalize_phone(s: str) -> str:
    digits = "".join(c for c in str(s) if c.isdigit())
    if len(digits) == 8:
        digits = "216" + digits
    return digits

def wa_link(number: str, message: str) -> str:
    num = normalize_phone(number)
    if not num:
        return ""
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}"

def as_float(x) -> float:
    try:
        return float(str(x).replace(",", ".").strip() or 0)
    except Exception:
        return 0.0

def get_spreadsheet():
    if st.session_state.get("sh_id") == SPREADSHEET_ID and "sh_obj" in st.session_state:
        return st.session_state["sh_obj"]
    sh = client.open_by_key(SPREADSHEET_ID)
    st.session_state["sh_obj"] = sh
    st.session_state["sh_id"] = SPREADSHEET_ID
    return sh

def ensure_ws(title: str, cols: list[str]):
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(title)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="2000", cols=str(max(len(cols), 8)))
        ws.update("1:1", [cols])
        return ws
    header = ws.row_values(1)
    if not header or header[:len(cols)] != cols:
        ws.update("1:1", [cols])
    return ws

def append_record(sheet_name: str, cols: list[str], rec: dict):
    ws = ensure_ws(sheet_name, cols)
    row = [str(rec.get(c, "")) for c in cols]
    ws.append_row(row)
    st.cache_data.clear()

def delete_absence_by_id(abs_id: str):
    ws = ensure_ws(ABSENCES_SHEET, ABSENCES_COLS)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return
    header = vals[0]
    if "id" not in header:
        return
    id_idx = header.index("id")
    for i, r in enumerate(vals[1:], start=2):
        if len(r) > id_idx and r[id_idx] == abs_id:
            ws.delete_rows(i)
            st.cache_data.clear()
            break

@st.cache_data(ttl=300)
def load_df(sheet_name: str, cols: list[str]) -> pd.DataFrame:
    ws = ensure_ws(sheet_name, cols)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(vals[1:], columns=vals[0])

# ================== التبويبات ==================
tab1, tab2 = st.tabs(["📅 الغيابات", "🚨 التنبيهات & واتساب"])

# ------------------------------------------------
# تبويب 1: الغيابات (إضافة + حذف فردي/جماعي)
# ------------------------------------------------
with tab1:
    st.subheader("📅 تسجيل و إدارة الغيابات")

    df_tr = load_df(TRAINEES_SHEET, TRAINEES_COLS)
    df_sub = load_df(SUBJECTS_SHEET, SUBJECTS_COLS)
    df_abs = load_df(ABSENCES_SHEET, ABSENCES_COLS)

    if df_tr.empty:
        st.info("❕ ما فماش متكوّنين في الشيت Trainees.")
    elif df_sub.empty:
        st.info("❕ ما فماش مواد في الشيت Subjects.")
    else:
        # اختيار المتربص
        trainees_options = {
            f"{r['nom']} — {r['specialite']} ({r['telephone']})": r
            for _, r in df_tr.iterrows()
        }
        trainee_label = st.selectbox("👤 اختر المتكوّن", list(trainees_options.keys()))
        trainee_row = trainees_options[trainee_label]
        trainee_id = str(trainee_row["id"]).strip()

        # المواد اللي مربوطة بتخصّص المتربص
        spec_tr = str(trainee_row["specialite"])
        df_sub_for_tr = df_sub[df_sub["specialites"].fillna("").str.contains(spec_tr)]
        if df_sub_for_tr.empty:
            st.warning("⚠️ ما فماش مواد مربوطة بهذا التخصّص. زيدهم من تبويب المواد في النسخة الأصلية.")
        else:
            subject_options = {
                f"{r['nom_matiere']} ({r['heures_totales']}h)": r
                for _, r in df_sub_for_tr.iterrows()
            }
            subj_label = st.selectbox("📚 اختر المادة", list(subject_options.keys()))
            subj_row = subject_options[subj_label]
            subject_id = str(subj_row["id"]).strip()

            col1, col2, col3 = st.columns(3)
            with col1:
                abs_date = st.date_input("📅 تاريخ الغياب", value=date.today())
            with col2:
                h_abs = st.number_input("⏱ عدد ساعات الغياب", min_value=0.0, step=0.5)
            with col3:
                is_just = st.checkbox("غياب مبرّر؟", value=False)
            comment = st.text_area("🗒️ ملاحظة (اختيارية)")

            if st.button("💾 تسجيل الغياب"):
                if h_abs <= 0:
                    st.error("❌ عدد الساعات لازم > 0.")
                else:
                    rec = {
                        "id": uuid.uuid4().hex[:10],
                        "trainee_id": trainee_id,
                        "subject_id": subject_id,
                        "date": abs_date.strftime("%Y-%m-%d"),
                        "heures_absence": str(h_abs),
                        "justifie": "Oui" if is_just else "Non",
                        "commentaire": comment.strip(),
                    }
                    append_record(ABSENCES_SHEET, ABSENCES_COLS, rec)
                    st.success("✅ تم تسجيل الغياب.")
                    st.rerun()

    st.markdown("---")
    st.subheader("🗑️ حذف غياب أو مجموعة غيابات")

    df_abs = load_df(ABSENCES_SHEET, ABSENCES_COLS)
    if df_abs.empty:
        st.info("لا توجد غيابات بعد.")
    else:
        # نجهز داتا لعرض أوضح
        df_abs_view = df_abs.copy()
        df_abs_view["date_dt"] = pd.to_datetime(df_abs_view["date"], errors="coerce")
        df_abs_view = df_abs_view.sort_values("date_dt", ascending=False)

        # join مع المتربصين والمواد (اختياري للعرض)
        df_abs_view = df_abs_view.merge(
            df_tr[["id", "nom", "specialite"]],
            left_on="trainee_id", right_on="id", how="left", suffixes=("", "_tr")
        )
        df_abs_view = df_abs_view.merge(
            df_sub[["id", "nom_matiere"]],
            left_on="subject_id", right_on="id", how="left", suffixes=("", "_sub")
        )

        df_abs_view["date_str"] = df_abs_view["date_dt"].dt.strftime("%Y-%m-%d").fillna(df_abs_view["date"])

        options_del = [
            f"{r['id']} — {r.get('nom','?')} — {r.get('nom_matiere','?')} — {r['date_str']} — {r['heures_absence']}h"
            for _, r in df_abs_view.iterrows()
        ]
        picked = st.multiselect("اختر الغيابات للحذف", options_del)

        if st.button("❗ تأكيد الحذف"):
            for opt in picked:
                abs_id = opt.split(" — ")[0]
                delete_absence_by_id(abs_id)
            if picked:
                st.success("✅ تم حذف الغيابات المختارة.")
                st.rerun()
            else:
                st.info("لم يتم اختيار أي غياب.")

# ------------------------------------------------
# تبويب 2: التنبيهات + واتساب
# ------------------------------------------------
with tab2:
    st.subheader("🚨 تنبيهات 10٪ + رسالة واتساب")

    df_tr = load_df(TRAINEES_SHEET, TRAINEES_COLS)
    df_sub = load_df(SUBJECTS_SHEET, SUBJECTS_COLS)
    df_abs_all = load_df(ABSENCES_SHEET, ABSENCES_COLS)

    if df_tr.empty or df_sub.empty or df_abs_all.empty:
        st.info("يلزم يكون فما متكوّنين + مواد + غيابات باش تخدم التنبيهات.")
    else:
        # نضيف أعمدة مساعدة
        df_abs_all = df_abs_all.copy()
        df_abs_all["trainee_id_norm"] = df_abs_all["trainee_id"].astype(str).str.strip()
        df_abs_all["subject_id_norm"] = df_abs_all["subject_id"].astype(str).str.strip()
        df_abs_all["date_dt"] = pd.to_datetime(df_abs_all["date"], errors="coerce")

        # اختيار التخصّص
        specs = sorted([s for s in df_tr["specialite"].dropna().unique() if s])
        spec_choice = st.selectbox("🔧 اختر التخصّص", specs)

        df_tr_spec = df_tr[df_tr["specialite"] == spec_choice].copy()
        if df_tr_spec.empty:
            st.info("ما فماش متكوّنين بهذا التخصّص.")
        else:
            # اختيار المتربص
            trainees_options = {
                f"{r['nom']} ({r['telephone']})": r
                for _, r in df_tr_spec.iterrows()
            }
            trainee_label = st.selectbox("👤 اختر المتكوّن", list(trainees_options.keys()))
            trainee_row = trainees_options[trainee_label]
            trainee_id_norm = str(trainee_row["id"]).strip()

            # اختيار الفترة
            filt_type = st.radio("⏳ اختر الفترة", ["📅 يوم", "📆 أسبوع", "🗓️ شهر"], horizontal=True)
            today = date.today()
            if filt_type == "📅 يوم":
                start_date = today
                end_date = today
            elif filt_type == "📆 أسبوع":
                start_date = today - timedelta(days=7)
                end_date = today
            else:  # شهر
                start_date = today.replace(day=1)
                end_date = today

            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date)

            # فلترة الغيابات لهذا المتربص في هذه الفترة ONLY
            mask_tr = df_abs_all["trainee_id_norm"] == trainee_id_norm
            mask_date = df_abs_all["date_dt"].notna() & df_abs_all["date_dt"].between(start_ts, end_ts, inclusive="both")
            df_abs_period = df_abs_all[mask_tr & mask_date].copy()

            if df_abs_period.empty:
                st.success("🎉 لا توجد غيابات لهذا المتكوّن في هذه الفترة.")
            else:
                # ندمج مع المواد باش نعرف heures_totales
                df_abs_period = df_abs_period.merge(
                    df_sub[["id", "nom_matiere", "heures_totales"]],
                    left_on="subject_id_norm",
                    right_on="id",
                    how="left",
                    suffixes=("", "_sub")
                )

                df_abs_period["heures_absence_f"] = df_abs_period["heures_absence"].apply(as_float)
                df_abs_period["heures_totales_f"] = df_abs_period["heures_totales"].apply(as_float)

                # نحسب مجموع الغيابات في الفترة حسب المادة
                grp = (
                    df_abs_period
                    .groupby(["subject_id_norm", "nom_matiere"], as_index=False)
                    .agg(
                        total_abs=("heures_absence_f", "sum"),
                        heures_tot=("heures_totales_f", "first"),
                    )
                )
                grp["limit_10"] = grp["heures_tot"] * 0.10
                grp["remaining_before_10"] = grp["limit_10"] - grp["total_abs"]

                # المواد اللي تعدّت الحد (Élimination)
                elim_subjects = grp[grp["remaining_before_10"] <= 0]["nom_matiere"].tolist()

                st.markdown("### 📊 جدول الغيابات في الفترة")
                df_abs_period["date_str"] = df_abs_period["date_dt"].dt.strftime("%Y-%m-%d").fillna(df_abs_period["date"])
                st.dataframe(
                    df_abs_period[["nom_matiere", "date_str", "heures_absence", "justifie"]],
                    use_container_width=True
                )

                st.markdown("### 🧮 ملخّص حسب المادة")
                grp_disp = grp.copy()
                grp_disp["total_abs"] = grp_disp["total_abs"].round(2)
                grp_disp["limit_10"] = grp_disp["limit_10"].round(2)
                grp_disp["remaining_before_10"] = grp_disp["remaining_before_10"].round(2)
                st.dataframe(
                    grp_disp.rename(columns={
                        "nom_matiere": "المادة",
                        "total_abs": "مجموع الغياب في الفترة",
                        "heures_tot": "إجمالي الساعات",
                        "limit_10": "حدّ 10٪",
                        "remaining_before_10": "الساعات المتبقية قبل 10٪"
                    }),
                    use_container_width=True
                )

                # ---------- إعداد رسالة واتساب ----------
                total_abs_all = grp["total_abs"].sum()
                # نبني سطور المواد
                lines_mat = []
                for _, r in grp.iterrows():
                    remaining = r["remaining_before_10"]
                    rem_txt = f"{remaining:.2f}h متبقية قبل 10٪" if remaining > 0 else "تعدّى حدّ 10٪"
                    lines_mat.append(
                        f"- {r['nom_matiere']}: {r['total_abs']:.2f}h غياب (الحدّ 10٪ = {r['limit_10']:.2f}h، {rem_txt})"
                    )
                mat_block = "\n".join(lines_mat)

                elim_txt = ""
                if elim_subjects:
                    elim_txt = "\n🚨 المواد التي يمكن أن يقع فيها الإقصاء (تجاوز حدّ 10٪): " + ", ".join(elim_subjects)

                msg = (
                    "مرحبا بيك إدارة هيكل التكوين تعلمك أنو:\n\n"
                    f"📌 المتكوّن: {trainee_row['nom']}\n"
                    f"📚 التخصّص: {spec_choice}\n"
                    f"📅 الفترة من {start_date} إلى {end_date}\n\n"
                    f"⏱️ مجموع ساعات الغياب في هذه الفترة: {total_abs_all:.2f}h\n\n"
                    "📘 توزيع الغياب حسب المواد:\n"
                    f"{mat_block}"
                    f"{elim_txt}\n\n"
                    "يرجى التواصل مع الإدارة لمزيد التوضيح.\n"
                    "مع تحيات إدارة Mega Formation."
                )

                st.markdown("### 💬 رسالة الواتساب الجاهزة")
                st.text_area("نصّ الرسالة", value=msg, height=220)

                phone_target = trainee_row["telephone"]
                if normalize_phone(phone_target):
                    link = wa_link(phone_target, msg)
                    st.markdown(f"[📲 فتح واتساب و إرسال الرسالة]({link})")
                else:
                    st.warning("⚠️ رقم الهاتف غير مضبوط لهذا المتكوّن.")
