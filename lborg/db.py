import os, sqlite3
from collections import namedtuple

db_student = namedtuple('db_student', ['nome', 'cognome', 'matricola', 'mail','coorte'])

def print_db_student(item):
    """Prints information of a db_student item

    Args:
        item (db_student): the database item to print

    Returns:
        str: a string with the information of the database item
    """    
    out = f'Studente: {item.cognome} {item.nome}\n'
    out+= f'Matricola: {item.matricola}\n'
    out+= f'Indirizzo Email: {item.mail}\n'
    out+= f'Coorte: {item.coorte}\n'
    return out

def print_db_student_as_tuple(item):
    """Prints the information of a db_item as a tuple

    Args:
        item (db_item): the database item to print

    Returns:
        str: the information of the database item as a tuple
    """    
    out = f"('{item.cognome}',"
    out+= f"'{item.nome}',"
    out+= f"{item.matricola},"
    out+= f"'{item.mail}',"
    out+= f"'{item.coorte}')"
    return out 

def create_database(name, overwrite=False):
    """Creates a database with the default structure 

    | key | type |
    |---|---|
    | cognome | text |
    | nome | text |
    | matricola | integer |
    | mail | text |
    | coorte | text |
    
    and saves it to file

    Args:
        name (str): the file name containing the database
    """
    # Check if the file already exists
    if os.path.exists(name): 
        if overwrite: 
            os.remove(name)
        else:
            raise ValueError(f'Database {name} already exists!')
    # Connect to a database (or create it if it doesn't exist)
    if not os.path.exists(name[:name.rfind('/')]): os.makedirs(name[:name.rfind('/')])
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Create a table
    cursor.execute("""CREATE TABLE IF NOT EXISTS students (
        cognome text,
        nome text,
        matricola integer,
        mail text,
        coorte text
    )""")
    # Commit the changes and close the connection
    connection.commit()
    connection.close()
    return

def create_query(columns=None, filter=None, order=None):
    """Given the columns and the order, creates a query to be used with the database

    Args:
        columns (list, optional): a list of columns to extract from the database. Defaults to None.
        order (str, optional): a specific column to order the output. Defaults to None.

    Raises:
        ValueError: One or more columns not found in the database
        ValueError: `order` column is not found in the database

    Returns:
        str: the query to be used with the database
    """
    query = "SELECT "
    if columns is None:
        query += "*"
    else:
        if not all([hasattr(db_student, col) for col in columns]):
            raise ValueError("One or more columns not found in the database")
        query += ', '.join(columns)
    query += " FROM students"
    if filter is not None:
        query += " WHERE " + filter
    if order is not None:
        if not hasattr(db_student, order):
            raise ValueError(f"Column {order} not found in the database")
        query += " ORDER BY " + order
    return query

def query_database(name,query):
    """Query the database

    Args:
        name (str): name of the file containing the database
        query (str): the query

    Raises:
        ValueError: file name does not exist

    Returns:
        tuple: a tuple with the result of the query
    """    
    if not os.path.exists(name): raise ValueError(f'Database {name} does not exist!')
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Return all results of query
    cursor.execute(query)
    result = cursor.fetchall()
    description = cursor.description
    return result, description

def insert_items(name, items):
    """Add many items at once to the database

    Args:
        name (str): the file name containing the database
        items (list): a list of db_items
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Insert items
    exec_str = "INSERT INTO students VALUES "
    for it in items:
        exec_str += print_db_student_as_tuple(it) + ','
    exec_str = exec_str[:-1]
    cursor.execute(exec_str)
    # Commit the changes
    connection.commit()
    # Close the connection
    connection.close()
    return
