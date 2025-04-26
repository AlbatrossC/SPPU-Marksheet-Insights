from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
import subprocess
import re
import tempfile
import os
import json
from io import BytesIO
from typing import Tuple, List, Dict, Any
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this for production
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB upload limit

# Register blueprint (to be created later)
from processed import processed_bp
app.register_blueprint(processed_bp)

# ANSI color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

def print_success(message: str) -> None:
    app.logger.info(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_error(message: str) -> None:
    app.logger.error(f"{Colors.RED}❌ {message}{Colors.RESET}")

def print_info(message: str) -> None:
    app.logger.info(f"{Colors.BLUE}ℹ️ {message}{Colors.RESET}")

def print_warning(message: str):
    app.logger.warning(f"{Colors.YELLOW}⚠️ {message}{Colors.RESET}")

def print_processing_header(message: str):
    app.logger.info(f"\n{Colors.CYAN}{Colors.BOLD}=== {message} ==={Colors.RESET}")

def print_processing_step(step: int, message: str):
    app.logger.info(f"{Colors.BLUE}{step}. {message}{Colors.RESET}")

def extract_pdf_text(pdf_bytes: bytes) -> Tuple[bool, str]:
    """Extract text from PDF bytes using pdftotext"""
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf.flush()  # Ensure all data is written to disk
            
            result = subprocess.run(
                ['pdftotext', '-layout', temp_pdf.name, '-'],
                check=True,
                capture_output=True,
                text=True
            )
            return True, result.stdout
    except subprocess.CalledProcessError as e:
        print_error(f"pdftotext failed: {e.stderr}")
        return False, ""
    except Exception as e:
        print_error(f"PDF extraction error: {str(e)}")
        return False, ""

def extract_subject_table(raw_text: str) -> str:
    """Extract the subject table from raw text"""
    lines = raw_text.split('\n')
    table_lines = []
    header_found = False
    header_line_index = -1

    # Find the table header
    for i, line in enumerate(lines):
        if re.search(r'Sem\s+SubCode\s+Subject Name', line):
            header_found = True
            header_line_index = i
            table_lines.append(line.strip())
            break
    
    if not header_found:
        print_error("Table header not found in PDF text")
        return ""
    
    # Extract table rows until end marker
    for line in lines[header_line_index+1:]:
        if re.search(r'SGPA|RESULT DATE', line, re.IGNORECASE):
            break
        if line.strip():
            table_lines.append(line.rstrip())

    return '\n'.join(table_lines)

def fix_table_headers(table_text: str) -> str:
    """Standardize table headers"""
    lines = table_text.split('\n')
    if len(lines) < 2:
        return table_text
    
    header = lines[0]
    
    # Add missing columns if needed
    if 'Ern' not in header and 'Crd' in header:
        crd_pos = header.find('Crd')
        header = header[:crd_pos+3] + " Ern" + header[crd_pos+3:]
    
    if 'Pnt' not in header and 'Crd' in header:
        crd_positions = [i for i in range(len(header)) if header.startswith('Crd', i)]
        if crd_positions:
            last_crd_pos = crd_positions[-1]
            header = header[:last_crd_pos+3] + "Pnt" + header[last_crd_pos+3:]
    
    # Standardize subject name column
    header = re.sub(r'Subject\s+name', 'SubjectName', header)
    
    lines[0] = header
    return '\n'.join(lines)

def remove_sem_column(table_text: str) -> str:
    """Remove the semester column from the table"""
    lines = table_text.split('\n')
    if not lines:
        return table_text

    header = lines[0]
    sem_index = header.find("Sem")
    if sem_index == -1:
        return table_text

    sem_width = 4
    new_lines = []
    for line in lines:
        if len(line) > sem_index + sem_width:
            new_lines.append(line[:sem_index] + line[sem_index+sem_width:])
        else:
            new_lines.append(line[:sem_index])

    return '\n'.join(new_lines)

def parse_marksheet(text: str) -> List[Dict[str, Any]]:
    """Parse marksheet text into structured records"""
    lines = text.split('\n')
    records = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        
        if not line or line.startswith('SubCode'):
            continue
            
        # Subject line processing
        main_line_match = re.match(r'^\*?\s*(\S+)\s+(.*)', line)
        if not main_line_match:
            continue
            
        sub_code = main_line_match.group(1)
        rest_of_line = main_line_match.group(2).strip()
        
        # Handle foreign language subjects
        if sub_code.endswith('E') and rest_of_line.startswith('FOREIGN LANGUAGE'):
            sub_code = sub_code[:-1]
            
        # Parse subject data
        subject_name = ""
        data_part = ""
        has_ac = False
        
        # Check for AC (Additional Credit)
        ac_match = re.search(r'\bAC\b', rest_of_line)
        if ac_match:
            has_ac = True
            data_part = "AC"
            subject_name = rest_of_line[:ac_match.start()].strip()
            
            # Handle multi-line subject names
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                if re.match(r'^\*?\s*\d+', next_line):
                    break
                subject_name += " " + next_line
                i += 1
        else:
            # Handle normal grade lines
            data_match = re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*)$', rest_of_line)
            if data_match:
                data_part = data_match.group(1)
                subject_name = rest_of_line[:data_match.start()].strip()
                
                # Handle multi-line subject names
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                    if re.match(r'^\*?\s*\d+', next_line) or \
                       re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*|\bAC\b)$', next_line):
                        break
                    subject_name += " " + next_line
                    i += 1
            else:
                # Handle special cases
                subject_name = rest_of_line
                found_data = False
                while i < len(lines) and not found_data:
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                        
                    if re.match(r'^\*?\s*\d+', next_line):
                        if "FOREIGN LANGUAGE" in subject_name:
                            data_part = "AC"
                            has_ac = True
                            found_data = True
                            break
                        break
                    
                    ac_match = re.search(r'\bAC\b', next_line)
                    if ac_match:
                        data_part = "AC"
                        has_ac = True
                        subject_name += " " + next_line[:ac_match.start()].strip()
                        found_data = True
                        i += 1
                        continue
                        
                    data_match = re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*)$', next_line)
                    if data_match:
                        data_part = data_match.group(1)
                        subject_name += " " + next_line[:data_match.start()].strip()
                        found_data = True
                        i += 1
                    else:
                        subject_name += " " + next_line
                        i += 1
                
                if not found_data and "FOREIGN LANGUAGE" in subject_name:
                    data_part = "AC"
                    has_ac = True
        
        # Create record
        subject_name = re.sub(r'\s+', ' ', subject_name).strip()
        
        if has_ac or data_part == "AC":
            record = {
                'SubCode': sub_code,
                'SubjectName': subject_name,
                'Credit': None,
                'EarnedCredit': None,
                'Grade': 'AC',
                'GradePoint': None,
                'CreditPoint': None
            }
        else:
            data_values = re.findall(r'\S+', data_part)
            if len(data_values) >= 5:
                record = {
                    'SubCode': sub_code,
                    'SubjectName': subject_name,
                    'Credit': data_values[0],
                    'EarnedCredit': data_values[1],
                    'Grade': data_values[2],
                    'GradePoint': data_values[3],
                    'CreditPoint': data_values[4]
                }
            else:
                continue
        
        records.append(record)
    
    return records

