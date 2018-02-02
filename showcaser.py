
from __future__ import print_function
import httplib2
import os
import random
import logging

from googleapiclient import discovery
from googleapiclient.errors import *
from oauth2client import client
from oauth2client import tools
from oauth2client.client import UnknownClientSecretsFlowError # for export - don't clean up
from oauth2client.clientsecrets import InvalidClientSecretsError # for export - don't clean up
from oauth2client.file import Storage

import config

logger = logging.getLogger('kaztron.showcaser')

try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
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

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = config.get("core", "name")
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        logger.info('Storing credentials to ' + credential_path)
    return credentials

def main():
    list = []

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    discoveryUrl = ('https://sheets.googleapis.com/$discovery/rest?'
                    'version=v4')
    service = discovery.build('sheets', 'v4', http=http,
                              discoveryServiceUrl=discoveryUrl)

    result = service.spreadsheets().values().get(
        spreadsheetId=config.get("showcase", "spreadsheet_id"),
        range=config.get("showcase", "spreadsheet_range")).execute()
    values = result.get('values', [])

    if not values:
        logger.warn('No data found in showcaser spreadsheet.')
    else:
        for row in values:
            list.append(row)

    return list

def roll():
    list = main()
    choice = random.choice(list)
    while choice[16] != "Yes":
        choice = random.choice(list)
    return choice

def choose(num):
    list = main()
    choice = list[num]
    return choice
