#! /usr/bin/env python3
from collections import OrderedDict
import csv
import discord

from pathutils import *


def import_file(filename, dry_run, verbose, check_matches):
    """ Import a CSV file. Params correspond to command-line arguments. """
    success = True

    fieldnames = ['discord_id', 'title', 'genre', 'subgenre', 'type', 'pitch', 'description', 'url']
    with open(filename, 'r', newline='', encoding='utf-8') as f:
        csvr = csv.DictReader(f, fieldnames=fieldnames)
        print("Importing {}...".format(filename))
        for row_dict in csvr:
            try:
                with query.transaction():
                    import_project(row_dict, dry_run, verbose, check_matches)
            except Exception as ee:
                print("[ERROR]", tb_log_str(ee))
                success = False
                continue
            finally:
                print("")
    return success


def import_project(row_dict, dry_run, verbose, check_matches):
    """
    Import a single project from a CSV row (via DictReader). Key names must correspond to the
    :cls:`.kaztron.cog.projects.model.Project` attributes, or ``'discord_id'`` for the user's
    (author's) discord ID.

    Flags correspond to command-line flags.
    """

    proj_dict = process_project_row(row_dict)
    print_project(proj_dict, verbose)
    if dry_run:
        return False
    if not check_matches or not check_match(proj_dict):
        project = query.add_project(proj_dict)
        print("Project added.")
        if verbose:
            print(repr(project))
    else:
        print("Skipping project: duplicate found.")
    return True


def process_project_row(row_dict) -> dict:
    """
    Process a project row. Pre-process and validate all fields, and look up the user in the database
    based on the discord_id field.
    """
    proj_dict = OrderedDict()

    if None in row_dict:  # too many columns
        raise ValueError("CSV file row contains too many columns (title={!r})"
            .format(row_dict['title']))

    for key, val in row_dict.items():
        if key == 'discord_id':
            member_obj = discord.Object(extract_user_id(row_dict['discord_id']))
            user = query.get_or_make_user(member_obj)
            proj_dict['user'] = user
        else:
            proj_dict[key] = wizard.validators[key](val.strip()) if val else None
    proj_dict.user_id = proj_dict['user'].discord_id
    return proj_dict


def print_project(proj_dict, verbose):
    print("Importing project...")
    if verbose:
        for key, val in proj_dict.items():
            print(key, "=", repr(val))
    else:
        print("Title:", proj_dict['title'])


def check_match(proj_dict):
    """ Check if a project by the same title and for the same user already exists. """
    res = query.query_projects(user=proj_dict['user'], title=proj_dict['title'])
    return len(res) > 0


if __name__ == '__main__':
    import os
    import sys
    import argparse
    import textwrap

    try:
        width = int(os.environ['COLUMNS'])
    except (KeyError, ValueError):
        width = 80
    width -= 2

    comma_remark = "If it contains any commas, enclose in double quotes."

    description = textwrap.fill(
        "Import new projects for KazTron from a CSV file. This script will always ADD new projects "
        "and cannot update old projects. However, it will refuse to add a project if an exact "
        "user+title match already exists (unless --no-check is passed).",
        width=width
    )
    epilogue = '\n\n'.join(
        textwrap.fill(t, width=width) for t in [
            "The CSV file has the following column structure:",
            "User ID, Title, Genre, Subgenre, Project Type, Elevator Pitch, Description, URL"
        ]
    )
    epilogue += '\n\n' + '\n'.join(
        textwrap.fill(t, width=width, subsequent_indent='  ') for t in [
            "* User ID: The numerical Discord User ID",
            "* Title: Project title. " + comma_remark,
            "* Genre: Genre name. Must already exist in the Projects module.",
            "* Subgenre: Optional. Sub-genre or more specific genre descriptor. " + comma_remark,
            "* Project Type: Project type. Must already exist in the Projects module.",
            "* Elevator pitch: A max 70 word elevator pitch. Enclose in double quotes.",
            "* Description: Optional. A longer description, max 1000 characters. "
                "Enclose in double quotes.",
            "* URL: Optional. URL to a website with more project info. " + comma_remark,
        ]
    )
    epilogue += '\n\n' + textwrap.fill(
        "Optional fields should be left blank if unused.", width=width
    )
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilogue,
        allow_abbrev=True,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('file', help="File to import.")
    parser.add_argument('--dry-run', '-s', action='store_true',
        help="If true, read file without writing to database. This will validate the CSV file, but "
             "will NOT validate that the data can be inserted into the database (e.g. genre names, "
             "length limits). Use this with --verbose in order to show the extracted data.")
    parser.add_argument('--verbose', '-v', action='store_true',
        help='Show each project added to the database.')
    parser.add_argument('--allow-duplicates', '-d', action='store_true',
        help='Do not check if an existing project exists before adding. If not specified, this '
             'script will skip any user+title matches already in the database.')
    args = parser.parse_args()
    args.file = str(Path(args.file).resolve())

    add_application_path()
    from kaztron.cog.projects import query, wizard
    from kaztron.utils.discord import extract_user_id
    from kaztron.utils.logging import tb_log_str, exc_log_str

    query.init_db()

    try:
        r = import_file(args.file, args.dry_run, args.verbose, not args.allow_duplicates)
    except OSError as e:
        print("[ERROR]", exc_log_str(e))
        sys.exit(1)
    except Exception as e:
        print("[ERROR]", tb_log_str(e))
        sys.exit(1)
    sys.exit(0 if r else 1)