def extract_sgpa_info(text: str) -> List[Dict[str, Any]]:
    """Extract SGPA information from raw text"""
    pattern = re.compile(
        r'(?P<semester>\b(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth)\s+Semester)\s+SGPA\s*:\s*(?P<sgpa>[^\s]+)\s+Credits Earned/Total\s*:\s*(?P<earned>\d+)/(?P<total>\d+)\s+Total Credit Points\s*:\s*(?P<points>\d+)',
        re.IGNORECASE
    )

    return [{
        "semester": match.group("semester").title(),
        "sgpa": match.group("sgpa") if re.match(r'^\d+\.\d+$', match.group("sgpa")) else "--",
        "earned_credits": match.group("earned"),
        "total_credits": match.group("total"),
        "total_credit_points": match.group("points")
    } for match in pattern.finditer(text)]

def generate_result_data(data):
    """Generate JSON data in memory"""
    return json.dumps(data, indent=4)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and file.filename.lower().endswith('.pdf'):
            try:
                # Process PDF
                pdf_bytes = file.read()
                
                print_processing_header(f"Processing {file.filename}")
                
                # Step 1: Extract text
                print_processing_step(1, "Extracting text")
                success, raw_text = extract_pdf_text(pdf_bytes)
                if not success:
                    flash('Text extraction failed')
                    return redirect(request.url)
                
                # Step 2: Extract table
                print_processing_step(2, "Extracting subject table")
                table_text = extract_subject_table(raw_text)
                if not table_text:
                    flash('No subject table found')
                    return redirect(request.url)
                
                # Step 3: Fix headers
                print_processing_step(3, "Standardizing headers")
                fixed_table = fix_table_headers(table_text)
                
                # Step 4: Remove semester column
                print_processing_step(4, "Removing semester column")
                final_table = remove_sem_column(fixed_table)
                
                # Step 5: Parse marksheet
                print_processing_step(5, "Parsing marksheet")
                subject_records = parse_marksheet(final_table)
                if not subject_records:
                    flash('No subject records parsed')
                    return redirect(request.url)
                
                # Step 6: Extract SGPA
                print_processing_step(6, "Extracting SGPA info")
                sgpa_info = extract_sgpa_info(raw_text)
                
                # Prepare results
                combined_data = {
                    "filename": secure_filename(file.filename),
                    "basic_info": sgpa_info,
                    "subject_table": subject_records
                }
                
                # Step 7: Generate JSON data in memory
                print_processing_step(7, "Generating JSON data")
                json_data = generate_result_data(combined_data)
                print_success("JSON data generated successfully")
                
                # Store JSON data in session (in memory)
                session['result_json'] = json_data
                
                return redirect(url_for('processed.show_results'))
                
            except Exception as e:
                print_error(f"Processing error: {str(e)}")
                flash(f'Processing failed: {str(e)}')
                return redirect(request.url)
        else:
            flash('Only PDF files are allowed')
            return redirect(request.url)
    
    return render_template('upload.html')

@app.route('/clear_session')
def clear_session():
    """Clear the session data"""
    session.pop('result_json', None)
    flash('Session cleared successfully')
    return redirect(url_for('upload_file'))

if __name__ == '__main__':
    app.run(debug=True)