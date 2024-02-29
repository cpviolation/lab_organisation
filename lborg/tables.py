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
    for group, item in data.items():
        print(group, item)
        for it in item:
            data_table.append([group, f'{it[0]} {it[1]}', ''])

    # Tabulate the rows
    columns = ['Gruppo', 'Studente', 'Firma\phantom{pppppppppppppppppp}']
    table = tabulate(data_table, headers=columns, tablefmt="latex_longtable")

    # Index of groups on multirow
    group_id = 1
    n_students = table.count(f' {group_id} &')
    while (n_students):
        table = table.replace(f' {group_id} &', f' \\multirow{{{n_students}}}{{*}}{{{group_id}}} &', 1)
        table = table.replace(f' {group_id} &', f' &', n_students-1)
        group_id += 1
        n_students = table.count(f' {group_id} &')

    # Print the tabulated data
    print(table)
    return