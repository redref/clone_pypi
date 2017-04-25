#!/bin/bash

DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

pack="${DIR}/packages/"

find "${pack}" -xtype l -exec rm -f {} \;

find "${pack}" -name "desc.json" -mtime +20 | while read i; do rm -rf "$(dirname "${i}")"; done
