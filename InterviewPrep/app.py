"""
Interview Prep — RAG-based Interview Question Finder
Scrapes real interview questions from ANY site and shows them with source links.
Dark theme with AI Answer generation.
"""

import streamlit as st
import os
import json
import time
import hashlib
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from ddgs import DDGS
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY"))
MODEL_NAME = "gemini-2.5-flash"

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "interview_prep_db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


def get_cached_results(cache_key):
    db = get_db()
    doc = db["cache"].find_one({"_id": cache_key})
    if doc and datetime.utcnow() - doc.get("ts", datetime.min) < timedelta(hours=24):
        return doc["data"]
    return None


def set_cached_results(cache_key, data):
    db = get_db()
    db["cache"].update_one(
        {"_id": cache_key},
        {"$set": {"data": data, "ts": datetime.utcnow()}},
        upsert=True,
    )


def save_search_history(username, company, role):
    db = get_db()
    db["search_history"].insert_one({
        "username": username,
        "company": company,
        "role": role,
        "timestamp": datetime.utcnow(),
    })


# ---------------------------------------------------------------------------
# Search & Scrape
# ---------------------------------------------------------------------------
def search_web(query, max_results=12):
    """Search using ddgs library — reliable and no API key needed."""
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        st.warning(f"Search error: {e}")
    return results


def scrape_page_text(url, max_chars=8000):
    """Fetch a page and extract readable text."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "svg", "form"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception:
        return ""


def search_and_scrape(company, role, status_container):
    """Run multiple search queries and scrape results from ANY site."""
    all_scraped = []

    queries = [
        f"{company} {role} interview questions",
        f"{company} {role} interview experience",
        f"{company} interview questions asked for {role}",
    ]

    status_container.markdown("#### 🔎 Searching the web...")
    progress = status_container.progress(0)

    total_steps = len(queries)
    seen_urls = set()

    for qi, query in enumerate(queries):
        progress.progress((qi) / total_steps, text=f"Query {qi+1}/{total_steps}: {query[:50]}...")
        search_results = search_web(query, max_results=10)

        for sr in search_results:
            url = sr["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            content = sr.get("snippet", "")
            page_text = scrape_page_text(url, max_chars=6000)
            if len(page_text) > 100:
                content = page_text

            if len(content) > 50:
                domain = ""
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    pass

                all_scraped.append({
                    "title": sr["title"],
                    "url": url,
                    "domain": domain,
                    "content": content,
                })

        time.sleep(0.3)

    progress.progress(1.0, text="Search complete!")
    status_container.markdown(f"✅ Found **{len(all_scraped)}** relevant pages from **{len(seen_urls)}** URLs")
    return all_scraped


# ---------------------------------------------------------------------------
# Gemini RAG — Extract structured questions from scraped content
# ---------------------------------------------------------------------------
def extract_questions_with_gemini(company, role, scraped_data):
    """Use Gemini to extract REAL interview questions from scraped web content."""
    if not scraped_data:
        return None

    context_parts = []
    for i, item in enumerate(scraped_data[:15]):
        context_parts.append(
            f"[SOURCE {i+1}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Domain: {item['domain']}\n"
            f"Content:\n{item['content'][:4500]}\n"
            f"[END SOURCE {i+1}]\n"
        )

    context = "\n".join(context_parts)

    prompt = f"""You are an interview preparation assistant. I have scraped web pages that contain 
real interview experiences and questions for **{company}** for the **{role}** role.

Your job: Extract ONLY the actual interview questions found in the scraped content below.
Do NOT invent or generate new questions. Only extract what is genuinely present in the sources.

SCRAPED WEB CONTENT:
{context}

RULES:
1. Extract every interview question you can find from the content above.
2. For each question, you MUST include the exact source URL where it was found.
3. Group questions into categories: Technical, HR/Behavioral, Coding/DSA, System Design, Aptitude/Puzzle.
4. Mark difficulty as Easy, Medium, or Hard based on the question complexity.
5. If a source contains an answer or hint, include a very brief hint.
6. Include the domain name (e.g. geeksforgeeks.org) as the source platform.
7. If you cannot find any questions in the content, return an empty categories object.
8. NEVER make up questions — only use what is in the scraped content.

Return ONLY valid JSON (no markdown fences, no extra text) in this format:
{{
  "company": "{company}",
  "role": "{role}",
  "total_questions_found": <number>,
  "categories": {{
    "Technical": [
      {{
        "question": "the actual question text",
        "difficulty": "Easy|Medium|Hard",
        "source_platform": "domain name like geeksforgeeks.org",
        "source_url": "the exact URL from the source",
        "hint": "brief hint or empty string"
      }}
    ],
    "HR_Behavioral": [],
    "Coding_DSA": [],
    "System_Design": [],
    "Aptitude": []
  }},
  "sources_used": [
    {{"title": "page title", "url": "page url", "domain": "domain"}}
  ],
  "tips": ["tip about this company interview process"]
}}
"""

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt])
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?\s*```$", "", text)
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return None
    except Exception as e:
        st.error(f"Gemini error: {e}")
        return None


# ---------------------------------------------------------------------------
# AI Answer Generator
# ---------------------------------------------------------------------------
def generate_ai_answer(question, company, role):
    """Use Gemini to generate a model answer for an interview question."""
    prompt = f"""You are an expert interview coach. A candidate is preparing for an interview 
