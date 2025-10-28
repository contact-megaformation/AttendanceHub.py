import streamlit as st
import random
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

# ==========================
# English Exam — 4 Épreuves (with Audio Listening)
# Sections: Listening • Reading (Comprehension) • Use of English • Writing
# Levels: A1 / A2 / B1 / B2
# ==========================

st.set_page_config(page_title="English Exam — 4 Épreuves (Audio)", layout="wide")

# ---------- Styles ----------
st.markdown(
    """
    <style>
      .title {text-align:center; font-size: 36px; font-weight:800; margin-bottom:0}
      .subtitle {text-align:center; color:#555; margin-top:4px}
      .card {background:#fff; padding:18px 20px; border-radius:16px; box-shadow:0 6px 24px rgba(0,0,0,0.06); margin-bottom:12px}
      .muted {color:#666}
      .kpi {font-size:28px; font-weight:700}
      .badge {display:inline-block; padding:4px 10px; border-radius:999px; background:#eef2ff; color:#3730a3; font-weight:700; font-size:12px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='title'>English Placement / Exam</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>4 Épreuves • Listening (with Audio) / Reading / Use of English / Writing</div>", unsafe_allow_html=True)

# ---------- Config ----------
LEVEL_ORDER = ["A1", "A2", "B1", "B2"]
SECTION_ORDER = ["Listening", "Reading", "Use of English", "Writing"]

# time per section (minutes) — total shown on top
LEVEL_TIME = {
    "A1": {"Listening": 8, "Reading": 8, "Use of English": 8, "Writing": 15},
    "A2": {"Listening": 10, "Reading": 10, "Use of English": 10, "Writing": 20},
    "B1": {"Listening": 12, "Reading": 12, "Use of English": 12, "Writing": 25},
    "B2": {"Listening": 15, "Reading": 15, "Use of English": 15, "Writing": 30},
}
PASS_MARK = 60
Q_PER = {"Listening": 6, "Reading": 6, "Use of English": 8}

# ---------- Listening Bank ----------
L_BANK = {
    "A1": [
        {"q": "(Audio) 'Hello, my name is Anna. I am from Italy.' What is her name?",
         "options": ["Ana", "Anna", "Anne", "Anaa"], "answer": "Anna",
         "transcript": "Hello, my name is Anna. I am from Italy."},
        {"q": "(Audio) 'The bus leaves at half past three.' What time does the bus leave?",
         "options": ["3:30", "3:15", "3:45", "2:30"], "answer": "3:30",
         "transcript": "The bus leaves at half past three."},
        {"q": "(Audio) 'I work in a bank and I love my job.' Where does the speaker work?",
         "options": ["At a school", "In a bank", "At a shop", "In a hospital"], "answer": "In a bank",
         "transcript": "I work in a bank and I love my job."},
        {"q": "(Audio) 'Please open the window. It's very hot.' What does the speaker want?",
         "options": ["Close the door", "Open the window", "Turn on the TV", "Bring water"], "answer": "Open the window",
         "transcript": "Please open the window. It's very hot."},
        {"q": "(Audio) 'We have English on Monday and Wednesday.' When do they have English?",
         "options": ["Monday and Friday", "Tuesday and Thursday", "Monday and Wednesday", "Saturday only"], "answer": "Monday and Wednesday",
         "transcript": "We have English on Monday and Wednesday."},
        {"q": "(Audio) 'My phone number is zero nine eight seven.' What's the number?",
         "options": ["0987", "0978", "9870", "9087"], "answer": "0987",
         "transcript": "My phone number is zero nine eight seven."},
    ],
    "A2": [
        {"q": "(Audio) 'I'm looking for a cheaper hotel near the station.' What is the speaker looking for?",
         "options": ["An expensive hotel", "A cheaper hotel near the station", "A taxi", "A restaurant"], "answer": "A cheaper hotel near the station",
         "transcript": "I'm looking for a cheaper hotel near the station."},
        {"q": "(Audio) 'The museum opens at 10 but the guided tour starts at 11.' When does the tour start?",
         "options": ["10:00", "11:00", "09:30", "12:00"], "answer": "11:00",
         "transcript": "The museum opens at 10 but the guided tour starts at 11."},
        {"q": "(Audio) 'Could you send me the report by Friday?' What does he want?",
         "options": ["To meet Friday", "To send the report by Friday", "To call on Friday", "To delay the report"], "answer": "To send the report by Friday",
         "transcript": "Could you send me the report by Friday?"},
        {"q": "(Audio) 'There's heavy traffic, so I'll be about 15 minutes late.' What is the problem?",
         "options": ["Car broke down", "Heavy traffic", "Lost keys", "No petrol"], "answer": "Heavy traffic",
         "transcript": "There's heavy traffic, so I'll be about 15 minutes late."},
        {"q": "(Audio) 'Your package has arrived; you can collect it this afternoon.' What arrived?",
         "options": ["A letter", "A package", "A person", "A taxi"], "answer": "A package",
         "transcript": "Your package has arrived; you can collect it this afternoon."},
        {"q": "(Audio) 'I prefer tea to coffee, especially in the evening.' What does the speaker prefer?",
         "options": ["Coffee", "Tea", "Juice", "Water"], "answer": "Tea",
         "transcript": "I prefer tea to coffee, especially in the evening."},
    ],
    "B1": [
        {"q": "(Audio) 'Due to maintenance work, platform 3 is closed today.' What's closed?",
         "options": ["The station", "Platform 3", "The ticket office", "The train"], "answer": "Platform 3",
         "transcript": "Due to maintenance work, platform 3 is closed today."},
        {"q": "(Audio) 'I'll forward you the agenda and minutes after the meeting.' What will he send?",
         "options": ["Photos", "Agenda and minutes", "Invoice", "Invitation"], "answer": "Agenda and minutes",
         "transcript": "I'll forward you the agenda and minutes after the meeting."},
        {"q": "(Audio) 'The lecture has been postponed until next Thursday.' What happened to the lecture?",
         "options": ["Cancelled", "Postponed", "Moved today", "Finished"], "answer": "Postponed",
         "transcript": "The lecture has been postponed until next Thursday."},
        {"q": "(Audio) 'We need to cut costs without compromising quality.' What do they need to do?",
         "options": ["Increase costs", "Cut costs", "Hire more", "Stop production"], "answer": "Cut costs",
         "transcript": "We need to cut costs without compromising quality."},
        {"q": "(Audio) 'There will be scattered showers in the north.' What's the weather in the north?",
         "options": ["Sunny", "Windy", "Showers", "Snow"], "answer": "Showers",
         "transcript": "There will be scattered showers in the north."},
        {"q": "(Audio) 'Passengers must keep their luggage with them at all times.' What must passengers do?",
         "options": ["Leave luggage", "Check luggage", "Keep luggage with them", "Pay for luggage"], "answer": "Keep luggage with them",
         "transcript": "Passengers must keep their luggage with them at all times."},
    ],
    "B2": [
        {"q": "(Audio) 'Preliminary results indicate a significant rise in consumer confidence.' What do results indicate?",
         "options": ["A fall", "No change", "A rise", "Unclear"], "answer": "A rise",
         "transcript": "Preliminary results indicate a significant rise in consumer confidence."},
        {"q": "(Audio) 'The panel reached a consensus after extensive deliberation.' What did the panel reach?",
         "options": ["A conflict", "A consensus", "A vote", "A delay"], "answer": "A consensus",
         "transcript": "The panel reached a consensus after extensive deliberation."},
        {"q": "(Audio) 'Remote work has broadened access to global talent pools.' What has remote work done?",
         "options": ["Reduced access", "Broadened access", "Eliminated access", "Complicated access"], "answer": "Broadened access",
         "transcript": "Remote work has broadened access to global talent pools."},
        {"q": "(Audio) 'The committee urged immediate implementation of the safety protocol.' What did the committee urge?",
         "options": ["Delay", "Immediate implementation", "Cancellation", "Review"], "answer": "Immediate implementation",
         "transcript": "The committee urged immediate implementation of the safety protocol."},
        {"q": "(Audio) 'New findings challenge the prevailing hypothesis.' What do findings do?",
         "options": ["Support it", "Ignore it", "Challenge it", "Prove it"], "answer": "Challenge it",
         "transcript": "New findings challenge the prevailing hypothesis."},
        {"q": "(Audio) 'Although promising, the pilot study had a limited sample size.' What was limited?",
         "options": ["Budget", "Sample size", "Time", "Staff"], "answer": "Sample size",
         "transcript": "Although promising, the pilot study had a limited sample size."},
    ],
}

# ---------- Reading passages ----------
R_PASSAGES = {
    "A1": {
        "text": "Maria lives in a small town near the sea. She works in a café and goes to the beach after work.",
        "qs": [
            ("Where does Maria live?", ["In a big city", "In a small town near the sea", "In the mountains", "In the desert"], "In a small town near the sea"),
            ("Where does Maria work?", ["In a shop", "In a café", "In a bank", "At school"], "In a café"),
            ("What does she do after work?", ["Goes home", "Goes to the gym", "Goes to the beach", "Studies"], "Goes to the beach"),
            ("Maria lives __ the sea.", ["at", "near", "on", "under"], "near"),
            ("The text says Maria works __.", ["in a café", "in an office", "from home", "at night only"], "in a café"),
            ("The opposite of 'small' is __.", ["little", "tiny", "big", "short"], "big"),
        ]
    },
    "A2": {
        "text": "The city library moved to a larger building. Now it offers weekend workshops, free Wi-Fi, and study rooms.",
        "qs": [
            ("Why did the library move?", ["It was closed", "To a smaller place", "To a larger building", "For repairs"], "To a larger building"),
            ("Which service is mentioned?", ["Paid internet", "Free Wi-Fi", "Gym", "Cinema"], "Free Wi-Fi"),
            ("When are workshops offered?", ["Weekdays", "Weekends", "Every night", "Holidays only"], "Weekends"),
            ("Study rooms are available __.", ["for staff only", "for students only", "for users", "for teachers"], "for users"),
            ("The library now has more __.", ["space", "noise", "rules", "fees"], "space"),
            ("'Offers' is closest to __.", ["gives", "buys", "sells", "hides"], "gives"),
        ]
    },
    "B1": {
        "text": "Volunteering can strengthen communities by connecting people with local needs. However, volunteers require training to be effective.",
        "qs": [
            ("What strengthens communities?", ["Traffic", "Volunteering", "Taxes", "Tourism"], "Volunteering"),
            ("What do volunteers require?", ["Money", "Uniforms", "Training", "Cars"], "Training"),
            ("Volunteering connects people with __.", ["local needs", "sports", "politics", "fashion"], "local needs"),
            ("To be effective, volunteers need __.", ["experience only", "training", "nothing", "luck"], "training"),
            ("The tone of the passage is __.", ["critical", "informative", "funny", "angry"], "informative"),
            ("'However' shows __.", ["addition", "contrast", "time", "cause"], "contrast"),
        ]
    },
    "B2": {
        "text": "While renewable energy adoption is accelerating, integrating intermittent sources into aging grids demands investment and regulatory coordination.",
        "qs": [
            ("What is accelerating?", ["Fossil fuel use", "Renewable energy adoption", "Electricity prices", "Grid failures"], "Renewable energy adoption"),
            ("What makes integration challenging?", ["Cheap technology", "Intermittent sources", "Abundant storage", "Public support"], "Intermittent sources"),
            ("Grids described are __.", ["new", "aging", "perfect", "private"], "aging"),
            ("What does integration demand?", ["No changes", "Investment and coordination", "Less regulation", "Fewer workers"], "Investment and coordination"),
            ("'Intermittent' most nearly means __.", ["constant", "irregular", "fast", "expensive"], "irregular"),
            ("The passage focuses on __.", ["transport", "energy policy", "education", "health"], "energy policy"),
        ]
    },
}

# ---------- Use of English ----------
U_BANK = {
    "A1": [
        ("He __ a student.", ["am", "is", "are", "be"], "is"),
        ("We __ in Tunis.", ["live", "lives", "living", "to live"], "live"),
        ("There __ two apples.", ["is", "are", "be", "been"], "are"),
        ("I __ coffee every day.", ["drink", "drinks", "drank", "drinking"], "drink"),
        ("Choose the plural: one man → two __.", ["mans", "men", "manses", "menses"], "men"),
        ("She __ from Spain.", ["are", "am", "is", "be"], "is"),
        ("I go __ school by bus.", ["to", "in", "on", "at"], "to"),
        ("Opposite of 'hot' is __.", ["warm", "cold", "heat", "cool"], "cold"),
    ],
    "A2": [
        ("I have lived here __ 2019.", ["for", "since", "during", "from"], "since"),
        ("If it rains, we __ at home.", ["stay", "will stay", "stayed", "stays"], "will stay"),
        ("He can't __ the meeting.", ["to attend", "attends", "attend", "attending"], "attend"),
        ("We didn't go out __ the rain.", ["because", "because of", "so", "although"], "because of"),
        ("Choose the past: buy → __.", ["buyed", "bought", "buys", "buy"], "bought"),
        ("You're coming, __?", ["isn't you", "aren't you", "don't you", "won't you"], "aren't you"),
        ("I'm interested __ history.", ["in", "on", "at", "about"], "in"),
        ("This test is __ than the last.", ["easyer", "easier", "more easy", "most easy"], "easier"),
    ],
    "B1": [
        ("I wish I __ more time.", ["have", "had", "would have", "am having"], "had"),
        ("Hardly __ the meeting begun when the alarm rang.", ["had", "has", "did", "was"], "had"),
        ("He denied __ the window.", ["to break", "break", "breaking", "to have broke"], "breaking"),
        ("We need someone __ can code.", ["who", "which", "whom", "what"], "who"),
        ("Despite __ late, she finished.", ["to arrive", "arrive", "arriving", "arrived"], "arriving"),
        ("The manager suggested that he __ earlier.", ["comes", "come", "came", "would come"], "come"),
        ("It's high time you __.", ["come", "came", "would come", "had come"], "came"),
        ("Make __ decision.", ["do a", "make a", "take a", "create a"], "make a"),
    ],
    "B2": [
        ("No sooner __ the announcement made than shares fell.", ["was", "had", "has", "having"], "had"),
        ("The project, __ objectives were unclear, was delayed.", ["whose", "who's", "which", "that"], "whose"),
        ("Had I known, I __ earlier.", ["left", "would have left", "would leave", "had left"], "would have left"),
        ("He insisted that she __ present.", ["be", "was", "is", "would be"], "be"),
        ("The proposal was rejected on the __ that ...", ["grounds", "reasons", "basis", "causes"], "grounds"),
        ("Seldom __ such a case.", ["I hear", "do I hear", "I have heard", "did I heard"], "do I hear"),
        ("By the time it finishes, we __ ten modules.", ["will have completed", "completed", "have completed", "had completed"], "will have completed"),
        ("We should consider __ a pilot program.", ["to launch", "launch", "launching", "to be launching"], "launching"),
    ],
}

# ---------- Writing prompts ----------
W_PROMPTS = {
    "A1": ("Write about your daily routine (50–70 words).", ["morning", "work", "eat", "go", "home"]),
    "A2": ("Describe your last holiday (80–100 words).", ["where", "when", "with", "activities", "feelings"]),
    "B1": ("Do you prefer studying alone or in groups? Explain (120–150 words).", ["prefer", "because", "example", "time", "learn"]),
    "B2": ("Some companies allow remote work. Discuss advantages and disadvantages (180–220 words).", ["productivity", "balance", "communication", "costs", "team"]),
}

# ---------- State ----------
def init_state():
    if "started" not in st.session_state:
        st.session_state.started = False
    for k, v in {"name": "", "level": "B1", "seed": random.randint(1, 10_000_000)}.items():
        st.session_state.setdefault(k, v)
    st.session_state.setdefault("answers", {s: {} for s in SECTION_ORDER})
    st.session_state.setdefault("deadline", None)
    # audio map: per level -> {index -> bytes}
    st.session_state.setdefault("audio_map", {lvl: {} for lvl in LEVEL_ORDER})

init_state()

# ---------- Helpers ----------
def pick_items(level, bank, n):
    """
    Return n items for a given level.
    - If `bank` is a dict keyed by level -> use bank[level]
    - If `bank` is already a list -> use it directly
    """
    rnd = random.Random(st.session_state.seed)
    if isinstance(bank, dict):
        pool = list(bank.get(level, []))
    else:
        pool = list(bank)
    rnd.shuffle(pool)
    return pool[:n]

def reading_items(level, n):
    data = R_PASSAGES[level]
    qs = data["qs"][:]
    rnd = random.Random(st.session_state.seed)
    rnd.shuffle(qs)
    return data["text"], qs[:n]

def set_deadline(level):
    minutes = sum(LEVEL_TIME[level].values())
    st.session_state.deadline = datetime.utcnow() + timedelta(minutes=minutes)

def time_left_str():
    if not st.session_state.deadline:
        return ""
    left = st.session_state.deadline - datetime.utcnow()
    if left.total_seconds() <= 0:
        return "00:00"
    mm, ss = divmod(int(left.total_seconds()), 60)
    return f"{mm:02d}:{ss:02d}"

def score_mcq(items, user_map):
    correct = 0
    rows = []
    for i, it in enumerate(items):
        q = it.get("q") if isinstance(it, dict) else it[0]
        opts = it.get("options") if isinstance(it, dict) else it[1]
        ans = it.get("answer") if isinstance(it, dict) else it[2]
        user = user_map.get(i)
        ok = (user == ans)
        correct += int(ok)
        rows.append({"Q#": i+1, "Question": q, "User": user or "", "Correct": ans, "IsCorrect": ok})
    pct = round(100*correct/max(1, len(items)), 1)
    return pct, pd.DataFrame(rows)

def score_writing(text, level):
    min_w = {"A1":50,"A2":80,"B1":120,"B2":180}[level]
    max_w = {"A1":70,"A2":100,"B1":150,"B2":220}[level]
    kws = W_PROMPTS[level][1]
    wc = len(text.strip().split()) if text.strip() else 0
    hits = sum(1 for k in kws if k.lower() in text.lower())
    base = 40 if min_w <= wc <= max_w else 20 if wc>0 else 0
    kw_score = min(60, hits*12)
    pct = min(100, base + kw_score)
    return pct, wc, hits, kws

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Setup")
    st.session_state.name = st.text_input("Candidate name", value=st.session_state.name)
    st.session_state.level = st.selectbox("Level", LEVEL_ORDER, index=LEVEL_ORDER.index(st.session_state.level))
    st.session_state.seed = st.number_input("Random seed", value=st.session_state.seed, step=1, format="%d")
    st.caption("⏱ Time per section set by level. Total time shows on top.")

    # Bulk audio upload for current level
    st.subheader("🎧 Listening Audio (bulk upload)")
    bulk_files = st.file_uploader(
        "Upload MP3/WAV/OGG for current level (assigned by order)",
        type=["mp3", "wav", "ogg", "m4a"],
        accept_multiple_files=True,
        key="bulk_audio",
    )
    if bulk_files:
        # Save in the current level mapping sequentially
        lvl = st.session_state.level
        for i, f in enumerate(bulk_files):
            try:
                st.session_state.audio_map[lvl][i] = f.read()
            except Exception:
                pass
        st.success(f"Assigned {len(bulk_files)} audio files to level {lvl} (L1..L{len(bulk_files)}).")

    if not st.session_state.started:
        if st.button("▶️ Start Exam"):
            st.session_state.answers = {s:{} for s in SECTION_ORDER}
            st.session_state.started = True
            set_deadline(st.session_state.level)
    else:
        if st.button("🔁 Restart (new shuffle)"):
            st.session_state.seed = random.randint(1, 10_000_000)
            st.session_state.answers = {s:{} for s in SECTION_ORDER}
            set_deadline(st.session_state.level)

# ---------- Main ----------
if st.session_state.started:
    k1,k2,k3 = st.columns([1,1,2])
    with k1:
        st.markdown("**Level**")
        st.markdown(f"<span class='badge'>{st.session_state.level}</span>", unsafe_allow_html=True)
    with k2:
        st.markdown("**Time Left**")
        st.markdown(f"<div class='kpi'>{time_left_str()}</div>", unsafe_allow_html=True)
    with k3:
        st.info("Complete the four sections, then click Submit All at the bottom. "
                "Upload/adjust audio any time from sidebar or each question.")

    if time_left_str() == "00:00":
        st.warning("Time is up! Auto-submitting your exam.")

    lvl = st.session_state.level
    L_items = pick_items(lvl, L_BANK, Q_PER["Listening"])              # list of dicts
    R_text, R_items = reading_items(lvl, Q_PER["Reading"])             # passage + list of tuples
    U_raw = pick_items(lvl, U_BANK, Q_PER["Use of English"])           # list of tuples
    U_items = [{"q": q, "options": opts, "answer": ans} for (q, opts, ans) in U_raw]  # list of dicts

    tabs = st.tabs(SECTION_ORDER)

    # --- Listening ---
    with tabs[0]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write("**Instructions:** Listen to the audio, then choose the correct answer."
                 " If no audio is provided, you can use the transcript below.")
        for i, it in enumerate(L_items):
            st.markdown(f"**L{i+1}.** {it['q']}")
            # Per-question audio uploader (overrides bulk assignment)
            q_file = st.file_uploader(
                f"Upload/replace audio for L{i+1}",
                type=["mp3", "wav", "ogg", "m4a"],
                key=f"aud_{lvl}_{i}",
            )
            if q_file is not None:
                st.session_state.audio_map[lvl][i] = q_file.read()

            # Play audio if found (bulk or per-question)
            audio_bytes = st.session_state.audio_map.get(lvl, {}).get(i)
            if audio_bytes:
                # Let browser infer mime; mp3/ogg/wav will work
                st.audio(audio_bytes)
            else:
                with st.expander("Transcript (fallback if no audio)"):
                    st.caption(it["transcript"])

            st.session_state.answers["Listening"][i] = st.radio("Select one:", it["options"], index=None, key=f"L_{i}")
            st.divider()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Reading (Comprehension) ---
    with tabs[1]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write("**Read the passage and answer the questions.**")
        st.info(R_text)
        for i, (q, opts, ans) in enumerate(R_items):
            st.markdown(f"**R{i+1}.** {q}")
            st.session_state.answers["Reading"][i] = st.radio("Select one:", opts, index=None, key=f"R_{i}")
            st.divider()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Use of English ---
    with tabs[2]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write("**Grammar & Vocabulary.** Choose the best answer.")
        for i, it in enumerate(U_items):
            st.markdown(f"**U{i+1}.** {it['q']}")
            st.session_state.answers["Use of English"][i] = st.radio("Select one:", it["options"], index=None, key=f"U_{i}")
            st.divider()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Writing ---
    with tabs[3]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        prompt, kws = W_PROMPTS[lvl]
        st.write(f"**Prompt:** {prompt}")
        st.caption(f"Try to include: {', '.join(kws)}")
        st.session_state.answers["Writing"][0] = st.text_area("Your essay:", height=220, key="W_0")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Submit ---
    if st.button("✅ Submit All", type="primary") or time_left_str()=="00:00":
        L_pct, L_df = score_mcq(L_items, st.session_state.answers["Listening"])
        R_df_items = [{"q": q, "options": opts, "answer": ans} for (q,opts,ans) in R_items]
        R_pct, R_df = score_mcq(R_df_items, st.session_state.answers["Reading"])
        U_pct, U_df = score_mcq(U_items, st.session_state.answers["Use of English"])
        W_text = st.session_state.answers["Writing"].get(0,"")
        W_pct, wc, hits, kws = score_writing(W_text, lvl)

        overall = round((L_pct + R_pct + U_pct + W_pct)/4, 1)

        # Summary
        st.success(f"**Overall Score: {overall}%** — {'✅ PASS' if overall >= PASS_MARK else '❌ FAIL'}")
        st.write({"Listening": L_pct, "Reading": R_pct, "Use of English": U_pct, "Writing": W_pct})
        st.caption(f"Writing auto-check → words={wc}, keywords matched={hits}/{len(kws)} (manual review recommended)")

        # Downloads
        def to_csv_bytes(df):
            buf = StringIO(); df.to_csv(buf, index=False); return buf.getvalue().encode()
        st.download_button("⬇️ Listening report (CSV)", to_csv_bytes(L_df), file_name=f"{st.session_state.name or 'candidate'}_{lvl}_Listening.csv")
        st.download_button("⬇️ Reading report (CSV)", to_csv_bytes(R_df), file_name=f"{st.session_state.name or 'candidate'}_{lvl}_Reading.csv")
        st.download_button("⬇️ UseOfEnglish report (CSV)", to_csv_bytes(U_df), file_name=f"{st.session_state.name or 'candidate'}_{lvl}_UseOfEnglish.csv")

        # Reset after submit
        st.session_state.started = False
        st.session_state.deadline = None

else:
    st.info("اختار المستوى واضغط Start Exam. في Listening تنجم ترفع MP3/WAV/OGG لكل سؤال أو بالجملة من الشريط الجانبي.")
