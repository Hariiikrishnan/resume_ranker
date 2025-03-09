from flask import Flask, request, render_template, jsonify , send_from_directory
import os
import random  # Simulating ranking logic


import fitz  # PyMuPDF
import pdfplumber
import matplotlib.pyplot as plt
from pypdf import PdfReader
import nltk
from nltk.corpus import wordnet
import PyPDF2
import re
from datetime import datetime



app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
r = {}

p = {}
skills_rankings = {}
experience_rankings = {}


nltk.download('wordnet')

def extract_text_with_bboxes(pdf_path):                                             #NISHITHA
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

def detect_column_layout(text_data):                                                  #NISHITHA
    # Analyze bounding boxes to detect columns
    x_coords = [item["bbox"][0] for item in text_data]  # X-coordinate of each text block
    min_x = min(x_coords)
    max_x = max(x_coords)
    mid_x = (max_x + min_x) / 2  # Middle X-coordinate to check for columns

    # If there are two distinct groups of text blocks, it's likely double-columned
    left_block = sum(1 for x in x_coords if x < mid_x)
    right_block = sum(1 for x in x_coords if x >= mid_x)
    if left_block - right_block < 20 or left_block>50 or right_block>50:
        return "Double Column"
    else:
        return  "Single Column"

# Function to extract text line by line, preserving reading order
# def extract_text_lines(pdf_path):                                                          #SAI
#     with pdfplumber.open(pdf_path) as pdf:
#         all_lines = []

#         for page_num in range(len(pdf.pages)):
#             page = pdf.pages[page_num]

#             # Extract words with positions
#             words = page.extract_words()

#             # Sort words first by top (vertical position) and then by x0 (horizontal position)
#             sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))

#             # Group words into lines based on vertical proximity (top position)
#             current_line = []
#             current_top = None

#             for word in sorted_words:
#                 # If the word's vertical position differs significantly from the last line, it's a new line
#                 if current_top is None or abs(word['top'] - current_top) > 3:  # 3 pixels threshold for line separation
#                     if current_line:
#                         all_lines.append(" ".join(current_line))
#                     current_line = [word['text']]
#                     current_top = word['top']
#                 else:
#                     current_line.append(word['text'])

#             # Add the last line
#             if current_line:
#                 all_lines.append(" ".join(current_line))

#         return all_lines

def calculate_column_threshold(pdf_path):                                                 #SAI
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]  # Take the first page

        # Extract all line objects
        lines = first_page.objects.get("line", [])

        # Filter for vertical lines (where x0 ≈ x1, meaning it's a straight vertical line)
        vertical_lines = [line for line in lines if abs(line["x0"] - line["x1"]) < 1]

        if not vertical_lines:
            return 250  # Default threshold if no vertical lines are found

        # Sort vertical lines by x-coordinate (left to right)
        vertical_lines.sort(key=lambda x: x["x0"])

        # Check for a valid threshold line
        threshold = None
        for line in vertical_lines:
            if line["x0"] > 90:  # Ensure threshold is greater than 90
                threshold = line["x0"]
                break  # Use the first valid line and stop checking

        # If no valid vertical line is found, return a default threshold
        return threshold if threshold else 250

def detect_columns_and_extract_text(pdf_path):                                           #SAI
    with pdfplumber.open(pdf_path) as pdf:
        l = []
        first_page = pdf.pages[0]  # Take the first page

        # Automatically determine the column threshold
        column_threshold = calculate_column_threshold(pdf_path)

        # Extract words with their positions
        text_elements = first_page.extract_words(x_tolerance=2, y_tolerance=2)

        # Separate words into left and right columns based on x-coordinates
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

        # Append the last lines in each column
        if current_left_line:
            left_lines.append(" ".join(current_left_line))
        if current_right_line:
            right_lines.append(" ".join(current_right_line))

        l.extend(left_lines)
        l.extend(right_lines)

