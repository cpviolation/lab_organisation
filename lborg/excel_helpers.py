from datetime import datetime

MONTHS_IT_TO_EN = {
    'gen': 'jan', 'feb': 'feb', 'mar': 'mar', 'apr': 'apr',
    'mag': 'may', 'giu': 'jun', 'lug': 'jul', 'ago': 'aug',
    'set': 'sep', 'ott': 'oct', 'nov': 'nov', 'dic': 'dec'
}

def translate_date(date):
    """Translate dates from Italian to English format.
    Args:
        date (list): List of dates in Italian
    Returns:
        list: List of dates in English format
    """
    for it, en in MONTHS_IT_TO_EN.items():
        date = date.replace(it, en)
    td = datetime.strptime(date, '%d %b %Y')
    formatted_date = td.strftime('%Y-%m-%d')
    return formatted_date


def get_dates_from_excel_columns(columns):
    """Extract dates from Excel columns.
    
    Args:
        columns (list): List of column names from an Excel sheet.
    
    Returns:
        dict: Dictionary mapping dates to their corresponding column names.
    """
    dates_and_cols = {}
    for col in columns:
        if '10.30AM' in col:
            date = "\'"+translate_date(col[:col.find('10.30AM')-1])+"\'"
            dates_and_cols[date] = col
    return dates_and_cols


def get_attendance_from_excel(data):
    """Extract attendance data from Excel rows.
    
    Args:
        data (list): List of rows from an Excel sheet.
    
    Returns:
        dict: Dictionary with student IDs as keys and their attendance as values.
    """
    attendance = {}
    dates_and_cols = get_dates_from_excel_columns(data.keys())  # Assuming first row contains column names
    for date, col in dates_and_cols.items():
        attendance_info = []
        for index, row in data.iterrows():
            attendance_info += [{
                "nome": row['Nome'],
                "cognome": row['Cognome'],
                "presente": 1 if any(x in row[dates_and_cols[date]] for x in ('P', 'R', 'G')) else 0
            }]
        attendance[date] = attendance_info
    return attendance