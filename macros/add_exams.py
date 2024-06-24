from context import lborg
from lborg.data_helpers import add_exams_db
from lborg.db import create_query, query_database
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Add exam dates to Database')
parser.add_argument('--db_name', type=str, default='data/exams_dates.db', help='Database name')
parser.add_argument('--json_name', type=str, help='Input JSON name', required=True)
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def main():
    # add dates to database
    add_exams_db(args.json_name,db_name=args.db_name)
    # query the database (partial)
    query = create_query(args.db_name,'exams',columns=['date','type'], order='date')
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()