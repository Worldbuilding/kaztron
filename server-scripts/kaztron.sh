#! /usr/bin/env bash

source ./venv/bin/activate
cd app
python3 KazTron.py "$@" --noauth_local_webserver

