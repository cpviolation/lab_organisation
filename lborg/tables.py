import os
import numpy as np
from tabulate import tabulate
from lborg.data_helpers import get_groups, get_attendance, get_hours

def make_table(data, columns=['cognome','nome','matricola','mail']):
    """Creates a table from a list of db_student items

    Args:
        data (list): list of db_student items
        columns (list, optional): list of column names. Defaults to ['cognome','nome','matricola','mail'].
    """
    # Tabulate the rows
    table = tabulate(data, headers=columns, tablefmt="grid")

    # Print the tabulated data
    print(table)
    return

def make_latex_table(data, columns=['Gruppo','Studente','Firma']):
    """Creates a latex table from a list of db_student items

    Args:
        data (list): list of db_student items
        columns (list, optional): list of column names. Defaults to ['Gruppo','Studente','Firma'].
    """
    # modify to get table data
    data_table = []
    group_ids = [ key for key in data.keys() if data[key] ]
    for group, item in data.items():
        print(group, item)
        for it in item:
            data_table.append([group, f'{it[0]} {it[1]}', ''])
    table = tabulate(data_table, headers=columns, tablefmt="latex_longtable")
    # Fix table
    table = table.replace(r'{longtable}', r'{tabularx}')
    table = table.replace(r'\endhead', '')
    table = table.replace(r'\begin{tabularx}{rll}', r'\begin{tabularx}{\textwidth}{|r|l|X|}')
    # Index of groups on multirow
    for group_id in group_ids:
        n_students = table.count(f' {group_id} &')
        table = table.replace(f' {group_id} &', ("\\hline" if group_id>1 else "")+f' \\multirow{{{n_students}}}{{*}}{{{group_id}}} &', 1)
        table = table.replace(f' {group_id} &', r'\cline{2-3} &', n_students-1)
    return table

def get_latex_tables(tables, lhead='', rhead=''):
    # write the latex table to file
    latex = r'\documentclass[12pt]{article}'+'\n'
    latex +=r'\usepackage{multirow}'+'\n'
    latex +=r'\usepackage{tabularx}'+'\n'
    latex +=r'\usepackage[margin=1in]{geometry} % Set all margins to 1 inch'+'\n'
    latex +=r'\usepackage{fancyhdr}'+'\n\n'
    latex +=r'% Set fancy headers'+'\n'
    latex +=r'\pagestyle{fancy}'+'\n'
    latex +=r'\fancyhf{} % Clear header and footer'+'\n'
    latex +=f'\\lhead{{{lhead}}} % Set title on the top left'+'\n\n'
    latex +=f'\\rhead{{{rhead}}} % Set date on the top right'+'\n\n'
    latex +=r'\begin{document}'+'\n\n'
    for table in tables:
        latex +=r'\begin{table}[t]'+'\n'
        latex +=r'\centering'
        latex +=table
        latex +=r'\end{table}'+'\n\n'
    latex +=r'\end{document}'+'\n'
    return latex

def save_latex_table(latex_table, fname, output_dir):
    if not os.path.exists(f'{output_dir}/latex'):
        os.makedirs(f'{output_dir}/latex')
    with open(f'{output_dir}/latex/{fname}', 'w') as f:
        f.write(latex_table)
    # create pdf
    os.system(f'pdflatex -output-directory={output_dir} {output_dir}/latex/{fname}')
    return

def make_signature_table(db_name, cohort, date='', title='Laboratorio I - Turno Beta', output_dir='pdfs'):
    """Creates a table from a list of db_student items

    Args:
        db_name (str): database name
        cohort (str): cohort name
        date (str, optional): date on the signature table. Defaults to ''.
        title (str, optional): title of the signature table. Defaults to 'Laboratorio I - Turno Beta'.
        output_dir (str, optional): output directory. Defaults to 'pdfs'.
    """
    # get the data
    data = get_groups(cohort, db_name)
    # get tables
    tables = []
    groups_id_split = int(len(data)/2)
    data_split = {
        1 : {key: data[key] if key in data.keys() else [] for key in range(1,groups_id_split)},
        groups_id_split: {key: data[key] if key in data.keys() else [] for key in range(groups_id_split,int(len(data)+1))}
    }
    for group_id, data_table in data_split.items():
        filtered_data_table = {key: value for key, value in data_table.items() if value}
        print(filtered_data_table)
        tables += [make_latex_table(filtered_data_table)]

    # write the latex table to file
    latex = r'\documentclass[12pt]{article}'+'\n'
    latex +=r'\usepackage{multirow}'+'\n'
    latex +=r'\usepackage{tabularx}'+'\n'
    latex +=r'\usepackage[margin=1in]{geometry} % Set all margins to 1 inch'+'\n'
    latex +=r'\usepackage{fancyhdr}'+'\n\n'
    latex +=r'% Set fancy headers'+'\n'
    latex +=r'\pagestyle{fancy}'+'\n'
    latex +=r'\fancyhf{} % Clear header and footer'+'\n'
    latex +=f'\\lhead{{{title}}} % Set title on the top left'+'\n\n'
    latex +=f'\\rhead{{{date}}} % Set date on the top right'+'\n\n'
    latex +=r'\begin{document}'+'\n\n'
    for table in tables:
        latex +=r'\begin{table}[t]'+'\n'
        latex +=r'\centering'
        latex +=table
        latex +=r'\end{table}'+'\n\n'
    latex +=r'\end{document}'+'\n'

    if not os.path.exists(f'{output_dir}/latex'):
        os.makedirs(f'{output_dir}/latex')
    fname= cohort.replace("/","_") if date=='' else date
    fname+='_signature_table.tex'
    with open(f'{output_dir}/latex/{fname}', 'w') as f:
        f.write(latex)
    
    # create pdf
    os.system(f'pdflatex -output-directory={output_dir} {output_dir}/latex/{fname}')
    return 

def make_attendance_table(db_name, cohort, output_dir='pdfs'):
    """Creates an attendance table for a given cohort
    """
    # checks
    if not os.path.exists(db_name):
        raise ValueError(f'Database {db_name} not found!')

    # get the data
    data, desc = get_attendance(db_name)
    # add a column for percentage
    columns = [description[0] for description in desc]
    columns.append(r'\%')
    hours = get_hours(f'data/dates_{cohort.replace("/","_")}.db')
    print(hours)
    data_table = []
    for d in data:
        d_tab = list(d)
        count_hours = 0
        for i in d_tab[1:]:
            count_hours += i if i != None else 0
        valid_hours = np.sum(hours[:-1])
        d_tab.append(f'{float(count_hours)/valid_hours*100:.1f}')
        data_table.append(d_tab)
    # Tabulate the rows
    table = tabulate(data_table, headers=columns, tablefmt="latex")
    table = table.replace(' 1 ',' P ')
    table = table.replace(' 0 ',' A ')
    table = table.replace(' 2024-', ' ')
    latex = get_latex_tables([table],lhead='Laboratorio I - Turno Beta',rhead='2023/24')

    print(table)

    fname=f'{cohort.replace("/","_")}_attendance_table.tex'
    save_latex_table(latex, fname, output_dir)

    return