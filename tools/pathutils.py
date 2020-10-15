from pathlib import Path
import sys
import os

def add_application_path():
    app_path = Path(__file__).resolve().parents[1]
    sys.path.append(str(app_path))
    os.chdir(str(app_path))
