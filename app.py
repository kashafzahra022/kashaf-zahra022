import streamlit as st
import pypdf
import sqlite3
import urllib.parse
import collections
import re
import pandas as pd
import plotly.express as px
import hashlib
import os
import html
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Database Setup
DB_NAME = 'research_vault.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            full_name TEXT,
            organization TEXT,
            role TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    for column_name, column_type in [("full_name", "TEXT"), ("organization", "TEXT"), ("role", "TEXT")]:
        if column_name not in columns:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS research_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            authors TEXT,
            pub_year TEXT,
            abstract TEXT,
            keywords TEXT,
            upload_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("PRAGMA table_info(research_papers)")
    research_columns = [row[1] for row in cursor.fetchall()]
    if 'user_id' not in research_columns:
        cursor.execute('ALTER TABLE research_papers ADD COLUMN user_id INTEGER')
    if 'source_file' not in research_columns:
        cursor.execute('ALTER TABLE research_papers ADD COLUMN source_file TEXT')

    conn.commit()
    conn.close()

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Authentication functions
def register_user(username, email, password, full_name="", organization="", role=""):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, email, password, full_name, organization, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, email, hash_password(password), full_name, organization, role))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def check_email_exists(email):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1], "email": user[2]}
    return None

# SMTP Email Sender for OTP Verification
def send_otp_email(receiver_email, otp_code):
    CENTRAL_SENDER = "zahrakashaf263@gmail.com"
    # ⚠️ Replace with your 16-character App Password (Gmail App Passwords)
    CENTRAL_PASSWORD = "idylfopyzqbbrayy" 
    
    message = MIMEMultipart()
    message["From"] = f"Research Vault Security <{CENTRAL_SENDER}>"
    message["To"] = receiver_email  
    message["Subject"] = f"🔑 {otp_code} is your Research Vault Verification Code"
    
    body = f"""
    Hello,
    
    You are trying to log in to the Additive Manufacturing Composite Analyzer.
    
    Your secure Verification Code is: {otp_code}
    
    If you did not request this, please ignore this email.
    
    Regards,
    Research Hub Security Team
    """
    message.attach(MIMEText(body, "plain"))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(CENTRAL_SENDER, CENTRAL_PASSWORD)
        server.sendmail(CENTRAL_SENDER, receiver_email, message.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to deliver security code. Error details: {e}")
        return False

def insert_paper(title, authors, pub_year, abstract, keywords, source_file=""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    user_id = st.session_state.get('user_id')
    cursor.execute('''
        INSERT INTO research_papers (user_id, title, authors, pub_year, abstract, keywords, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, title, authors, pub_year, abstract, keywords, source_file))
    conn.commit()
    conn.close()

def get_filtered_papers(search_query, search_by):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    user_id = st.session_state.get('user_id')

    if search_query:
        if search_by == "Keyword":
            cursor.execute("SELECT * FROM research_papers WHERE user_id = ? AND keywords LIKE ? ORDER BY id DESC",
                          (user_id, f'%{search_query}%'))
        elif search_by == "Author":
            cursor.execute("SELECT * FROM research_papers WHERE user_id = ? AND authors LIKE ? ORDER BY id DESC",
                          (user_id, f'%{search_query}%'))
        elif search_by == "Year":
            cursor.execute("SELECT * FROM research_papers WHERE user_id = ? AND pub_year LIKE ? ORDER BY id DESC",
                          (user_id, f'%{search_query}%'))
        else: # Topic / Title
            cursor.execute("SELECT * FROM research_papers WHERE user_id = ? AND (title LIKE ? OR abstract LIKE ?) ORDER BY id DESC",
                          (user_id, f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('SELECT * FROM research_papers WHERE user_id = ? ORDER BY id DESC', (user_id,))

    data = cursor.fetchall()
    conn.close()
    return data

# --- SMART AI HEURISTIC EXTRACTOR ---
def automatic_extractor(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    if not lines:
        return "Untitled Paper", "Unknown Author", "", "", "2026"

    # 1. Title Extraction
    title = "Untitled Paper"
    author_start_idx = 0

    title_lines = []
    for i, line in enumerate(lines[:15]):
        line_lower = line.lower()
        line_clean = line.strip()

        if any(stop in line_lower for stop in ["email", "@", "department of", "university", "institute", "*correspondence", "abstract"]):
            author_start_idx = i
            break

        if len(line_clean) < 5 or re.match(r'^[\d\s.,-]+$', line_clean):
            continue

        if re.search(r'\b[A-Z][a-z]+,\s*[A-Z]{2}\b|\b[A-Z][a-z]+,\s*[A-Z][a-z\s]+\b', line_clean):
            if len(title_lines) > 0:
                author_start_idx = i
                break
            continue

        if any(word in line_lower for word in ["michigan state", "maryland", "department of", "college", "street", "avenue"]):
            if len(title_lines) > 0:
                author_start_idx = i
                break
            continue

        if len(line_clean) > 8:
            title_lines.append(line_clean)
            if len(title_lines) >= 3:
                break

    if title_lines:
        title = " ".join(title_lines).strip()
        title = re.sub(r'[,;]*\s*$', '', title)
        if title.isupper() and len(title) > 10:
            title = title.title()

    if author_start_idx == 0 and title_lines:
        author_start_idx = min(len(title_lines) + 1, len(lines) - 1)

    # 2. Author Extraction
    authors = "Unknown Author"

    for i, line in enumerate(lines[author_start_idx:min(author_start_idx+15, len(lines))]):
        line_lower = line.lower()

        if any(word in line_lower for word in ["department", "university", "email", "@", "institute", "faculty", "abstract", "background", "correspondence", "résumé"]):
            continue

        has_comma = ',' in line
        has_and = ' and ' in line_lower
        capital_word_count = len([w for w in line.split() if w and w[0].isupper()])

        if (has_comma or has_and) and capital_word_count >= 2:
            clean_line = re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹*•†‡§∥¶#]', '', line)
            clean_line = re.sub(r',?\d+[,\s]', ', ', clean_line)
            clean_line = clean_line.strip()
            clean_line = re.sub(r'\s+', ' ', clean_line)

            parts = re.split(r',\s*|and\s+|&\s*', clean_line, flags=re.IGNORECASE)

            valid_names = []
            for part in parts:
                part = part.strip()
                if not part or len(part) < 2:
                    continue

                if any(skip in part.lower() for skip in ["background", "article", "research", "letter", "online", "correspondence", "affiliation"]):
                    continue

                if any(c.isupper() for c in part):
                    part = re.sub(r'^[\d\s]+|[\d\s]+$', '', part).strip()
                    if part and len(part) >= 2:
                        valid_names.append(part)

            if len(valid_names) >= 2:
                authors = ", ".join(valid_names)
                break

    if authors == "Unknown Author" and len(lines) > author_start_idx:
        for line in lines[author_start_idx:min(author_start_idx+10, len(lines))]:
            if any(word in line.lower() for word in ["department", "abstract", "background", "email", "@"]):
                continue
            capital_words = [w for w in line.split() if w and w[0].isupper()]
            if len(capital_words) >= 2:
                clean = re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹*•†‡§\d]', '', line).strip()
                clean = re.sub(r'\s+', ' ', clean)
                if len(clean) > 10:
                    authors = clean
                    break

    # 3. Year Extraction
    pub_year = "2026"
    year_match = re.search(r'\b(20[0-2][0-6]|19[9][0-9])\b', text)
    if year_match:
        pub_year = year_match.group(0)

    # 4. Keywords Extraction
    kw_match = re.search(r'\b(keywords|key\s*words|index\s*terms|key-words)\b\s*[:.-]?(.*)', text, re.IGNORECASE)
    if kw_match:
        kw_line = kw_match.group(2).split('\n')[0]
        keywords = kw_line.strip().rstrip('.-')
    else:
        clean_text = re.sub(r'[^a-zA-Z\s]', '', text)
        words = [w.title() for w in clean_text.split() if len(w) > 5 and w.lower() not in ['abstract', 'introduction', 'keywords', 'journal', 'university', 'research']]
        unique_words = list(dict.fromkeys(words))
        keywords = ", ".join(unique_words[:5])

    # 5. Abstract Extraction
    abs_match = re.search(r'\b(abstract|summary)\b\s*[:.-]?', text, re.IGNORECASE)
    if abs_match:
        start_idx = abs_match.end()
        remaining_text = text[start_idx:].strip()
        end_markers = ["keywords", "key words", "index terms", "1. introduction", "introduction"]
        end_idx = -1
        for marker in end_markers:
            m_match = re.search(r'\b' + marker + r'\b', remaining_text, re.IGNORECASE)
            if m_match:
                end_idx = m_match.start()
                break
        if end_idx != -1 and end_idx > 10:
            abstract = remaining_text[:end_idx].strip()
        else:
            abstract = " ".join(remaining_text.split()[:150]) + "..."
    else:
        valid_lines = [l for l in lines[2:8] if not any(k in l.lower() for k in ["doi", "vol", "http", "issn"])]
        abstract = " ".join(valid_lines)[:400] + "..."

    return title, authors, abstract, keywords, pub_year

init_db()

# --- STREAMLIT CONFIG ---
st.set_page_config(page_title="AddiComp Research Hub", page_icon="🔬", layout="wide")

# Initialize session state variables
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'auth_step' not in st.session_state:
    st.session_state.auth_step = 'welcome'
if 'temp_user_data' not in st.session_state:
    st.session_state.temp_user_data = None
if 'sent_otp' not in st.session_state:
    st.session_state.sent_otp = None

# Custom sign-in function
def login_user(username_or_email, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hashed = hash_password(password)
    cursor.execute('''
        SELECT id, username, email FROM users 
        WHERE (username = ? OR email = ?) AND password = ?
    ''', (username_or_email, username_or_email, hashed))
    user = cursor.fetchone()
    conn.close()
    return user

# --- SHARED THEME CSS ---
AUTH_THEME_CSS = """
<style>
[data-testid="stAppViewContainer"], .main {
    background:
        radial-gradient(circle at 15% 20%, rgba(56,189,248,0.20), transparent 28%),
        radial-gradient(circle at 85% 10%, rgba(129,140,248,0.24), transparent 30%),
        radial-gradient(circle at 50% 100%, rgba(14,165,233,0.18), transparent 35%),
        linear-gradient(135deg, #030712 0%, #0f172a 40%, #111827 100%) !important;
    background-attachment: fixed !important;
}

#MainMenu, header, footer {visibility: hidden;}

.hero-wrap {
    text-align: center;
    padding: 70px 24px 34px 24px;
}

.hero-badge {
    display: inline-block;
    padding: 8px 18px;
    border-radius: 999px;
    background: rgba(56,189,248,0.12);
    border: 1px solid rgba(56,189,248,0.35);
    color: #7dd3fc;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 2.2px;
    text-transform: uppercase;
    margin-bottom: 18px;
}

.hero-title {
    font-size: 58px;
    font-weight: 900;
    line-height: 1.12;
    margin: 0 auto 18px auto;
    max-width: 780px;
    background: linear-gradient(120deg, #ffffff 15%, #bfdbfe 40%, #c4b5fd 80%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-shadow: 0 10px 40px rgba(56,189,248,0.16);
}

.hero-subtitle {
    font-size: 19px;
    color: #dbeafe;
    font-weight: 600;
    max-width: 680px;
    margin: 0;
    line-height: 1.7;
    text-align: center;
    width: 100%;
}

.hero-subtitle-wrap {
    display: flex;
    justify-content: center;
    width: 100%;
    margin-bottom: 18px;
}

.hero-pill-row {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
}

.hero-pill {
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.14);
    color: #e2e8f0;
    padding: 8px 16px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
}

.card-panel {
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
    backdrop-filter: blur(22px);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 24px;
    padding: 36px 30px;
    box-shadow: 0 25px 80px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.08);
    max-width: 480px;
    margin: 0 auto;
}

.card-title {
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 6px;
}

.card-subtitle {
    font-size: 14px;
    color: #94a3b8;
    margin-bottom: 22px;
}

.stTextInput > div > div > input {
    border-radius: 12px !important;
    padding: 11px 14px !important;
    background: rgba(255,255,255,0.98) !important;
    color: #0f172a !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
}

.stButton > button {
    border-radius: 14px !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #2563eb, #7c3aed) !important;
    color: white !important;
    border: none !important;
    padding: 12px 18px !important;
    box-shadow: 0 10px 28px rgba(37,99,235,0.34) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 14px 34px rgba(124,58,237,0.42) !important;
}

.secondary-btn button {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    box-shadow: none !important;
}

.back-link button {
    background: transparent !important;
    color: #93c5fd !important;
    box-shadow: none !important;
    font-weight: 700 !important;
    padding: 4px 0 !important;
}

.privacy-note {
    text-align: center;
    color: #94a3b8;
    font-size: 13px;
    margin-top: 24px;
}
</style>
"""

UPLOAD_SUMMARY_CSS = """
<style>
.upload-summary-list {
    display: grid;
    gap: 12px;
    margin-top: 10px;
}
.upload-summary-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04));
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 16px;
    padding: 14px 16px;
    box-shadow: 0 10px 26px rgba(0,0,0,0.24);
    border-left: 3px solid #38bdf8;
}
.upload-summary-file {
    font-size: 14px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 6px;
    word-break: break-word;
}
.upload-summary-status {
    display: inline-block;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #7dd3fc;
    margin-bottom: 8px;
}
.upload-summary-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
}
.upload-summary-chip {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    background: rgba(56,189,248,0.16);
    color: #bae6fd;
    border: 1px solid rgba(56,189,248,0.28);
}
.upload-summary-text {
    color: #cbd5e1;
    font-size: 13px;
    line-height: 1.45;
    margin-top: 6px;
}
</style>
"""

# --- LANDING / AUTH FLOW (not logged in) ---
if not st.session_state.logged_in:
    st.markdown(AUTH_THEME_CSS, unsafe_allow_html=True)

    if st.session_state.auth_step == 'welcome':
        st.markdown("""
        <div class="hero-wrap">
            <div class="hero-badge">Premium Research Experience</div>
            <div class="hero-title">Welcome to Your<br>3D Research Hub</div>
            <div class="hero-subtitle-wrap">
                <p class="hero-subtitle">
                    A modern and polished workspace for uploading research papers, extracting smart metadata,
                    and managing your private composite-materials library with clarity and confidence.
                </p>
            </div>
            <div class="hero-pill-row">
                <div class="hero-pill">Smart PDF Extraction</div>
                <div class="hero-pill">Private Secure Vault</div>
                <div class="hero-pill">Beautiful Analytics</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        b1, b2, b3 = st.columns(3, gap="medium")
        with b1:
            if st.button("Sign Up", use_container_width=True, key="go_signup"):
                st.session_state.auth_step = 'signup'
                st.rerun()
        with b2:
            if st.button("Sign In", use_container_width=True, key="go_signin"):
                st.session_state.auth_step = 'signin'
                st.rerun()
        with b3:
            if st.button("Continue with Google", use_container_width=True, key="go_google"):
                st.session_state.auth_step = 'google'
                st.rerun()

        st.markdown('<p class="privacy-note">Your data stays private — passwords are hashed and never stored in plain text.</p>', unsafe_allow_html=True)

    elif st.session_state.auth_step == 'signup':
        st.markdown('<div class="back-link">', unsafe_allow_html=True)
        if st.button("⬅ Back to Welcome", key="back_from_signup"):
            st.session_state.auth_step = 'welcome'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Create Your Account</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-subtitle">Set up your private research vault in a minute.</div>', unsafe_allow_html=True)

        signup_full_name = st.text_input("Full Name", key="signup_full_name", placeholder="Enter your full name")
        signup_username = st.text_input("Username", key="signup_user", placeholder="Pick a unique username")
        signup_email = st.text_input("Email Address", key="signup_email", placeholder="your.email@example.com")
        signup_organization = st.text_input("Organization", key="signup_org", placeholder="University / Lab / Company")
        signup_role = st.text_input("Role", key="signup_role", placeholder="Researcher / Student / Engineer")
        signup_password = st.text_input("Password", type="password", key="signup_pass", placeholder="At least 6 characters")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_pass", placeholder="Re-enter password")

        if st.button("Create Account", use_container_width=True, key="signup_btn"):
            if not signup_full_name or not signup_username or not signup_email or not signup_password:
                st.error("Please fill all required fields")
            elif signup_password != confirm_password:
                st.error("Passwords do not match")
            elif len(signup_password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                if register_user(signup_username, signup_email, signup_password, signup_full_name, signup_organization, signup_role):
                    st.success("Account created successfully. You can sign in now.")
                    st.balloons()
                    st.session_state.auth_step = 'welcome'
                    st.rerun()
                else:
                    st.error("Username or email already exists")
        st.markdown('</div>', unsafe_allow_html=True)

    elif st.session_state.auth_step == 'signin':
        st.markdown('<div class="back-link">', unsafe_allow_html=True)
        if st.button("⬅ Back to Welcome", key="back_from_signin"):
            st.session_state.auth_step = 'welcome'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Welcome Back</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-subtitle">Sign in to access your research vault.</div>', unsafe_allow_html=True)

        login_username = st.text_input("Username or Email", key="login_user", placeholder="Enter your username or email")
        login_password = st.text_input("Password", type="password", key="login_pass", placeholder="Enter your password")

        if st.button("Sign In", use_container_width=True, key="login_btn"):
            user = login_user(login_username, login_password)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = user[1]
                st.session_state.user_id = user[0]
                st.session_state.auth_step = 'welcome'
                st.success(f"Welcome back, {user[1]}!")
                st.balloons()
                st.rerun()
            else:
                st.error("Invalid username/email or password")
        st.markdown('</div>', unsafe_allow_html=True)

    elif st.session_state.auth_step == 'google':
        st.markdown('<div class="back-link">', unsafe_allow_html=True)
        if st.button("⬅ Back to Welcome", key="back_from_google"):
            st.session_state.auth_step = 'welcome'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Continue with Google</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-subtitle">Secure verification via email.</div>', unsafe_allow_html=True)

        google_email = st.text_input("Google Email", key="google_email", placeholder="name@gmail.com")
        google_name = st.text_input("Display Name", key="google_name", placeholder="Your name")
        
        if st.button("Request Security Code", use_container_width=True, key="google_btn"):
            if google_email:
                user_info = check_email_exists(google_email)
                if user_info:
                    generated_otp = str(random.randint(100000, 999999))
                    st.session_state.sent_otp = generated_otp
                    st.session_state.temp_user_data = user_info
                    with st.spinner("Delivering secure access code..."):
                        if send_otp_email(google_email, generated_otp):
                            st.session_state.auth_step = 'otp_verify'
                            st.rerun()
                else:
                    st.error("Account matching this email was not found. Please sign up first.")
            else:
                st.error("Please enter your Google email")
        st.markdown('</div>', unsafe_allow_html=True)

    elif st.session_state.auth_step == 'otp_verify':
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Verify OTP Code</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-subtitle">A verification code has been dispatched to your email.</div>', unsafe_allow_html=True)

        otp_val = st.text_input("Verification Code", max_chars=6, placeholder="Enter 6-digit code")

        if st.button("Confirm & Login", use_container_width=True):
            if otp_val == st.session_state.sent_otp:
                st.session_state.logged_in = True
                st.session_state.username = st.session_state.temp_user_data['username']
                st.session_state.user_id = st.session_state.temp_user_data['id']
                st.session_state.auth_step = 'welcome'
                st.success("Secure verification completed successfully.")
                st.balloons()
                st.rerun()
            else:
                st.error("The verification code entered is invalid.")
        st.markdown('</div>', unsafe_allow_html=True)

# --- MAIN APP (AFTER LOGIN) ---
else:
    st.title("AddiComp Research Hub")
    # Show research topic and, if available, the currently extracted paper's title and authors
    topic_text = "Mechanical characterization of 3D printed/additively manufactured composite materials."
    if st.session_state.get('auto_title'):
        paper_title = st.session_state.get('auto_title')
        paper_authors = st.session_state.get('auto_authors') or 'Unknown Author'
        st.markdown(f"**Research Topic:** {topic_text}  ")
        st.markdown(f"**Current Paper:** **{html.escape(paper_title)}** — {html.escape(paper_authors)}")
    else:
        st.markdown(f"**Research Topic:** {topic_text}")

    with st.sidebar:
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.user_id = None
            st.session_state.auth_step = 'welcome'
            st.session_state.extracted_papers = []
            st.session_state.uploaded_pdf_names = []
            st.rerun()
        st.caption(f"Logged in as: **{st.session_state.username}**")

    if 'auto_title' not in st.session_state: st.session_state.auto_title = ""
    if 'auto_authors' not in st.session_state: st.session_state.auto_authors = ""
    if 'auto_abstract' not in st.session_state: st.session_state.auto_abstract = ""
    if 'auto_keywords' not in st.session_state: st.session_state.auto_keywords = ""
    if 'auto_year' not in st.session_state: st.session_state.auto_year = "2026"
    if 'extracted_papers' not in st.session_state: st.session_state.extracted_papers = []
    if 'uploaded_pdf_names' not in st.session_state: st.session_state.uploaded_pdf_names = []

    st.sidebar.header("Step 1: Upload Paper(s)")
    uploaded_files = st.sidebar.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

    if uploaded_files:
        current_names = [uploaded_file.name for uploaded_file in uploaded_files]
        if st.session_state.get('uploaded_pdf_names') != current_names:
            with st.spinner("Auto-extracting metadata from uploaded PDFs..."):
                extracted_papers = []
                for uploaded_file in uploaded_files:
                    reader = pypdf.PdfReader(uploaded_file)
                    full_text = ""
                    for page in reader.pages[:3]:
                        text_content = page.extract_text()
                        if text_content:
                            full_text += text_content + "\n"

                    t, a, abs_txt, k, y = automatic_extractor(full_text)
                    if not t or t == "Untitled Paper":
                        t = uploaded_file.name.rsplit('.', 1)[0]

                    extracted_papers.append({
                        "name": uploaded_file.name,
                        "title": t,
                        "authors": a,
                        "abstract": abs_txt,
                        "keywords": k,
                        "year": y,
                    })

                st.session_state.extracted_papers = extracted_papers
                st.session_state.uploaded_pdf_names = current_names
                if extracted_papers:
                    first_paper = extracted_papers[0]
                    st.session_state.auto_title = first_paper['title']
                    st.session_state.auto_authors = first_paper['authors']
                    st.session_state.auto_abstract = first_paper['abstract']
                    st.session_state.auto_keywords = first_paper['keywords']
                    st.session_state.auto_year = first_paper['year']
                st.sidebar.success(f"Extraction complete for {len(extracted_papers)} PDF(s)!")

    tab_upload, tab_search, tab_stats = st.tabs(["Upload & Process", "Advanced Search", "System Statistics"])

    # --- TAB 1: UPLOAD & PROCESS ---
    with tab_upload:
        st.markdown(UPLOAD_SUMMARY_CSS, unsafe_allow_html=True)
        col1, col2 = st.columns([1.3, 0.7])
        with col1:
            st.subheader("Extracted Papers")
            if st.session_state.extracted_papers:
                for idx, paper in enumerate(st.session_state.extracted_papers):
                    with st.expander(f"{idx + 1}. {paper['title']}", expanded=(idx == 0)):
                        st.write(f"**File:** {paper['name']}")
                        st.write(f"**Authors:** {paper['authors']}")
                        st.write(f"**Year:** {paper['year']}")
                        st.write(f"**Keywords:** {paper['keywords']}")
                        st.write(f"**Abstract:** {paper['abstract']}")

                if st.button("Save All Extracted Papers", use_container_width=True, key="save_all_papers"):
                    saved_count = 0
                    for paper in st.session_state.extracted_papers:
                        if paper.get('title'):
                            insert_paper(paper['title'], paper['authors'], paper['year'], paper['abstract'], paper['keywords'], paper.get('name', ''))
                            saved_count += 1
                    if saved_count:
                        st.success(f"Saved {saved_count} paper(s) into SQLite database!")
                        st.rerun()
                    else:
                        st.error("No valid papers were available to save.")
            else:
                st.info("Upload one or more PDF files to extract their metadata here.")

        with col2:
            st.subheader("Upload Summary")
            if st.session_state.extracted_papers:
                st.markdown("<div class='upload-summary-list'>", unsafe_allow_html=True)
                for paper in st.session_state.extracted_papers:
                    title = paper['title'] if paper['title'] else paper['name']
                    title = title[:90] + "..." if len(title) > 90 else title
                    authors = paper['authors'] or 'Unknown Author'
                    year = paper['year'] or 'N/A'
                    keywords = paper['keywords'] or 'No keywords'
                    keyword_count = len([k.strip() for k in keywords.split(',') if k.strip()]) if keywords else 0
                    safe_file_name = paper['name'].replace('<', '&lt;').replace('>', '&gt;')
                    safe_title = title.replace('<', '&lt;').replace('>', '&gt;')
                    safe_authors = authors.replace('<', '&lt;').replace('>', '&gt;')
                    st.markdown(f"""
                    <div class='upload-summary-card'>
                        <div class='upload-summary-file'>{safe_file_name}</div>
                        <div class='upload-summary-status'>Status: Extracted</div>
                        <div class='upload-summary-text'><b>Title:</b> {safe_title}</div>
                        <div class='upload-summary-text'><b>Authors:</b> {safe_authors}</div>
                        <div class='upload-summary-meta'>
                            <span class='upload-summary-chip'>Extracted</span>
                            <span class='upload-summary-chip'>Year: {year}</span>
                            <span class='upload-summary-chip'>Keywords: {keyword_count}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No files extracted yet.")

            st.markdown("---")
            st.subheader("Quick Research Links")
            st.caption("Auto-generated web search links for your loaded papers:")
            
            if st.session_state.extracted_papers:
                for idx, paper in enumerate(st.session_state.extracted_papers):
                    query = urllib.parse.quote_plus(paper['title'])
                    search_url = f"https://duckduckgo.com/?q={query}"
                    st.link_button(f"Search web: '{paper['title'][:40]}...'", search_url, use_container_width=True, key=f"search_link_{idx}")
            else:
                st.caption("Upload a paper to activate search shortcuts.")

    # --- TAB 2: ADVANCED SEARCH ---
    with tab_search:
        st.subheader("Filter & Retrieve")
        search_query = st.text_input("Enter search phrase...", placeholder="e.g., Carbon Fiber, 2026, or Mechanical Strength")
        search_by = st.selectbox("Field Focus", ["Topic / Title", "Author", "Year", "Keyword"])

        db_papers = get_filtered_papers(search_query, search_by)
        if db_papers:
            st.markdown(f"**Found {len(db_papers)} paper(s)** inside your vault:")
            for paper in db_papers:
                with st.expander(f"[{paper['pub_year']}] - {paper['title']}"):
                    st.write(f"**Abstract:**\n{paper['abstract']}")
        else:
            st.warning("No papers match your query inside the database.")

    # --- TAB 3: SYSTEM STATISTICS (MATCHED TO YOUR SCREENSHOTS) ---
    with tab_stats:
        db_papers = get_filtered_papers("", "")
        
        if db_papers:
            df = pd.DataFrame([dict(p) for p in db_papers])
            
            # Clean dataframe values
            df['pub_year'] = df['pub_year'].fillna('Unknown')
            df['source_file'] = df['source_file'].fillna('unnamed_paper.pdf')
            
            # Row 1: Papers by Year and Author Breakdown
            st.markdown("### Document Overview")
            fig_col1, fig_col2 = st.columns(2)
            
            with fig_col1:
                year_group = df.groupby('pub_year').size().reset_index(name='Papers')
                fig_year = px.bar(
                    year_group,
                    x='pub_year',
                    y='Papers',
                    title='Papers by Year',
                    labels={'pub_year': 'Year', 'Papers': 'Number of Papers'},
                    template='plotly_white'
                )
                fig_year.update_layout(
                    xaxis_title='Year',
                    yaxis_title='Number of Papers',
                    bargap=0.2,
                    margin=dict(t=50, b=40)
                )
                st.plotly_chart(fig_year, use_container_width=True)
                
            with fig_col2:
                author_expanded = df.assign(
                    Author=df['authors'].fillna('Unknown Author').str.split(',')
                ).explode('Author')
                author_expanded['Author'] = author_expanded['Author'].astype(str).str.strip()
                author_expanded = author_expanded[author_expanded['Author'] != '']
                author_group = author_expanded.groupby('Author').size().reset_index(name='Papers')
                author_group = author_group.sort_values('Papers', ascending=False).head(10)
                fig_author = px.pie(
                    author_group,
                    values='Papers',
                    names='Author',
                    title='Paper Distribution by Author',
                    hole=0.4,
                    template='plotly_white'
                )
                fig_author.update_traces(textposition='inside', textinfo='percent+label')
                fig_author.update_layout(margin=dict(t=50, b=40))
                st.plotly_chart(fig_author, use_container_width=True)
                
            st.markdown('---')
            
            # Row 2: Publication Overview Table
            st.markdown('### Publications Data Table')
            table_df = df.groupby(['pub_year', 'source_file']).size().reset_index(name='Papers')
            table_df.columns = ['Year', 'File', 'Papers']
            st.dataframe(table_df, use_container_width=True)
            
            st.markdown('---')
            
            # Row 3: Topic and Keyword Charts
            st.markdown('## Topic and Keyword Analysis')
            st.caption('Visualize your collection by top topics, publication year, and author distribution.')
            
            topic_data = []
            for _, row in df.iterrows():
                topic_text = row['keywords']
                if topic_text and topic_text != 'No keywords':
                    parts = [t.strip().title() for t in re.split(r',|;', topic_text) if t.strip()]
                    for topic in parts:
                        topic_data.append({'Topic': topic, 'Source File': row['source_file']})
            
            if topic_data:
                df_topic = pd.DataFrame(topic_data)
                topic_group = df_topic.groupby('Topic').size().reset_index(name='Mentions')
                topic_group = topic_group.sort_values('Mentions', ascending=False).head(10)
                topic_col1, topic_col2 = st.columns(2)
                
                with topic_col1:
                    fig_topic_bar = px.bar(
                        topic_group,
                        x='Topic',
                        y='Mentions',
                        title='Top Topics from Keywords',
                        labels={'Topic': 'Topic', 'Mentions': 'Mentions'},
                        template='plotly_white'
                    )
                    fig_topic_bar.update_layout(xaxis_tickangle=-45, margin=dict(t=50, b=80))
                    st.plotly_chart(fig_topic_bar, use_container_width=True)
                
                with topic_col2:
                    fig_topic_pie = px.pie(
                        topic_group,
                        values='Mentions',
                        names='Topic',
                        title='Top Topic Share',
                        hole=0.4,
                        template='plotly_white'
                    )
                    fig_topic_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_topic_pie.update_layout(margin=dict(t=50, b=40))
                    st.plotly_chart(fig_topic_pie, use_container_width=True)
            else:
                st.info('No keyword/topic data available for charts.')

            st.markdown('---')

            keyword_data_list = []
            for _, row in df.iterrows():
                kws = row['keywords']
                filename = row['source_file']
                if kws and kws != 'No keywords':
                    parts = [k.strip().title() for k in re.split(r',|;', kws) if k.strip()]
                    for p in parts:
                        keyword_data_list.append({'Keyword': p, 'Source File': filename})

            if keyword_data_list:
                df_kws_expanded = pd.DataFrame(keyword_data_list)
                kw_counts = df_kws_expanded.groupby(['Keyword', 'Source File']).size().reset_index(name='Frequency')
                top_10_kws_list = df_kws_expanded['Keyword'].value_counts().head(10).index.tolist()
                kw_counts_filtered = kw_counts[kw_counts['Keyword'].isin(top_10_kws_list)]

                fig_kw_col1, fig_kw_col2 = st.columns(2)

                with fig_kw_col1:
                    fig_kw_stacked = px.bar(
                        kw_counts_filtered,
                        x='Keyword',
                        y='Frequency',
                        color='Source File',
                        title='Top Keywords by File',
                        labels={'Keyword': 'Keyword', 'Frequency': 'Frequency', 'Source File': 'Source File'},
                        template='plotly_white'
                    )
                    fig_kw_stacked.update_layout(
                        barmode='stack',
                        legend=dict(orientation='h', yanchor='bottom', y=-0.3, xanchor='left', x=0),
                        margin=dict(t=50, b=80)
                    )
                    st.plotly_chart(fig_kw_stacked, use_container_width=True)

                with fig_kw_col2:
                    kw_file_mentions = df_kws_expanded.groupby('Source File').size().reset_index(name='Mentions')
                    fig_kw_donut = px.pie(
                        kw_file_mentions,
                        values='Mentions',
                        names='Source File',
                        title='Keyword Mentions per File',
                        hole=0.4,
                        template='plotly_white'
                    )
                    fig_kw_donut.update_traces(textposition='inside', textinfo='percent+label')
                    fig_kw_donut.update_layout(margin=dict(t=50, b=40))
                    st.plotly_chart(fig_kw_donut, use_container_width=True)

                st.markdown('---')
                st.markdown('### Keywords Analysis Table')
                kw_grouped_table = df_kws_expanded.groupby('Keyword').agg(
                    Total_Frequency=('Keyword', 'count'),
                    From_Papers=('Source File', lambda x: ', '.join(sorted(list(set(x)))))
                ).reset_index().sort_values(by='Total_Frequency', ascending=False)
                st.dataframe(kw_grouped_table, use_container_width=True)
            else:
                st.info('No keyword datas extracted to plot charts.')
        else:
            st.info("The system statistics require processed and saved database documents.")