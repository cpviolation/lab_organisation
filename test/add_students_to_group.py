from context import lborg
from lborg.data_helpers import assign_group
from lborg.db import add_column, create_query, query_database, get_db_columns
from lborg.tables import make_table

def main():
    # add "gruppo" column to database
    add_column('test/dummy.db', 'gruppo', 'INTEGER', 0)
    # add participants to database
    assign_group('test/dummy_participants_group.json', db_name='test/dummy.db')

    #print(get_db_columns('test/dummy.db'))

    # query the database (partial)
    query = create_query(columns=['cognome','nome','mail','gruppo'], order='cognome')
    data, desc = query_database('test/dummy.db',query)
    # print table out of data and omit column 'coorte'
    make_table(data, columns=[description[0] for description in desc])
    return

if __name__ == '__main__':
    main()