"""
Shared CampusLaunch theme — import in all Streamlit apps for consistent look.
Usage:  from theme import inject_theme;  inject_theme()
"""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Base ── */
.stApp {
    background: linear-gradient(145deg, #0a0a14 0%, #12121f 40%, #0f1628 100%) !important;
    font-family: 'Inter', sans-serif !important;
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111122 0%, #0a0a14 100%) !important;
    border-right: 1px solid rgba(99, 102, 241, 0.15) !important;
}
section[data-testid="stSidebar"] * { color: #c9d1d9 !important; }

/* ── Typography ── */
h1, h2, h3, h4, h5, h6 { color: #f1f5f9 !important; font-family: 'Inter', sans-serif !important; }
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span,
label, .stTextInput label, .stSelectbox label, .stTextArea label,
.stRadio label, .stNumberInput label { color: #e2e8f0 !important; }
a { color: #818cf8 !important; }

/* ── Inputs ── */
.stTextInput input, .stSelectbox select, .stTextArea textarea, .stNumberInput input {
    background: rgba(22, 22, 40, 0.85) !important;
    border: 1px solid rgba(99, 102, 241, 0.25) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.2) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: rgba(22, 22, 40, 0.8) !important;
    color: #c9d1d9 !important;
    border: 1px solid rgba(99, 102, 241, 0.3) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    transition: all 0.25s ease !important;
}
.stButton > button:hover {
    background: rgba(99, 102, 241, 0.15) !important;
    border-color: #6366f1 !important;
    color: #fff !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2) !important;
}
button[kind="primary"], .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366f1, #818cf8) !important;
    color: #fff !important;
    border: none !important;
}
button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #4f46e5, #6366f1) !important;
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35) !important;
}

/* ── Tabs ── */
div[data-testid="stTabs"] button {
    font-size: 14px !important; font-weight: 600 !important;
    color: #8b949e !important; background: transparent !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #818cf8 !important;
    border-bottom-color: #818cf8 !important;
}

/* ── Expanders ── */
div[data-testid="stExpander"] {
    background: rgba(18, 18, 32, 0.7) !important;
    border: 1px solid rgba(99, 102, 241, 0.2) !important;
    border-radius: 12px !important;
}
div[data-testid="stExpander"] summary { color: #c9d1d9 !important; font-weight: 600 !important; }

/* ── Alerts ── */
div[data-testid="stAlert"] {
    background: rgba(18, 18, 32, 0.6) !important;
    border-color: rgba(99, 102, 241, 0.2) !important;
    color: #c9d1d9 !important;
    border-radius: 10px !important;
}

/* ── Metrics ── */
div[data-testid="stMetric"] {
    background: rgba(18, 18, 32, 0.6) !important;
    border: 1px solid rgba(99, 102, 241, 0.15) !important;
    border-radius: 12px !important;
    padding: 12px !important;
}

/* ── Dividers ── */
hr { border-color: rgba(99, 102, 241, 0.12) !important; }

/* ── Hide Streamlit default footer & header ── */
footer { visibility: hidden !important; }
footer::after { visibility: hidden !important; }
#MainMenu { visibility: hidden !important; }
header[data-testid="stHeader"] { background: transparent !important; }

/* ── Progress Bar ── */
div[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #6366f1, #818cf8) !important;
    border-radius: 10px !important;
}

/* ── Glass card helper ── */
.cc-glass {
    background: rgba(18, 18, 32, 0.65);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 16px;
}
.cc-badge {
    display: inline-block;
    background: linear-gradient(135deg, #6366f1, #818cf8);
    color: white; font-weight: 700;
    border-radius: 50%; width: 36px; height: 36px;
    text-align: center; line-height: 36px;
    margin-right: 10px;
}
.cc-hero {
    text-align: center; padding: 18px 0 8px;
}
.cc-hero h1 {
    font-size: 2.4rem;
    background: linear-gradient(135deg, #6366f1, #818cf8, #a5b4fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 6px;
}
.cc-hero p { color: #94a3b8; font-size: 1.05rem; }
</style>
"""


def inject_theme():
    """Call at the top of every Streamlit app to apply the CampusLaunch theme."""
    import streamlit as _st
    _st.markdown(THEME_CSS, unsafe_allow_html=True)
