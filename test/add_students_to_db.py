from context import lborg
from lborg.data_helpers import add_participants_to_db

def main():
    # add participants to database
    add_participants_to_db('test/dummy_participants.json', cohort='2023/24',db_name='test/dummy.db', overwrite=True)
    return

if __name__ == '__main__':
    main()