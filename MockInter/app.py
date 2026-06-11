import streamlit as st
import os
import sys
import json
import time
import re
import google.generativeai as genai
import numpy as np
import speech_recognition as sr
import threading
import cv2
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, RTCConfiguration
from PIL import Image as PILImage

# Add parent dir to path for shared theme
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------
# Environment and API Configuration
# ---------------------------
load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY') or os.getenv('API_KEY'))

# ---------------------------
# MongoDB Connection
# ---------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client["mock_interviews"]
feedback_collection = db["feedbacks"]


def store_face_log(student_id, message):
    collection = db["face_logs"]
    try:
        collection.insert_one({
            "student_id": student_id,
            "timestamp": datetime.now(),
            "violation": message
        })
    except Exception as e:
        st.error(f"Error logging face violation: {e}")


def rerun_app():
    st.rerun()


# ---------------------------
# Video Transformer with Proctoring
# ---------------------------
class VideoTransformer(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
        self.no_face_warning_count = 0
        self.multiple_face_warning_count = 0
        self.eye_gaze_warning_count = 0
        self.last_no_face_warning_time = time.time()
        self.last_multiple_warning_time = time.time()
        self.last_eye_gaze_warning_time = time.time()
        self.test_terminated = False
        self.no_face_frames = 0
        self.multiple_face_frames = 0
        self.frame_threshold = 5
        self.warning_interval = 2
        self.warning_limit = 10
        self.proctoring_enabled = False
        self.student_id = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        if not self.proctoring_enabled:
            return img

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        current_time = time.time()
        violation_message = None

        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) == 0:
            self.no_face_frames += 1
            if self.no_face_frames >= self.frame_threshold:
                if current_time - self.last_no_face_warning_time > self.warning_interval:
                    self.no_face_warning_count += 1
                    self.last_no_face_warning_time = current_time
                    if self.student_id:
                        store_face_log(self.student_id, "No Face Detected!")
                violation_message = "No Face Detected!"
        else:
            self.no_face_frames = 0

        if len(faces) > 1:
            self.multiple_face_frames += 1
            if self.multiple_face_frames >= self.frame_threshold:
                if current_time - self.last_multiple_warning_time > self.warning_interval:
                    self.multiple_face_warning_count += 1
                    self.last_multiple_warning_time = current_time
                    if self.student_id:
                        store_face_log(self.student_id, "Multiple Faces Detected!")
                violation_message = "Multiple Faces Detected!"
        else:
            self.multiple_face_frames = 0

        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if len(faces) == 1:
            (fx, fy, fw, fh) = faces[0]
            face_roi_gray = gray[fy:fy + fh, fx:fx + fw]
            eyes = self.eye_cascade.detectMultiScale(face_roi_gray, scaleFactor=1.1, minNeighbors=5)
            for (ex, ey, ew, eh) in eyes:
                cv2.rectangle(img, (fx + ex, fy + ey), (fx + ex + ew, fy + ey + eh), (255, 0, 0), 2)

            eye_violation = False
            if len(eyes) < 2:
                eye_violation = True
            else:
                for (ex, ey, ew, eh) in eyes:
                    eye_roi = face_roi_gray[ey:ey + eh, ex:ex + ew]
                    eye_roi = cv2.equalizeHist(eye_roi)
                    _, thresholded = cv2.threshold(eye_roi, 30, 255, cv2.THRESH_BINARY_INV)
                    contours, _ = cv2.findContours(thresholded, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        max_contour = max(contours, key=cv2.contourArea)
                        M = cv2.moments(max_contour)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            if cx < ew / 4 or cx > 3 * ew / 4:
                                eye_violation = True
                    else:
                        eye_violation = True

            if eye_violation:
                violation_message = "Not Looking at Screen!"
                if current_time - self.last_eye_gaze_warning_time > self.warning_interval:
                    self.eye_gaze_warning_count += 1
                    self.last_eye_gaze_warning_time = current_time
                    if self.student_id:
                        store_face_log(self.student_id, "Not Looking at Screen!")

        if violation_message:
            overlay = img.copy()
            cv2.rectangle(overlay, (0, 0), (img.shape[1], img.shape[0]), (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.4, img, 0.6, 0, img)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = img.shape[1] / 800
            thickness = max(2, int(img.shape[1] / 400))
            text_size, _ = cv2.getTextSize(violation_message, font, font_scale, thickness)
            text_x = (img.shape[1] - text_size[0]) // 2
            text_y = (img.shape[0] + text_size[1]) // 2
            cv2.putText(img, violation_message, (text_x, text_y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        if (self.no_face_warning_count >= self.warning_limit or
                self.multiple_face_warning_count >= self.warning_limit or
                self.eye_gaze_warning_count >= self.warning_limit):
            self.test_terminated = True

        return img


RTC_CONFIGURATION = RTCConfiguration({
    "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
})


# ---------------------------
# Interview Functions
# ---------------------------
def get_gemini_questions(job_role, job_description, experience):
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"""Generate five interview questions for a **{job_role}** role.
The candidate has {experience} years of experience.

Job Description:
{job_description}

Based on the job description above, generate 5 targeted interview questions that:
1. Assess the specific skills and technologies mentioned in the JD
2. Test both technical knowledge and problem-solving ability
3. Are appropriate for the candidate's experience level
4. Include a mix of conceptual, practical, and behavioral questions

Return ONLY the numbered questions, one per line."""
    response = model.generate_content([prompt])
    questions = response.text.split("\n")
    filtered = [q.strip() for q in questions if q.strip() and q.strip()[0].isdigit()]
    for i, q in enumerate(filtered):
        if not q.endswith("?"):
            filtered[i] = q + "?"
    return filtered


def process_answer(question, answer):
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"""Evaluate the following candidate's answer to an interview question.
    Provide a score out of 10 based on correctness, depth, and relevance, and give detailed feedback.
    Question: {question}
    Answer: {answer}"""
    response = model.generate_content([prompt])
    return response.text


def record_audio():
    """Record audio from microphone using PyAudio and transcribe via Google."""
    recognizer = sr.Recognizer()
    result = {"text": None, "error": None}

    def _do_record():
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)
            text = recognizer.recognize_google(audio)
            result["text"] = text
        except sr.WaitTimeoutError:
            result["error"] = "timeout"
        except sr.UnknownValueError:
            result["error"] = "unclear"
        except sr.RequestError:
            result["error"] = "network"
        except Exception as e:
            result["error"] = str(e)

    thread = threading.Thread(target=_do_record, daemon=True)
    thread.start()
    thread.join(timeout=45)  # hard cap so it never hangs forever

    if thread.is_alive():
        result["error"] = "timeout"

    return result


# ---------------------------
# Page Config & Custom CSS
# ---------------------------
st.set_page_config(page_title="AI Mock Interview", page_icon="🎙️", layout="wide")

try:
    from cc_theme import inject_theme
    inject_theme()
except ImportError:
    pass


# ---------------------------
# Session State Init
# ---------------------------
if "interviews" not in st.session_state:
    st.session_state.interviews = []

params = st.query_params
query_username = params.get("username", "")

# ---------------------------
# Sidebar: Camera + Proctoring
# ---------------------------
with st.sidebar:
    st.markdown("### 📹 Live Proctoring")
    camera = webrtc_streamer(
        key="camera",
        video_transformer_factory=VideoTransformer,
        rtc_configuration=RTC_CONFIGURATION,
        async_processing=True,
        media_stream_constraints={"video": True, "audio": False}
    )

    cam_active = (camera and hasattr(camera, "video_transformer") and camera.video_transformer is not None)

    if cam_active:
        st.divider()
        st.markdown("#### ⚠️ Violation Tracker")
        c1, c2, c3 = st.columns(3)
        c1.metric("👤", camera.video_transformer.no_face_warning_count, help="No Face")
        c2.metric("👥", camera.video_transformer.multiple_face_warning_count, help="Multiple")
        c3.metric("👁️", camera.video_transformer.eye_gaze_warning_count, help="Gaze")
    else:
        st.caption("Start camera for proctoring")

    st.divider()
    st.markdown("### ℹ️ How it works")
    st.markdown("""
    1. Fill in your interview details
    2. Start the camera for proctoring
    3. Answer questions via **voice** or **text**
    4. Get AI-powered feedback
    """)


# ---------------------------
# Main Interface
# ---------------------------
if "current_interview" not in st.session_state:
    # === LANDING PAGE ===
    st.markdown("""
    <div class="cc-hero">
        <h1>🎙️ AI Mock Interview</h1>
        <p>Practice with AI-generated questions & get instant feedback</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    if st.button("➕ Start New Interview", type="primary", use_container_width=True):
        st.session_state.show_form = True

    if st.session_state.get("show_form"):
        st.markdown("### 📋 Interview Setup")
        with st.form("interview_form"):
            if query_username:
                username = query_username
                st.text_input("👤 Logged in as:", value=username, disabled=True)
            else:
                username = st.text_input("👤 Username", placeholder="Enter your username")

            col_a, col_b = st.columns([1, 1])
            with col_a:
                job_role = st.text_input("💼 Job Role", placeholder="Ex. Full Stack Developer")
            with col_b:
                experience = st.number_input("📅 Years of Experience", min_value=0, max_value=30, step=1)

            job_description = st.text_area(
                "📄 Job Description",
                placeholder="Paste the job description here for better, more targeted interview questions...",
                height=150
            )

            fc1, fc2 = st.columns(2)
            with fc1:
                start_btn = st.form_submit_button("🚀 Start Interview", type="primary", use_container_width=True)
            with fc2:
                cancel_btn = st.form_submit_button("✖ Cancel", use_container_width=True)

            if cancel_btn:
                st.session_state.show_form = False
                rerun_app()

            if start_btn:
                if not username or not job_role or not job_description:
                    st.warning("Please fill in username, job role, and job description.")
                else:
                    with st.spinner("🤖 Generating interview questions from your JD..."):
                        questions = get_gemini_questions(job_role, job_description, experience)

                    interview_data = {
                        "username": username,
                        "role": job_role,
                        "job_description": job_description,
                        "experience": experience,
                        "questions": questions,
                        "responses": [],
                        "created_at": datetime.now().strftime('%Y-%m-%d %H:%M')
                    }
                    st.session_state.current_interview = interview_data
                    st.session_state.interviews.append(interview_data)
                    st.session_state.show_form = False
                    st.session_state.question_index = 0
                    if cam_active:
                        camera.video_transformer.proctoring_enabled = True
                        camera.video_transformer.student_id = username
                    rerun_app()

    # === PREVIOUS INTERVIEWS ===
    if st.session_state.interviews:
        st.divider()
        st.markdown("### 📂 Previous Interviews")
        for i, iv in enumerate(st.session_state.interviews):
            if not iv.get("responses"):
                continue
            created = iv.get("created_at", "N/A")
            with st.expander(f"🎯 {iv['role']} ({created})"):
                for idx, resp in enumerate(iv["responses"]):
                    st.markdown(f"**Q{idx+1}.** {resp['question']}")
                    st.markdown(f"**Your Answer:** {resp['answer']}")
                    st.markdown(f"**Feedback:** {resp['feedback']}")
                    st.divider()

# ---------------------------
# Active Interview
# ---------------------------
if "current_interview" in st.session_state:
    interview = st.session_state.current_interview
    index = st.session_state.question_index
    total_q = len(interview["questions"])

    # Show camera warning but DON'T block the interview
    if not cam_active:
        st.warning("📹 Camera not active — start it in the sidebar for proctoring. You can still proceed.")

    # Header
    st.markdown(f"""
    <div class="cc-glass" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
        <div>
            <h3 style="margin:0; color:#818cf8 !important;">🎯 {interview['role']}</h3>
            <p style="color:#94a3b8; margin:4px 0 0;">📅 {interview['experience']} yrs experience</p>
        </div>
        <div style="text-align:right;">
            <span style="color:#94a3b8;">Question</span>
            <span style="font-size:1.5rem; font-weight:700; color:#818cf8;"> {min(index+1, total_q)}</span>
            <span style="color:#94a3b8;"> / {total_q}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Progress bar
    progress_val = index / total_q if total_q > 0 else 0
    st.progress(progress_val)

    if index < total_q:
        question_text = interview["questions"][index]

        # Question card
        st.markdown(f"""
        <div class="cc-glass">
            <div style="display:flex; align-items:center; margin-bottom:12px;">
                <span class="cc-badge">{index+1}</span>
                <span style="color:#818cf8; font-weight:600; font-size:0.9rem;">QUESTION {index+1} OF {total_q}</span>
            </div>
            <p style="font-size:1.15rem; color:#f1f5f9; line-height:1.6; margin:0;">{question_text}</p>
        </div>
        """, unsafe_allow_html=True)

        # Answer section
        recorded_key = f"recorded_answer_{index}"
        if recorded_key not in st.session_state:
            st.session_state[recorded_key] = ""

        answer_widget_key = f"answer_{index}"
        answer = st.text_area(
            "✍️ Your Answer",
            key=answer_widget_key,
            value=st.session_state.get(recorded_key, ""),
            height=150,
            placeholder="Type your answer here, or click Record to speak..."
        )

        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            if st.button("🎤 Record Answer", key=f"record_{index}", use_container_width=True):
                with st.spinner("🎤 Listening... speak now!"):
                    result = record_audio()

                if result["text"]:
                    st.session_state[recorded_key] = result["text"]
                    st.success(f"✅ Recorded: \"{result['text'][:80]}...\"")
                    time.sleep(1)
                    rerun_app()
                elif result["error"] == "timeout":
                    st.warning("⏱️ No speech detected. Try again or type your answer.")
                elif result["error"] == "unclear":
                    st.warning("🔇 Could not understand audio. Please try again.")
                elif result["error"] == "network":
                    st.error("🌐 Speech recognition service unavailable.")
                else:
                    st.error(f"🎤 Error: {result['error']}")

        with col2:
            is_last = (index == total_q - 1)
            btn_label = "✅ Submit & Finish" if is_last else "➡️ Next Question"
            if st.button(btn_label, key=f"next_{index}", type="primary", use_container_width=True):
                final_answer = st.session_state.get(answer_widget_key, "")
                if not final_answer.strip():
                    st.warning("Please provide an answer before proceeding.")
                else:
                    with st.spinner("🤖 AI is evaluating your answer..."):
                        feedback = process_answer(question_text, final_answer)
                    response_data = {
                        "username": interview["username"],
                        "question": question_text,
                        "answer": final_answer,
                        "feedback": feedback
                    }
                    feedback_collection.insert_one(response_data)
                    interview["responses"].append(response_data)
                    st.session_state.question_index += 1
                    # Clear recorded answer and audio processed flag
                    for k in [recorded_key, f"audio_processed_{index}"]:
                        if k in st.session_state:
                            del st.session_state[k]
                    rerun_app()

        with col3:
            if st.button("🚪 End Interview", key="end_early", use_container_width=True):
                if cam_active:
                    camera.video_transformer.proctoring_enabled = False
                del st.session_state["current_interview"]
                del st.session_state["question_index"]
                rerun_app()

    else:
        # === INTERVIEW COMPLETE ===
        if cam_active:
            camera.video_transformer.proctoring_enabled = False

        st.markdown("""
        <div class="cc-hero">
            <h1>🎉 Interview Completed!</h1>
            <p>Here's your detailed performance summary</p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        for idx, response in enumerate(interview["responses"]):
            with st.expander(f"📝 Question {idx + 1}: {response['question'][:80]}...", expanded=(idx == 0)):
                st.markdown(f"**🗣️ Your Answer:**")
                st.info(response['answer'])
                st.markdown(f"**🤖 AI Feedback:**")
                st.markdown(response['feedback'])
            st.markdown("")

        if st.button("🏠 Close & Return", type="primary", use_container_width=True):
            if cam_active:
                camera.video_transformer.no_face_warning_count = 0
                camera.video_transformer.multiple_face_warning_count = 0
                camera.video_transformer.eye_gaze_warning_count = 0
            del st.session_state["current_interview"]
            del st.session_state["question_index"]
            rerun_app()
