import os
import streamlit as st
import json
import requests
import google.generativeai as genai
from google.api_core.exceptions import NotFound, ResourceExhausted
from dotenv import load_dotenv
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
from io import BytesIO
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables from .env file
load_dotenv()

# Configure Google Generative AI with the API key from .env
genai.configure(api_key=os.getenv('GEMINI_API_KEY') or os.getenv('API_KEY'))
MODEL_NAME = 'gemini-2.5-flash'

SERVER_URL = 'http://localhost:3000'


def _generate_content(parts):
    model = genai.GenerativeModel(MODEL_NAME)
    return model.generate_content(parts, request_options={"retry": None}).text

# Define cached functions
@st.cache_data()
def get_gemini_response(input, pdf_content, prompt):
    response_text = _generate_content([
        input,
        f"Resume Content:\n{pdf_content}",
        f"Job Description:\n{prompt}"
    ])
    return response_text

@st.cache_data()
def get_gemini_response_keywords(input, pdf_content, prompt):
    response_text = _generate_content([
        input,
        f"Resume Content:\n{pdf_content}",
        f"Job Description:\n{prompt}"
    ])
    json_text = response_text.strip()
    if json_text.startswith("```json"):
        json_text = json_text[7:]
    if json_text.startswith("```"):
        json_text = json_text[3:]
    if json_text.endswith("```"):
        json_text = json_text[:-3]
    return json.loads(json_text.strip())

@st.cache_data()
def input_pdf_setup(pdf_bytes):
    """Extract text from PDF bytes."""
    if pdf_bytes is not None:
        if PdfReader is None:
            raise ImportError("Missing dependency: pypdf. Install it with 'pip install pypdf'.")
        reader = PdfReader(BytesIO(pdf_bytes))
        extracted_pages = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text and page_text.strip():
                extracted_pages.append(page_text.strip())
        resume_text = "\n".join(extracted_pages)
        if not resume_text:
            raise ValueError("Unable to extract text from the PDF.")
        return resume_text
    else:
        raise FileNotFoundError("No PDF data provided")


def fetch_user_resume(username):
    """Fetch the user's resume from the server."""
    try:
        download_url = f"{SERVER_URL}/students/{username}/resume/download"
        resp = requests.get(download_url, timeout=10)
        if resp.status_code == 200:
            return resp.content
        return None
    except Exception:
        return None


def get_resume_info(username):
    """Get resume metadata from the server."""
    try:
        info_url = f"{SERVER_URL}/students/{username}/resume"
        resp = requests.get(info_url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# Streamlit App
st.set_page_config(page_title="ATS Resume Scanner", page_icon="📝", layout="wide")

try:
    from cc_theme import inject_theme
    inject_theme()
except ImportError:
    pass

st.header("Application Tracking System")

# Get username from query params
params = st.query_params
username = params.get("username", "")

if 'resume_bytes' not in st.session_state:
    st.session_state.resume_bytes = None
if 'resume_name' not in st.session_state:
    st.session_state.resume_name = None

# Auto-load resume from server if username is provided
if username and st.session_state.resume_bytes is None:
    resume_info = get_resume_info(username)
    if resume_info and resume_info.get('resumePath'):
        st.session_state.resume_name = resume_info.get('resumeOriginalName', 'resume.pdf')
        pdf_data = fetch_user_resume(username)
        if pdf_data:
            st.session_state.resume_bytes = pdf_data
            st.success(f"✅ Resume auto-loaded: **{st.session_state.resume_name}**")
        else:
            st.warning("Could not download your resume from the server. Please check if the server is running.")
    else:
        st.warning("No resume found on your profile. Please upload a resume in your Profile section on the dashboard.")
elif st.session_state.resume_bytes is not None:
    st.success(f"✅ Resume loaded: **{st.session_state.resume_name}**")

input_text = st.text_area("Job Description: ", key="input")

col1, col2, col3 = st.columns(3, gap="medium")

with col1:
    submit1 = st.button("Tell Me About the Resume")

with col2:
    submit2 = st.button("Get Keywords")

with col3:
    submit3 = st.button("Percentage match")

input_prompt1 = """
 You are an experienced Technical Human Resource Manager, your task is to review the provided resume against the job description. 
 Please share your professional evaluation on whether the candidate's profile aligns with the role. 
 Highlight the strengths and weaknesses of the applicant in relation to the specified job requirements.
"""

input_prompt2 = """
As an expert ATS (Applicant Tracking System) scanner with an in-depth understanding of AI and ATS functionality, 
your task is to evaluate a resume against a provided job description. Please identify the specific skills and keywords 
necessary to maximize the impact of the resume and provide response in json format as {Technical Skills:[], Analytical Skills:[], Soft Skills:[]}.

Note: Please do not make up the answer, only answer from the job description provided.
"""

input_prompt3 = """
You are a skilled ATS (Applicant Tracking System) scanner with a deep understanding of data science and ATS functionality, 
your task is to evaluate the resume against the provided job description. Give me the percentage of match if the resume matches
the job description. First the output should come as percentage and then keywords missing and last final thoughts.
"""

if submit1:
    if st.session_state.resume_bytes is not None:
        try:
            pdf_content = input_pdf_setup(st.session_state.resume_bytes)
            response = get_gemini_response(input_prompt1, pdf_content, input_text)
            st.subheader("The Response is")
            st.write(response)
        except (ValueError, ImportError, ResourceExhausted, NotFound) as err:
            st.error(str(err))
    else:
        st.write("Please upload a resume in your Profile section first.")

elif submit2:
    if st.session_state.resume_bytes is not None:
        try:
            pdf_content = input_pdf_setup(st.session_state.resume_bytes)
            response = get_gemini_response_keywords(input_prompt2, pdf_content, input_text)
            st.subheader("Skills are:")
            if response is not None:
                st.write(f"Technical Skills: {', '.join(response['Technical Skills'])}.")
                st.write(f"Analytical Skills: {', '.join(response['Analytical Skills'])}.")
                st.write(f"Soft Skills: {', '.join(response['Soft Skills'])}.")
        except (ValueError, ImportError, ResourceExhausted, NotFound) as err:
            st.error(str(err))
    else:
        st.write("Please upload a resume in your Profile section first.")

elif submit3:
    if st.session_state.resume_bytes is not None:
        try:
            pdf_content = input_pdf_setup(st.session_state.resume_bytes)
            response = get_gemini_response(input_prompt3, pdf_content, input_text)
            st.subheader("The Response is")
            st.write(response)
        except (ValueError, ImportError, ResourceExhausted, NotFound) as err:
            st.error(str(err))
    else:
        st.write("Please upload a resume in your Profile section first.")
