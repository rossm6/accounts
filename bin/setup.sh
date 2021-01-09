#!/bin/bash
python3 manage.py migrate && python3 manage.py runscript setup && python3 manage.py populate_history --auto