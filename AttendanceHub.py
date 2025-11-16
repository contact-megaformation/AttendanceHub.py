# AttendanceHub_GSheets.py
# إدارة الغيابات للمكوّنين + Google Sheets backend (كيف MegaCRM)

import json
import time
import uuid
import urllib.parse
from datetime import datetime, date

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
    try:
        sa = st.secrets["gcp_service_account"]
        sa_info = dict(sa) if hasattr(sa, "keys") else (
            json.loads(sa) if isinstance(sa, str) else {}
        )
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPE)
        client = gspread.authorize(creds)
        sheet_id = st.secrets["SPREADSHEET_ID"]
        return client, sheet_id
    except Exception:
        # وضع التطوير المحلي
        creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPE)
        client = gspread.authorize(creds)
        sheet_id = "PUT_YOUR_SHEET_ID_HERE"
        return client, sheet_id

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

# ================== Helpers ==================
def normalize_phone(s: str) -> str:
    digits = "".join(c for c in str(s) if c.isdigit())
    # لو تونسي 8 أرقام نزيد 216
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

def save_df_to_sheet(df: pd.DataFrame, sheet_name: str, cols: list[str]):
    ws = ensure_ws(sheet_name, cols)
    if df.empty:
        ws.clear()
        ws.update("1:1", [cols])
    else:
        df = df[cols].copy()
        rows = [cols] + df.astype(str).values.tolist()
        ws.clear()
        ws.update("1:1", rows)
    st.cache_data.clear()

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
    ["👤 المتكوّنون", "📚 المواد", "📅 الغيابات", "🚨 تنبيهات 10٪"]
)

# ----------------- تبويب 1: المتكوّنون -----------------
with tab1:
    st.subheader("👤 إدارة المتكوّنين")

    df_tr = load_trainees()
    df_tr = df_tr[df_tr["branche"] == branch].copy()

    # قائمة التخصّصات المتوفّرة في هذا الفرع
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
            df_all_tr = load_trainees()
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
            df_new = pd.concat(
                [df_all_tr, pd.DataFrame([new_row])],
                ignore_index=True
            )
            save_df_to_sheet(df_new, TRAINEES_SHEET, TRAINEES_COLS)
            st.success("✅ تم إضافة المتكوّن.")
            st.rerun()

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
                    df_all_tr = load_trainees()
                    df_all_tr = df_all_tr[df_all_tr["id"] != tr_id]
                    save_df_to_sheet(df_all_tr, TRAINEES_SHEET, TRAINEES_COLS)
                    st.success("✅ تم الحذف.")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ أثناء الحذف: {e}")

