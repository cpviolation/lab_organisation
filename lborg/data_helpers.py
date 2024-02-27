import os
import json
from lborg.db import db_student, create_database, insert_items

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
    return data