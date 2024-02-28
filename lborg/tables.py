from tabulate import tabulate, SEPARATING_LINE
from lborg.db import db_student
from lborg.data_helpers import get_groups

def make_table(data, columns=['cognome','nome','matricola','mail']):
    """Creates a table from a list of db_student items
    """
    # Tabulate the rows
    table = tabulate(data, headers=columns, tablefmt="grid")

    # Print the tabulated data
    print(table)
    return

def make_signature_table(db_name, cohort, date):
    """Creates a table from a list of db_student items
    """
    # get the data
    data = get_groups(cohort, db_name)

    # modify to get table data
    data_table = []
    group_idx = 0
    for group, item in data.items():
        print(group, item)
        for it in item:
            data_table.append([group, f'{it[0]} {it[1]}', ''])

    # Tabulate the rows
    columns = ['Gruppo', 'Studente', 'Firma']
    table = tabulate(data_table, headers=columns, tablefmt="grid")

    # Print the tabulated data
    print(table)
    return