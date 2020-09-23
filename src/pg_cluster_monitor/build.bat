rmdir /Q /S dist
copy config.ini dist\config.ini
pip install flake8 psycopg2 urllib3 coloredlogs pywin32 servicemanager pyinstaller
pyinstaller.exe -F main.py
rem pyinstaller.exe -F --hidden-import=win32timezone windows_service.py
