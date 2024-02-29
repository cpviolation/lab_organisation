from context import lborg
from lborg.data_helpers import get_groups
from lborg.tables import make_signature_table

import argparse
parser = argparse.ArgumentParser('Assign Groups Options')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, default='2023/24', help='Cohort name')
parser.add_argument('--date', type=str, help='date', required=True)
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def main():
    # get groups
    #groups = get_groups(args.cohort, db_name=args.db_name)
    make_signature_table(args.db_name, args.cohort, args.date)
    return

if __name__ == '__main__':
    if not args.dryrun: main()