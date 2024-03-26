import os
from context import lborg
from lborg.data_helpers import create_attendance_db, create_query, query_database, update_attendance_db
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Create Attendance Database Options')
parser.add_argument('--db_name', type=str, default='data/attendance.db', help='Database name')
parser.add_argument('--students_db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, help='Cohort name')
parser.add_argument('--json_dates', type=str, help='Input JSON with course dates')
parser.add_argument('--json_attendance', type=str, help='Input JSON with attendance results', nargs='+')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()


def main():
    # create the attendance database if not existing
    if not os.path.exists(args.db_name):
        if args.json_dates is None:
            raise ValueError('Please provide a JSON file with course dates')
        create_attendance_db(args.json_dates, args.db_name)
    
    # update the attendance database
    for jat in args.json_attendance:
        update_attendance_db(jat, args.students_db_name, args.db_name)
    # print database
    query = create_query(args.db_name, 'attendance', order='matricola')
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()