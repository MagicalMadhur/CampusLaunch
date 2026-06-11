"""
Study Plan Generator — Personalized AI-Powered Placement Prep Planner
Aggregates student data from ALL modules, identifies gaps, and generates
a day-by-day study plan using Gemini AI with direct links to practice modules.
"""

import streamlit as st
import os
import sys
import json
import re
from datetime import datetime, date, timedelta
from statistics import mean
from dotenv import load_dotenv
from bson import ObjectId

import google.generativeai as genai
from pymongo import MongoClient

# Shared theme
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY"))
MODEL_NAME = "gemini-2.5-flash"
MONGO_URI = "mongodb://localhost:27017/"

# Module link templates
MODULE_LINKS = {
    "aptitude": "http://localhost:8501/?username={username}",
    "aptitude_dash": "http://localhost:8502/?username={username}",
    "dsa": "http://localhost:8503/?username={username}",
    "dsa_dash": "http://localhost:8504/?username={username}",
    "mock_interview": "http://localhost:8505/?username={username}",
    "resume_ats": "http://localhost:8506/?username={username}",
    "interview_prep": "http://localhost:8507/?username={username}&company={company}&role={role}",
    "resume_builder": "http://localhost:8508/?username={username}",
}

# ---------------------------------------------------------------------------
# MongoDB Helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def get_mongo():
    return MongoClient(MONGO_URI)


def get_plan_db():
    return get_mongo()["study_plan_db"]


def save_plan(username, company, role, deadline, plan_data, profile_snapshot):
    db = get_plan_db()
    doc = {
        "username": username,
        "company": company,
        "role": role,
        "deadline": deadline,
        "plan_data": plan_data,
        "profile_snapshot": profile_snapshot,
        "created_at": datetime.utcnow(),
        "completed_days": [],
    }
    result = db["plans"].insert_one(doc)
    return str(result.inserted_id)


def get_user_plans(username):
    db = get_plan_db()
    return list(db["plans"].find({"username": username}).sort("created_at", -1))


def toggle_day_complete(plan_id, day_num):
    db = get_plan_db()
    plan = db["plans"].find_one({"_id": ObjectId(plan_id)})
    if not plan:
        return
    completed = plan.get("completed_days", [])
    if day_num in completed:
        completed.remove(day_num)
    else:
        completed.append(day_num)
    db["plans"].update_one(
        {"_id": ObjectId(plan_id)},
        {"$set": {"completed_days": completed}},
    )


def delete_plan(plan_id):
    db = get_plan_db()
    db["plans"].delete_one({"_id": ObjectId(plan_id)})


