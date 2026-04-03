#!/usr/bin/env bash
# exit on error
set -o errexit

# Install required packages
pip install -r requirements.txt

# Gather static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate
