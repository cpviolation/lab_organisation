from context import lborg
from lborg.data_helpers import assign_group
from lborg.db import create_query, query_database
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Assign Groups Options')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--cohort', type=str, default='2023/24', help='Cohort name')
parser.add_argument('--groups', type=int, help='the groups to print', required=True)
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def main():
    # query the database 
    query = create_query(args.db_name,columns=['cognome','nome','mail','gruppo'], 
                         order='cognome', filter='gruppo = {}'.format(args.groups))
    data, desc = query_database(args.db_name,query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()