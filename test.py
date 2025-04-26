import subprocess
import re
import os
import json
import sys
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any, Union

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
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_error(message: str) -> None:
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")

def print_info(message: str) -> None:
    print(f"{Colors.BLUE}ℹ️ {message}{Colors.RESET}")

def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠️ {message}{Colors.RESET}")

def print_processing_header(message: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}=== {message} ==={Colors.RESET}")

def print_processing_step(step: int, message: str):
    print(f"{Colors.BLUE}{step}. {message}{Colors.RESET}")

# Create a folder based on PDF name and return its path
def create_output_folder(pdf_file: str) -> str:    
    base_name = os.path.splitext(os.path.basename(pdf_file))[0]
    folder_name = f"{base_name}"
    os.makedirs(folder_name, exist_ok=True)
    return folder_name

# Extract text from PDF using pdftotext and save to output file
def extract_pdf_text(pdf_file: str, output_txt: str) -> Tuple[bool, str]:   
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', pdf_file, '-'],
            check=True, capture_output=True, text=True
        )
        raw_text = result.stdout
        
        with open(output_txt, 'w', encoding='utf-8') as f:
            f.write(raw_text)
            
        return True, raw_text
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to extract text: {e}")
        return False, ""
    except FileNotFoundError:
        print_error("'pdftotext' not found. Make sure Poppler is installed and in PATH.")
        return False, ""

# Save raw text data to a file
def save_raw_data(raw_text: str, folder_path: str, base_name: str) -> str:
    raw_filename = os.path.join(folder_path, f"raw_{base_name}.txt")
    with open(raw_filename, 'w', encoding='utf-8') as f:
        f.write(raw_text)
    return raw_filename

# Extract subject table from raw text and save to file
def extract_subject_table(input_txt: str, raw_text: str) -> str:
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
        print_error("Could not find table header in the PDF text.")
        return ""
    
    # Extract table rows until end marker is found
    for line in lines[header_line_index+1:]:
        if re.search(r'SGPA|RESULT DATE', line, re.IGNORECASE):
            break
        if line.strip() == "":
            continue
        table_lines.append(line.rstrip())

    # Save extracted table
    table_text = '\n'.join(table_lines)
    with open(input_txt, 'w', encoding='utf-8') as out_file:
        out_file.write(table_text)
    return table_text