at **{company}** for the **{role}** role.

Question: "{question}"

Provide a comprehensive answer that includes:
1. **How to approach this question** — what the interviewer is looking for
2. **Model Answer** — a strong, well-structured answer
3. **Key points to mention** — bullet points of must-cover topics
4. **Common mistakes to avoid**

Keep it practical and concise. Format with markdown headings and bullet points.
"""
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt])
        return response.text
    except Exception as e:
        return f"Error generating answer: {e}"


# ---------------------------------------------------------------------------
# UI Rendering — using native Streamlit components (no raw HTML issues)
# ---------------------------------------------------------------------------
def render_question_card(q, idx, cat_key, company, role):
    """Render a single question using Streamlit-native components."""
    diff = q.get("difficulty", "Medium")
    source_url = q.get("source_url", "#")
    source_platform = q.get("source_platform", "web")
    hint = q.get("hint", "")
    question_text = q.get("question", "N/A")

    # Difficulty badge colors
    diff_emoji = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴"}.get(diff, "🟡")

    # Use a container with divider
    with st.container():
        # Question header row
        cols = st.columns([0.85, 0.15])
        with cols[0]:
            st.markdown(f"**Q{idx+1}.** {question_text}")
        with cols[1]:
            st.markdown(f"{diff_emoji} **{diff}**")

        # Source link + hint + AI answer in columns
        c1, c2, c3 = st.columns([1, 1, 1])

        with c1:
            st.markdown(f"📌 *{source_platform}*  \n🔗 [View Source]({source_url})")

        with c2:
            if hint:
                with st.expander("💡 Hint"):
                    st.write(hint)

        with c3:
            # AI Answer button with unique key
            btn_key = f"ai_ans_{cat_key}_{idx}"
            if st.button("🤖 AI Answer", key=btn_key):
                # Generate the answer immediately and cache it in session_state
                ai_cache_key = f"ai_answer_{cat_key}_{idx}"
                if ai_cache_key not in st.session_state:
                    with st.spinner("Generating answer..."):
                        answer = generate_ai_answer(question_text, company, role)
                        st.session_state[ai_cache_key] = answer
                st.session_state[f"show_ai_{cat_key}_{idx}"] = True

        # Show AI answer if button was clicked (persists across reruns)
        if st.session_state.get(f"show_ai_{cat_key}_{idx}", False):
            ai_cache_key = f"ai_answer_{cat_key}_{idx}"
            with st.expander("🤖 AI-Generated Model Answer", expanded=True):
                if ai_cache_key in st.session_state:
                    st.markdown(st.session_state[ai_cache_key])
                else:
                    with st.spinner("Generating answer..."):
                        answer = generate_ai_answer(question_text, company, role)
                        st.session_state[ai_cache_key] = answer
                        st.markdown(answer)

        st.divider()


def render_results(data):
    """Render all extracted questions."""
    if not data:
        st.error("Could not extract questions. Try different search terms.")
        return

    company = data.get("company", "")
    role = data.get("role", "")
    total = data.get("total_questions_found", 0)

    # Hero banner
    st.markdown(f"## 🎯 Interview Prep: {company}")
    st.markdown(f"**Role:** {role}  |  **{total}** real questions scraped from the web")
    st.divider()

    # Sources used
    sources = data.get("sources_used", [])
    if sources:
        with st.expander(f"📚 Sources Referenced ({len(sources)} pages)", expanded=False):
            for s in sources:
                domain = s.get("domain", "")
                url = s.get("url", "#")
                title = s.get("title", url)
                st.markdown(f"- **{domain}** — [{title}]({url})")

    # Tips
    tips = data.get("tips", [])
    if tips:
        with st.expander("💡 Interview Tips for " + company, expanded=False):
            for tip in tips:
                st.markdown(f"✅ {tip}")

    # Questions by category
    categories = data.get("categories", {})
    cat_labels = {
        "Technical": "💻 Technical",
        "HR_Behavioral": "🤝 HR / Behavioral",
        "Coding_DSA": "🧩 Coding & DSA",
        "System_Design": "🏗️ System Design",
        "Aptitude": "🧠 Aptitude / Puzzles",
    }

    active_cats = {k: v for k, v in categories.items() if v}
    if not active_cats:
        st.warning("No questions could be extracted. Try a more well-known company or role.")
        return

    tab_names = [f"{cat_labels.get(k, k)} ({len(v)})" for k, v in active_cats.items()]
    tabs = st.tabs(tab_names)

    for tab, (cat_key, questions) in zip(tabs, active_cats.items()):
        with tab:
            for idx, q in enumerate(questions):
                render_question_card(q, idx, cat_key, company, role)


# ---------------------------------------------------------------------------
# Streamlit config + dark theme
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Interview Prep", page_icon="🎯", layout="wide")

try:
    from cc_theme import inject_theme
    inject_theme()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------
st.title("🎯 Interview Prep")
st.caption("Scrapes REAL interview questions from across the web — with source links to prove it.")

params = st.query_params
username = params.get("username", "")

# ---- Input Form ----
# Pre-fill from query params (used by Recent Searches sidebar)
prefill_company = params.get("company", "")
prefill_role = params.get("role", "")

col1, col2 = st.columns(2)
with col1:
    company = st.text_input("🏢 Company Name", value=prefill_company, placeholder="e.g. Google, TCS, Infosys, Wipro")
with col2:
    role = st.text_input("💼 Role / Position", value=prefill_role, placeholder="e.g. Software Engineer, Data Analyst")

search_btn = st.button("🔍 Find Interview Questions", type="primary", use_container_width=True)

# ---- Determine if we should load from recent search (query params) ----
load_from_history = bool(prefill_company and prefill_role and not search_btn)

# ---- Search Flow ----
if search_btn or load_from_history:
    effective_company = company.strip() if search_btn else prefill_company.strip()
    effective_role = role.strip() if search_btn else prefill_role.strip()

    if not effective_company or not effective_role:
        st.warning("Please enter both company name and role.")
    else:
        cache_key = hashlib.md5(
            f"{effective_company.lower().strip()}|{effective_role.lower().strip()}".encode()
        ).hexdigest()

        cached = get_cached_results(cache_key)

        if load_from_history and cached:
            # Loading from Recent Searches — use cache directly, no re-scrape
            st.success("⚡ Loaded from your recent search (cached results)")
            st.session_state["current_results"] = cached
            render_results(cached)
        elif cached and search_btn:
            st.success("⚡ Showing cached results (refreshed within last 24 hours)")
            st.session_state["current_results"] = cached
            render_results(cached)
        elif load_from_history and not cached:
            # History item clicked but cache expired — run fresh search
            status_area = st.container()
            scraped = search_and_scrape(effective_company, effective_role, status_area)

            if not scraped:
                st.error(
                    "❌ Could not find any pages. Possible reasons:\n"
                    "- Check your internet connection\n"
                    "- Try a more well-known company name\n"
                    "- Try a broader role like 'Software Engineer'"
                )
            else:
                status_area.markdown("#### 🤖 AI is extracting questions from scraped pages...")
                results = extract_questions_with_gemini(effective_company, effective_role, scraped)

                if results:
                    set_cached_results(cache_key, results)
                    status_area.empty()
                    st.session_state["current_results"] = results
                    render_results(results)
                else:
                    st.error("AI could not extract structured questions. Try a different company or role.")
        else:
            # Fresh search triggered by button
            status_area = st.container()
            scraped = search_and_scrape(effective_company, effective_role, status_area)

            if not scraped:
                st.error(
                    "❌ Could not find any pages. Possible reasons:\n"
                    "- Check your internet connection\n"
                    "- Try a more well-known company name\n"
                    "- Try a broader role like 'Software Engineer'"
                )
            else:
                status_area.markdown("#### 🤖 AI is extracting questions from scraped pages...")
                results = extract_questions_with_gemini(
                    effective_company, effective_role, scraped
                )

                if results:
                    set_cached_results(cache_key, results)
                    if username:
                        save_search_history(username, effective_company, effective_role)
                    status_area.empty()
                    st.session_state["current_results"] = results
                    render_results(results)
                else:
                    st.error("AI could not extract structured questions. Try a different company or role.")
elif "current_results" in st.session_state and st.session_state["current_results"]:
    # Re-render stored results on rerun (e.g. after AI Answer button click)
    render_results(st.session_state["current_results"])

# ---- Sidebar: Search History ----
if username:
    with st.sidebar:
        st.markdown("### 📜 Recent Searches")
        db = get_db()
        history = list(
            db["search_history"]
            .find({"username": username})
            .sort("timestamp", -1)
            .limit(10)
        )
        if history:
            for h in history:
                ts = h.get("timestamp", datetime.utcnow()).strftime("%b %d, %H:%M")
                label = f"🏢 {h['company']} — {h['role']} ({ts})"
                if st.button(label, key=str(h["_id"])):
                    # Clear previous AI answer state to avoid stale data
                    keys_to_clear = [k for k in st.session_state if k.startswith("show_ai_") or k.startswith("ai_answer_")]
                    for k in keys_to_clear:
                        del st.session_state[k]
                    st.session_state["current_results"] = None
                    st.query_params["company"] = h["company"]
                    st.query_params["role"] = h["role"]
                    st.rerun()
        else:
            st.caption("No searches yet. Try searching above!")