# ---------------------------------------------------------------------------
# Data Aggregation — Pull from ALL module databases
# ---------------------------------------------------------------------------
def collect_student_profile(username):
    """Query all 6 MongoDB databases and build a comprehensive student profile."""
    client = get_mongo()
    profile = {}

    # 1. Aptitude Performance (quiz_system.apti_test)
    try:
        apti_col = client["quiz_system"]["apti_test"]
        apti_tests = list(apti_col.find({"student_id": username}))
        if apti_tests:
            cat_scores = {}
            for t in apti_tests:
                cat = t.get("category", "General")
                acc = (t.get("marks_achieved", 0) / max(t.get("no_of_questions", 1), 1)) * 100
                cat_scores.setdefault(cat, []).append(acc)
            cat_avg = {c: round(mean(scores), 1) for c, scores in cat_scores.items()}
            weakest = min(cat_avg, key=cat_avg.get) if cat_avg else "N/A"
            best = max(cat_avg, key=cat_avg.get) if cat_avg else "N/A"
            overall_avg = round(mean([s for scores in cat_scores.values() for s in scores]), 1)
            profile["aptitude"] = {
                "total_tests": len(apti_tests),
                "avg_accuracy": overall_avg,
                "category_scores": cat_avg,
                "weakest_category": weakest,
                "best_category": best,
            }
        else:
            profile["aptitude"] = {"total_tests": 0, "avg_accuracy": 0, "category_scores": {},
                                   "weakest_category": "N/A", "best_category": "N/A"}
    except Exception:
        profile["aptitude"] = {"total_tests": 0, "avg_accuracy": 0, "category_scores": {},
                               "weakest_category": "N/A", "best_category": "N/A"}

    # 2. DSA Performance (DSA_code_app_db.submissions)
    try:
        dsa_col = client["DSA_code_app_db"]["submissions"]
        dsa_subs = list(dsa_col.find({"username": username}))
        if dsa_subs:
            diff_counts = {}
            all_topics = []
            langs = []
            for s in dsa_subs:
                d = s.get("difficulty", "Unknown")
                diff_counts[d] = diff_counts.get(d, 0) + 1
                topics = s.get("topics", [])
                if isinstance(topics, list):
                    all_topics.extend([t.strip() for t in topics if t.strip()])
                langs.append(s.get("coding_lang", "Unknown"))
            unique_topics = list(set(all_topics))
            common_dsa = ["Array", "String", "Linked List", "Stack", "Queue", "Tree",
                          "Binary Search", "Dynamic Programming", "Graph", "Hash Table",
                          "Sorting", "Recursion", "Greedy", "Backtracking", "Two Pointers",
                          "Sliding Window", "Heap", "Math", "Bit Manipulation"]
            not_practiced = [t for t in common_dsa if t.lower() not in [x.lower() for x in unique_topics]]
            profile["dsa"] = {
                "total_solved": len(dsa_subs),
                "difficulty_breakdown": diff_counts,
                "topics_solved": unique_topics[:15],
                "topics_not_solved": not_practiced[:10],
                "languages_used": list(set(langs)),
            }
        else:
            profile["dsa"] = {"total_solved": 0, "difficulty_breakdown": {},
                              "topics_solved": [], "topics_not_solved": [
                    "Array", "String", "Dynamic Programming", "Tree", "Graph"],
                              "languages_used": []}
    except Exception:
        profile["dsa"] = {"total_solved": 0, "difficulty_breakdown": {},
                          "topics_solved": [], "topics_not_solved": [], "languages_used": []}

    # 3. Mock Interview Performance (mock_interviews.feedbacks)
    try:
        iv_col = client["mock_interviews"]["feedbacks"]
        feedbacks = list(iv_col.find({"username": username}).sort("_id", -1))
        profile["mock_interviews"] = {
            "total_answered": len(feedbacks),
            "recent_questions": [f.get("question", "")[:100] for f in feedbacks[:3]],
        }
    except Exception:
        profile["mock_interviews"] = {"total_answered": 0, "recent_questions": []}

    # 4. Resume Data (resume_builder_db.resumes)
    try:
        res_col = client["resume_builder_db"]["resumes"]
        resumes = list(res_col.find({"username": username}).sort("updated_at", -1).limit(1))
        if resumes:
            data = resumes[0].get("data", {})
            profile["resume"] = {
                "has_resume": True,
                "skills": data.get("skills", {}).get("technical", []),
                "tools": data.get("skills", {}).get("tools", []),
                "experience_count": len(data.get("experience", [])),
                "projects_count": len(data.get("projects", [])),
                "certifications_count": len(data.get("certifications", [])),
                "target_role": data.get("target_role", ""),
            }
        else:
            profile["resume"] = {"has_resume": False, "skills": [], "tools": [],
                                 "experience_count": 0, "projects_count": 0,
                                 "certifications_count": 0, "target_role": ""}
    except Exception:
        profile["resume"] = {"has_resume": False, "skills": [], "tools": [],
                             "experience_count": 0, "projects_count": 0,
                             "certifications_count": 0, "target_role": ""}

    # 5. Interview Prep History (interview_prep_db.search_history)
    try:
        prep_col = client["interview_prep_db"]["search_history"]
        searches = list(prep_col.find({"username": username}).sort("timestamp", -1).limit(5))
        profile["interview_prep"] = {
            "companies_researched": list(set(s.get("company", "") for s in searches)),
            "roles_researched": list(set(s.get("role", "") for s in searches)),
        }
    except Exception:
        profile["interview_prep"] = {"companies_researched": [], "roles_researched": []}

    # 6. Resume upload status (studentDB.students)
    try:
        stu_col = client["studentDB"]["students"]
        student = stu_col.find_one({"username": username})
        if student:
            profile["student_info"] = {
                "department": student.get("department", "N/A"),
                "has_uploaded_resume": bool(student.get("resumePath")),
            }
        else:
            profile["student_info"] = {"department": "N/A", "has_uploaded_resume": False}
    except Exception:
        profile["student_info"] = {"department": "N/A", "has_uploaded_resume": False}

    return profile


