import os
import json
import pandas as pd
from datetime import datetime
from lborg.excel_helpers import get_dates_from_excel_columns, get_attendance_from_excel
from lborg.db_items import db_student, db_date, db_exam, db_exam_results
from lborg.db import create_database, insert_items, check_column, update_db, create_query, query_database, check_entry, add_row, get_entry


def add_participants_to_db(json_file, cohort='2023/24',db_name='data/dummy.db', 
                           update=False, overwrite=False, verbose=False):
    """Add participants to a database

    Args:
        json_file (str): the file name of the json file with participants
        cohort (str, optional): the academic year of attendance. Defaults to '2023/24'.
        db_name (str, optional): the file name with the database. Defaults to 'data/dummy.db'.
        update (bool, optional): update the database. Defaults to False.
        overwrite (bool, optional): overwrites the database. Defaults to False.
        verbose (bool, optional): verbose mode. Defaults to False.

    Raises:
        ValueError: database already exists and neither update nor overwrite are set
        ValueError: no data is found in the json file
    """    
    # check if database exists
    if os.path.exists(db_name) and not (update or overwrite):
        raise ValueError(f'Database {db_name} already exists! Use `update` to update it')
    # load participants
    with open(json_file) as f:
        data = json.load(f)
    if not data:
        raise ValueError(f'No data found in {json_file}')
    # create database
    if not os.path.exists(db_name) or overwrite:
        create_database(db_name, overwrite=overwrite)
    # add participants to database
    students = []
    for student in data[0]:
        students += [ db_student(student['cognome'].replace("'", "''"),
                                 student['nome'].replace("'", "''"),
                                 student['matricola'],
                                 student['indirizzoemail'],
                                 cohort,
                                 0) ]
    insert_items(db_name, students, ignore_keys=['gruppo'], verbose=verbose)
    print(f'Added {len(students)} students from {cohort} cohort to {db_name}')
    return

def create_attendance_db_from_excel(excel_file, db_name='data/dummy.db', 
                         update=False, overwrite=False):
    """Add dates to attendance database

    Args:
        json_file (str): the file name of the json file with participants
        db_name (str, optional): the file name with the database. Defaults to 'data/dummy.db'.
        update (bool, optional): update the database. Defaults to False.
        overwrite (bool, optional): overwrites the database. Defaults to False.

    Raises:
        ValueError: database already exists and neither update nor overwrite are set
        ValueError: no data is found in the json file
    """    
    # check if database exists
    if os.path.exists(db_name) and not (update or overwrite):
        raise ValueError(f'Database {db_name} already exists! Use `update` to update it')
    # load participants
    data = pd.read_excel(excel_file)
    if data is None or data.empty:
        raise ValueError(f'No data found in {excel_file}')
    # extract dates from the dataframe
    dates = get_dates_from_excel_columns(data.keys())
    # create database
    if not os.path.exists(db_name) or overwrite: 
        db_columns = {'matricola':'integer'}
        for date in dates.keys():
            db_columns[date] = 'boolean'
        create_database(db_name, 'attendance', db_columns, overwrite=overwrite)
    # Message   
    print(f'Created attendance database in {db_name}')
    return


def create_attendance_db(json_file, db_name='data/dummy.db', 
                         update=False, overwrite=False):
    """Add dates to attendance database

    Args:
        json_file (str): the file name of the json file with participants
        db_name (str, optional): the file name with the database. Defaults to 'data/dummy.db'.
        update (bool, optional): update the database. Defaults to False.
        overwrite (bool, optional): overwrites the database. Defaults to False.

    Raises:
        ValueError: database already exists and neither update nor overwrite are set
        ValueError: no data is found in the json file
    """    
    # check if database exists
    if os.path.exists(db_name) and not (update or overwrite):
        raise ValueError(f'Database {db_name} already exists! Use `update` to update it')
    # load participants
    with open(json_file) as f:
        data = json.load(f)
    if not data:
        raise ValueError(f'No data found in {json_file}')
    # create database
    if not os.path.exists(db_name) or overwrite: 
        db_columns = {'matricola':'integer'}
        for date in data.keys():
            db_columns[date] = 'boolean'
        create_database(db_name, 'attendance', db_columns, overwrite=overwrite)
    # Message   
    print(f'Created attendance database in {db_name}')
    return


