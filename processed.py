from flask import Blueprint, render_template, session, redirect, url_for, flash
import json
import re
from io import BytesIO
from flask import send_file
import pandas as pd 
from datetime import datetime

processed_bp = Blueprint('processed', __name__, template_folder='templates')


def process_subject_name(subject_name):
    """Processes subject names by removing leading numeric codes"""
    if not subject_name:
        return subject_name
    
    # Use regex to remove leading numbers and any following whitespace
    processed_name = re.sub(r'^\d+\s*', '', subject_name)
    return processed_name.strip()

###############################
# CREDIT POINT CALCULATIONS
###############################

def calculate_student_credit_points(subjects):
    """Calculate students' credit points (handling special symbols)"""
    total_credit_points = 0
    
    for subject in subjects:
        if subject.get('CreditPoint'):
            # Extract numeric value by removing any special characters
            credit_point_str = subject.get('CreditPoint')
            # Remove any non-digit characters except decimal point
            credit_point_numeric = re.sub(r'[^\d.]', '', credit_point_str)
            
            if credit_point_numeric:
                total_credit_points += int(float(credit_point_numeric))
    
    return total_credit_points

def calculate_final_credit_points(subjects):
    """Calculate final credit points"""
    total_credits = 0
    
    for subject in subjects:
        if subject.get('Credit'):
            try:
                total_credits += int(float(subject.get('Credit')))
            except (ValueError, TypeError):
                pass  # Skip if credit is not a valid number
    
    # Multiply by 10 as specified
    return total_credits * 10

def calculate_sgpa(student_credit_points, final_credit_points):
    """Calculate SGPA"""
    if final_credit_points == 0:
        return 0  # Avoid division by zero
    
    sgpa = (student_credit_points / final_credit_points) * 10
    return round(sgpa, 2)

def calculate_cgpa(basic_info):
    """Calculates CGPA from multiple semester information"""
    total_credit_points = 0
    total_credits = 0
    
    for sem in basic_info:
        # Skip semesters where student failed (SGPA is None)
        if sem.get('sgpa') is None:
            continue
        total_credit_points += float(sem['total_credit_points'])
        total_credits += float(sem['total_credits'])
    
    if total_credits == 0:
        return None  # Indicates failure
    return round(total_credit_points / total_credits, 2)

###############################
# GRADE CLASSIFICATION FUNCTIONS
###############################

def cgpa_to_percentage(cgpa):
    """Converts CGPA to percentage using standard formula"""
    if cgpa is None:
        return None
    # Using common conversion formula (approximate)
    percentage = cgpa * 9.5
    return round(percentage, 2)

def get_grade(percentage):
    """Determines grade letter based on percentage"""
    if percentage is None:
        return "F"
    if percentage >= 75:
        return "A+"
    elif 60 <= percentage < 75:
        return "A"
    elif 50 <= percentage < 60:
        return "B"
    elif 40 <= percentage < 50:
        return "C"
    else:
        return "D"

def get_semester_class(sgpa):
    """Determines class awarded for a specific SGPA"""
    if sgpa is None:
        return "Failed"
    sgpa_float = float(sgpa)
    if sgpa_float >= 7.75:
        return "First Class with Distinction"
    elif 6.75 <= sgpa_float < 7.75:
        return "First Class"
    elif 6.25 <= sgpa_float < 6.75:
        return "Higher Second Class"
    elif 5.5 <= sgpa_float < 6.25:
        return "Second Class"
    else:
        return "Pass"

def get_class_awarded(cgpa):
    """Determines overall class awarded based on CGPA"""
    if cgpa is None:
        return "Failed"
    if cgpa >= 7.75:
        return "First Class with Distinction"
    elif 6.75 <= cgpa < 7.75:
        return "First Class"
    elif 6.25 <= cgpa < 6.75:
        return "Higher Second Class"
    elif 5.5 <= cgpa < 6.25:
        return "Second Class"
    else:
        return "Pass"

###############################
# DATA PROCESSING FUNCTIONS
###############################

def detect_and_split_semester(subject_table):
    """Detects and splits a subject table into two semesters if necessary"""
    if not subject_table:
        return [subject_table]  # Return as-is if empty
    
    # Find the first subject that has null Credit and 'AC' grade
    split_index = None
    for i, subject in enumerate(subject_table):
        if (subject.get('Credit') is None and 
            subject.get('EarnedCredit') is None and 
            subject.get('Grade') == 'AC' and 
            subject.get('GradePoint') is None and 
            subject.get('CreditPoint') is None):
            
            # Check if this is not the last subject (potential split point)
            if i < len(subject_table) - 1:
                split_index = i + 1
                break
    
    # If no split point found or it's the last element, return the original list
    if split_index is None or split_index >= len(subject_table):
        return [subject_table]
    
    # Split the semester
    first_sem = subject_table[:split_index]
    second_sem = subject_table[split_index:]
    
    return [first_sem, second_sem]

