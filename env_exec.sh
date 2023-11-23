#!/bin/bash

# Get app home from symlink
APP_HOME=$(dirname $(readlink -f $0))

# Source env
. $APP_HOME/.venv/bin/activate

# Strip sans from script name and add .py
SCRIPT_NAME=$(basename $0)
SCRIPT_NAME=${SCRIPT_NAME#sans_}.py

NLTK_DATA=$APP_HOME/nltk_data python "$APP_HOME/$SCRIPT_NAME" "$@"