def create_exams_db(db_name='data/dummy_exams.db', 
                    update=False, overwrite=False):
    """Create the exams database

    Args:
        json_file (str): the file name of the json file with participants
        db_name (str, optional): the file name with the database. Defaults to 'data/dummy_exams.db'.
        update (bool, optional): update the database. Defaults to False.
        overwrite (bool, optional): overwrites the database. Defaults to False.

    Raises:
        ValueError: database already exists and neither update nor overwrite are set
        ValueError: no data is found in the json file
    """    
    # check if database exists
    if os.path.exists(db_name) and not (update or overwrite):
        raise ValueError(f'Database {db_name} already exists! Use `update` to update it')
    # # load participants
    # with open(json_file) as f:
    #     data = json.load(f)
    # if not data:
    #     raise ValueError(f'No data found in {json_file}')
    # create database
    if not os.path.exists(db_name) or overwrite: 
        db_columns = {'matricola':'integer',
                      'written_date':'text',
                      'written':'text',
                      'reports_date':'text',
                      'reports':'text',
                      'oral_date':'text',
                      'result':'text'}
        create_database(db_name, 'exams', db_columns, overwrite=overwrite)
    # Message   
    print(f'Created exams database in {db_name}')
    return


def assign_group(json_file, db_name='data/dummy.db', verbose=False):
    """Assign groups to participants in database

    Args:
        json_file (str): the file name of the json file with participants and groups
        db_name (str, optional): the file name with the database to update. Defaults to 'data/dummy.db'.

    Raises:
        ValueError: database not found
        ValueError: group column not found
        ValueError: no data found in json file
    """    
    # check if database exists
    if not os.path.exists(db_name):
        raise ValueError(f'Database {db_name} not found!')
    # check if group column is present
    if not check_column(db_name, 'gruppo'):
        raise ValueError(f'Column "gruppo" not found in {db_name}!')
    # load participants
    with open(json_file) as f:
        data = json.load(f)
    if not data:
        raise ValueError(f'No data found in {json_file}')
    # update participants group to database
    for student in data[0]:
        st_item = db_student(student['nome'].replace("'", "''"),  # Escape single quotes
                             student['cognome'].replace("'", "''"),  # Escape single quotes
                             student['matricola'] if 'matricola' in student.keys() else None,
                             student['indirizzoemail'] if 'indirizzoemail' in student.keys() else None,
                             None,
                             student['gruppo'])
        if verbose: print(student, st_item)
        update_db(db_name, 'gruppo', student['gruppo'],
                  f"cognome = \'{student['cognome'].replace("'", "''")}\' AND nome = \'{student['nome'].replace("'", "''")}\'", 
                  verbose=verbose)
    return


def get_groups(cohort, db_name='data/dummy.db'):
    """Returns a dictionary with groups from a database

    Args:
        cohort (str): the academic year of attendance
        db_name (str, optional): the file name of the database. Defaults to 'data/dummy.db'.

    Raises:
        ValueError: Database not found

    Returns:
        dict: a dictionary with students keyed by group number
    """    
    # check if database exists
    if not os.path.exists(db_name):
        raise ValueError(f'Database {db_name} not found!')
    # query the database
    query = create_query(db_name, columns=['cognome','nome','mail','gruppo'], order='cognome')
    data, desc = query_database(db_name,query)
    # order data by group number
    sorted_array = sorted(data, key=lambda x: x[3])
    # create dictionary with groups
    groups = {}
    for student in sorted_array:
        if student[3] not in groups.keys():
            groups[student[3]] = []
        if student[3]: 
            groups[student[3]].append(student) 
    return groups


def add_dates_db(json_file,db_name='data/dummy_dates.db'):
    """Creates a database with dates and hours from a json file

    Args:
        json_file (str): the json file name with dates and hours
        db_name (str, optional): _description_. Defaults to 'data/dummy_dates.db'.
    """    
    table_name = 'dates'
    # check if database exists
    if not os.path.exists(db_name):
        create_database(db_name,table_name,{'date':'text','hours':'INTEGER'})
    # update dates to database
    data = json.load(open(json_file))
    items = []
    for date, hours in data.items():
        items += [db_date(date, hours)]
    insert_items(db_name, items, 'dates')
    return


