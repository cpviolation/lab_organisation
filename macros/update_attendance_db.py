import os
from context import lborg
from lborg.data_helpers import create_attendance_db, create_attendance_db_from_excel, create_query, query_database, update_attendance_db, update_attendance_db_from_excel
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Create Attendance Database Options\n'+
                                 'This script creates the attendance database and updates it with the given JSON files or Excel files.\n'+
                                 '   $ python $LBORG/macros/update_attendance_db.py --json_dates dates.json --json_attendance attendance.json --cohort 2024_25\n'+
                                 '   $ python $LBORG/macros/update_attendance_db.py --excel_attendance attendance.xlsx --cohort 2024_25\n')
parser.add_argument('--db_name', type=str, default='data/attendance.db', help='Database name')
parser.add_argument('--students_db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, help='Cohort name')
parser.add_argument('--json_dates', type=str, help='Input JSON with course dates')
parser.add_argument('--json_attendance', type=str, help='Input JSON with attendance results', nargs='+')
parser.add_argument('--excel_attendance', type=str, help='Input excel file with attendance results')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()


def main():
    # create the attendance database if not existing
    if not os.path.exists(args.db_name):
        if args.json_dates is None and args.excel_attendance is None:
            raise ValueError('Please provide either a JSON file with course dates or an Excel file with attendance results.')
        if args.json_dates is not None:
            create_attendance_db(args.json_dates, args.db_name)
        elif args.excel_attendance is not None:
            create_attendance_db_from_excel(args.excel_attendance, args.db_name)
    # update the attendance database
    if args.json_attendance is not None:
        for jat in args.json_attendance:
            update_attendance_db(jat, args.students_db_name, args.db_name)
    if args.excel_attendance is not None:
        update_attendance_db_from_excel(args.excel_attendance, args.students_db_name, args.db_name)
    # print database
    query = create_query(args.db_name, 'attendance', order='matricola')
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()