@echo off

REM Base directory
set BASE_DIR=D:\MIT\sem 7\capstone\Working V3

REM Terminal 1 — Main Node.js Server
start cmd /k "cd /d "%BASE_DIR%" && node server.js"

REM Terminal 2 — Aptitude Test (port 8501)
start cmd /k "cd /d "%BASE_DIR%\Aptitude" && streamlit run AptiApp.py --server.port 8501 --server.headless true"

REM Terminal 3 — Aptitude Dashboard (port 8502)
start cmd /k "cd /d "%BASE_DIR%\Aptitude" && streamlit run InteractiveDashboard.py --server.port 8502 --server.headless true"

REM Terminal 4 — DSA Coding Test (port 8503)
start cmd /k "cd /d "%BASE_DIR%\CodingPract" && streamlit run DSA_app_db.py --server.port 8503 --server.headless true"

REM Terminal 5 — DSA Dashboard (port 8504)
start cmd /k "cd /d "%BASE_DIR%\CodingPract" && streamlit run DSA_dash.py --server.port 8504 --server.headless true"

REM Terminal 6 — Mock Interview (port 8505)
start cmd /k "cd /d "%BASE_DIR%\MockInter" && streamlit run app.py --server.port 8505 --server.headless true"

REM Terminal 7 — Resume ATS & Builder (port 8506)
start cmd /k "cd /d "%BASE_DIR%\ResumeATS" && streamlit run app.py --server.port 8506 --server.headless true"

REM Terminal 8 — Interview Prep (port 8507)
start cmd /k "cd /d "%BASE_DIR%\InterviewPrep" && python -m streamlit run app.py --server.port 8507 --server.headless true"

REM Terminal 9 — Resume Builder (port 8508)
start cmd /k "cd /d "%BASE_DIR%\ResumeBuilder" && python -m streamlit run app.py --server.port 8508 --server.headless true"

REM Terminal 10 — Study Plan Generator (port 8509)
start cmd /k "cd /d "%BASE_DIR%\StudyPlan" && python -m streamlit run app.py --server.port 8509 --server.headless true"
timeout /t 2 /nobreak >nul

REM Open ONLY the main page in browser
timeout /t 3 /nobreak >nul
start http://localhost:3000