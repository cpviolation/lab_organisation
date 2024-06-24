from context import lborg
from lborg.db import create_query, query_database, get_entry
from lborg.tables import make_table
from lborg.data_helpers import calculate_attendance
from lborg.db_items import db_student, db_exam_results

import argparse
parser = argparse.ArgumentParser('Exams Table')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--db_exams_name', type=str, default='data/exams.db', help='Exams database name')
parser.add_argument('--db_attendance_name', type=str, default='data/attendance.db', help='Attendance database name')
parser.add_argument('--ids', type=int, default=None, nargs='+', help='Student id number',required=True)
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def check_exams_db(data):
    """Cross-check the list of students with the exams database

    Args:
        data (list): list of students (as db_student items)
    """
    valid_students = []
    for d in data:
        student = db_student(*d)
        exam = get_entry(args.db_exams_name, 'matricola', student.matricola, 'exams', db_exam_results)
        if exam is not None and exam.written is not None and exam.written > 17:
            valid_students.append(student)
    return valid_students

def check_attendance_db(data):
    """Cross-check the list of students with the attendance database and verify 
    that their attendance is above 75%

    Args:
        data (list): list of students (as db_student items)
    """
    valid_students = []
    for d in data:
        student = db_student(*d)
        attendance = calculate_attendance(args.db_attendance_name, 
                                          f'data/dates_{student.coorte.replace("/","_")}.db',
                                          student.matricola)
        if attendance[student.matricola] > 0.75:
            valid_students.append(student)
        else:
            print(f'Student {student.nome} {student.cognome} has an attendance of {attendance*100:.0f}% and is not added to the list')
    return valid_students

def main():
    # query the database for id
    fltr = 'matricola = {}'.format(args.ids[0])
    for i in args.ids[1:]:
        fltr += ' OR matricola = {}'.format(i)
    query = create_query(args.db_name,columns=None,#['cognome','nome','mail','gruppo','coorte','matricola'], 
                         order='gruppo', filter=fltr)
    data, desc = query_database(args.db_name,query)
    valid_data = check_exams_db(data)
    valid_data = check_attendance_db(valid_data)
    if not len(valid_data):
        print('No student found with the given parameters')
        return
    # print table out of data and omit column 'coorte'
    make_table(valid_data, columns=[description[0] for description in desc])
    print(f'Number of students that have passed the written exam: {len(valid_data)}')
    return

if __name__ == '__main__':
    if not args.dryrun: main()