# Filter the words that start with a lowercase letter and join them with a space
        result = []
        for word in l:
            if word[0].islower():
                  if result:
                     result[-1] += ' ' + word  # Merge with the previous one
                  else:
                     result.append(word)
            else:
              result.append(word)  # Keep words that start with an uppercase letter as they are

# Join the list into a single string with '/n' between them
        final = '\n'.join(result)
        s = final.split('\n')
        return s

def get_synonyms(word):
    """
    Retrieves synonyms for a given word using WordNet.

    Args:
        word: The word to find synonyms for.

    Returns:
        A list of synonyms for the word.
    """
    synonyms = []
    for synset in wordnet.synsets(word):
        for lemma in synset.lemmas():
            synonyms.append(lemma.name())
    return list(set(synonyms))

# Function to extract and display the layout of the page
def display_pdf_layout(pdf_path):                                                  #SANDY
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        im = page.to_image()

        # Show the page image with word boxes
        im.debug_tablefinder()
        plt.imshow(im.original)
        plt.axis('off')
        plt.show()

# Function to extract text from a PDF while maintaining the correct order

# Function to extract text line by line, preserving reading order
def extract_text_lines(pdf_path):                                                   #SAI
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []

        for page_num in range(len(pdf.pages)):
            page = pdf.pages[page_num]

            # Extract words with positions
            words = page.extract_words()

            # Sort words first by top (vertical position) and then by x0 (horizontal position)
            sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))

            # Group words into lines based on vertical proximity (top position)
            current_line = []
            current_top = None

            for word in sorted_words:
                # If the word's vertical position differs significantly from the last line, it's a new line
                if current_top is None or abs(word['top'] - current_top) > 3:  # 3 pixels threshold for line separation
                    if current_line:
                        all_lines.append(" ".join(current_line))
                    current_line = [word['text']]
                    current_top = word['top']
                else:
                    current_line.append(word['text'])

            # Add the last line
            if current_line:
                all_lines.append(" ".join(current_line))

        return all_lines


def extract_paragraph_after_keywords(lines, keywords):                               #SAI
    # Normalize section headers for better matching
    section_headers = {'experience', 'professional experience', 'education', 'projects', 'language', 'certifications',"L A N G U A G E S","LANGUAGES","E X P E R I E N C E"}

    # Loop through the lines to find any of the keywords
    for i, line in enumerate(lines):
        if any(keyword.lower()==line.lower().replace(":", "") for keyword in keywords):  # Case-insensitive match
            paragraph = []
            for line_after in lines[i + 1:]:
                normalized_line = line_after.strip().lower()

                # Stop at the next section header or if line contains 'skills'
                if any(header.lower() == normalized_line.replace(":", "") for header in section_headers) :
                    break  # Stop once 'skills' is found

                paragraph.append(line_after.strip())  # Keep adding text until the next section

            return '\n'.join(paragraph)  # Return as a single paragraph
    return None


def extract_paragraph_after_keywords1(lines, keywords):
    # Normalize section headers for better matching
    section_headers = {'Skills','References','education', 'projects','language', 'certifications','L a n g u a g e s','E D U C A T I O N',"LANGUAGES","P R O J E C T",'PROJECTS'}

    # Loop through the lines to find any of the keywords
    for i, line in enumerate(lines):
        if any(keyword.lower()==line.lower().replace(":", "") for keyword in keywords):  # Case-insensitive match
            paragraph = []
            for line_after in lines[i + 1:]:
                normalized_line = line_after.strip().lower()

                # Stop at the next section header or if line contains 'skills'
                if any(header.lower() == normalized_line.replace(":", "") for header in section_headers) :
                    break  # Stop once 'skills' is found

                paragraph.append(line_after.strip())  # Keep adding text until the next section

            return '\n'.join(paragraph)  # Return as a single paragraph
    return None