def get_dates(db_name='data/dummy_dates.db'):
    """Returns the dates dictionary from the 'dates' database

    Returns:
        dict: a dictionary with the dates and corresponding hours
    """    
    query = create_query(db_name, 'dates', order='date')
    data = query_database(db_name,query)
    return data


def get_hours(db_name='data/dummy_dates.db'):
    """Returns the hours from the 'dates' database

    Returns:
        list: a list with the hours
    """    
    query = create_query(db_name, 'dates', order='date')
    data = query_database(db_name,query)
    print(data)
    hours = [d[1] for d in data[0]]
    return hours


def add_exams_db(json_file,db_name='data/dummy_exams_dates.db'):
    """Creates a database with dates and type of exam from a json file

    Args:
        json_file (str): the json file name with dates and type (oral/written)
        db_name (str, optional): _description_. Defaults to 'data/dummy_exams_dates.db'.
    """    
    table_name = 'exams dates'
    # check if database exists
    if not os.path.exists(db_name):
        create_database(db_name,table_name,{'date':'text','type':'text'})
    # update dates to database
    data = json.load(open(json_file))
    items = []
    for date, exam_type in data.items():
        items += [db_exam(date, exam_type)]
    insert_items(db_name, items, table_name)
    return


def int_report(mark):
    """Translates the report mark to an integer

    Args:
        mark (str): the mark value in the database
    """
    valid_marks = ['A+','A','A-','A-/B+',
                   'B+','B','B-','B-/C+',
                   'C+','C','C-','C-/C+',
                   'D+','D','D-','E']
    if mark not in valid_marks: 
        return 0
    return 31 - valid_marks.index(mark)


def compact_report(marks):
    """Translate the dictionary of the reports marks to a compact string

    Args:
        marks (dict): a dictionary with the marks for each experience

    Returns:
        str: the compact string with the marks
    """    
    txt = ''
    for experience, mark in marks.items():
        txt+= f'{experience}:{mark} '
    return txt[:-1]


def int_mark(mark,exam_type='written'):
    """Translates the exam mark to an integer

    Args:
        mark (str): the mark value in the database
        exam_type (str): the type of exam (written, oral, reports)
    """
    int_mark = 0
    if exam_type in ['written','oral']:
        if mark not in ['A','I','R','30L']: 
            int_mark = int(mark)
        if mark == 'A': int_mark = -1
        if mark == 'R': int_mark = -2
        if mark == '30L': int_mark = 31
    elif exam_type == 'reports':
        print(mark)
        int_mark = 0
        for experience, m in mark.items():
            int_mark += int_report(m)
    return int_mark


def update_exams_entry(matricola, mark, db_exams_name, date, exam_type, force=False):
    """Update the exams database with the exam results

    Args:
        matricola (int): the student id
        mark (str/dict): the mark value in the database
        db_exams_name (str): the name of the exams database
        date (str): the date of the exam
        exam_type (str): the type of the exam
        force (bool, optional): force the update of the database. Defaults to False.
    """    
    # add student's entry if not present
    if not check_entry(db_exams_name, 'matricola', matricola, 'exams'):
        add_row(db_exams_name, 'matricola', matricola, 'exams')
    # check if the student has already a result
    date_column = exam_type+'_date' if exam_type != 'result' else 'oral_date'
    old_entry = db_exam_results(*(get_entry(db_exams_name, 'matricola', matricola, 'exams')[0]))
    old_date = old_entry.__getattribute__(date_column)
    if old_date is not None and int(old_date) < int(date):
        old_mark = old_entry.__getattribute__(exam_type)
        print(f'Warning: {matricola} already has a {exam_type} mark from a different date!'+
              f' ({old_date}({old_mark}) vs {date}({mark}))')
        if int_mark(mark) <= int_mark(old_mark) and not force: 
            return
        print('Forcing update...')
    if exam_type == 'reports':
        mark = compact_report(mark)
    update_db(db_exams_name, exam_type, mark, 
              filter=f'matricola = {matricola}',
              table_name='exams')
    update_db(db_exams_name, date_column, date, 
              filter=f'matricola = {matricola}', 
              table_name='exams')
    return


