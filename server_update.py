import subprocess
import hashlib
import sys
import os

# --- USER VARIABLES ---
# a list of local files to exclude from the archive
ignored_files = []


# the function to move the archive to the server
def upload():
    # files.7z is available in the current folder
    print('Please copy the created archive to your web server and unpack')
    print('You can edit this script to do this automatically!')
    input('--- END ---')


# --- CODE, HOPEFULLY NO NEED TO CHANGE ANYTHING BELOW HERE ---
def md5(fn):
    hash_md5 = hashlib.md5()
    with open(fn, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def cmd(s, ssh=False):
    if ssh:
        s = f'ssh srv "stdbuf -oL {s}"'
    p = subprocess.Popen(s, stdout=subprocess.PIPE)
    for c in iter(p.stdout.readline, b''):
        sys.stdout.buffer.write(c)
        sys.stdout.flush()


# files from this program are always ignored
ignored_files.append(['updater.py', 'updater_package.bat', 'server_updater.py', 'server_package.bat'])
# the generated updater.exe CANNOT be ignored
if 'updater.exe' in ignored_files: ignored_files.remove('updater.exe')

print('Enumerating files...')
files = []
for root, _, fs in os.walk('.'):
    for i in fs:
        files.append(root+'\\'+i)
for i in ignored_files:
    if i in files: files.remove(i)

print('Creating checksums...')
if os.path.exists('checksums.csv'):
    os.remove('checksums.csv')
with open('checksums.csv', mode='w', newline='') as f:
    for i in files:
        v = i.lstrip('.\\')
        f.write(f'{v},{md5(i)}')

print('Creating archive...')
subprocess.Popen('7z -y -mx9 a files.7z .')
for i in ignored_files:
    subprocess.Popen(f'7z d files.7z {i}')
os.remove('checksums.csv')
os.remove('updater.exe')

upload()
