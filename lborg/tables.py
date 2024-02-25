from tabulate import tabulate
from lborg.db import db_student

def make_table(data, columns=['cognome','nome','matricola','mail']):
    """Creates a table from a list of db_student items
    """
    # Tabulate the rows
    table = tabulate(data, headers=columns, tablefmt="grid")

    # Print the tabulated data
    print(table)
    return