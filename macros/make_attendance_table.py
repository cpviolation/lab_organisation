from context import lborg
from lborg.tables import make_attendance_table

import argparse
parser = argparse.ArgumentParser('Print a table with attandance information\n'+
                                 'Beware that the `dates` database should be named after the cohort, e.g. `data/dates_2023_24.db`.\n'+
                                 '   $ python $LBORG/macros/make_attendance_table.py --db_name data/attendance.db --cohort 2023/24\n')
parser.add_argument('--db_name', type=str, default='data/attendance.db', help='Database name')
parser.add_argument('--cohort', type=str, default='2023/24', help='Cohort name')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def main():
    # get groups
    #groups = get_groups(args.cohort, db_name=args.db_name)
    make_attendance_table(args.db_name, args.cohort)
    return

if __name__ == '__main__':
    if not args.dryrun: main()