def identify_skills(text,target_skills,keywords):                                     #SAI
    found_skills = []
    skills_paragraph = extract_paragraph_after_keywords(text,keywords)
    skills_paragraph = skills_paragraph.lower()
    for i in target_skills:
      if i.lower() in skills_paragraph.lower():
        found_skills.append(i)
    return found_skills





# Function to extract experience from resume text
def calculate_years_worked(start_year, end_year):                                        #SANDY
    try:
        start = datetime.strptime(str(start_year), "%Y")
        end = datetime.strptime(str(end_year), "%Y")
        years_worked = (end - start).days / 365.25
        return years_worked
    except Exception as e:
        return 0

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
]

# Function to convert month name to number
def month_to_number(month):
    """Convert month name to a numerical value (1-12)."""
    months_dict = {m: i+1 for i, m in enumerate(MONTHS)}
    return months_dict.get(month.lower(), 1)  # Default to 1 if not found

# Function to check if a line contains a month
def contains_month(text):
    """Returns True if a month is found in the text."""
    return any(month in text.lower() for month in MONTHS)

# Function to calculate years worked (only if a month is present)
def calculate_years_worked(start_year, start_month, end_year, end_month):
    """Calculate total years worked based on month & year values."""
    return round(((end_year - start_year) * 12 + (end_month - start_month)) / 12, 1)

# Function to extract experience from resume text
def extract_experience(text):                                                         #SANDY
    experiences = []
    lines = text.splitlines()

    # Regex pattern for date range (supports both "Year-Year" and "Month Year - Month Year")
    year_pattern = r'([A-Za-z]+)?\s*(\d{4})\s*[-–]\s*([A-Za-z]+)?\s*(\d{4}|PRESENT|Present)'
    role_pattern = r'\b(?:engineer|manager|developer|designer|specialist|analyst|consultant|lead|architect|marketer|secretary|assistant|executive\s+secretary)\b'  # Common roles

    current_year = datetime.now().year
    current_month = datetime.now().month

    for i, line in enumerate(lines):
        year_match = re.search(year_pattern, line)
        if year_match:
            start_month_name, start_year, end_month_name, end_year_raw = year_match.groups()

            # Check if months are present in the extracted data
            has_month = contains_month(line)

            if has_month:
                start_month = month_to_number(start_month_name) if start_month_name else 1
                end_month = month_to_number(end_month_name) if end_month_name else 12
            else:
                start_month, end_month = 1, 12  # Default to full years if no months present

            start_year = int(start_year)
            end_year = current_year if end_year_raw.lower() in ['present'] else int(end_year_raw)

            # Call calculate_years_worked() only if a month is present
            years = calculate_years_worked(start_year, start_month, end_year, end_month)

            # Search for the role in the current line, next two lines, and the previous two lines (if available)
            role = "Unknown"
            for offset in range(-2, 3):  # Check from two lines before to two lines after
                    line_index = i + offset
                    if 0 <= line_index < len(lines): # Ensure the index is within bounds
                        role_line = lines[line_index]
                        role_match = re.search(role_pattern, role_line, re.IGNORECASE)
                        if role_match:
                            role = role_match.group(0)
                            break  # Exit the loop once a role is found

            experiences.append({
                "years": years,
                "start_year": start_year,
                "end_year": end_year if end_year else "Present",
                "months_used": has_month,  # Indicate if months were used
                "role": role
            })

    print("Experiences:", experiences, '\n')

    return experiences


# Function to assign priority to different roles (you can modify this priority system)
def assign_priority(role):
    role_priority = {
        'manager': 2,
        'designer': 1,
        'developer': 1,
        'engineer': 1,
        'assistant': 2,
        'director': 3,
        'analyst': 1,
        'secretary':0.5
        # Add more roles as necessary
    }
    role = role.lower()
    return role_priority.get(role, 0)  # Default priority is 1 if not listed

# Function to calculate total weighted experience value
def calculate_experience_value(experiences):                                         #SANDY
    total_experience_value = 0
    for exp in experiences:
        years = exp.get("years", 0)
        role = exp.get("role", "Unknown")
        priority = assign_priority(role)
        total_experience_value += years * priority
    return total_experience_value

