import logging
import os
import random

import httplib2
from googleapiclient import discovery
from oauth2client import client, tools
from oauth2client.file import Storage

from kaztron.config import get_kaztron_config

logger = logging.getLogger('kaztron.showcaser')

try:
    import argparse
except ImportError:
    argparse = None

if argparse:
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
else:
    flags = None


# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/spreadsheets.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'sheets.googleapis.com-python-quickstart.json')

    config = get_kaztron_config()
    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = config.get("core", "name")
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        logger.info('Storing credentials to ' + credential_path)
    return credentials


def main():
    rows = []

    config = get_kaztron_config()
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    discovery_url = ('https://sheets.googleapis.com/$discovery/rest?'
                    'version=v4')
    service = discovery.build('sheets', 'v4', http=http,
                              discoveryServiceUrl=discovery_url)

    result = service.spreadsheets().values().get(
        spreadsheetId=config.get("showcase", "spreadsheet_id"),
        range=config.get("showcase", "spreadsheet_range")).execute()
    values = result.get('values', [])

    if not values:
        logger.warn('No data found in showcaser spreadsheet.')
    else:
        for row in values:
            rows.append(row)

    return rows


def roll():
    rows = main()
    choice = random.choice(rows)
    while choice[16] != "Yes":
        choice = random.choice(rows)
    return choice


def choose(num):
    rows = main()
    choice = rows[num]
    return choice
