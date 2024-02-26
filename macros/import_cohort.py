from context import lborg
from lborg.data_helpers import add_participants_to_db

import argparse
parser = argparse.ArgumentParser('Import Cohort Options')
parser.add_argument('--cohort', type=str, help='Cohort name')
parser.add_argument('--json_name', type=str, help='Input JSON name')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()


def main():
    # add participants to database
    add_participants_to_db(args.json_name, cohort=args.cohort,
                           db_name=f'data/{args.cohort}.db', overwrite=True)
    return

if __name__ == '__main__':
    if not args.dryrun: main()