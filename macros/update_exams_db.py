import os
from context import lborg
from lborg.data_helpers import create_exams_db, create_query, query_database, update_exams_db
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Create Attendance Database Options')
parser.add_argument('--db_name', type=str, default='data/exams.db', help='Database name')
parser.add_argument('--students_db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, help='Cohort name')
parser.add_argument('--json_exams', type=str, help='Input JSON with exams dates', nargs='+')
parser.add_argument('--exam_type', type=str, default='written', help='Exam Type')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()


def main():
    # create the attendance database if not existing
    if not os.path.exists(args.db_name):
        create_exams_db(args.db_name)
    # update the exams database
    for jex in args.json_exams:
        update_exams_db(jex, args.students_db_name, args.db_name, args.exam_type)
    # print database
    query = create_query(args.db_name, 'exams', order='matricola')
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()