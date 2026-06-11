"""
Resume Builder — Create, store, and download professional resumes.
Captures details section-wise, generates PDF, and stores history in MongoDB.
"""

import streamlit as st
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from bson import ObjectId

# google.generativeai imported lazily inside functions to save memory
from pymongo import MongoClient

from pdf_generator import generate_resume_pdf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
MODEL_NAME = "gemini-2.5-flash"
_genai_configured = False

def _get_genai():
    global _genai_configured
    import google.generativeai as genai
    if not _genai_configured:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY"))
        _genai_configured = True
    return genai

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "resume_builder_db"

# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return MongoClient(MONGO_URI)[DB_NAME]


def save_resume(username, data):
    db = get_db()
    doc = {
        "username": username,
        "data": data,
        "target_role": data.get("target_role", "General"),
        "target_stack": data.get("target_stack", ""),
        "name": data.get("personal", {}).get("name", "Untitled"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = db["resumes"].insert_one(doc)
    return str(result.inserted_id)


def update_resume(resume_id, data):
    db = get_db()
    db["resumes"].update_one(
        {"_id": ObjectId(resume_id)},
        {"$set": {
            "data": data,
            "target_role": data.get("target_role", "General"),
            "target_stack": data.get("target_stack", ""),
            "name": data.get("personal", {}).get("name", "Untitled"),
            "updated_at": datetime.utcnow(),
        }}
    )


def get_user_resumes(username):
    db = get_db()
    return list(db["resumes"].find({"username": username}).sort("updated_at", -1))


def get_resume_by_id(resume_id):
    db = get_db()
    return db["resumes"].find_one({"_id": ObjectId(resume_id)})


def delete_resume(resume_id):
    db = get_db()
    db["resumes"].delete_one({"_id": ObjectId(resume_id)})


# ---------------------------------------------------------------------------
# AI Helpers
# ---------------------------------------------------------------------------
def ai_generate_summary(personal, target_role, target_stack, experience, skills):
    """Generate a professional summary using Gemini."""
    prompt = f"""Write a professional resume summary (3-4 sentences) for:
Name: {personal.get('name', '')}
Target Role: {target_role}
Tech Stack: {target_stack}
Experience: {json.dumps(experience[:2]) if experience else 'Fresher'}
Key Skills: {json.dumps(skills.get('technical', [])) if skills else 'Not specified'}

Make it compelling, concise, and tailored to the target role. No markdown, just plain text."""
    try:
        genai = _get_genai()
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content([prompt])
        return resp.text.strip()
    except Exception as e:
        return f"Error: {e}"


def ai_suggest_skills(target_role, target_stack):
    """Suggest relevant skills for a role."""
    prompt = f"""For a {target_role} role using {target_stack or 'common technologies'},
suggest skills in JSON format (no markdown fences):
{{"technical": ["skill1","skill2",...], "tools": ["tool1","tool2",...], "soft": ["skill1","skill2",...]}}
Keep 6-8 items per category. Return ONLY the JSON."""
    try:
        genai = _get_genai()
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content([prompt])
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?\s*```$", "", text)
        return json.loads(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Form Helpers — dynamic section management
# ---------------------------------------------------------------------------
def init_session_defaults():
    """Initialize session state with empty resume template."""
    defaults = {
        "personal": {"name": "", "email": "", "phone": "", "location": "",
                      "linkedin": "", "github": "", "portfolio": ""},
        "summary": "",
        "target_role": "",
        "target_stack": "",
        "education": [{"degree": "", "institution": "", "year": "", "gpa": ""}],
        "skills": {"technical": [], "soft": [], "tools": [], "languages": []},
        "experience": [],
        "projects": [],
        "certifications": [],
        "editing_id": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def load_resume_into_session(data):
    """Load a saved resume dict into session state for editing."""
    for key in ["personal", "summary", "target_role", "target_stack",
                "education", "skills", "experience", "projects", "certifications"]:
        if key in data:
            st.session_state[key] = data[key]


def collect_form_data():
    """Collect all form data from session state into a single dict."""
    return {
        "personal": st.session_state["personal"],
        "summary": st.session_state["summary"],
        "target_role": st.session_state["target_role"],
        "target_stack": st.session_state["target_stack"],
        "education": st.session_state["education"],
        "skills": st.session_state["skills"],
        "experience": st.session_state["experience"],
        "projects": st.session_state["projects"],
        "certifications": st.session_state["certifications"],
    }


# ---------------------------------------------------------------------------
# UI Sections
# ---------------------------------------------------------------------------
def render_target_section():
    st.markdown("### 🎯 Target Role")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state["target_role"] = st.text_input(
            "Job Role", value=st.session_state["target_role"],
            placeholder="e.g. Software Engineer", key="inp_role")
    with c2:
        st.session_state["target_stack"] = st.text_input(
            "Tech Stack", value=st.session_state["target_stack"],
            placeholder="e.g. React, Node.js, Python", key="inp_stack")


def render_personal_section():
    st.markdown("### 👤 Personal Information")
    p = st.session_state["personal"]
    c1, c2 = st.columns(2)
    with c1:
        p["name"] = st.text_input("Full Name", value=p["name"], key="p_name")
        p["email"] = st.text_input("Email", value=p["email"], key="p_email")
        p["phone"] = st.text_input("Phone", value=p["phone"], key="p_phone")
        p["location"] = st.text_input("Location", value=p["location"], key="p_loc")
    with c2:
        p["linkedin"] = st.text_input("LinkedIn URL", value=p["linkedin"], key="p_li")
        p["github"] = st.text_input("GitHub URL", value=p["github"], key="p_gh")
        p["portfolio"] = st.text_input("Portfolio URL", value=p["portfolio"], key="p_pf")


def render_summary_section():
    st.markdown("### 📝 Professional Summary")
    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button("🤖 AI Generate", key="ai_sum"):
            with st.spinner("Generating..."):
                ai_summary = ai_generate_summary(
                    st.session_state["personal"],
                    st.session_state["target_role"],
                    st.session_state["target_stack"],
                    st.session_state["experience"],
                    st.session_state["skills"],
                )
                st.session_state["summary"] = ai_summary
                st.rerun()
    st.session_state["summary"] = st.text_area(
        "Summary", value=st.session_state["summary"],
        height=100, key="inp_summary",
        placeholder="A brief professional summary tailored to the target role...")


def render_education_section():
    st.markdown("### 🎓 Education")
    edu_list = st.session_state["education"]

    for i, edu in enumerate(edu_list):
        with st.expander(f"Education {i+1}: {edu.get('degree') or 'New Entry'}", expanded=(i == 0)):
            c1, c2 = st.columns(2)
            with c1:
                edu["degree"] = st.text_input("Degree", value=edu["degree"], key=f"edu_d_{i}",
                                               placeholder="B.Tech in Computer Science")
                edu["institution"] = st.text_input("Institution", value=edu["institution"], key=f"edu_i_{i}")
            with c2:
                edu["year"] = st.text_input("Year", value=edu["year"], key=f"edu_y_{i}",
                                             placeholder="2021 - 2025")
                edu["gpa"] = st.text_input("GPA / Percentage", value=edu["gpa"], key=f"edu_g_{i}")

            if len(edu_list) > 1:
                if st.button(f"🗑️ Remove", key=f"edu_rm_{i}"):
                    edu_list.pop(i)
                    st.rerun()

    if st.button("➕ Add Education", key="add_edu"):
        edu_list.append({"degree": "", "institution": "", "year": "", "gpa": ""})
        st.rerun()


def render_skills_section():
    st.markdown("### 🛠️ Skills")

    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button("🤖 AI Suggest", key="ai_skills"):
            with st.spinner("Suggesting skills..."):
                suggested = ai_suggest_skills(
                    st.session_state["target_role"],
                    st.session_state["target_stack"],
                )
                if suggested:
                    for k in ["technical", "tools", "soft"]:
                        if suggested.get(k):
                            existing = st.session_state["skills"].get(k, [])
                            merged = list(dict.fromkeys(existing + suggested[k]))
                            st.session_state["skills"][k] = merged
                    st.rerun()

    sk = st.session_state["skills"]
    sk["technical"] = st.text_input(
        "Technical Skills (comma-separated)",
        value=", ".join(sk["technical"]) if isinstance(sk["technical"], list) else sk["technical"],
        key="sk_tech", placeholder="Python, Java, React, SQL"
    ).split(",")
    sk["technical"] = [s.strip() for s in sk["technical"] if s.strip()]

    sk["tools"] = st.text_input(
        "Tools & Frameworks (comma-separated)",
        value=", ".join(sk["tools"]) if isinstance(sk["tools"], list) else sk["tools"],
        key="sk_tools", placeholder="Git, Docker, AWS, VS Code"
    ).split(",")
    sk["tools"] = [s.strip() for s in sk["tools"] if s.strip()]

    sk["soft"] = st.text_input(
        "Soft Skills (comma-separated)",
        value=", ".join(sk["soft"]) if isinstance(sk["soft"], list) else sk["soft"],
        key="sk_soft", placeholder="Leadership, Communication, Problem Solving"
    ).split(",")
    sk["soft"] = [s.strip() for s in sk["soft"] if s.strip()]

    sk["languages"] = st.text_input(
        "Languages (comma-separated)",
        value=", ".join(sk["languages"]) if isinstance(sk["languages"], list) else sk["languages"],
        key="sk_lang", placeholder="English, Hindi"
    ).split(",")
    sk["languages"] = [s.strip() for s in sk["languages"] if s.strip()]


def render_experience_section():
    st.markdown("### 💼 Work Experience")
    exp_list = st.session_state["experience"]

    for i, exp in enumerate(exp_list):
        with st.expander(f"Experience {i+1}: {exp.get('title') or 'New Entry'}", expanded=(i == 0)):
            c1, c2 = st.columns(2)
            with c1:
                exp["title"] = st.text_input("Job Title", value=exp.get("title", ""), key=f"exp_t_{i}")
                exp["company"] = st.text_input("Company", value=exp.get("company", ""), key=f"exp_c_{i}")
            with c2:
                exp["start"] = st.text_input("Start Date", value=exp.get("start", ""), key=f"exp_s_{i}",
                                              placeholder="Jan 2023")
                exp["end"] = st.text_input("End Date", value=exp.get("end", ""), key=f"exp_e_{i}",
                                            placeholder="Present")

            bullets_str = "\n".join(exp.get("bullets", []))
            bullets_text = st.text_area("Key Responsibilities (one per line)",
                                         value=bullets_str, key=f"exp_b_{i}", height=100)
            exp["bullets"] = [b.strip() for b in bullets_text.split("\n") if b.strip()]

            if st.button(f"🗑️ Remove", key=f"exp_rm_{i}"):
                exp_list.pop(i)
                st.rerun()

    if st.button("➕ Add Experience", key="add_exp"):
        exp_list.append({"title": "", "company": "", "start": "", "end": "", "bullets": []})
        st.rerun()


def render_projects_section():
    st.markdown("### 🚀 Projects")
    proj_list = st.session_state["projects"]

    for i, proj in enumerate(proj_list):
        with st.expander(f"Project {i+1}: {proj.get('name') or 'New Entry'}", expanded=(i == 0)):
            c1, c2 = st.columns(2)
            with c1:
                proj["name"] = st.text_input("Project Name", value=proj.get("name", ""), key=f"proj_n_{i}")
                proj["tech"] = st.text_input("Technologies Used", value=proj.get("tech", ""), key=f"proj_t_{i}")
            with c2:
                proj["link"] = st.text_input("Project Link", value=proj.get("link", ""), key=f"proj_l_{i}",
                                              placeholder="https://github.com/...")

            proj["description"] = st.text_area("Description", value=proj.get("description", ""),
                                                key=f"proj_d_{i}", height=80)

            if st.button(f"🗑️ Remove", key=f"proj_rm_{i}"):
                proj_list.pop(i)
                st.rerun()

    if st.button("➕ Add Project", key="add_proj"):
        proj_list.append({"name": "", "tech": "", "description": "", "link": ""})
        st.rerun()


def render_certifications_section():
    st.markdown("### 📜 Certifications")
    cert_list = st.session_state["certifications"]

    for i, cert in enumerate(cert_list):
        with st.expander(f"Certification {i+1}: {cert.get('name') or 'New Entry'}", expanded=(i == 0)):
            c1, c2 = st.columns(2)
            with c1:
                cert["name"] = st.text_input("Certification Name", value=cert.get("name", ""), key=f"cert_n_{i}")
                cert["issuer"] = st.text_input("Issuing Org", value=cert.get("issuer", ""), key=f"cert_i_{i}")
            with c2:
                cert["year"] = st.text_input("Year", value=cert.get("year", ""), key=f"cert_y_{i}")
                cert["link"] = st.text_input("Certificate Link", value=cert.get("link", ""), key=f"cert_l_{i}")

            if st.button(f"🗑️ Remove", key=f"cert_rm_{i}"):
                cert_list.pop(i)
                st.rerun()

    if st.button("➕ Add Certification", key="add_cert"):
        cert_list.append({"name": "", "issuer": "", "year": "", "link": ""})
        st.rerun()


# ---------------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Resume Builder", page_icon="📄", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117 !important; color: #fafafa !important; }
    section[data-testid="stMain"] { background-color: #0e1117 !important; }
    section[data-testid="stSidebar"] { background-color: #161b22 !important; }
    section[data-testid="stSidebar"] * { color: #c9d1d9 !important; }
    .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span,
    label, .stTextInput label { color: #e6edf3 !important; }
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    .stTextInput input, .stTextArea textarea {
        background-color: #21262d !important; color: #e6edf3 !important; border-color: #30363d !important;
    }
    div[data-testid="stTabs"] button {
        font-size: 15px !important; font-weight: 600 !important;
        color: #8b949e !important; background: transparent !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #58a6ff !important; border-bottom-color: #58a6ff !important;
    }
    details { background-color: #161b22 !important; border: 1px solid #30363d !important; border-radius: 8px !important; }
    details summary { color: #c9d1d9 !important; }
    hr { border-color: #21262d !important; }
    .stButton > button {
        background-color: #21262d !important; color: #c9d1d9 !important;
        border: 1px solid #30363d !important; border-radius: 8px !important;
    }
    .stButton > button:hover {
        background-color: #30363d !important; color: #fff !important; border-color: #58a6ff !important;
    }
    button[kind="primary"] {
        background-color: #238636 !important; color: #fff !important; border-color: #238636 !important;
    }
    a { color: #58a6ff !important; }
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }
    header[data-testid="stHeader"] { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

init_session_defaults()

st.title("📄 Resume Builder")
st.caption("Build professional resumes section-by-section • AI-powered • Stored for multiple roles")

params = st.query_params
username = params.get("username", "")

# ── Sidebar: Saved Resumes ──
with st.sidebar:
    st.markdown("### 📂 My Resumes")

    if st.button("📝 New Resume", key="new_resume", use_container_width=True):
        for k in ["personal", "summary", "target_role", "target_stack",
                   "education", "skills", "experience", "projects", "certifications", "editing_id"]:
            if k in st.session_state:
                del st.session_state[k]
        init_session_defaults()
        st.rerun()

    st.divider()

    if username:
        resumes = get_user_resumes(username)
        if resumes:
            for r in resumes:
                rid = str(r["_id"])
                role_tag = r.get("target_role", "General")
                name = r.get("name", "Untitled")
                ts = r.get("updated_at", datetime.utcnow()).strftime("%b %d, %H:%M")
                label = f"📄 {name} — {role_tag}"

                col_a, col_b = st.columns([3, 1])
                with col_a:
                    if st.button(label, key=f"load_{rid}"):
                        load_resume_into_session(r["data"])
                        st.session_state["editing_id"] = rid
                        st.rerun()
                with col_b:
                    if st.button("🗑️", key=f"del_{rid}"):
                        delete_resume(rid)
                        if st.session_state.get("editing_id") == rid:
                            st.session_state["editing_id"] = None
                        st.rerun()

                st.caption(f"   Updated: {ts}")
        else:
            st.caption("No saved resumes yet.")
    else:
        st.warning("Login to save resumes")

# ── Main Content: Tabs ──
tab_build, tab_preview = st.tabs(["✏️ Build Resume", "👁️ Preview & Download"])

with tab_build:
    render_target_section()
    st.divider()
    render_personal_section()
    st.divider()
    render_summary_section()
    st.divider()
    render_education_section()
    st.divider()
    render_skills_section()
    st.divider()
    render_experience_section()
    st.divider()
    render_projects_section()
    st.divider()
    render_certifications_section()

    st.divider()

    # ── Save / Update ──
    col_save, col_preview = st.columns(2)
    with col_save:
        if st.button("💾 Save Resume", type="primary", use_container_width=True):
            if not username:
                st.warning("Login required to save. Pass ?username=... in the URL.")
            elif not st.session_state["personal"].get("name"):
                st.warning("Please enter your name before saving.")
            else:
                data = collect_form_data()
                editing_id = st.session_state.get("editing_id")
                if editing_id:
                    update_resume(editing_id, data)
                    st.success("✅ Resume updated!")
                else:
                    new_id = save_resume(username, data)
                    st.session_state["editing_id"] = new_id
                    st.success("✅ Resume saved!")
                st.rerun()

    with col_preview:
        if st.button("👁️ Go to Preview", use_container_width=True):
            st.info("Switch to the 'Preview & Download' tab above ☝️")

with tab_preview:
    data = collect_form_data()
    name = data["personal"].get("name", "")

    if not name:
        st.info("Fill in at least your name in the Build tab to preview your resume.")
    else:
        st.markdown(f"## 📄 Resume Preview: {name}")
        st.markdown(f"**Target:** {data['target_role']} ({data['target_stack']})")
        st.divider()

        # Quick text preview
        if data.get("summary"):
            st.markdown("**Summary:** " + data["summary"])

        if data.get("skills", {}).get("technical"):
            st.markdown("**Technical Skills:** " + ", ".join(data["skills"]["technical"]))

        for exp in data.get("experience", []):
            if exp.get("title"):
                st.markdown(f"**{exp['title']}** at {exp.get('company', '')} ({exp.get('start', '')} - {exp.get('end', '')})")

        for proj in data.get("projects", []):
            if proj.get("name"):
                st.markdown(f"**{proj['name']}** [{proj.get('tech', '')}]")

        for edu in data.get("education", []):
            if edu.get("degree"):
                st.markdown(f"🎓 {edu['degree']} — {edu.get('institution', '')}")

        for cert in data.get("certifications", []):
            if cert.get("name"):
                st.markdown(f"📜 {cert['name']} — {cert.get('issuer', '')}")

        st.divider()

        # ── Generate & Download PDF ──
        if st.button("📥 Generate & Download PDF", type="primary", use_container_width=True):
            with st.spinner("Generating PDF..."):
                try:
                    filepath, filename = generate_resume_pdf(data)
                    with open(filepath, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                        use_container_width=True,
                    )
                    st.success(f"✅ PDF generated: {filename}")
                except Exception as e:
                    st.error(f"Error generating PDF: {e}")
