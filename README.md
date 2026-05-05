# Lab Organisation

A repository to load the students from a laboratory course on a database and keep track of their laboratory duties and exams.

This repository can be used for the following purposes:

- load the students from a laboratory course on a database
- split them in groups
- keep track of attendance and create a report
- keep track of exams and create a report
- keep track of written reports from the students

## Installation

It is recommended to use a virtual environment to install the required packages. To do so, run the following commands:

```bash
python3 -m venv lborg
source lborg/bin/activate
pip install -r requirements.txt
```

## Create the database
To create the database, run the following command:

```bash
python $LBORG/macros/import_cohort.py --json_name data/raw/<file_name>.json --cohort <cohort>
```

where `<cohort>` is the name of the cohort you want to create (e.g. `2025/26`) and `<file_name>` is the name of the JSON file containing the student data extracted from elearning.

To assign the students to groups, run the following command:

```bash
python $LBORG/macros/assign_groups.py --cohort <cohort> --json_name data/raw/<file_name>.json
```
where each entry in the JSON file should contain at least these information about the student and the group number (e.g. `{"nome": <name>, "cognome": <surname>, "gruppo": <group_number>}`).

## Print the presence sheet for a specific date

To print the presence sheet for a specific date, run the following command:

```bash
python $LBORG/macros/make_signature_page.py --cohort 2025/26 --date <date>
```

where `<date>` is the date of the lesson in the format `YYYY-MM-DD` (e.g. `2025-10-01`).
```