def update_exams_db(json_file, db_students_name, db_exams_name, exam_type='written', force=False):
    """Updates the exams database with the data from a json file

    Args:
        json_file (str): the json file name with attendance data
        db_students_name (str): the file name of the database with students
        db_exams_name (str): the file name of the database with the exams results
        exam_type (str): the type of exams given (written, reports, result)
    """    
    data = json.load(open(json_file))
    for date, students in data.items():
        if exam_type == 'reports':
            for group, marks in students.items():
                # get the students in the group by their id (matricola)
                query = create_query(db_students_name,columns=['matricola'], 
                                     order='matricola', filter=f'gruppo = {group}')
                data, desc = query_database(db_students_name,query)
                if not data: continue
                ids =  [i[0] for i in data]
                # add report results to exams database
                for matricola in ids:
                    update_exams_entry(matricola, marks, db_exams_name, date,
                                       exam_type, force=False)
        else:
            for matricola, mark in students.items():
                print(matricola, mark)
                query = create_query(db_students_name, 
                                     columns=['cognome','nome','matricola'], 
                                     filter=f'matricola = "{matricola}"')
                result, description = query_database(db_students_name,query)
                if not result: continue
                # add student to exams database if not present
                update_exams_entry(result[0][2], mark, db_exams_name, 
                                   date, exam_type, force=False)
    return

def update_attendance_db(json_file, db_students_name, db_attendance_name):
    """Updates the attendance database with the data from a json file

    Args:
        json_file (str): the json file name with attendance data
        db_students_name (str): the file name of the database with students
        db_attendance_name (str): the file name of the database with attendance
    """    
    data = json.load(open(json_file))
    for date, students in data.items():
        for student in students:
            query = create_query(db_students_name, columns=['cognome','nome','matricola'], filter=f'cognome = "{student["cognome"]}" AND nome = "{student["nome"]}"')
            result, description = query_database(db_students_name,query)
            if not result: continue
            # add student to attendance database if not present
            if not check_entry(db_attendance_name, 'matricola', result[0][2], 'attendance'):
                add_row(db_attendance_name, 'matricola', result[0][2], 'attendance')
            update_db(db_attendance_name, date, student['presente']==1, filter=f'matricola = {result[0][2]}', table_name='attendance')
    return

def update_attendance_db_from_excel(excel_file, db_students_name, db_attendance_name):
    """Updates the attendance database with the data from a json file

    Args:
        excel_file (str): the excel file name with attendance data
        db_students_name (str): the file name of the database with students
        db_attendance_name (str): the file name of the database with attendance
    """
    data = pd.read_excel(excel_file)
    if data is None or data.empty:
        raise ValueError(f'No data found in {excel_file}')
    attendance_data = get_attendance_from_excel(data)
    for date, students in attendance_data.items():
        for student in students:
            query = create_query(db_students_name, columns=['cognome','nome','matricola'], filter=f'cognome = "{student["cognome"]}" AND nome = "{student["nome"]}"')
            result, description = query_database(db_students_name,query)
            if not result: continue
            # add student to attendance database if not present
            if not check_entry(db_attendance_name, 'matricola', result[0][2], 'attendance'):
                add_row(db_attendance_name, 'matricola', result[0][2], 'attendance')
            update_db(db_attendance_name, date, student['presente']==1, filter=f'matricola = {result[0][2]}', table_name='attendance')
    return

def get_attendance(db_name='data/dummy_attendance.db', matricola=None):
    """Returns the attendance from the database

    Returns:
        list: a list with the attendance
    """
    query = create_query(db_name, 'attendance', order='matricola', 
                         filter=f"matricola = {matricola}" if matricola is not None else None)
    data, desc = query_database(db_name,query)
    return data, desc

def calculate_attendance(db_name='data/dummy_attendance.db', db_dates='data/dummy_dates.db', matricola=None):
    """Calculates the fraction attendance from the database
    """
    # get the data
    data, desc = get_attendance(db_name, matricola)
    # get dates
    dates, desc_dates = get_dates(db_dates)
    # calculate attendance
    valid_hours = 0
    attendance = {}
    for student in data:
        days = [student[i] for i in range(1,len(student))]
        if valid_hours == 0:
            valid_hours = [dates[i][1] for i in range(len(days)) if days[i] is not None]
            valid_hours = sum(valid_hours)
            if valid_hours > 56: valid_hours = 56
        hours = 0
        for d, p in zip(dates,days):
            if p is not None and p:
                hours += d[1]
        att = float(hours)/valid_hours
        if att > 1: att = 1
        attendance[student[0]] = att
    return attendance