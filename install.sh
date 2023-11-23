#!/bin/bash

# Be root
if [ "$(whoami)" != "root" ]; then
    echo "Please run as root"
    exit 1
fi

# Get app home
APP_HOME=$(cd "$(dirname "$0")"; pwd)
echo "App home: $APP_HOME"

UNINSTALL=0

if [ -f "/usr/bin/sans_pdf_to_csv" ]; then
    unlink /usr/bin/sans_pdf_to_csv
    UNINSTALL=1
fi

if [ -f "/usr/bin/sans_create_index" ]; then
    unlink /usr/bin/sans_create_index
    UNINSTALL=1
fi

if [ -f "/usr/bin/sans_unc_pdf" ]; then
    unlink /usr/bin/sans_unc_pdf
    UNINSTALL=1
fi

if [ $UNINSTALL -eq 1 ]; then
    echo "Uninstalled"
    exit 0
fi

apt install -y tesseract-ocr makeindex pdflatex
pip install -f requirements.txt

ln -s $APP_HOME/env_exec.sh /usr/bin/sans_pdf_to_csv
if [ ! -f "/usr/bin/sans_pdf_to_csv" ]; then
    echo "Unable to install"
    exit 0
fi

ln -s $APP_HOME/env_exec.sh /usr/bin/sans_create_index
if [ ! -f "/usr/bin/sans_create_index" ]; then
    echo "Unable to install"
    exit 0
fi

ln -s $APP_HOME/env_exec.sh /usr/bin/sans_unc_pdf

if [ ! -f "/usr/bin/sans_unc_pdf" ]; then
    echo "Unable to install"
    exit 0
fi

# Get app home from symlink
# APP_HOME=$(dirname $(readlink -f $0))

# Source env
. $APP_HOME/.venv/bin/activate
python -c "import nltk; nltk.download('punkt', download_dir='$APP_HOME/nltk_data'); nltk.download('brown', download_dir='$APP_HOME/nltk_data')"

echo "Installed"