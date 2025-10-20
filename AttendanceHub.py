# AbsencesHub.py
# إدارة غيابات المتكوّنين (محليًا بدون Google Sheets)
# يحفظ البيانات في attn/index.json
# حساب الغياب = 10% من إجمالي ساعات البرنامج
# "الغياب بشهادة طبية" لا يحتسب ضمن ساعات الغياب

import os, json, uuid, urllib.parse
from datetime import datetime, date
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# ---------- إعداد عام ----------
st.set_page_config(page_title="منظومة الغيابات", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>🕒 منظومة الغيابات للمتكوّنين</h1>
  <p>تسجيل الحصص والغيابات | حساب 10% | رسالة واتساب</p>
</div>
<hr/>
""", unsafe_allow_html=True)

# ---------- تخزين محلّي ----------
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "attn")
IDX_PATH = os.path.join(DATA_DIR, "index.json")

def ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(IDX_PATH):
        with open(IDX_PATH, "w", encoding="utf-8") as f:
            json.dump({"trainees": [], "subjects": [], "sessions": []}, f, ensure_ascii=False, indent=2)

def load_db() -> Dict[str, Any]:
    ensure_store()
    try:
        with open(IDX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"trainees": [], "subjects": [], "sessions": []}

def save_db(db: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = IDX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, IDX_PATH)

def normalize_tn_phone(s: str) -> str:
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if digits.startswith("216"): return digits
    if len(digits) == 8: return "216" + digits
    return digits

def wa_link(number: str, message: str) -> str:
    num = "".join(c for c in str(number) if c.isdigit())
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}" if num else ""

# ---------- ثوابت ----------
ABS_LIMIT_PCT = 10.0  # % الحد الأقصى للغياب

# ---------- Tabs ----------
tab_mng, tab_sess, tab_dash = st.tabs(["👥 المتكوّنون والمواد", "🗓️ تسجيل الحصص/الغياب", "📊 ملخّص وحسابات"])

db = load_db()

# ========== تبويب إدارة المتكوّنين والمواد ==========
with tab_mng:
    colA, colB = st.columns(2)

    with colA:
        st.subheader("➕ إضافة متكوّن")
        with st.form("add_trainee"):
            tr_name = st.text_input("الاسم الكامل")
            tr_phone = st.text_input("الهاتف")
            total_hours = st.number_input("إجمالي ساعات البرنامج", min_value=0.0, step=1.0, help="يُستعمل لاحتساب 10%")
            weekly_hours = st.number_input("ساعات الأسبوع (اختياري)", min_value=0.0, step=1.0, help="لتسهيل إدخال ساعات الحصّة default")
            submitted = st.form_submit_button("حفظ المتكوّن")
        if submitted:
            if not tr_name.strip() or not tr_phone.strip() or total_hours <= 0:
                st.error("❌ الاسم/الهاتف مطلوبان، وإجمالي الساعات يجب أن يكون أكبر من 0.")
            else:
                new_rec = {
                    "id": uuid.uuid4().hex[:10],
                    "name": tr_name.strip(),
                    "phone": normalize_tn_phone(tr_phone),
                    "total_hours": float(total_hours),
                    "weekly_hours": float(weekly_hours),
                    "created_at": datetime.now().isoformat(timespec="seconds")
                }
                db["trainees"].append(new_rec)
                save_db(db)
                st.success("✅ تمّت إضافة المتكوّن.")

        if db["trainees"]:
            st.markdown("#### قائمة المتكوّنين")
            tdf = pd.DataFrame(db["trainees"])
            tdf["الهاتف"] = tdf["phone"]
            tdf["الاسم"] = tdf["name"]
            tdf["إجمالي الساعات"] = tdf["total_hours"]
            tdf["ساعات الأسبوع"] = tdf["weekly_hours"]
            tdf["أضيف في"] = pd.to_datetime(tdf["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(tdf[["الاسم","الهاتف","إجمالي الساعات","ساعات الأسبوع","أضيف في"]], use_container_width=True)

    with colB:
        st.subheader("📚 المواد")
        with st.form("add_subject"):
            subj_name = st.text_input("اسم المادة")
            ok_s = st.form_submit_button("إضافة مادة")
        if ok_s:
            if not subj_name.strip():
                st.error("❌ اسم المادة مطلوب.")
            else:
                if subj_name.strip().lower() in [s["name"].lower() for s in db["subjects"]]:
                    st.warning("⚠️ المادة موجودة من قبل.")
                else:
                    db["subjects"].append({"id": uuid.uuid4().hex[:10], "name": subj_name.strip()})
                    save_db(db)
                    st.success("✅ تمّت إضافة المادة.")

        if db["subjects"]:
            sdf = pd.DataFrame(db["subjects"])
            sdf["المادة"] = sdf["name"]
            st.dataframe(sdf[["المادة"]], use_container_width=True)

# ========== تبويب تسجيل الحصص/الغياب ==========
with tab_sess:
    st.subheader("تسجيل حصة (حاضر/غائب)")

    if not db["trainees"] or not db["subjects"]:
        st.info("أضِف على الأقل متكوّنًا ومادة واحدة أولاً.")
    else:
        # اختيار متكوّن
        tr_options = {f"{t['name']} — +{t['phone']}": t for t in db["trainees"]}
        tr_key = st.selectbox("اختر المتكوّن", list(tr_options.keys()))
        tr = tr_options[tr_key]

        # اختيار مادة
        sub_options = {s["name"]: s for s in db["subjects"]}
        sub_key = st.selectbox("اختر المادة", list(sub_options.keys()))
        subj = sub_options[sub_key]

        sess_date = st.date_input("تاريخ الحصة", value=date.today())
        default_hours = float(tr.get("weekly_hours", 0.0)) if float(tr.get("weekly_hours", 0.0)) > 0 else 2.0
        sess_hours = st.number_input("ساعات الحصة", min_value=0.5, step=0.5, value=default_hours)
        is_absent = st.checkbox("المتكوّن غائب؟")
        has_medical = False
        if is_absent:
            has_medical = st.checkbox("غياب بشهادة طبية؟ (لا يُحتسب ضمن الغياب)")

        note = st.text_area("ملاحظة (اختياري)")

        if st.button("💾 حفظ الحصة"):
            rec = {
                "id": uuid.uuid4().hex[:10],
                "trainee_id": tr["id"],
                "subject_id": subj["id"],
                "date": sess_date.isoformat(),
                "hours": float(sess_hours),
                "is_absent": bool(is_absent),
                "medical": bool(has_medical),
                "note": note.strip(),
                "ts": datetime.now().isoformat(timespec="seconds")
            }
            db["sessions"].append(rec)
            save_db(db)
            st.success("✅ تمّ الحفظ.")

        # عرض حصص المتكوّن
        sess = [s for s in db["sessions"] if s["trainee_id"] == tr["id"]]
        if sess:
            df = pd.DataFrame(sess)
            # enrich
            sub_map = {s["id"]: s["name"] for s in db["subjects"]}
            df["التاريخ"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["المادة"] = df["subject_id"].map(sub_map)
            df["الساعات"] = df["hours"].astype(float)
            df["غائب؟"] = df["is_absent"].map({True:"نعم", False:"لا"})
            df["طبي؟"] = df["medical"].map({True:"نعم", False:"لا"})
            df = df.sort_values("date")
            st.markdown("#### حصص المتكوّن")
            st.dataframe(df[["التاريخ","المادة","الساعات","غائب؟","طبي؟","note"]], use_container_width=True)

# ========== تبويب الملخّص والحسابات ==========
with tab_dash:
    st.subheader("حساب الغياب ونسبة 10% + رسالة واتساب")

    if not db["trainees"]:
        st.info("لا يوجد متكوّنون.")
    else:
        tr_options = {f"{t['name']} — +{t['phone']}": t for t in db["trainees"]}
        tr_key = st.selectbox("اختر المتكوّن لحساب الملخّص", list(tr_options.keys()), key="dash_tr")
        tr = tr_options[tr_key]

        # فلترة حسب مادة (اختياري)
        sub_filter = st.selectbox("فلترة حسب مادة (اختياري)", ["(الكل)"] + [s["name"] for s in db["subjects"]])

        # سحب كل الحصص
        sess_all = [s for s in db["sessions"] if s["trainee_id"] == tr["id"]]
        if sub_filter != "(الكل)":
            subj_id = next((s["id"] for s in db["subjects"] if s["name"] == sub_filter), None)
            sess_all = [s for s in sess_all if s["subject_id"] == subj_id]

        total_program_hours = float(tr.get("total_hours", 0.0))
        if total_program_hours <= 0:
            st.error("هذا المتكوّن لا يملك إجمالي ساعات برنامج صالح. عدّل بياناته أولاً.")
        else:
            # الساعات المجدولة = مجموع ساعات كل الحصص المسجلة (حاضر + غائب)
            scheduled_hours = float(sum(s["hours"] for s in sess_all))
            # ساعات الغياب الفعلية = مجموع ساعات الحصص الغائبة بدون شهادة طبية
            absent_effective = float(sum(s["hours"] for s in sess_all if s["is_absent"] and not s["medical"]))

            # نسبة الغياب (من البرنامج الكلي) = absent_effective / total_program_hours
            pct_abs = (absent_effective / total_program_hours * 100.0) if total_program_hours > 0 else 0.0

            # الباقي قبل بلوغ 10% (بالساعات)
            max_abs_hours = 0.10 * total_program_hours
            remain_before_10 = max(0.0, max_abs_hours - absent_effective)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("📚 إجمالي برنامج", f"{total_program_hours:.1f} س")
            c2.metric("🗓️ مسجّل لحدّ الآن", f"{scheduled_hours:.1f} س")
            c3.metric("⛔ غياب فعلي", f"{absent_effective:.1f} س")
            c4.metric("📊 % الغياب", f"{pct_abs:.2f}%")
            c5.metric("🟢 الباقي قبل 10%", f"{remain_before_10:.1f} س")

            st.caption("ملاحظة: الغياب بشهادة طبية لا يُحتسب في ⛔ غياب فعلي.")

            # جدول تفصيلي حسب المادة
            if sess_all:
                df = pd.DataFrame(sess_all)
                sub_map = {s["id"]: s["name"] for s in db["subjects"]}
                df["المادة"] = df["subject_id"].map(sub_map)
                df["حصة غياب فعلي"] = df.apply(lambda r: (r["hours"] if (r["is_absent"] and not r["medical"]) else 0.0), axis=1)
                grp = df.groupby("المادة").agg(
                    حصص=("id","count"),
                    ساعات_مجدولة=("hours","sum"),
                    غياب_فعلي=("حصة غياب فعلي","sum"),
                ).reset_index()
                st.markdown("#### تفاصيل حسب المادة")
                st.dataframe(grp, use_container_width=True)

            # رسالة واتساب جاهزة
            msg = (
                f"سلام {tr['name']},\n"
                f"نعلّموك بعد المتابعة إنّو ساعات الغياب الفعلية: {absent_effective:.1f} س،\n"
                f"ونسبة الغياب من برنامجك: {pct_abs:.2f}%.\n"
                f"باقي عندك قبل 10%: {remain_before_10:.1f} س.\n"
                f"لو عندك شهادة طبية لأي غياب، بعثلنا نسخة.\n"
                f"شكراً."
            )
            link = wa_link(tr["phone"], msg)
            if link:
                st.markdown(f"[📲 إرسال رسالة واتساب للمتكوّن]({link})")
            else:
                st.warning("رقم هاتف المتكوّن غير صالح لإرسال واتساب.")

        # إدارة سريعة: حذف جلسة إن لزم
        st.markdown("---")
        st.subheader("🧹 إدارة سريعة للجلسات")
        sess_all_sorted = sorted([s for s in db["sessions"] if s["trainee_id"] == tr["id"]], key=lambda x: (x["date"], x["ts"]))
        if sess_all_sorted:
            opts = [
                f"{i+1}. {s['date']} — {next((x['name'] for x in db['subjects'] if x['id']==s['subject_id']), '?')} — {s['hours']}س — {'غائب' if s['is_absent'] else 'حاضر'}{' (طبي)' if s['medical'] else ''}"
                for i,s in enumerate(sess_all_sorted)
            ]
            pick = st.selectbox("اختر جلسة للحذف (اختياري)", ["(لا شيء)"] + opts)
            if pick != "(لا شيء)":
                idx = opts.index(pick)
                if st.button("❗ حذف الجلسة المختارة"):
                    del_id = sess_all_sorted[idx]["id"]
                    db["sessions"] = [s for s in db["sessions"] if s["id"] != del_id]
                    save_db(db)
                    st.success("تم الحذف.")
        else:
            st.caption("لا توجد جلسات لهذا المتكوّن بعد.")