# ranking the candidate according to their skills
def rank_candidate(pdf_path,required_skills,keywords,text):                           #SANDY

    candidate_ranks = {}
    skills = identify_skills(text,required_skills,keywords)
    num_required_skills_found = len(set(skills) & set(required_skills))  # Number of matching skills

    if num_required_skills_found == len(required_skills):  # All required skills present
        rank = 1
    elif num_required_skills_found > 0:
        rank = len(required_skills) - num_required_skills_found + 1  # Adjust rank based on missing skills
    else:  # No required skill present
        rank = len(required_skills) + 1

    candidate_ranks[pdf_path] = rank

    return candidate_ranks

# Function to rank candidates based on their experience values
def rank_candidates(resumes,keywords):                                               #SANDY

  candidates_data = []
  for resume in resumes:
        if resume in p and p[resume] == "Single Column":
            lines = extract_text_lines(resume)

        else:
            lines = detect_columns_and_extract_text(resume)
        text = extract_paragraph_after_keywords1(lines,keywords)
        print(resume,"\n",text,"\n")
        if text:
          experiences = extract_experience(text)
          total_value = calculate_experience_value(experiences)
          print("the score : ",total_value,"\n")
          candidates_data.append((resume, total_value))
        else:
          candidates_data.append((resume,0))

  return candidates_data




def sort_and_rank_dict(input_dict):                                                        #NISHITHA
    # Sort the dictionary by the values (ascending order)
    sorted_items = sorted(input_dict.items(), key=lambda item: item[1], reverse=True)

    # Create a dictionary to store the ranks
    rank_dict = {key: rank + 1 for rank, (key, _) in enumerate(sorted_items)}

    # Retain the original order of keys and add the ranks to them
    result = {key: rank_dict[key] for key in input_dict}

    return result

def sort_dictionaries(d, d1):
    # Ensure d1 is a dictionary
    if isinstance(d1, list):
        d1 = dict(d1)  # Convert list to dictionary

    # Step 1: Sort the first dictionary d by its values (low to high)
    sorted_d = sorted(d.items(), key=lambda x: d1.get(x[0], 0))

    # Step 2: Check for ties in d and sort using d1 if necessary (low to high)
    sorted_result = []
    i = 0
    while i < len(sorted_d):
        # Get all keys with the same value from d
        same_value_keys = [sorted_d[i]]
        j = i + 1
        while j < len(sorted_d) and sorted_d[j][1] == sorted_d[i][1]:
            same_value_keys.append(sorted_d[j])
            j += 1

        # If there are multiple keys with the same value in d, sort them using d1 (low to high)
        if len(same_value_keys) > 1:
            same_value_keys.sort(key=lambda x: d1.get(x[0], 0))  # Ascending order for d1

        # Add the sorted keys (by d1 if needed) to the result
        sorted_result.extend(same_value_keys)

        # Move to the next set of different values
        i = j

    # Extract just the keys and return as a list
    sorted_keys = [key for key, value in sorted_result]
    return sorted_keys


# a=0
# for i in sorted_keys:
#   # Display the page layout
#         a+=1
#         print(a,"\n")
#         # display_pdf_layout(i)


if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)



@app.route('/')
def index():
    return render_template('index.html')

# Endpoint to serve resumes
@app.route("/resume/<filename>")
def get_resume(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)   

