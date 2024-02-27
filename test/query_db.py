import os
from context import lborg
from lborg.db import query_database, create_query
from lborg.tables import make_table

def main():
    # search for dummy database
    if not os.path.exists('test/dummy.db'):
        raise ValueError('Database test/dummy.db not found! Run test/add_students_to_db.py first')
    # query the database
    print('Print all the database entries ordered by "cognome"')
    query = create_query(order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])

    # query the database (partial)
    print('\nPrint all the database entries ordered by "cognome" and show only "cognome","nome","mail" columns')
    query = create_query(columns=['cognome','nome','mail'], order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])

    # query the database (partial with filter)
    print('\nPrint the database entries corresponding to "coorte" = "2022/23" ordered by "cognome" and show only "cognome","nome","mail" columns')
    query = create_query(columns=['cognome','nome','mail'], filter='coorte = "2022/23"', order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__': 
    main()