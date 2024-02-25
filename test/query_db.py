import os
from context import lborg
from lborg.db import query_database, create_query
from lborg.tables import make_table

def main():
    # search for dummy database
    if not os.path.exists('test/dummy.db'):
        raise ValueError('Database test/dummy.db not found! Run test/add_students_to_db.py first')
    # query the database
    query = create_query(order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])

    # query the database (partial)
    query = create_query(columns=['cognome','nome','mail'], order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__': 
    main()