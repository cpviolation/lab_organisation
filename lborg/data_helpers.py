import os
import json
from lborg.db_items import db_student, db_date
from lborg.db import create_database, insert_items, check_column, update_db, create_query, query_database, check_entry, add_row

def add_participants_to_db(json_file, cohort='2023/24',db_name='data/dummy.db', 
                           update=False, overwrite=False):
    """Add participants to a database

    Args:
        json_file (str): the file name of the json file with participants
        cohort (str, optional): the academic year of attendance. Defaults to '2023/24'.
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
        create_database(db_name, overwrite=overwrite)
    # add participants to database
    students = []
    for student in data[0]:
        students += [ db_student(student['nome'],
                                 student['cognome'],
                                 student['matricola'],
                                 student['indirizzoemail'],
                                 cohort,
                                 0) ]
    insert_items(db_name, students, ignore_keys=['gruppo'])
    print(f'Added {len(students)} students from {cohort} cohort to {db_name}')
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

def assign_group(json_file, db_name='data/dummy.db'):
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
        st_item = db_student(student['nome'],
                             student['cognome'],
                             student['matricola'] if 'matricola' in student.keys() else None,
                             student['indirizzoemail'] if 'indirizzoemail' in student.keys() else None,
                             None,
                             0)
        update_db(db_name, 'gruppo', student['gruppo'],f"cognome = \'{student['cognome']}\' AND nome = \'{student['nome']}\'")
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
    attendance = {}
    return