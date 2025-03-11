from context import lborg
from lborg.data_helpers import add_participants_to_db
from lborg.db import create_query, query_database
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Import Cohort Options')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, help='Cohort name', required=True)
parser.add_argument('--json_name', type=str, help='Input JSON name')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
parser.add_argument('--verbose', action='store_true', help='Verbose mode')
args = parser.parse_args()


def main():
    # add participants to database
    add_participants_to_db(args.json_name, cohort=args.cohort,
                           db_name=args.db_name, update=True, verbose=args.verbose)
    # print the database
    query = create_query(args.db_name,columns=['cognome','nome','mail','gruppo'], order='cognome')
    if args.verbose:
        print(query)
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    if args.verbose: 
        print(data)
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()