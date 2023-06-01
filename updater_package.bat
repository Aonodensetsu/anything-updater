python -m venv venv
call .\venv\Scripts\activate
pip install -r .\requirements.txt
pyinstaller --onefile --workpath .\buildupdater --distpath . .\updater.py
call deactivate
rmdir /s /q venv
rmdir /s /q buildupdater
del /q updater.spec
