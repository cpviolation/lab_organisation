from collections import namedtuple

db_student = namedtuple('db_student', ['nome', 'cognome', 'matricola', 'mail','coorte','gruppo'])
db_date = namedtuple('db_date', ['date', 'hours'])
db_exam = namedtuple('db_exam', ['date', 'type'])
db_attendance = namedtuple('db_attendance', ['date', 'matricola'])
db_item = {'students': db_student, 'dates': db_date, 'attendance': db_attendance}

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
    out+= f'Gruppo: {item.gruppo}\n'
    return out

def print_db_item_as_tuple(item):
    """Prints the information of a db_item as a tuple

    Args:
        item (db_item): the database item to print

    Returns:
        str: the information of the database item as a tuple
    """    
    out = "("
    for key in item._fields:
        out += f"'{getattr(item,key)}'," if type(getattr(item,key)) == str else f"{getattr(item,key)},"
    out = out[:-1] + ")"
    return out