def process_semester_credit_data(subjects, semester_key):
    """Process credit points for a single semester"""
    if not subjects:
        return None
        
    student_credit_points = calculate_student_credit_points(subjects)
    final_credit_points = calculate_final_credit_points(subjects)
    
    return {
        'student_credit_points': student_credit_points,
        'final_credit_points': final_credit_points
    }

def find_special_marks(subjects, symbol):
    """Find subjects with special marks (# for grace marks, $ for condo marks)"""
    special_subjects = []
    
    for subject in subjects:
        if subject.get('CreditPoint') and symbol in str(subject.get('CreditPoint')):
            special_subjects.append({
                'code': subject.get('SubCode'),
                'name': process_subject_name(subject.get('SubjectName'))
            })
    
    return special_subjects

def find_backlogs(subjects):
    """Find subjects with failing grades"""
    backlog_subjects = []
    
    for subject in subjects:
        if subject.get('Grade') == 'F':
            backlog_subjects.append({
                'code': subject.get('SubCode'),
                'name': process_subject_name(subject.get('SubjectName'))
            })
    
    return backlog_subjects

def prepare_result_data(processed_data):
    """Main processing function that prepares all result data for display"""
    # Process subject names and check if we need to split the subject table
    if 'subject_table' in processed_data:
        # Process subject names before splitting
        for subject in processed_data['subject_table']:
            if 'SubjectName' in subject:
                subject['SubjectName'] = process_subject_name(subject['SubjectName'])
        
        split_tables = detect_and_split_semester(processed_data['subject_table'])
        
        # If we found that there are two semesters in one table
        if len(split_tables) > 1:
            # Update the subject_table to contain only first semester
            processed_data['subject_table'] = split_tables[0]
            # Add second_semester_subjects
            processed_data['second_semester_subjects'] = split_tables[1]
    
    # Process first semester data
    if 'subject_table' in processed_data:
        # Calculate and store credit points for first semester
        processed_data['first_sem_credit_points'] = process_semester_credit_data(
            processed_data['subject_table'], 'first_sem')
        
        # Calculate SGPA if basic info exists
        if ('basic_info' in processed_data and 
            len(processed_data['basic_info']) > 0 and 
            processed_data['first_sem_credit_points']['final_credit_points'] > 0):
            
            processed_data['first_sem_calculated_sgpa'] = calculate_sgpa(
                processed_data['first_sem_credit_points']['student_credit_points'],
                processed_data['first_sem_credit_points']['final_credit_points']
            )
    
    # Process second semester data if present
    if 'second_semester_subjects' in processed_data:
        # Calculate and store credit points for second semester
        processed_data['second_sem_credit_points'] = process_semester_credit_data(
            processed_data['second_semester_subjects'], 'second_sem')
        
        # Calculate SGPA if basic info exists
        if ('basic_info' in processed_data and 
            len(processed_data['basic_info']) > 1 and 
            processed_data['second_sem_credit_points']['final_credit_points'] > 0):
            
            processed_data['second_sem_calculated_sgpa'] = calculate_sgpa(
                processed_data['second_sem_credit_points']['student_credit_points'],
                processed_data['second_sem_credit_points']['final_credit_points']
            )
    
    # Process basic_info - convert strings to numbers and add class awards
    if 'basic_info' in processed_data:
        for sem in processed_data['basic_info']:
            # Check if SGPA is '--' and handle it
            if sem['sgpa'] == '--':
                sem['sgpa'] = None
                sem['class_awarded'] = "Failed"
            else:
                sem['sgpa'] = float(sem['sgpa'])
                sem['class_awarded'] = get_semester_class(sem['sgpa'])
                
            # Convert credit values to integers
            sem['earned_credits'] = int(sem['earned_credits'])
            sem['total_credits'] = int(sem['total_credits'])
            sem['total_credit_points'] = int(sem['total_credit_points'])
    
    # Calculate overall CGPA and class awarded if there are 2 semesters
    if 'basic_info' in processed_data and len(processed_data['basic_info']) == 2:
        cgpa = calculate_cgpa(processed_data['basic_info'])
        processed_data['cgpa'] = cgpa
        processed_data['class_awarded'] = get_class_awarded(cgpa)
        
        # Calculate percentage and grade
        percentage = cgpa_to_percentage(cgpa)
        processed_data['percentage'] = percentage
        processed_data['grade'] = get_grade(percentage)
    
    # Process special cases - backlogs, grace marks, condo marks
    
    # Process backlog status
    processed_data['backlogs'] = {'first_sem': [], 'second_sem': [], 'total': 0}
    if 'subject_table' in processed_data:
        processed_data['backlogs']['first_sem'] = find_backlogs(processed_data['subject_table'])
        processed_data['backlogs']['total'] += len(processed_data['backlogs']['first_sem'])
    
    if 'second_semester_subjects' in processed_data:
        processed_data['backlogs']['second_sem'] = find_backlogs(processed_data['second_semester_subjects'])
        processed_data['backlogs']['total'] += len(processed_data['backlogs']['second_sem'])
    
    # Process grace marks (# symbol in credit points)
    processed_data['grace_marks'] = {'first_sem': [], 'second_sem': [], 'total': 0}
    if 'subject_table' in processed_data:
        processed_data['grace_marks']['first_sem'] = find_special_marks(processed_data['subject_table'], '#')
        processed_data['grace_marks']['total'] += len(processed_data['grace_marks']['first_sem'])
    
    if 'second_semester_subjects' in processed_data:
        processed_data['grace_marks']['second_sem'] = find_special_marks(processed_data['second_semester_subjects'], '#')
        processed_data['grace_marks']['total'] += len(processed_data['grace_marks']['second_sem'])
    
    # Process condo marks ($ symbol in credit points)
    processed_data['condo_marks'] = {'first_sem': [], 'second_sem': [], 'total': 0}
    if 'subject_table' in processed_data:
        processed_data['condo_marks']['first_sem'] = find_special_marks(processed_data['subject_table'], '$')
        processed_data['condo_marks']['total'] += len(processed_data['condo_marks']['first_sem'])
    
    if 'second_semester_subjects' in processed_data:
        processed_data['condo_marks']['second_sem'] = find_special_marks(processed_data['second_semester_subjects'], '$')
        processed_data['condo_marks']['total'] += len(processed_data['condo_marks']['second_sem'])
    
    return processed_data

