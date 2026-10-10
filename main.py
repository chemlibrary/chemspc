"""
REQUIREMENTS:
python3 -m pip install fastapi[standard]

USAGE:
uv run fastapi dev
"""

from fastapi import FastAPI
from functions import check_for_missing_tables
from chempy.conf import read_conf


## Load configuration and prepare database
try:
    conf = read_conf('./cruise-control.conf')
    if 'db_user' in conf:
        DB_USER = conf['db_user']
    else:
        DB_USER = None
        print('[WARN] Failed to load database user!')
    if 'db_password' in conf:
        DB_PASSWORD = conf['db_password']
    else:
        DB_PASSWORD = None
        print('[WARN] Failed to load database password!')
except:
    print('[WARN] Failed to load database user/password!')
    DB_USER = None
    DB_PASSWORD = None

check_for_missing_tables(db_user=DB_USER, db_password=DB_PASSWORD)

app = FastAPI()



@app.get('/')
async def root():
    return {
        'message': 'Welcome to Cruise Control!'
    }

"""
@app.get('/generate/password/{length}')
async def create_new_password(length:int = None):
    if length == None:
        length = 16
    password = generate_password(length=length)
    return {
        'password': password
    }
"""


"""
@app.post('/file/save/', description='Save a file to the local system.')
async def save_file(file_details: ATAFile) -> bool:
    path = file_details.path
    contents = file_details.contents
    try:
        result = file_safe_write(path=path, contents=contents)
    except:
        result = False
    if result: message = f'File saved to {path}'
    else: message = 'File failed to save!'
    return {
        'success': result,
        'path': path,
        'message': message,
    }
"""