# ---------------------------------------------------------------------------
# Gemini — Generate Study Plan
# ---------------------------------------------------------------------------
def generate_study_plan(profile, company, role, days_available):
    prompt = f"""You are an expert placement preparation coach for Indian engineering students.
Generate a detailed, personalized day-by-day study plan.

TARGET: {company} — {role} position
PREPARATION TIME: {days_available} days

STUDENT'S CURRENT PROFILE:
━━━━━━━━━━━━━━━━━━━━━━━━
📊 APTITUDE:
- Tests taken: {profile['aptitude']['total_tests']}
- Average accuracy: {profile['aptitude']['avg_accuracy']}%
- Category scores: {json.dumps(profile['aptitude']['category_scores'])}
- Weakest area: {profile['aptitude']['weakest_category']}

💻 DSA CODING:
- Problems solved: {profile['dsa']['total_solved']}
- Difficulty: {json.dumps(profile['dsa']['difficulty_breakdown'])}
- Topics practiced: {json.dumps(profile['dsa']['topics_solved'][:10])}
- Topics NOT practiced: {json.dumps(profile['dsa']['topics_not_solved'])}
- Languages: {profile['dsa']['languages_used']}

🎙️ MOCK INTERVIEWS:
- Questions answered: {profile['mock_interviews']['total_answered']}

📄 RESUME:
- Technical skills: {profile.get('resume', {}).get('skills', [])}
- Tools: {profile.get('resume', {}).get('tools', [])}
- Projects: {profile.get('resume', {}).get('projects_count', 0)}
- Experience entries: {profile.get('resume', {}).get('experience_count', 0)}

🔍 Companies already researched: {profile['interview_prep']['companies_researched']}
📚 Department: {profile.get('student_info', {}).get('department', 'N/A')}

RULES:
1. Create a day-by-day plan. If days > 14, group into weekly themes with daily tasks.
2. Prioritize WEAK areas — more time on low-performing topics.
3. For DSA: recommend SPECIFIC topics and difficulty levels based on what's NOT practiced yet.
4. For Aptitude: focus on the weakest category first.
5. Include at least 2 mock interview sessions spread across the plan.
6. Include a resume review session if projects < 3 or skills list is small.
7. Each day should have 2-3 tasks with estimated time in minutes.
8. Each task must have a "module" field that is EXACTLY one of: aptitude, dsa, mock_interview, interview_prep, resume_builder, resume_ats, aptitude_dash, dsa_dash
9. Give a readiness_score (0-100) based on the current profile for this specific company+role.

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "company": "{company}",
  "role": "{role}",
  "total_days": {days_available},
  "readiness_score": 0,
  "key_gaps": [],
  "daily_plan": [
    {{
      "day": 1,
      "theme": "theme title",
      "tasks": [
        {{
          "title": "task name",
          "module": "aptitude",
          "duration_minutes": 45,
          "details": "specific instructions"
        }}
      ],
      "tip": "daily tip"
    }}
  ],
  "final_tips": []
}}"""

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt])
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?\s*```$", "", text)
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in response
        try:
            match = re.search(r"\{.*\}", response.text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return None
    except Exception as e:
        st.error(f"Gemini error: {e}")
        return None


def get_module_link(module, username, company="", role=""):
    tpl = MODULE_LINKS.get(module, "")
    if not tpl:
        return None
    return tpl.format(username=username, company=company, role=role)


# ---------------------------------------------------------------------------
# UI Helpers
# ---------------------------------------------------------------------------
def render_profile_snapshot(profile):
    """Show the student's aggregated profile as metric cards."""
    st.markdown("### 📊 Your Profile Snapshot")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        apt_acc = profile["aptitude"]["avg_accuracy"]
        st.metric("🧠 Aptitude", f"{apt_acc}%",
                   delta=f"{profile['aptitude']['total_tests']} tests",
                   delta_color="off")
    with c2:
        st.metric("💻 DSA Solved", profile["dsa"]["total_solved"],
                   delta=f"{len(profile['dsa']['topics_solved'])} topics",
                   delta_color="off")
    with c3:
        st.metric("🎙️ Interview Qs", profile["mock_interviews"]["total_answered"])
    with c4:
        sk_count = len(profile.get("resume", {}).get("skills", []))
        proj_count = profile.get("resume", {}).get("projects_count", 0)
        st.metric("📄 Resume", f"{sk_count} skills",
                   delta=f"{proj_count} projects", delta_color="off")

    # Show gaps
    gaps = []
    if apt_acc < 50:
        gaps.append("⚠️ Aptitude accuracy below 50%")
    if profile["dsa"]["total_solved"] < 10:
        gaps.append("⚠️ Less than 10 DSA problems solved")
    if not profile["dsa"]["difficulty_breakdown"].get("Hard", 0):
        gaps.append("⚠️ No Hard DSA problems attempted")
    if profile["mock_interviews"]["total_answered"] < 5:
        gaps.append("⚠️ Fewer than 5 mock interview questions practiced")
    if not profile.get("resume", {}).get("has_resume"):
        gaps.append("⚠️ No resume built in Resume Builder")
    if profile["dsa"]["topics_not_solved"]:
        gaps.append(f"⚠️ DSA gaps: {', '.join(profile['dsa']['topics_not_solved'][:5])}")

    if gaps:
        st.markdown("#### ⚠️ Identified Gaps")
        for g in gaps:
            st.markdown(f"- {g}")


def render_plan(plan_data, username, plan_id=None):
    """Render the generated study plan as an interactive timeline."""
    company = plan_data.get("company", "")
    role = plan_data.get("role", "")
    total_days = plan_data.get("total_days", 0)
    readiness = plan_data.get("readiness_score", 0)
    key_gaps = plan_data.get("key_gaps", [])
    daily_plan = plan_data.get("daily_plan", [])
    final_tips = plan_data.get("final_tips", [])

    # Get completed days
    completed_days = []
    if plan_id:
        db = get_plan_db()
        plan_doc = db["plans"].find_one({"_id": ObjectId(plan_id)})
        if plan_doc:
            completed_days = plan_doc.get("completed_days", [])

    # Header
    st.markdown(f"""
    <div class="cc-hero">
        <h1>📚 {total_days}-Day Plan for {company}</h1>
        <p>{role} • Readiness Score: {readiness}%</p>
    </div>
    """, unsafe_allow_html=True)

    # Progress
    if daily_plan:
        progress = len(completed_days) / len(daily_plan) if daily_plan else 0
        st.progress(progress, text=f"Progress: {len(completed_days)}/{len(daily_plan)} days completed")

    # Key gaps
    if key_gaps:
        with st.expander("🔍 Key Gaps Identified", expanded=False):
            for g in key_gaps:
                st.markdown(f"- {g}")

    # Daily plan
    st.markdown("---")
    for day_info in daily_plan:
        day_num = day_info.get("day", 0)
        theme = day_info.get("theme", "")
        tasks = day_info.get("tasks", [])
        tip = day_info.get("tip", "")
        is_done = day_num in completed_days

        icon = "✅" if is_done else f"📅"
        header = f"{icon} Day {day_num} — {theme}"

        with st.expander(header, expanded=(day_num <= 2 and not is_done)):
            for task in tasks:
                title = task.get("title", "")
                module = task.get("module", "")
                duration = task.get("duration_minutes", 30)
                details = task.get("details", "")

                tc1, tc2 = st.columns([4, 1])
                with tc1:
                    st.markdown(f"**{title}** • ⏱️ {duration} min")
                    st.caption(details)
                with tc2:
                    link = get_module_link(module, username, company, role)
                    if link:
                        st.link_button("Open →", link, use_container_width=True)

            if tip:
                st.info(f"💡 **Tip:** {tip}")

            # Mark day complete button
            if plan_id:
                btn_label = "↩️ Undo" if is_done else "✅ Mark Complete"
                if st.button(btn_label, key=f"toggle_{plan_id}_{day_num}"):
                    toggle_day_complete(plan_id, day_num)
                    st.rerun()

    # Final tips
    if final_tips:
        st.markdown("---")
        st.markdown("### 🎯 Final Tips")
        for t in final_tips:
            st.markdown(f"✅ {t}")


# ---------------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Study Plan Generator", page_icon="📚", layout="wide")

try:
    from cc_theme import inject_theme
    inject_theme()
except ImportError:
    pass

# Session state
if "generated_plan" not in st.session_state:
    st.session_state.generated_plan = None
if "saved_plan_id" not in st.session_state:
    st.session_state.saved_plan_id = None
if "student_profile" not in st.session_state:
    st.session_state.student_profile = None

params = st.query_params
username = params.get("username", "")

# ── Sidebar: Saved Plans ──
with st.sidebar:
    st.markdown("### 📂 Saved Plans")

    if st.button("📝 New Plan", key="new_plan", use_container_width=True):
        st.session_state.generated_plan = None
        st.session_state.saved_plan_id = None
        st.session_state.student_profile = None
        st.rerun()

    st.divider()

    if username:
        plans = get_user_plans(username)
        if plans:
            for p in plans:
                pid = str(p["_id"])
                label = f"🏢 {p['company']} — {p['role']}"
                ts = p.get("created_at", datetime.utcnow()).strftime("%b %d, %H:%M")
                total = len(p.get("plan_data", {}).get("daily_plan", []))
                done = len(p.get("completed_days", []))

                col_a, col_b = st.columns([3, 1])
                with col_a:
                    if st.button(label, key=f"load_{pid}"):
                        st.session_state.generated_plan = p["plan_data"]
                        st.session_state.saved_plan_id = pid
                        st.session_state.student_profile = p.get("profile_snapshot")
                        st.rerun()
                with col_b:
                    if st.button("🗑️", key=f"del_{pid}"):
                        delete_plan(pid)
                        if st.session_state.saved_plan_id == pid:
                            st.session_state.generated_plan = None
                            st.session_state.saved_plan_id = None
                        st.rerun()
                st.caption(f"   {done}/{total} days done • {ts}")
        else:
            st.caption("No saved plans yet.")
    else:
        st.warning("Login to save plans")

# ── Main Content ──
st.markdown("""
<div class="cc-hero">
    <h1>📚 Study Plan Generator</h1>
    <p>AI-powered personalized placement preparation planner</p>
</div>
""", unsafe_allow_html=True)

# If no plan is loaded/generated, show the input form
if st.session_state.generated_plan is None:
    st.divider()
    st.markdown("### 🎯 Enter Your Target")

    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("🏢 Target Company", placeholder="e.g. Google, TCS, Infosys")
    with col2:
        role = st.text_input("💼 Target Role", placeholder="e.g. Software Engineer, Data Analyst")

    col3, col4 = st.columns(2)
    with col3:
        deadline = st.date_input("📅 Interview / Target Date",
                                  value=date.today() + timedelta(days=14),
                                  min_value=date.today() + timedelta(days=1))
    with col4:
        days_available = (deadline - date.today()).days
        st.metric("📆 Days Available", f"{days_available} days")

    generate_btn = st.button("🚀 Generate My Study Plan", type="primary", use_container_width=True)

    if generate_btn:
        if not company.strip() or not role.strip():
            st.warning("Please enter both company name and role.")
        elif not username:
            st.warning("Username not found. Please access this page from the Student Dashboard.")
        else:
            # Step 1: Collect profile
            with st.spinner("📊 Analyzing your performance across all modules..."):
                profile = collect_student_profile(username)
                st.session_state.student_profile = profile

            render_profile_snapshot(profile)

            # Step 2: Generate plan
            with st.spinner(f"🤖 Generating your personalized {days_available}-day plan for {company}..."):
                plan = generate_study_plan(profile, company.strip(), role.strip(), days_available)

            if plan:
                st.session_state.generated_plan = plan

                # Auto-save
                plan_id = save_plan(
                    username, company.strip(), role.strip(),
                    deadline.isoformat(), plan, profile
                )
                st.session_state.saved_plan_id = plan_id
                st.rerun()
            else:
                st.error("Failed to generate plan. Please try again.")

    # Show profile if available but no plan yet
    if st.session_state.student_profile and not generate_btn:
        render_profile_snapshot(st.session_state.student_profile)

else:
    # Show saved/generated plan
    if st.session_state.student_profile:
        render_profile_snapshot(st.session_state.student_profile)
        st.divider()

    render_plan(
        st.session_state.generated_plan,
        username,
        plan_id=st.session_state.saved_plan_id,
    )
