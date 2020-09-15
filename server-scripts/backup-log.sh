#! /usr/bin/env bash

cd KazTron
gzip kaztron.log
mv kaztron.log.gz ../logs-bak/$(date -Idate).log.gz

