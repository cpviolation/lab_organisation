import os
from tabulate import tabulate
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

def make_latex_table(data, columns=['Gruppo','Studente','Firma'],group_id_start=1):
    # modify to get table data
    data_table = []
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
    group_id = group_id_start
    n_students = table.count(f' {group_id} &')
    while (n_students):
        table = table.replace(f' {group_id} &', ("\\hline" if group_id>1 else "")+f' \\multirow{{{n_students}}}{{*}}{{{group_id}}} &', 1)
        table = table.replace(f' {group_id} &', r'\cline{2-3} &', n_students-1)
        group_id += 1
        n_students = table.count(f' {group_id} &')
    return table

def make_signature_table(db_name, cohort, date, title='Laboratorio I - Turno Beta', output_dir='pdfs'):
    """Creates a table from a list of db_student items
    """
    # get the data
    data = get_groups(cohort, db_name)
    # get tables
    tables = []
    groups_id_split = int(len(data)/2)
    data_split = {
        1 : {key: data[key] for key in range(1,groups_id_split)},
        groups_id_split: {key: data[key] for key in range(groups_id_split,int(len(data)))}
    }
    for group_id, data_table in data_split.items():
        tables += [make_latex_table(data_table,group_id_start=group_id)]

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
    with open(f'{output_dir}/latex/{cohort.replace("/","_")}_signature_table.tex', 'w') as f:
        f.write(latex)
    return