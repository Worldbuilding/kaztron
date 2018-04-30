import logging
import os

import httplib2
from googleapiclient import discovery
from oauth2client import client, tools
from oauth2client.file import Storage

# Do NOT remove - exported for external use
# noinspection PyUnresolvedReferences
from oauth2client.client import UnknownClientSecretsFlowError
# noinspection PyUnresolvedReferences
from oauth2client.clientsecrets import InvalidClientSecretsError
# noinspection PyUnresolvedReferences
from googleapiclient.errors import Error


logger = logging.getLogger(__name__)

try:
    import argparse
except ImportError:
    argparse = None

if argparse:
    flags, _ = argparse.ArgumentParser(parents=[tools.argparser]).parse_known_args()
else:
    flags = None


# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/spreadsheets.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'


# noinspection PyUnresolvedReferences
def _get_credentials(user_agent: str):
    """
    Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    :return: Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    os.makedirs(credential_dir, exist_ok=True)
    credential_path = os.path.join(credential_dir, 'sheets.googleapis.com-python-quickstart.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        logger.warning("No valid credentials, running OAuth2 flow...")
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = user_agent
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        logger.info("Storing credentials to '{}'".format(credential_path))
    else:
        logger.info("Credentials OK.")
    return credentials


def get_sheet_rows(sheet_id: str, sheet_range: str, user_agent: str):
    credentials = _get_credentials(user_agent)
    http = credentials.authorize(httplib2.Http())
    discovery_url = 'https://sheets.googleapis.com/$discovery/rest?version=v4'

    service = discovery.build('sheets', 'v4', http=http, discoveryServiceUrl=discovery_url,
        cache_discovery=False)
    result = service.spreadsheets() \
                    .values()  \
                    .get(spreadsheetId=sheet_id, range=sheet_range) \
                    .execute()
    values = result.get('values', [])

    if values:
        return [row for row in values]  # was this intentional? why not list(values)? -- Lao
    else:
        logger.warning('No data found in spreadsheet: {} @ {}'.format(sheet_range, sheet_id))
        return []
