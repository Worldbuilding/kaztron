#!/usr/bin/env python
from pathutils import *

if __name__ == '__main__':
    add_application_path()

    import sys
    from urllib.parse import urlparse, parse_qs

    import kaztron
    from kaztron.driver.reddit import RedditLoginManager

    rlm = RedditLoginManager()

    try:
        cmd = sys.argv[1].lower()
    except IndexError:
        cmd = None

    if not cmd or cmd == 'login':
        print(f"KazTron {kaztron.__version__}: Reddit authorization tool\n\n"
              "This tool allows you to authorize KazTron on a Reddit account, in order to make use "
              "functionality which requires Reddit access.\n")

        scopes = rlm.get_extension_scopes()

        print('')
        print("Go to this URL to authorize a Reddit account:")
        print(rlm.get_authorization_url(scopes) + "\n")
        print("You will be redirected to a URL (it might fail to load, that's OK).\n")
        response_url = input("Paste the URL here: ")

        response_parts = urlparse(response_url)
        query_vars = parse_qs(response_parts.query)

        rlm.authorize(query_vars['state'][0], query_vars['code'][0])

        print("Done.")
        exit(0)

    elif cmd == 'logout':
        user = None
        try:
            user = sys.argv[2]
        except IndexError:
            print("Must specify a username to log out.")
            exit(2)
        try:
            rlm.logout(user)
        except KeyError:
            print(f"User '{user}' not logged in.")
            exit(3)
        print(f"User '{user}' has been logged out. Note that this app's authorization will remain "
              "on the user's account and must be removed via the Reddit website.")
        exit(0)

    elif cmd == 'clear':
        rlm.clear()
        print(f"All user sessions cleared. Note that this app's authorization will remain "
              "on user accounts and must be removed via the Reddit website.")
        exit(0)

    else:
        print("Usage: ./reddit_auth.py <login|logout <username>|clear>\n")
        exit(0)