@app.route("/upload", methods=["POST"])
def upload_file():
    print(request.form.get("role"))
    if "files" not in request.files:
        return jsonify({"error": "No file part"})

    files = request.files.getlist("files")  # Get all uploaded files
    role = request.form.get("role")  # Get all uploaded files

    if not files or files[0].filename == '':
        return jsonify({"error": "No selected files"})

    file_paths = []  # Store paths of uploaded files
    for file in files:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)
        file_paths.append(file_path)

    # Now, process ALL uploaded files
    pdf_files = [f for f in file_paths if f.endswith((".pdf", ".docx"))]

    # required_skills = ["user research", "Python", "data Structures", "algorithms"]
    role_skills = {
    "Software Engineer": ["Python", "Data Structures", "Algorithms", "System Design", "Git", "OOP"],
    "Data Scientist": ["Python", "Machine Learning", "Statistics", "Data Visualization", "SQL", "Deep Learning"],
    "UI/UX Designer": ["User Research", "Wireframing", "Figma", "Prototyping", "Adobe XD", "Interaction Design"],
    "Backend Developer": ["Node.js", "Python", "API", "Java", "Database", "SpringBoot"],
    "Frontend Developer": ["JavaScript", "React", "CSS", "HTML", "TypeScript", "Redux"],
    "DevOps Engineer": ["CI/CD", "Docker", "Kubernetes", "Cloud Platforms", "Terraform", "Bash Scripting"],
    "Cybersecurity Analyst": ["Network Security", "Penetration Testing", "Cryptography", "SIEM", "Incident Response"],
    "Mobile App Developer": ["Flutter", "React Native", "Swift", "Kotlin", "Firebase", "REST APIs"],
    "AI Engineer": ["Deep Learning", "TensorFlow", "PyTorch", "Computer Vision", "NLP", "Reinforcement Learning"],
    "Cloud Engineer": ["AWS", "Azure", "Google Cloud", "Infrastructure as Code", "Serverless Computing"],
    "Product Manager": ["Agile Methodologies", "Roadmap Planning", "User Research", "Market Analysis", "Scrum"],
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

    # Get user input for role
    user_role = role

    # Fetch required skills dynamically
    required_skills = role_skills.get(user_role, [])

    if required_skills:
        print(f"Required Skills for {user_role}: {required_skills}")
    else:
        print("Role not found! Please enter a valid role.")

    ranked = len(required_skills) + 1

    skill_keywords = get_synonyms("skill") + ['skills', 'TECH SKILLS', 's k i l l s', 'skill']
    skill_keywords += [kw + "s" for kw in skill_keywords]

    experience_keywords = get_synonyms("experience") + [
        'W O R K E X P E R I E N C E', 'work experience', "Professional Experience",
        "e x p e r i e n c e", "RESEARCH EXPERIENCE", "experiences"
    ]
    experience_keywords += [kw + "s" for kw in experience_keywords]

    skills_rankings = {}
    for pdf_file in pdf_files:
        try:
            text_data = extract_text_with_bboxes(pdf_file)
            layout = detect_column_layout(text_data)

            if layout == "Single Column":
                lines = extract_text_lines(pdf_file)
            else:
                lines = detect_columns_and_extract_text(pdf_file)

            skills_paragraph = extract_paragraph_after_keywords(lines, skill_keywords)
            if skills_paragraph:
                candidate_ranks = rank_candidate(pdf_file, required_skills, skill_keywords, lines)
                skills_rankings[pdf_file] = candidate_ranks.get(pdf_file, ranked)
            else:
                skills_rankings[pdf_file] = ranked

        except Exception as e:
            skills_rankings[pdf_file] = ranked
            print(f"Error processing file {pdf_file}: {e}")

    experience_rankings = rank_candidates(pdf_files, experience_keywords)

    sorted_resumes = sort_dictionaries(skills_rankings, experience_rankings)

    response_data = []
    for pdf_file in sorted_resumes[:5]:
        response_data.append({
            "filename": os.path.basename(pdf_file),
            "skills_rank": skills_rankings.get(pdf_file, ranked),
            "experience_rank": experience_rankings[pdf_file] if pdf_file in experience_rankings else ranked,
            "file_url": f"http://127.0.0.1:5000/resume/{os.path.basename(pdf_file)}",
        })

    return jsonify({
        "message": "Files processed successfully",
        "rankings": response_data
    })


if __name__ == '__main__':
    app.run(debug=True)
