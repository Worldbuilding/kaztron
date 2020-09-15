#! /usr/bin/env bash

cd app
tar -czf ../bak/`date --rfc-3339=date`.tar.gz *.json *.sqlite userstats || (echo "Error" && exit)
echo "Done"