# Fix and standardize table headers
def fix_table_headers(input_txt: str) -> bool:
    try:
        with open(input_txt, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            print_error(f"Error: {input_txt} must have at least two lines for header fixing.")
            return False
        
        header_line1 = lines[0].rstrip()
        header_line2 = lines[1].rstrip()
        fixed_header = header_line1

        # Add 'Ern' if it's missing in header1 but present in header2
        if 'Ern' in header_line2:
            ern_pos = header_line1.find('Crd')
            if ern_pos >= 0:
                fixed_header = fixed_header[:ern_pos+3] + " Ern" + fixed_header[ern_pos+3:]

        # Add 'Pnt' if it's missing in header1 but present in header2
        if 'Crd' in fixed_header and 'Pnt' in header_line2:
            crd_positions = [i for i in range(len(fixed_header)) if fixed_header.startswith('Crd', i)]
            if crd_positions:
                last_crd_pos = crd_positions[-1]
                fixed_header = fixed_header[:last_crd_pos+3] + "Pnt" + fixed_header[last_crd_pos+3:]

        # Standardize subject name column
        fixed_header = re.sub(r'Subject\s+name', 'SubjectName', fixed_header)
        fixed_content = [fixed_header + '\n'] + lines[2:]

        with open(input_txt, 'w', encoding='utf-8') as f:
            f.writelines(fixed_content)

        return True
    except Exception as e:
        print_error(f"Error processing file: {e}")
        return False

# Remove the semester column from the table
def remove_sem_column(txt_path: str) -> bool:
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        if not lines:
            print_error("The file is empty.")
            return False

        header_line = lines[0]
        sem_index = header_line.find("Sem")
        if sem_index == -1:
            print_error("No 'Sem' column found.")
            return False

        sem_width = 4
        new_lines = []
        for line in lines:
            if len(line) > sem_index + sem_width:
                new_lines.append(line[:sem_index] + line[sem_index+sem_width:])
            else:
                new_lines.append(line[:sem_index])

        with open(txt_path, 'w', encoding='utf-8') as file:
            file.writelines(new_lines)

        return True
    except Exception as e:
        print_error(f"Error removing 'Sem' column: {e}")
        return False

# Parse marksheet text into structured records. Handles all cases including special characters and edge cases.
def parse_marksheet(text: str) -> List[Dict[str, Any]]:
    lines = text.split('\n')
    records = []
    skipped_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        
        if not line or line.startswith('SubCode'):
            continue
            
        # Check if this is a main subject line (with SubCode at the beginning)
        main_line_match = re.match(r'^\*?\s*(\S+)\s+(.*)', line)
        if not main_line_match:
            skipped_lines.append(f"Line not matched: {line}")
            continue
            
        # Extract SubCode and the rest of the line
        sub_code = main_line_match.group(1)
        rest_of_line = main_line_match.group(2).strip()
        
        # Check if there's an 'E' after the subject code
        if sub_code.endswith('E') and rest_of_line.startswith('FOREIGN LANGUAGE'):
            sub_code = sub_code[:-1]  # Remove 'E' from subject code
            
        # Extract subject name and data part
        subject_name = ""
        data_part = ""
        has_ac = False
        
        # Check if this line contains "AC" (Additional Credit)
        ac_match = re.search(r'\bAC\b', rest_of_line)
        if ac_match:
            has_ac = True
            # Extract subject name (everything before AC)
            data_part = "AC"
            subject_name = rest_of_line[:ac_match.start()].strip()
            
            # Check if there's a continuation line
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                
                # If next line starts with a SubCode, it's a new subject
                if re.match(r'^\*?\s*\d+', next_line):
                    break
                
                # Otherwise, it's a continuation of the current subject name
                subject_name += " " + next_line
                i += 1
        else:
            # Try to find where the data begins (normal grade pattern)
            data_match = re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*)$', rest_of_line)
            if data_match:
                # We found data on the same line
                data_part = data_match.group(1)
                subject_name = rest_of_line[:data_match.start()].strip()
                
                # Check if there's a continuation line
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                        
                    # If next line starts with a SubCode, it's a new subject
                    if re.match(r'^\*?\s*\d+', next_line):
                        break
                        
                    # If next line has data pattern, it's a new subject
                    if re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*|\bAC\b)$', next_line):
                        break
                        
                    # Otherwise, it's a continuation of the current subject name
                    subject_name += " " + next_line
                    i += 1
            else:
                # No data on this line, so the subject name might continue on next line
                subject_name = rest_of_line
                
                # Look for data on the next lines
                found_data = False
                while i < len(lines) and not found_data:
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                        
                    # If next line starts with a SubCode, it's a new subject
                    if re.match(r'^\*?\s*\d+', next_line):
                        # Special case for foreign language subject
                        if "FOREIGN LANGUAGE" in subject_name:
                            data_part = "AC"  # Assume it's AC
                            has_ac = True
                            found_data = True
                            break
                        else:
                            skipped_lines.append(f"No data found for subject: {subject_name}")
                            found_data = False
                            break
                    
                    # Check for "AC" in the next line
                    ac_match = re.search(r'\bAC\b', next_line)
                    if ac_match:
                        data_part = "AC"
                        has_ac = True
                        # There might be subject name continuation on this line
                        subject_name_part = next_line[:ac_match.start()].strip()
                        if subject_name_part:
                            subject_name += " " + subject_name_part
                        found_data = True
                        i += 1
                        continue
                        
                    # Check if this line has normal grade data
                    data_match = re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*)$', next_line)
                    if data_match:
                        data_part = data_match.group(1)
                        # There might be subject name continuation on this line
                        subject_name_part = next_line[:data_match.start()].strip()
                        if subject_name_part:
                            subject_name += " " + subject_name_part
                        found_data = True
                        i += 1
                    else:
                        # Special check for "Basic Electrical Engineering" case
                        basic_eng_match = re.search(r'(\d+\s+\d+\s+[A-Z+]+\s+\d+\s+\d+.*)', next_line)
                        if basic_eng_match:
                            data_part = basic_eng_match.group(1)
                            # There might be subject name continuation on this line
                            subject_name_part = next_line[:basic_eng_match.start()].strip()
                            if subject_name_part:
                                subject_name += " " + subject_name_part
                            found_data = True
                            i += 1
                        else:
                            # It's just a continuation of subject name
                            subject_name += " " + next_line
                            i += 1
                
                if not found_data:
                    # Special case for foreign language subjects
                    if "FOREIGN LANGUAGE" in subject_name:
                        data_part = "AC"
                        has_ac = True
                    else:
                        skipped_lines.append(f"No data found for subject: {subject_name}")
                        continue
        
        # Clean up the subject name (remove extra spaces)
        subject_name = re.sub(r'\s+', ' ', subject_name).strip()
        
        # Process the data and create a record
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
            # Keep the data part as-is (including # if present)
            data_values = re.findall(r'\S+', data_part)
            if len(data_values) >= 5:
                record = {
                    'SubCode': sub_code,
                    'SubjectName': subject_name,
                    'Credit': data_values[0],
                    'EarnedCredit': data_values[1],
                    'Grade': data_values[2],
                    'GradePoint': data_values[3],
                    'CreditPoint': data_values[4]  # This will include # if present
                }
            else:
                skipped_lines.append(f"Couldn't parse data: {data_part}")
                continue
        
        records.append(record)
    
    if skipped_lines:
        print_warning("Skipped lines during parsing:")
        for line in skipped_lines:
            print(f"  {Colors.YELLOW}{line}{Colors.RESET}", file=sys.stderr)
    
    return records

