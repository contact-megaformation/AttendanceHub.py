# AttendanceHub.py
# إدارة الغيابات للمتكوّنين — تخزين محلّي (JSON) — بدون Google Sheets
# ميزات: فروع (بكلمة سر) + اختصاصات + مواد (ساعات/أسبوع + إجمالي ساعات)
#        متكوّنون (رقم المتكوّن + رقم الولي) + غيابات مع شهادة طبية
#        واتساب للمتكوّن أو الولي + تقارير
# ملاحظة: حماية الفروع بكلمة سر عبر st.secrets['branch_passwords'] (MB/BZ)

import os, json, uuid
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# =============== إعداد الصفحة ===============
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style="text-align:center">
  <h1>🧾 Attendance Hub — إدارة غيابات المتكوّنين</h1>
  <p>فروع (محمية بكلمة سر) + اختصاصات + مواد + غيابات + واتساب</p>
</div>
<hr>
""", unsafe_allow_html=True)

# =============== مسارات التخزين ===============
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "attendance_data")
DB_PATH  = os.path.join(DATA_DIR, "attendance_db.json")

def ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "branches": ["Menzel Bourguiba", "Bizerte"],
                "specialties": [],            # قائمة الاختصاصات
                "subjects": [],               # [{id, name, branch, specialty, weekly_hours, total_hours}]
                "trainees": [],               # [{id, name, phone, guardian_phone, branch, specialty}]
                "absences": []                # [{id, trainee_id, subject_id, date, hours, medical_excused, note}]
            }, f, ensure_ascii=False, indent=2)

def load_db() -> Dict[str, Any]:
    ensure_store()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"branches": [], "specialties": [], "subjects": [], "trainees": [], "absences": []}

def save_db(db: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, DB_PATH)

def human_dt(ts) -> str:
    dt = pd.to_datetime(ts, errors="coerce")
    if pd.isna(dt): return "-"
    return dt.strftime("%Y-%m-%d")

def new_id() -> str:
    return uuid.uuid4().hex[:10]

# =============== دوال مساعدة للواتساب ===============
def normalize_phone(s: str) -> str:
    s = str(s or "")
    digits = "".join([c for c in s if c.isdigit()])
    if digits.startswith("216"):
        return digits
    if len(digits) == 8:
        return "216" + digits
    return digits

def wa_link(number: str, message: str) -> str:
    n = normalize_phone(number)
    if not n: return ""
    from urllib.parse import quote
    return f"https://wa.me/{n}?text={quote(message)}"

# =============== حماية الفروع بكلمة سر ===============
def _branch_passwords() -> Dict[str, str]:
    """يقرى كلمات سر الفروع من secrets، وإلا يستعمل قيم افتراضية."""
    try:
        b = st.secrets["branch_passwords"]
        return {
            "Menzel Bourguiba": str(b.get("MB", "MB_2025!")),
            "Bizerte": str(b.get("BZ", "BZ_2025!")),
        }
    except Exception:
        return {"Menzel Bourguiba": "MB_2025!", "Bizerte": "BZ_2025!"}

def _branch_unlocked(branch: str) -> bool:
    ok = st.session_state.get(f"branch_ok::{branch}", False)
    ts = st.session_state.get(f"branch_ok_at::{branch}")
    if not (ok and ts): return False
    return (datetime.now() - ts) <= timedelta(minutes=30)

def branch_lock_ui(branch: str, ns_key: str):
    """يرسم UI للفرع: إدخال كلمة سر/قفل. يوقف التاب إذا مش مفتوح."""
    pw_map = _branch_passwords()
    if _branch_unlocked(branch):
        c1, c2 = st.columns([3,1])
        c1.success(f"✅ فرع '{branch}' مفتوح (صالح لـ 30 دقيقة).")
        if c2.button("قفل الفرع", key=f"lock::{ns_key}::{branch}"):
            st.session_state[f"branch_ok::{branch}"] = False
            st.session_state[f"branch_ok_at::{branch}"] = None
            st.rerun()
        return True
    else:
        st.info(f"🔐 أدخل كلمة سرّ فرع: **{branch}** للمتابعة")
        pw_try = st.text_input("كلمة سرّ الفرع", type="password", key=f"pw::{ns_key}::{branch}")
        if st.button("فتح الفرع", key=f"open::{ns_key}::{branch}"):
            if pw_try == pw_map.get(branch, ""):
                st.session_state[f"branch_ok::{branch}"] = True
                st.session_state[f"branch_ok_at::{branch}"] = datetime.now()
                st.success("تمّ الفتح ✅")
                st.rerun()
            else:
                st.error("❌ كلمة سر غير صحيحة.")
        st.stop()

# =============== تحميل قاعدة البيانات ===============
db = load_db()

# =============== Tabs ===============
tab_cfg, tab_tr, tab_abs, tab_rpt, tab_msg = st.tabs([
    "⚙️ ضبط النظام", "👥 المتكوّنون", "🕓 الغيابات", "📊 التقارير", "💬 الرسائل"
])

# ========================== (1) ضبط النظام ==========================
with tab_cfg:
    st.subheader("الفروع و الاختصاصات و المواد")

    # ------ إدارة الاختصاصات ------
    with st.expander("📚 الاختصاصات", expanded=True):
        col_s1, col_s2 = st.columns([3,2])
        with col_s1:
            st.write("الاختصاصات الحالية:")
            if len(db["specialties"]) == 0:
                st.info("لا توجد اختصاصات بعد.")
            else:
                st.dataframe(pd.DataFrame({"الاختصاص": db["specialties"]}), use_container_width=True)

        with col_s2:
            new_spec = st.text_input("➕ إضافة اختصاص", key="cfg_add_spec_input")
            if st.button("إضافة الاختصاص", key="cfg_add_spec_btn"):
                spec = new_spec.strip()
                if not spec:
                    st.error("اكتب اسم اختصاص.")
                elif spec in db["specialties"]:
                    st.warning("الاختصاص موجود.")
                else:
                    db["specialties"].append(spec)
                    save_db(db)
                    st.success("تمّت الإضافة ✅")
                    st.rerun()

            if db["specialties"]:
                del_spec = st.selectbox("🗑️ حذف اختصاص", db["specialties"], key="cfg_del_spec_sel")
                if st.button("حذف", key="cfg_del_spec_btn"):
                    used_in_subjects = any(s["specialty"] == del_spec for s in db["subjects"])
                    used_in_trainees = any(t["specialty"] == del_spec for t in db["trainees"])
                    if used_in_subjects or used_in_trainees:
                        st.error("لا يمكن الحذف: الاختصاص مستعمل في مواد/متكوّنين.")
                    else:
                        db["specialties"] = [s for s in db["specialties"] if s != del_spec]
                        save_db(db)
                        st.success("تمّ الحذف ✅")
                        st.rerun()

    st.markdown("---")

    # ------ إدارة المواد ------
    with st.expander("📘 المواد لكل فرع + اختصاص", expanded=True):
        col_a, col_b = st.columns(2)

        with col_a:
            st.write("قائمة المواد")
            if not db["subjects"]:
                st.info("لا توجد مواد بعد.")
            else:
                subs = pd.DataFrame(db["subjects"])
                if not subs.empty:
                    subs_disp = subs.copy()
                    subs_disp["الفرع"] = subs_disp["branch"]
                    subs_disp["الاختصاص"] = subs_disp["specialty"]
                    subs_disp["المادة"] = subs_disp["name"]
                    subs_disp["س/أسبوع"] = subs_disp["weekly_hours"]
                    subs_disp["إجمالي ساعات"] = subs_disp["total_hours"]
                    st.dataframe(subs_disp[["الفرع","الاختصاص","المادة","س/أسبوع","إجمالي ساعات"]], use_container_width=True, height=320)

        with col_b:
            st.write("➕ إضافة/تعديل مادة")
            branch_sel = st.selectbox("الفرع", db["branches"], key="cfg_sub_branch")
            spec_sel   = st.selectbox("الاختصاص", db["specialties"] or ["—"], key="cfg_sub_spec")
            sub_name   = st.text_input("اسم المادة", key="cfg_sub_name")
            wh         = st.number_input("ساعات أسبوعية", min_value=0.0, step=1.0, key="cfg_sub_wh")
            th         = st.number_input("إجمالي ساعات المادة", min_value=0.0, step=1.0, key="cfg_sub_th")

            if st.button("حفظ مادة", key="cfg_sub_save"):
                if not sub_name.strip():
                    st.error("اسم المادة مطلوب.")
                elif spec_sel == "—" or not spec_sel:
                    st.error("اختر اختصاص.")
                else:
                    exist = next((s for s in db["subjects"]
                                  if s["name"].strip().lower()==sub_name.strip().lower()
                                  and s["branch"]==branch_sel and s["specialty"]==spec_sel), None)
                    if exist:
                        exist["weekly_hours"] = float(wh)
                        exist["total_hours"]  = float(th)
                        save_db(db); st.success("تمّ التحديث ✅")
                    else:
                        db["subjects"].append({
                            "id": new_id(),
                            "name": sub_name.strip(),
                            "branch": branch_sel,
                            "specialty": spec_sel,
                            "weekly_hours": float(wh),
                            "total_hours": float(th)
                        })
                        save_db(db); st.success("تمّت الإضافة ✅")
                    st.rerun()

            existing_subs = [f"{s['name']} — {s['branch']} — {s['specialty']}" for s in db["subjects"]]
            if existing_subs:
                del_pick = st.selectbox("🗑️ اختر مادة للحذف", existing_subs, key="cfg_sub_del_pick")
                if st.button("حذف المادة", key="cfg_sub_del_btn"):
                    idx = existing_subs.index(del_pick)
                    sub_id = db["subjects"][idx]["id"]
                    if any(a["subject_id"] == sub_id for a in db["absences"]):
                        st.error("لا يمكن الحذف: المادة مستعملة في سجلات غياب.")
                    else:
                        db["subjects"].pop(idx)
                        save_db(db)
                        st.success("تمّ الحذف ✅")
                        st.rerun()

# ========================== (2) المتكوّنون ==========================
with tab_tr:
    st.subheader("إدارة المتكوّنين")

    # اختيار الفرع (مع كلمة سر)
    tr_branch_view = st.selectbox("الفرع", db["branches"], key="tr_view_branch")
    branch_lock_ui(tr_branch_view, ns_key="tab_tr")

    # قائمة المتكوّنين (فرع فقط)
    col_tl, col_tr = st.columns([3,2])
    with col_tl:
        st.write(f"القائمة — فرع {tr_branch_view}")
        tr_df = pd.DataFrame([t for t in db["trainees"] if t["branch"] == tr_branch_view])
        if tr_df.empty:
            st.info("لا يوجد متكوّنون بعد في هذا الفرع.")
        else:
            disp = tr_df.copy()
            disp["الاسم"] = disp["name"]
            disp["الهاتف"] = disp["phone"]
            disp["هاتف الولي"] = disp["guardian_phone"]
            disp["الاختصاص"] = disp["specialty"]
            st.dataframe(disp[["الاسم","الهاتف","هاتف الولي","الاختصاص"]], use_container_width=True, height=380)

    # إضافة/تعديل/حذف (مقيّد بالفرع المفتوح)
    with col_tr:
        st.write("➕ إضافة متكوّن")
        t_name  = st.text_input("الاسم و اللقب", key="tr_add_name")
        # الفرع ثابت = المختار
        st.selectbox("الفرع", [tr_branch_view], index=0, key="tr_add_branch_show", disabled=True)
        t_spec  = st.selectbox("الاختصاص", db["specialties"] or ["—"], key="tr_add_spec")
        t_phone = st.text_input("هاتف المتكوّن", key="tr_add_phone")
        g_phone = st.text_input("هاتف الولي", key="tr_add_gphone")

        if st.button("إضافة", key="tr_add_btn"):
            if not t_name.strip():
                st.error("الاسم مطلوب.")
            elif not t_spec or t_spec == "—":
                st.error("الاختصاص مطلوب.")
            else:
                db["trainees"].append({
                    "id": new_id(),
                    "name": t_name.strip(),
                    "branch": tr_branch_view,  # فرع محمي
                    "specialty": t_spec,
                    "phone": normalize_phone(t_phone),
                    "guardian_phone": normalize_phone(g_phone)
                })
                save_db(db)
                st.success("تمّت الإضافة ✅")
                st.rerun()

        st.markdown("---")

        # تعديل/حذف متكوّن (في هذا الفرع فقط)
        tr_list = [t for t in db["trainees"] if t["branch"] == tr_branch_view]
        if tr_list:
            edit_pick = st.selectbox("✏️ اختر متكوّن للتعديل/الحذف",
                                     [f"{t['name']} — {t['specialty']}" for t in tr_list],
                                     key="tr_edit_pick")
            idx = [f"{t['name']} — {t['specialty']}" for t in tr_list].index(edit_pick)
            cur = tr_list[idx]

            ename  = st.text_input("الاسم", value=cur["name"], key=f"tr_edit_name_{cur['id']}")
            # الفرع ثابت
            st.selectbox("الفرع", [tr_branch_view], index=0, key=f"tr_edit_branch_{cur['id']}", disabled=True)
            espec  = st.selectbox("الاختصاص", db["specialties"] or ["—"],
                                  index=(db["specialties"].index(cur["specialty"]) if cur["specialty"] in db["specialties"] else 0),
                                  key=f"tr_edit_spec_{cur['id']}")
            ephone = st.text_input("هاتف المتكوّن", value=cur["phone"], key=f"tr_edit_phone_{cur['id']}")
            egphone= st.text_input("هاتف الولي", value=cur["guardian_phone"], key=f"tr_edit_gphone_{cur['id']}")

            c1, c2 = st.columns(2)
            if c1.button("💾 حفظ التعديلات", key=f"tr_edit_save_{cur['id']}"):
                if not ename.strip():
                    st.error("الاسم مطلوب.")
                elif not espec or espec == "—":
                    st.error("الاختصاص مطلوب.")
                else:
                    # تحديث في db الأصلي
                    for t in db["trainees"]:
                        if t["id"] == cur["id"]:
                            t["name"] = ename.strip()
                            t["specialty"] = espec
                            t["phone"] = normalize_phone(ephone)
                            t["guardian_phone"] = normalize_phone(egphone)
                            break
                    save_db(db)
                    st.success("تمّ الحفظ ✅")
                    st.rerun()

            if c2.button("🗑️ حذف المتكوّن", key=f"tr_edit_del_{cur['id']}"):
                tid = cur["id"]
                db["absences"] = [a for a in db["absences"] if a["trainee_id"] != tid]
                db["trainees"]  = [t for t in db["trainees"] if t["id"] != tid]
                save_db(db)
                st.success("تمّ الحذف ✅")
                st.rerun()

# ========================== (3) الغيابات ==========================
with tab_abs:
    st.subheader("تسجيل الغيابات / تعديلها")

    if not db["trainees"]:
        st.info("لا يوجد متكوّنون. أضف من تبويب المتكوّنين.")
        st.stop()

    col_f1, col_f2 = st.columns(2)
    pick_branch = col_f1.selectbox("الفرع", db["branches"], key="abs_pick_branch")
    # حماية الفرع
    branch_lock_ui(pick_branch, ns_key="tab_abs")

    specs_in_branch = sorted(list({t["specialty"] for t in db["trainees"] if t["branch"] == pick_branch}))
    if not specs_in_branch:
        col_f2.info("لا اختصاصات في هذا الفرع.")
        st.stop()
    pick_spec = col_f2.selectbox("الاختصاص", specs_in_branch, key="abs_pick_spec")

    trainees_scope = [t for t in db["trainees"] if t["branch"]==pick_branch and t["specialty"]==pick_spec]
    if not trainees_scope:
        st.info("لا متكوّنين في هذا الاختصاص.")
        st.stop()

    tr_pick = st.selectbox("اختر المتكوّن",
                           [f"{t['name']} — {t['specialty']}" for t in trainees_scope],
                           key="abs_tr_pick")
    tr_idx = [f"{t['name']} — {t['specialty']}" for t in trainees_scope].index(tr_pick)
    tr_obj = trainees_scope[tr_idx]

    sub_scope = [s for s in db["subjects"] if s["branch"]==pick_branch and s["specialty"]==pick_spec]
    if not sub_scope:
        st.warning("ما فماش مواد مضبوطة لهذا الفرع/الاختصاص. أضف مواد من ضبط النظام.")
        st.stop()

    sub_pick = st.selectbox("المادة",
                            [f"{s['name']} — س/أسبوع:{s['weekly_hours']} — إجمالي:{s['total_hours']}" for s in sub_scope],
                            key="abs_sub_pick")
    sub_idx = [f"{s['name']} — س/أسبوع:{s['weekly_hours']} — إجمالي:{s['total_hours']}" for s in sub_scope].index(sub_pick)
    sub_obj = sub_scope[sub_idx]

    total_hours = float(sub_obj.get("total_hours", 0.0))
    limit_hours = round(total_hours * 0.10, 2)
    abs_for_this = [a for a in db["absences"] if a["trainee_id"]==tr_obj["id"] and a["subject_id"]==sub_obj["id"]]
    non_excused_hours = sum(float(a.get("hours", 0.0)) for a in abs_for_this if not a.get("medical_excused", False))
    remaining = max(limit_hours - non_excused_hours, 0.0)

    st.info(f"سقف الغياب (10% من {total_hours} س) = **{limit_hours} س** | غير معذور مسجّل: **{non_excused_hours} س** | الباقي قبل السقف: **{remaining} س**")

    st.markdown("### ➕ تسجيل غياب")
    with st.form(f"abs_add_form_{tr_obj['id']}_{sub_obj['id']}"):
        adate = st.date_input("التاريخ", value=date.today(), key=f"abs_add_date_{tr_obj['id']}")
        ahours= st.number_input("عدد الساعات الغائبة", min_value=0.0, step=1.0, key=f"abs_add_hours_{tr_obj['id']}")
        med   = st.checkbox("شهادة طبية (غياب معذور — ما يتحسبش)", key=f"abs_add_med_{tr_obj['id']}")
        note  = st.text_area("ملاحظة (اختياري)", key=f"abs_add_note_{tr_obj['id']}")
        subm  = st.form_submit_button("حفظ الغياب", use_container_width=True)
    if subm:
        if ahours <= 0:
            st.error("الساعات لازم > 0.")
        else:
            db["absences"].append({
                "id": new_id(),
                "trainee_id": tr_obj["id"],
                "subject_id": sub_obj["id"],
                "date": str(adate),
                "hours": float(ahours),
                "medical_excused": bool(med),
                "note": note.strip()
            })
            save_db(db)
            st.success("تمّ الحفظ ✅")
            st.rerun()

    st.markdown("### ✏️ تعديل/حذف الغيابات السابقة")
    if not abs_for_this:
        st.info("لا توجد غيابات مسجّلة لهذه المادة.")
    else:
        gdf = pd.DataFrame(abs_for_this).copy()
        gdf["التاريخ"] = gdf["date"].apply(human_dt)
        gdf["ساعات"] = gdf["hours"]
        gdf["معذور؟"] = gdf["medical_excused"].apply(lambda x: "نعم" if x else "لا")
        gdf["ملاحظة"] = gdf["note"]
        st.dataframe(gdf[["التاريخ","ساعات","معذور؟","ملاحظة"]], use_container_width=True, height=260)

        pick_abs = st.selectbox(
            "اختر سجل غياب للتعديل/الحذف",
            [f"{a['date']} — {a['hours']}س — {'معذور' if a.get('medical_excused', False) else 'غير معذور'} — {a['id']}"
             for a in abs_for_this],
            key=f"abs_edit_pick_{tr_obj['id']}"
        )
        pick_id = pick_abs.split("—")[-1].strip()
        cur_abs = next(a for a in abs_for_this if a["id"] == pick_id)

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            edate = st.date_input("التاريخ", value=pd.to_datetime(cur_abs["date"]).date(), key=f"abs_edit_date_{pick_id}")
            ehours= st.number_input("الساعات", min_value=0.0, step=1.0, value=float(cur_abs["hours"]), key=f"abs_edit_hours_{pick_id}")
            emed  = st.checkbox("شهادة طبية (معذور)", value=bool(cur_abs.get("medical_excused", False)), key=f"abs_edit_med_{pick_id}")
        with col_e2:
            enote = st.text_area("ملاحظة", value=str(cur_abs.get("note","")), key=f"abs_edit_note_{pick_id}")
            c_b1, c_b2 = st.columns(2)
            if c_b1.button("💾 حفظ التعديلات", key=f"abs_edit_save_{pick_id}"):
                cur_abs["date"] = str(edate)
                cur_abs["hours"] = float(ehours)
                cur_abs["medical_excused"] = bool(emed)
                cur_abs["note"] = enote.strip()
                save_db(db)
                st.success("تم الحفظ ✅")
                st.rerun()
            if c_b2.button("🗑️ حذف السجل", key=f"abs_edit_del_{pick_id}"):
                db["absences"] = [a for a in db["absences"] if a["id"] != pick_id]
                save_db(db)
                st.success("تم الحذف ✅")
                st.rerun()

# ========================== (4) التقارير ==========================
with tab_rpt:
    st.subheader("تقارير / ملخصات")
    if not db["trainees"] or not db["subjects"]:
        st.info("أضف متكوّنين ومواد أولاً.")
        st.stop()

    col_r1, col_r2, col_r3 = st.columns(3)
    r_branch = col_r1.selectbox("الفرع", db["branches"], key="rpt_branch")
    branch_lock_ui(r_branch, ns_key="tab_rpt")  # حماية الفرع في التقارير

    r_specs = sorted(list({t["specialty"] for t in db["trainees"] if t["branch"] == r_branch}))
    if not r_specs:
        st.info("لا اختصاصات في هذا الفرع.")
        st.stop()
    r_spec = col_r2.selectbox("الاختصاص", r_specs, key="rpt_spec")
    r_subs = [s for s in db["subjects"] if s["branch"]==r_branch and s["specialty"]==r_spec]
    if not r_subs:
        st.info("لا مواد لهذا الاختصاص في هذا الفرع.")
        st.stop()
    r_sub = col_r3.selectbox("المادة", [f"{s['name']} — إجمالي:{s['total_hours']}" for s in r_subs], key="rpt_sub")
    r_sub_id = r_subs[[f"{s['name']} — إجمالي:{s['total_hours']}" for s in r_subs].index(r_sub)]["id"]
    r_total = float(next(s for s in db["subjects"] if s["id"]==r_sub_id)["total_hours"])
    r_limit = round(r_total*0.10, 2)

    trainees_scope = [t for t in db["trainees"] if t["branch"]==r_branch and t["specialty"]==r_spec]
    rows = []
    for t in trainees_scope:
        abs_t = [a for a in db["absences"] if a["trainee_id"]==t["id"] and a["subject_id"]==r_sub_id]
        non_exc = sum(float(a["hours"]) for a in abs_t if not a.get("medical_excused", False))
        rows.append({
            "المتكوّن": t["name"],
            "الهاتف": t["phone"],
            "هاتف الولي": t["guardian_phone"],
            "غياب غير معذور (س)": non_exc,
            "سقف 10% (س)": r_limit,
            "المتبقّي قبل السقف (س)": max(r_limit - non_exc, 0.0)
        })
    rpt_df = pd.DataFrame(rows)
    st.dataframe(rpt_df, use_container_width=True)

# ========================== (5) الرسائل ==========================
with tab_msg:
    st.subheader("إرسال رسالة واتساب")
    if not db["trainees"]:
        st.info("لا يوجد متكوّنون.")
        st.stop()

    col_m1, col_m2, col_m3 = st.columns(3)
    m_branch = col_m1.selectbox("الفرع", db["branches"], key="msg_branch")
    branch_lock_ui(m_branch, ns_key="tab_msg")  # حماية الفرع في الرسائل

    m_specs  = sorted(list({t["specialty"] for t in db["trainees"] if t["branch"]==m_branch}))
    if not m_specs:
        st.info("لا اختصاصات في هذا الفرع.")
        st.stop()
    m_spec   = col_m2.selectbox("الاختصاص", m_specs, key="msg_spec")
    m_subs   = [s for s in db["subjects"] if s["branch"]==m_branch and s["specialty"]==m_spec]
    if not m_subs:
        st.info("لا مواد.")
        st.stop()
    m_sub_pick = col_m3.selectbox("المادة", [f"{s['name']} — إجمالي:{s['total_hours']}" for s in m_subs], key="msg_sub")

    m_sub = m_subs[[f"{s['name']} — إجمالي:{s['total_hours']}" for s in m_subs].index(m_sub_pick)]
    m_total = float(m_sub["total_hours"])
    m_limit = round(m_total*0.10, 2)

    m_trs = [t for t in db["trainees"] if t["branch"]==m_branch and t["specialty"]==m_spec]
    m_tr_pick = st.selectbox("المتكوّن", [f"{t['name']} — {t['specialty']}" for t in m_trs], key="msg_tr_pick")
    m_tr = m_trs[[f"{t['name']} — {t['specialty']}" for t in m_trs].index(m_tr_pick)]

    m_abs = [a for a in db["absences"] if a["trainee_id"]==m_tr["id"] and a["subject_id"]==m_sub["id"]]
    m_non_exc = sum(float(a["hours"]) for a in m_abs if not a.get("medical_excused", False))
    m_rest = max(m_limit - m_non_exc, 0.0)

    target = st.radio("المرسل إليه", ["المتكوّن","الولي"], horizontal=True, key=f"msg_target_radio_{m_tr['id']}")
    base_phone = m_tr["phone"] if target == "المتكوّن" else m_tr["guardian_phone"]

    default_msg = (
        f"السلام عليكم {m_tr['name']}،\n"
        f"بخصوص مادة: {m_sub['name']}\n"
        f"إجمالي الساعات: {m_total} س — سقف الغياب (10%): {m_limit} س\n"
        f"غيابات غير معذورة مسجّلة: {m_non_exc} س — المتبقي قبل تجاوز السقف: {m_rest} س.\n"
        f"يرجى الالتزام بالحضور. شكراً."
    )
    msg_text = st.text_area("نص الرسالة", value=default_msg, key=f"msg_text_{m_tr['id']}")
    if st.button("📲 فتح واتساب", key=f"msg_send_btn_{m_tr['id']}"):
        link = wa_link(base_phone, msg_text)
        if link:
            st.markdown(f"[افتح المحادثة الآن]({link})")
            st.info("اضغط على الرابط لفتح واتساب.")
        else:
            st.error("رقم الهاتف غير صالح.")
