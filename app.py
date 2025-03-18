from flask import Flask, request, render_template, redirect, url_for, session, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import fitz  # PyMuPDF
import pdfplumber
import re
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "idkwihffyon?"
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# User class
class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

# Database setup
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2])
    return None

@app.route('/')
def index():
    return render_template('initial.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('register'))

    return render_template('register.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1], user[2]))
            return redirect(url_for('upload'))
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html', username=username)

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# PDF processing functions...

def extract_text_with_bboxes(pdf_path):
    doc = fitz.open(pdf_path)
    text_data = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text_data.append({
                            "text": span["text"],
                            "bbox": span["bbox"]
                        })
    return text_data

def detect_column_layout(text_data):
    x_coords = [item["bbox"][0] for item in text_data]
    min_x = min(x_coords)
    max_x = max(x_coords)
    mid_x = (max_x + min_x) / 2

    left_block = sum(1 for x in x_coords if x < mid_x)
    right_block = sum(1 for x in x_coords if x >= mid_x)
    if left_block - right_block < 20 or left_block > 50 or right_block > 50:
        return "Double Column"
    else:
        return "Single Column"

def calculate_column_threshold(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]
        lines = first_page.objects.get("line", [])
        vertical_lines = [line for line in lines if abs(line["x0"] - line["x1"]) < 1]

        if not vertical_lines:
            return 250

        vertical_lines.sort(key=lambda x: x["x0"])
        threshold = None
        for line in vertical_lines:
            if line["x0"] > 90:
                threshold = line["x0"]
                break

        return threshold if threshold else 250

def detect_columns_and_extract_text(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        l = []
        first_page = pdf.pages[0]
        column_threshold = calculate_column_threshold(pdf_path)
        text_elements = first_page.extract_words(x_tolerance=2, y_tolerance=2)

        left_lines = []
        right_lines = []
        current_left_line = []
        current_right_line = []

        last_top_left = -1
        last_top_right = -1

        for element in text_elements:
            word = element["text"]
            x0 = element["x0"]
            top = element["top"]

            if x0 < column_threshold:
                if last_top_left != -1 and top > last_top_left + 5:
                    left_lines.append(" ".join(current_left_line))
                    current_left_line = []
                current_left_line.append(word)
                last_top_left = top
            else:
                if last_top_right != -1 and top > last_top_right + 5:
                    right_lines.append(" ".join(current_right_line))
                    current_right_line = []
                current_right_line.append(word)
                last_top_right = top

        if current_left_line:
            left_lines.append(" ".join(current_left_line))
        if current_right_line:
            right_lines.append(" ".join(current_right_line))

        l.extend(left_lines)
        l.extend(right_lines)

        result = []
        for word in l:
            if word[0].islower():
                if result:
                    result[-1] += ' ' + word
                else:
                    result.append(word)
            else:
                result.append(word)

        final = '\n'.join(result)
        s = final.split('\n')
        return s

def extract_text_lines(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []

        for page_num in range(len(pdf.pages)):
            page = pdf.pages[page_num]
            words = page.extract_words()
            sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
            current_line = []
            current_top = None

            for word in sorted_words:
                if current_top is None or abs(word['top'] - current_top) > 3:
                    if current_line:
                        all_lines.append(" ".join(current_line))
                    current_line = [word['text']]
                    current_top = word['top']
                else:
                    current_line.append(word['text'])

            if current_line:
                all_lines.append(" ".join(current_line))

        return all_lines

def extract_paragraph_after_keywords(lines, keywords):
    section_headers = {'experience', 'professional experience', 'education', 'projects', 'language', 'certifications'}

    for i, line in enumerate(lines):
        if any(keyword.lower() == line.lower().replace(":", "") for keyword in keywords):
            paragraph = []
            for line_after in lines[i + 1:]:
                normalized_line = line_after.strip().lower()
                if any(header.lower() == normalized_line.replace(":", "") for header in section_headers):
                    break
                paragraph.append(line_after.strip())
            return '\n'.join(paragraph)
    return None

def identify_skills(text, target_skills, keywords):
    found_skills = []
    skills_paragraph = extract_paragraph_after_keywords(text, keywords)
    skills_paragraph = skills_paragraph.lower() if skills_paragraph else ""
    for skill in target_skills:
        if skill.lower() in skills_paragraph:
            found_skills.append(skill)
    return found_skills

def extract_experience(text):
    if isinstance(text, list):  # Ensure text is a string
        text = "\n".join(text)

    experiences = []
    lines = text.splitlines()
    year_pattern = r'([A-Za-z]+)?\s*(\d{4})\s*[-–]\s*([A-Za-z]+)?\s*(\d{4}|PRESENT|Present)'
    role_pattern = r'\b(?:engineer|manager|developer|designer|specialist|analyst|consultant|lead|architect|marketer|secretary|assistant|executive\s+secretary)\b'

    current_year = datetime.now().year
    current_month = datetime.now().month

    for i, line in enumerate(lines):
        year_match = re.search(year_pattern, line)
        if year_match:
            start_month_name, start_year, end_month_name, end_year_raw = year_match.groups()
            start_month = month_to_number(start_month_name) if start_month_name else 1
            end_month = month_to_number(end_month_name) if end_month_name else 12
            start_year = int(start_year)
            end_year = current_year if end_year_raw.lower() in ['present'] else int(end_year_raw)

            years = calculate_years_worked(start_year, start_month, end_year, end_month)

            role = "Unknown"
            for offset in range(-2, 3):
                line_index = i + offset
                if 0 <= line_index < len(lines):
                    role_line = lines[line_index]
                    role_match = re.search(role_pattern, role_line, re.IGNORECASE)
                    if role_match:
                        role = role_match.group(0)
                        break

            experiences.append({
                "years": years,
                "start_year": start_year,
                "end_year": end_year if end_year else "Present",
                "role": role
            })

    return experiences


def calculate_years_worked(start_year, start_month, end_year, end_month):
    return round(((end_year - start_year) * 12 + (end_month - start_month)) / 12, 1)

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
]

def month_to_number(month):
    months_dict = {m: i + 1 for i, m in enumerate(MONTHS)}
    return months_dict.get(month.lower(), 1)

def calculate_experience_value(experiences):
    total_experience_value = 0
    for exp in experiences:
        years = exp.get("years", 0)
        total_experience_value += years
    return total_experience_value

def rank_candidate(pdf_path, required_skills, keywords, text):
    candidate_ranks = {}
    skills = identify_skills(text, required_skills, keywords)
    num_required_skills_found = len(set(skills) & set(required_skills))

    if num_required_skills_found == len(required_skills):
        rank = 1
    elif num_required_skills_found > 0:
        rank = len(required_skills) - num_required_skills_found + 1
    else:
        rank = len(required_skills) + 1

    candidate_ranks[pdf_path] = rank
    return candidate_ranks

def process_resumes(file_paths, role, experience):
    role_skills = {
        "Software Engineer": ["Python", "Data Structures", "Algorithms", "System Design", "Git", "OOP"],
        "Data Scientist": ["Python", "Machine Learning", "Statistics", "Data Visualization", "SQL", "Deep Learning"],
        "UI/UX Designer": ["User  Research", "Wireframing", "Figma", "Prototyping", "Adobe XD", "Interaction Design"],
        "Backend Developer": ["Node.js", "Python", "API", "Java", "Database", "SpringBoot"],
        "Frontend Developer": ["JavaScript", "React", "CSS", "HTML", "TypeScript", "Redux"],
        "DevOps Engineer": ["CI/CD", "Docker", "Kubernetes", "Cloud Platforms", "Terraform", "Bash Scripting"],
        "Cybersecurity Analyst": ["Network Security", "Penetration Testing", "Cryptography", "SIEM", "Incident Response"],
        "Mobile App Developer": ["Flutter", "React Native", "Swift", "Kotlin", "Firebase", "REST APIs"],
        "AI Engineer": ["Deep Learning", "TensorFlow", "PyTorch", "Computer Vision", "NLP", "Reinforcement Learning"],
        "Cloud Engineer": ["AWS", "Azure", "Google Cloud", "Infrastructure as Code", "Serverless Computing"],
        "Product Manager": ["Agile Methodologies", "Roadmap Planning", "User  Research", "Market Analysis", "Scrum"],
        "Business Analyst": ["Data Analysis", "SQL", "Business Intelligence", "Requirements Gathering", "Excel"],
        "Database Administrator": ["SQL", "PostgreSQL", "NoSQL", "Database Optimization", "Backup & Recovery"],
        "Game Developer": ["Unity", "Unreal Engine", "C#", "Game Physics", "3D Modeling", "Blender"],
        "Embedded Systems Engineer": ["C", "Microcontrollers", "IoT", "RTOS", "Firmware Development"],
        "Blockchain Developer": ["Solidity", "Ethereum", "Smart Contracts", "Cryptography", "Hyperledger"],
        "Digital Marketer": ["SEO", "Google Ads", "Content Marketing", "Social Media", "Email Marketing"],
        "Mechanical Engineer": ["AutoCAD", "SolidWorks", "ANSYS", "Manufacturing Processes", "CFD"],
        "Electrical Engineer": ["Circuit Design", "MATLAB", "Embedded Systems", "Power Systems", "PLC"],
        "Biomedical Engineer": ["Medical Devices", "Biomaterials", "Biomedical Imaging", "Signal Processing"],
    }

    required_skills = role_skills.get(role, [])
    rankings = []

    for pdf_file in file_paths:
        try:
            text_data = extract_text_with_bboxes(pdf_file)
            layout = detect_column_layout(text_data)

            if layout == "Single Column":
                lines = extract_text_lines(pdf_file)
            else:
                lines = detect_columns_and_extract_text(pdf_file)

            skills_paragraph = extract_paragraph_after_keywords(lines, ['skills', 'TECH SKILLS', 's k i l l s', 'skill'])
            if skills_paragraph:
                candidate_ranks = rank_candidate(pdf_file, required_skills, ['skills'], lines)
                skills_rank = candidate_ranks.get(pdf_file, len(required_skills) + 1)
            else:
                skills_rank = len(required_skills) + 1

            experiences = extract_experience(lines)
            total_experience_value = calculate_experience_value(experiences)

            if total_experience_value < experience:
                skills_rank += 1  # Penalize if experience is less than required

            rankings.append({
                "filename": os.path.basename(pdf_file),
                "skills_rank": skills_rank,
                "experience_rank": total_experience_value,
                "file_url": url_for('get_resume', filename=os.path.basename(pdf_file)),
            })

        except Exception as e:
            print(f"Error processing file {pdf_file}: {e}")

    # Sort rankings based on skills rank and experience rank
    rankings.sort(key=lambda x: (x['skills_rank'], x['experience_rank']))
    return rankings

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == 'POST':
        if "files" not in request.files:
            flash("No file part")
            return redirect(request.url)

        files = request.files.getlist("files")
        role = request.form.get("role")
        experience = request.form.get("experience")

        if not files or files[0].filename == '':
            flash("No selected files")
            return redirect(request.url)

        if not experience or not experience.isdigit() or int(experience) < 0:
            flash("Please enter a valid work experience in years.")
            return redirect(request.url)

        experience = int(experience)

        file_paths = []
        for file in files:
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(file_path)
            file_paths.append(file_path)

        # Process the uploaded resumes
        rankings = process_resumes(file_paths, role, experience)
        session["rankings"] = rankings

        return redirect(url_for('results'))  # Redirect to results after upload
    
    return render_template('upload.html')


@app.route('/results')
@login_required
def results():
    rankings = session.get("rankings", [])
    top_rankings = rankings[:5]  # Get only the top 5 rankings
    return render_template('results.html', rankings=top_rankings)

@app.route('/resume/<filename>', endpoint='get_resume')  # Ensure unique endpoint name
def get_resume(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
