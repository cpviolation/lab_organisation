import os, sqlite3
from lborg.db_items import db_item, print_db_item_as_tuple

def create_database(name, table_name='students',
                    structure={'cognome':'text','nome':'text','matricola':'integer','mail':'text','coorte':'text','gruppo':'integer'}, 
                    overwrite=False):
    """Creates a database with user-define structure. Default is:

    | key | type |
    |---|---|
    | cognome | text |
    | nome | text |
    | matricola | integer |
    | mail | text |
    | coorte | text |
    | gruppo | integer |
    
    and saves it to file

    Args:
        name (str): the file name containing the database
        table_name (str, optional): the name of the table. Defaults to 'students'.
        structure (dict, optional): the structure of the database. Defaults to {'cognome':'text','nome':'text','matricola':'integer','mail':'text','coorte':'text','gruppo':'integer'}.
        overwrite (bool, optional): if True, overwrites the file if it already exists. Defaults to False.
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
    exec_str = f"CREATE TABLE IF NOT EXISTS {table_name} ("
    for key, value in structure.items():
        exec_str += f"{key} {value},"
    exec_str = exec_str[:-1] + ")"
    cursor.execute(exec_str)
    # Commit the changes and close the connection
    connection.commit()
    connection.close()
    return

def get_db_columns(name, table_name='students'):
    """Get the columns of the database

    Args:
        name (str): the file name containing the database
        table_name (str, optional): the name of the table. Defaults to 'students'.

    Returns:
        list: a list of the columns of the database
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Get the columns
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    connection.close()
    return [col[1] for col in columns]

def create_query(name, table_name='students', columns=None, filter=None, order=None):
    """Given the columns and the order, creates a query to be used with the database

    Args:
        name (str): the file name containing the database
        table_name (str, optional): the name of the table. Defaults to 'students'.
        columns (list, optional): a list of columns to extract from the database. Defaults to None.
        order (str, optional): a specific column to order the output. Defaults to None.

    Raises:
        ValueError: One or more columns not found in the database
        ValueError: `order` column is not found in the database

    Returns:
        str: the query to be used with the database
    """
    if not os.path.exists(name): raise ValueError(f'Database {name} does not exist!')
    query = "SELECT "
    if columns is None:
        query += "*"
    else:
        db_columns = get_db_columns(name,table_name)
        if not all([col in db_columns for col in columns]):
            raise ValueError("One or more columns not found in the database")
        query += ', '.join(columns)
    query += f" FROM {table_name}"
    if filter is not None:
        query += " WHERE " + filter
    if order is not None:
        if not hasattr(db_item[table_name], order):
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

def insert_items(name, items, table_name='students', ignore_keys=[]):
    """Add many items at once to the database

    Args:
        name (str): the file name containing the database
        items (list): a list of db_items
        table_name(str, optional): the name of the table. Defaults to 'students'.
        ignore_keys (list, optional): a list of keys to ignore when checking for duplicates. Defaults to [].
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Check if item exists in database
    items_to_add = []
    for it in items:
        if check_item(name, it, table_name, ignore_keys):
            continue
        items_to_add.append(it)
    if items_to_add == []:
        print('All items already present in the database!')
        connection.close()
        return
    # Insert items
    exec_str = f"INSERT INTO {table_name} VALUES "
    for it in items_to_add:
        exec_str += print_db_item_as_tuple(it, table_name) + ','
    exec_str = exec_str[:-1]
    cursor.execute(exec_str)
    # Commit the changes
    connection.commit()
    # Close the connection
    connection.close()
    return

def check_item(name, item, table_name='students',ignore_keys=[]):
    """Check if an item is present in the database

    Args:
        name (str): the file name containing the database
        item (db_item): the item to check
        table_name (str, optional): the name of the table. Defaults to 'students'.

    Returns:
        bool: True if the item is present, False otherwise
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Check if item exists in database
    filter = ''
    for key in item._fields:
        if key in ignore_keys: continue
        filter += f"{key} = '{getattr(item, key)}' AND "
    filter = filter[:-5]
    query= create_query(name, table_name, filter=filter)
    cursor.execute(query)
    result = cursor.fetchall()
    connection.close()
    return len(result) > 0

def check_entry(name, column, value, table_name='students'):
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Check if item exists in database
    filter = f'{column} = \'{value}\'' if type(value)==str else f'{column} = {value}'
    query= create_query(name, table_name, filter=filter)
    cursor.execute(query)
    result = cursor.fetchall()
    connection.close()
    return len(result) > 0

def add_row(name, column, value, table_name='students'):
    """Add a row to the database by setting the value of a single column

    Args:
        name (str): the file name containing the database
        column (str): the column to update
        value (any): the new value for the column
        table_name (str, optional): the name of the table. Defaults to 'students'.
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Insert the item
    exec_str = f"INSERT INTO {table_name} ({column}) VALUES ("
    exec_str += f"'{value}')" if type(value) == str else f"{value})"
    cursor.execute(exec_str)
    # Commit the changes
    connection.commit()
    # Close the connection
    connection.close()
    return

def update_db(name, column, value, filter='', table_name='students'):
    """Update a column of a database item

    Args:
        name (str): the file name containing the database
        item (db_item): the item to update
        column (str): the column to update
        value (str): the new value for the column
        table_name (str, optional): the name of the table. Defaults to 'students'.
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Update the column
    exec_str = f"UPDATE {table_name} SET {column} = "
    exec_str += f"'{value}'" if type(value) == str else f"{value}"
    if filter!='': exec_str += f" WHERE {filter}"
    print(exec_str)
    cursor.execute(exec_str)
    # Commit the changes
    connection.commit()
    # Close the connection
    connection.close()
    return

def check_column(name, column, table_name='students'):
    """Check if a column is present in the database

    Args:
        name (str): the file name containing the database
        column (str): the name of the column to check
        table_name (str, optional): the name of the table. Defaults to 'students'.

    Returns:
        bool: True if the column is present, False otherwise
    """    
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Check if the column is present
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    connection.close()
    return column in [col[1] for col in columns]

def add_column(name, column, type, default=None, table_name='students'):
    """Add a column to the database

    Args:
        name (str): the file name containing the database
        column (str): the name of the column to add
        type (str): the type of the column to add
        table_name (str, optional): the name of the table. Defaults to 'students'.
        default (str, optional): the default value for the column. Defaults to None.
    """    
    if check_column(name, column, table_name):
        print(f'Column {column} already present in the database {name}!')
        return
    # Connect to a database
    connection = sqlite3.connect(name)
    # Create a cursor object to interact with the database
    cursor = connection.cursor()
    # Add a column
    exec_str = f"ALTER TABLE {table_name} ADD COLUMN {column} {type}"
    if default is not None:
        exec_str += f" DEFAULT {default}"
    cursor.execute(exec_str)
    # Commit the changes
    connection.commit()
    # Close the connection
    connection.close()
    return