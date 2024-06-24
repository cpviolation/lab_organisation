from context import lborg
from lborg.db import create_query, query_database
from lborg.tables import make_table

import argparse
parser = argparse.ArgumentParser('Search Student Options')
parser.add_argument('--db_name', type=str, default='data/students.db', help='Database name')
parser.add_argument('--ids', type=int, default=None, nargs='+', help='Student id number')
parser.add_argument('--name', type=str, default=None, help='Student name')
parser.add_argument('--surname', type=str, default=None, help='Student surname')
parser.add_argument('--dryrun', action='store_true', help='Dry run')
args = parser.parse_args()

def main():
    if args.ids is None and args.name is None and args.surname is None:
        print('Please provide at least one of the following options: --id, --name, --surname')
        return
    if args.ids is not None:
        # query the database for id
        fltr = 'matricola = {}'.format(args.ids[0])
        for i in args.ids[1:]:
            fltr += ' OR matricola = {}'.format(i)
        query = create_query(args.db_name,columns=['cognome','nome','mail','gruppo','coorte'], 
                             order='cognome', filter=fltr)
    else:
        # query the database for name
        fltr = 'nome = {}'.format(args.name) if args.name is not None else ''
        if args.name is not None and args.surname is not None:
            fltr += ' AND '
        fltr += 'cognome = {}'.format(args.surname) if args.surname is not None else ''
        query = create_query(args.db_name,columns=['cognome','nome','mail','gruppo','coorte'], 
                             order='cognome', filter=fltr)
    data, desc = query_database(args.db_name,query)
    if not len(data):
        print('No student found with the given parameters')
        return
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    if not args.dryrun: main()