def extract_sgpa_info(text: str) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r'(?P<semester>\b(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth)\s+Semester)\s+SGPA\s*:\s*(?P<sgpa>[^\s]+)\s+Credits Earned/Total\s*:\s*(?P<earned>\d+)/(?P<total>\d+)\s+Total Credit Points\s*:\s*(?P<points>\d+)',
        re.IGNORECASE
    )

    results = []
    for match in pattern.finditer(text):
        raw_sgpa = match.group("sgpa")
        try:
            # Try to parse SGPA as float; if it works, it's valid
            float(raw_sgpa)
            sgpa = raw_sgpa
        except ValueError:
            # If it's not a float (e.g., symbols, dashes, gibberish), normalize to "--"
            sgpa = "--"

        results.append({
            "semester": match.group("semester").title(),
            "sgpa": sgpa,
            "earned_credits": match.group("earned"),
            "total_credits": match.group("total"),
            "total_credit_points": match.group("points")
        })
    return results


# Convert processed text file to JSON format with both subject table and SGPA info
def txt_to_json(input_filename: str, output_folder: str, raw_text: str) -> Optional[str]:
    try:
        with open(input_filename, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Parse subject table
        subject_records = parse_marksheet(content)
        
        if not subject_records:
            print_warning(f"No subject records parsed from {input_filename}")
        
        # Extract SGPA information from raw text
        sgpa_info = extract_sgpa_info(raw_text)
        
        if not sgpa_info:
            print_warning("No SGPA information found in the document")
        
        # Combine both sets of data
        combined_data = {
            "basic_info": sgpa_info,
            "subject_table": subject_records
        }
        
        # Generate JSON filename in the output folder
        base_name = os.path.splitext(os.path.basename(input_filename))[0]
        base_name = base_name.replace("subjects_", "")  # Remove subjects_ prefix if present
        output_filename = os.path.join(output_folder, f"{base_name}.json")
        
        with open(output_filename, 'w', encoding='utf-8') as file:
            json.dump(combined_data, file, indent=4)
        
        return output_filename, len(subject_records), len(sgpa_info)
    except Exception as e:
        print_error(f"Error converting to JSON: {e}")
        return None, 0, 0

# Main function that processes the PDF marksheet
def main() -> None:
    try:
        # Input PDF file
        pdf_input = "F.E Sem2 Marksheet.pdf"
        if not os.path.exists(pdf_input):
            print_error(f"Input file not found: {pdf_input}")
            return
            
        base_name = os.path.splitext(os.path.basename(pdf_input))[0]
        
        # Create output folder
        output_folder = create_output_folder(pdf_input)
        print_processing_header(f"Processing {pdf_input}")
        print_info(f"Output will be saved in: {output_folder}")
        
        # Generate filenames inside the folder
        intermediate_txt = os.path.join(output_folder, f"intermediate_{base_name}.txt")
        subjects_txt = os.path.join(output_folder, f"subjects_{base_name}.txt")
        
        # Step 1: Extract text from PDF and get raw data
        print_processing_step(1, "Extracting text from PDF")
        success, raw_text = extract_pdf_text(pdf_input, intermediate_txt)
        if not success:
            return
        
        # Save raw data separately
        raw_data_file = save_raw_data(raw_text, output_folder, base_name)
        print_info(f"Raw text saved to: {raw_data_file}")
        
        # Step 2: Extract subject table from raw text
        print_processing_step(2, "Extracting subject table")
        table_text = extract_subject_table(intermediate_txt, raw_text)
        if not table_text:
            return
        
        # Step 3: Fix headers
        print_processing_step(3, "Standardizing table headers")
        if not fix_table_headers(intermediate_txt):
            return
        
        # Step 4: Remove "Sem" column
        print_processing_step(4, "Removing semester column")
        if not remove_sem_column(intermediate_txt):
            return
        
        # Step 5: Rename to subjects file
        os.rename(intermediate_txt, subjects_txt)
        print_info(f"Processed subjects saved to: {subjects_txt}")
        
        # Step 6: Convert to JSON with both subject table and SGPA info
        print_processing_step(5, "Creating JSON output")
        json_output, subject_count, sgpa_count = txt_to_json(subjects_txt, output_folder, raw_text)
        
        if not json_output:
            return
        
        # Print summary
        print_processing_header("Processing Complete")
        print_info(f"Total subject records: {subject_count}")
        print_info(f"Total SGPA records: {sgpa_count}")
        print_success(f"All files saved in: {output_folder}")
        print_success(f"Final JSON output: {json_output}")
        
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        print_error("Please check your input file and try again.")

if __name__ == "__main__":
    main()