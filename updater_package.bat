python -m venv buildenv
buildenv\Scripts\pip install -r .\requirements.txt
buildenv\Scripts\pyinstaller --onefile --workpath .\buildupdater --distpath . .\updater.py
rmdir /s /q buildenv
rmdir /s /q buildupdater
del /q updater.spec
