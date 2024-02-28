from context import lborg
from lborg.data_helpers import add_participants_to_db

import argparse
parser = argparse.ArgumentParser('Import Cohort Options')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, help='Cohort name')
parser.add_argument('--json_name', type=str, help='Input JSON name')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()


def main():
    if args.cohort is None:
        raise ValueError('Cohort name is required')
    # add participants to database
    add_participants_to_db(args.json_name, cohort=args.cohort,
                           db_name=args.db_name, update=True)
    return

if __name__ == '__main__':
    if not args.dryrun: main()