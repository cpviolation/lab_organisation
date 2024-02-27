import os
import json
from lborg.db import db_student, create_database, insert_items, check_column, update_db, create_query, query_database

def add_participants_to_db(json_file, cohort='2023/24',db_name='data/dummy.db', 
                           update=False, overwrite=False):
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
                                 cohort) ]
    insert_items(db_name, students)
    print(f'Added {len(students)} students from {cohort} cohort to {db_name}')
    return 

def assign_group(json_file, db_name='data/dummy.db'):
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
                             None)
        update_db(db_name, st_item, 'gruppo', student['gruppo'])
    return

def get_groups(cohort, db_name='data/dummy.db'):
    # check if database exists
    if not os.path.exists(db_name):
        raise ValueError(f'Database {db_name} not found!')
    # query the database
    query = create_query(columns=['cognome','nome','mail','gruppo'], order='cognome')
    data, desc = query_database(db_name,query)
    # order data by group number
    sorted_array = sorted(data, key=lambda x: x[3])
    # create dictionary with groups
    groups = {}
    for student in sorted_array:
        if student[3] not in groups.keys():
            groups[student[3]] = []
        groups[student[3]].append(student) 
    return groups