###############################
# FLASK ROUTE HANDLERS
###############################

@processed_bp.route('/download_json')
def download_json():
    """Downloads the result data as JSON file"""
    # Get JSON data directly from session
    json_data = session.get('result_json')
    
    if not json_data:
        flash('No data available to download')
        return redirect(url_for('upload_file'))
    
    # Generate filename with timestamp
    filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Create BytesIO buffer and write JSON data
    mem_file = BytesIO()
    mem_file.write(json_data.encode('utf-8'))
    mem_file.seek(0)  # Rewind to start of file
    
    # Send as downloadable file
    return send_file(
        mem_file,
        mimetype='application/json',
        as_attachment=True,
        download_name=filename
    )

@processed_bp.route('/download_excel')
def download_excel():
    """Downloads the result data as Excel (XLSX) file"""
    json_data = session.get('result_json')
    
    if not json_data:
        flash('No data available to download')
        return redirect(url_for('upload_file'))
    
    try:
        processed_data = json.loads(json_data)
    except Exception as e:
        flash('Error processing result data. Please try again.')
        return redirect(url_for('upload_file'))

    mem_file = BytesIO()

    with pd.ExcelWriter(mem_file, engine='openpyxl') as writer:
        # Write semester subjects
        if 'subject_table' in processed_data:
            subject_table = processed_data['subject_table']
            semesters = detect_and_split_semester(subject_table)
            
            for idx, semester_subjects in enumerate(semesters, start=1):
                if semester_subjects:  # Only create sheet if data is present
                    sheet_name = f"Semester {idx}"
                    df_sem = pd.DataFrame(semester_subjects)
                    df_sem.to_excel(writer, sheet_name=sheet_name, index=False)

        # Write second semester subjects if separately available (fallback)
        if 'second_semester_subjects' in processed_data and not any(
            s.get('second_semester_subjects') for s in processed_data.get('subject_table', [])
        ):
            df_second_sem = pd.DataFrame(processed_data['second_semester_subjects'])
            df_second_sem.to_excel(writer, sheet_name='Semester 2', index=False)
        
        # Write basic info if exists
        if 'basic_info' in processed_data:
            df_basic_info = pd.DataFrame(processed_data['basic_info'])
            df_basic_info.to_excel(writer, sheet_name='Basic Info', index=False)

        # Write final summary if CGPA exists
        summary_data = {}
        if 'cgpa' in processed_data:
            summary_data['CGPA'] = processed_data['cgpa']
        if 'percentage' in processed_data:
            summary_data['Percentage'] = processed_data['percentage']
        if 'grade' in processed_data:
            summary_data['Grade'] = processed_data['grade']
        if 'class_awarded' in processed_data:
            summary_data['Class Awarded'] = processed_data['class_awarded']
        
        if summary_data:
            df_summary = pd.DataFrame([summary_data])
            df_summary.to_excel(writer, sheet_name='Summary', index=False)

    mem_file.seek(0)

    filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        mem_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@processed_bp.route('/results')
def show_results():
    """Displays processed student results"""
    # Get JSON data directly from session
    json_data = session.get('result_json')
    
    if not json_data:
        flash('No data found. Please upload a PDF file first.')
        return redirect(url_for('upload_file'))
    
    try:
        # Parse the JSON data
        processed_data = json.loads(json_data)
    except Exception as e:
        flash('Error processing result data. Please try again.')
        return redirect(url_for('upload_file'))
    
    # Prepare all result data
    processed_data = prepare_result_data(processed_data)
    
    # Don't clear the session yet - we need it for potential download
    return render_template('result.html', data=processed_data)

@processed_bp.route('/clear_session')
def clear_session():
    """Clears session data after download"""
    session.pop('result_json', None)
    return redirect(url_for('upload_file'))