# ----------------- تبويب 2: المواد -----------------
with tab2:
    st.subheader("📚 إدارة المواد")

    df_sub = load_subjects()
    df_sub = df_sub[df_sub["branche"] == branch].copy()

    # تخصّصات عامة (من المتكوّنين)
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
            df_all_sub = load_subjects()
            new_id = uuid.uuid4().hex[:10]
            rec = {
                "id": new_id,
                "nom_matiere": mat_nom.strip(),
                "branche": branch,
                "specialites": ",".join(spec_choices),
                "heures_totales": str(heures_tot),
                "heures_semaine": str(heures_week),
            }
            df_all_sub = pd.concat(
                [df_all_sub, pd.DataFrame([rec])],
                ignore_index=True
            )
            save_df_to_sheet(df_all_sub, SUBJECTS_SHEET, SUBJECTS_COLS)
            st.success("✅ تم إضافة المادة.")
            st.rerun()

    st.markdown("### 📋 قائمة المواد في هذا الفرع")
    if df_sub.empty:
        st.info("لا توجد مواد بعد.")
    else:
        df_show = df_sub.copy()
        df_show["specialites"] = df_show["specialites"].fillna("")
        st.dataframe(
            df_show[["id", "nom_matiere", "specialites", "heures_totales", "heures_semaine"]],
            use_container_width=True
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
                    new_name = st.text_input("اسم المادة", value=row_edit["nom_matiere"])
                with col2:
                    new_tot = st.number_input(
                        "إجمالي الساعات",
                        value=as_float(row_edit["heures_totales"]),
                        step=1.0
                    )
                with col3:
                    new_week = st.number_input(
                        "ساعات في الأسبوع",
                        value=as_float(row_edit["heures_semaine"]),
                        step=1.0
                    )
                current_specs = [s for s in str(row_edit["specialites"]).split(",") if s]
                new_specs = st.multiselect(
                    "التخصّصات",
                    specs_all,
                    default=current_specs
                )
                sub_ok = st.form_submit_button("💾 حفظ التعديلات")

            if sub_ok:
                df_all_sub = load_subjects()
                sid = row_edit["id"]
                mask = df_all_sub["id"] == sid
                df_all_sub.loc[mask, "nom_matiere"] = new_name.strip()
                df_all_sub.loc[mask, "heures_totales"] = str(new_tot)
                df_all_sub.loc[mask, "heures_semaine"] = str(new_week)
                df_all_sub.loc[mask, "specialites"] = ",".join(new_specs)
                save_df_to_sheet(df_all_sub, SUBJECTS_SHEET, SUBJECTS_COLS)
                st.success("✅ تم تعديل المادة.")
                st.rerun()

        st.markdown("### 🗑️ حذف مادة")
        opts_del = [
            f"[{i}] {r['nom_matiere']} — {r['specialites']}"
            for i, (_, r) in enumerate(df_sub.iterrows())
        ]
        if opts_del:
            pick_del = st.selectbox("اختر مادة للحذف", opts_del, key="del_subject_pick")
            if st.button("❗ حذف المادة"):
                try:
                    idxd = int(pick_del.split("]")[0].replace("[", "").strip())
                    sid = df_sub.iloc[idxd]["id"]
                    df_all_sub = load_subjects()
                    df_all_sub = df_all_sub[df_all_sub["id"] != sid]
                    save_df_to_sheet(df_all_sub, SUBJECTS_SHEET, SUBJECTS_COLS)
                    st.success("✅ تم الحذف.")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ أثناء الحذف: {e}")

# ----------------- تبويب 3: الغيابات -----------------
with tab3:
    st.subheader("📅 تسجيل و تعديل الغيابات")

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
        # ---- إضافة غياب جديد ----
        st.markdown("### ➕ إضافة غياب")

        options_tr = [
            f"[{i}] {r['nom']} — {r['specialite']} ({r['telephone']})"
            for i, (_, r) in enumerate(df_tr_b.iterrows())
        ]
        tr_pick = st.selectbox("اختر المتكوّن", options_tr)
        idx_tr = int(tr_pick.split("]")[0].replace("[", "").strip())
        row_tr = df_tr_b.iloc[idx_tr]

        # المواد المربوطة بتخصّص المتربص
        spec_tr = str(row_tr["specialite"])
        df_sub_for_tr = df_sub_b[
            df_sub_b["specialites"].fillna("").str.contains(spec_tr)
        ].copy()

        if df_sub_for_tr.empty:
            st.warning("لا توجد مواد مربوطة بهذا التخصّص. اضبط المواد في تبويب المواد.")
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
                    h_abs = st.number_input("عدد ساعات الغياب", min_value=0.0, step=0.5)
                with col3:
                    is_justified = st.checkbox("غياب مبرر (شهادة طبية؟)", value=False)

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
                    df_abs_new = pd.concat(
                        [df_abs_all, pd.DataFrame([rec])],
                        ignore_index=True
                    )
                    save_df_to_sheet(df_abs_new, ABSENCES_SHEET, ABSENCES_COLS)
                    st.success("✅ تم تسجيل الغياب.")

                    # ---- تنبيه واتساب ----
                    target = st.radio(
                        "المرسل إليه",
                        ["المتكوّن", "الولي"],
                        horizontal=True,
                        key="wa_target_new_abs"
                    )
                    phone_target = (
                        row_tr["telephone"] if target == "المتكوّن" else row_tr["tel_parent"]
                    )
                    phone_target = normalize_phone(phone_target)
                    if phone_target:
                        # حساب مجموع الغيابات لهذا المتربّص في هذه المادة (غير المبررة فقط)
                        df_abs_all2 = load_absences()
                        mask_pair = (
                            (df_abs_all2["trainee_id"] == row_tr["id"]) &
                            (df_abs_all2["subject_id"] == row_sub["id"]) &
                            (df_abs_all2["justifie"] != "Oui")
                        )
                        total_abs = df_abs_all2.loc[mask_pair, "heures_absence"].apply(as_float).sum()
                        total_hours = as_float(row_sub["heures_totales"])
                        ten_pct = total_hours * 0.10 if total_hours > 0 else 0
                        msg = (
                            f"السلام عليكم،\n\n"
                            f"📌 المتكوّن: {row_tr['nom']}\n"
                            f"📚 المادة: {row_sub['nom_matiere']}\n"
                            f"📅 تاريخ الغياب: {abs_date.strftime('%Y-%m-%d')}\n"
                            f"⏱ عدد ساعات الغياب اليوم: {h_abs}\n"
                            f"🧮 مجموع ساعات الغياب غير المبررة في هذه المادة: {total_abs}\n"
                        )
                        if total_hours > 0:
                            msg += f"🔢 الحد الأقصى (10٪ من {total_hours}h): {ten_pct}h\n"
                        msg += "\nمع تحيات Mega Formation."

                        link = wa_link(phone_target, msg)
                        st.markdown(f"[📲 إرسال تنبيه واتساب]({link})")
                    else:
                        st.info("لم يتم ضبط رقم هاتف صحيح للتلميذ أو الولي.")

        st.markdown("---")
        st.markdown("### ✏️ تغيير حالة غياب (مثلاً بعد شهادة طبية)")

        df_abs_all = load_absences()
        if df_abs_all.empty:
            st.info("لا توجد غيابات مسجلة بعد.")
        else:
            # join absences with trainees & subjects
            df_abs = df_abs_all.copy()
            df_abs["heures_absence_f"] = df_abs["heures_absence"].apply(as_float)

            # دمج مع المتكوّنين
            df_abs = df_abs.merge(
                df_tr_all[["id", "nom", "branche", "specialite"]],
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
                df_abs["date"] = pd.to_datetime(df_abs["date"], errors="coerce")
                df_abs = df_abs.sort_values("date", ascending=False).reset_index(drop=True)

                options_abs_edit = [
                    f"[{i}] {r['nom']} — {r['nom_matiere']} — {r['date'].date()} — {r['heures_absence_f']}h — مبرر: {r['justifie']}"
                    for i, (_, r) in enumerate(df_abs.iterrows())
                ]
                pick_abs = st.selectbox("اختر الغياب للتعديل", options_abs_edit)

                if pick_abs:
                    idx_abs = int(pick_abs.split("]")[0].replace("[", "").strip())
                    row_a = df_abs.iloc[idx_abs]

                    with st.form("edit_abs_form"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            new_date = st.date_input(
                                "تاريخ الغياب",
                                value=row_a["date"].date()
                            )
                        with col2:
                            new_hours = st.number_input(
                                "ساعات الغياب",
                                value=float(row_a["heures_absence_f"]),
                                step=0.5
                            )
                        with col3:
                            new_just = st.selectbox(
                                "مبرر؟",
                                ["Non", "Oui"],
                                index=(1 if row_a["justifie"] == "Oui" else 0)
                            )
                        new_comment = st.text_area(
                            "ملاحظة",
                            value=str(row_a.get("commentaire", "")),
                        )
                        submit_edit_abs = st.form_submit_button("💾 حفظ التعديل")

                    if submit_edit_abs:
                        df_all_abs = load_absences()
                        aid = row_a["id_x"] if "id_x" in row_a else row_a["id"]
                        mask_a = df_all_abs["id"] == aid
                        df_all_abs.loc[mask_a, "date"] = new_date.strftime("%Y-%m-%d")
                        df_all_abs.loc[mask_a, "heures_absence"] = str(new_hours)
                        df_all_abs.loc[mask_a, "justifie"] = new_just
                        df_all_abs.loc[mask_a, "commentaire"] = new_comment.strip()
                        save_df_to_sheet(df_all_abs, ABSENCES_SHEET, ABSENCES_COLS)
                        st.success("✅ تم تعديل الغياب.")
                        st.rerun()

# ----------------- تبويب 4: تنبيهات 10٪ -----------------
with tab4:
    st.subheader("🚨 تنبيهات اقتراب 10٪ غيابات")

    df_tr_all = load_trainees()
    df_tr_b = df_tr_all[df_tr_all["branche"] == branch].copy()
    df_sub_all = load_subjects()
    df_sub_b = df_sub_all[df_sub_all["branche"] == branch].copy()
    df_abs = load_absences()

    if df_tr_b.empty or df_sub_b.empty or df_abs.empty:
        st.info("يلزم يكون فما متكوّنين + مواد + غيابات باش تظهر التنبيهات.")
    else:
        # only this branch
        df_abs = df_abs.merge(
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

            # أخذ غير المبررة فقط
            df_eff = df_abs[df_abs["justifie"] != "Oui"].copy()

            if df_eff.empty:
                st.info("كل الغيابات مبررة، ما فماش تنبيهات.")
            else:
                # X ساعات قبل بلوغ 10%
                X = st.number_input(
                    "أرني المتكوّنين اللي بقايلهم أقل من X ساعات قبل بلوغ 10٪ غيابات",
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

                alerts = grp[(grp["remaining_before_10"] > 0) & (grp["remaining_before_10"] <= X)].copy()

                if alerts.empty:
                    st.success("💚 لا يوجد متكوّنون قريبين من 10٪ حسب الشرط الحالي.")
                else:
                    alerts["total_abs"] = alerts["total_abs"].round(2)
                    alerts["limit_10"] = alerts["limit_10"].round(2)
                    alerts["remaining_before_10"] = alerts["remaining_before_10"].round(2)
                    alerts = alerts.sort_values("remaining_before_10")

                    st.markdown("### قائمة المتكوّنين القريبين من بلوغ 10٪")
                    st.dataframe(
                        alerts[[
                            "nom", "spec", "matiere",
                            "total_abs", "limit_10", "remaining_before_10"
                        ]].rename(columns={
                            "nom": "المتكوّن",
                            "spec": "التخصّص",
                            "matiere": "المادة",
                            "total_abs": "مجموع الغياب",
                            "limit_10": "حد 10٪",
                            "remaining_before_10": "الباقي قبل 10٪",
                        }),
                        use_container_width=True
                    )
