from urllib.error import HTTPError
from urllib.request import urlopen
from time import sleep
from tqdm import tqdm
import subprocess
import hashlib
import sys
import os

# --- USER VARIABLES ---
# the remote folder where program files are located
# http(s) and the trailing slash are REQUIRED
# the checksums.csv and updater.exe files need to be available at this location
base_url: str = 'https://example.com/'
# a list of local files to exclude from the archive
ignored_files = []
# only adds changed files to the archive, saving a lot of time
# you might need to change this to True occasionally if the process failed for some reason and corrupted files
include_all = False

# Upload Variables
# this assumes a Linux server environment, if you use a Windows web server, you'll need to adjust the upload function
# enable the function
enabled = False
# the server IP / ssh alias to copy to
ssh_conn = ''
# the directory on the server to unpack into
root_dir = ''
# sudo password, leave empty if you have passwordless configured
passwd = ''


# the function to move the archive to the server
def upload():
    if enabled:
        print('Copying archive...')
        cmd(f'scp files.7z {ssh_conn}:/tmp/files.7z')
        os.remove('files.7z')
        # old files are kept on the server if updating partially
        # clients will not get them, because they are not tracked in the checksums file
        # this ensures cleaning will be done at least initially and after corruption occurs
        if include_all:
            cmd('rm -rf *', ssh=True, sudo=True, cd=root_dir)
        print('Moving archive...')
        cmd('mv -f /tmp/files.7z files.7z', ssh=True, sudo=True, cd=root_dir)
        print('Unpacking archive...')
        cmd('7z -aoa x files.7z', ssh=True, sudo=True, cd=root_dir)
        # wait until the file is released
        sleep(1)
        print('Setting permissions...')
        cmd('rm files.7z', ssh=True, sudo=True, cd=root_dir)
        cmd('find . -type d -exec chmod +rx {} \\;', ssh=True, sudo=True, cd=root_dir)
        cmd('find . -type f -exec chmod +r {} \\;', ssh=True, sudo=True, cd=root_dir)
        cmd('chown -R www-data:www-data .', ssh=True, sudo=True, cd=root_dir)
    else:
        print('Please copy the created archive to your web server and unpack')
        print('You can edit this script to do this automatically!')
        input('--- END ---')


# --- CODE, HOPEFULLY NO NEED TO CHANGE ANYTHING BELOW HERE ---
UPD = 'updater.exe'


def md5(fn):
    hash_md5 = hashlib.md5()
    with open(fn, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def cmd(s: str, ssh: bool = False, cd: str = None, sudo: bool = False, out: bool = True):
    if ssh:
        s = f'stdbuf -oL {s}'
        if sudo:
            sudocmd = f'echo {passwd} | sudo -S' if passwd else 'sudo'
            s = f'{sudocmd} {s}'
        if cd: s = f'cd {cd}; {s}'
        s = f'ssh {ssh_conn} "{s}"'
    if out:
        p = subprocess.Popen(s, stdout=subprocess.PIPE)
        for c in iter(p.stdout.readline, b''):
            sys.stdout.buffer.write(c)
            sys.stdout.flush()
    else:
        subprocess.Popen(s, stdout=subprocess.DEVNULL).communicate()


# files from this program are always ignored
ignored_files.append(['updater.py', 'updater_package.bat', 'server_updater.py', 'server_package.bat'])

print('Enumerating files...')
if os.path.exists('checksums.csv'):
    os.remove('checksums.csv')

files = []
for root, _, fs in os.walk('.'):
    for i in fs:
        if i in ignored_files: continue
        files.append((root + '\\' + i).removeprefix('.\\'))

print('Fetching remote checksums to compare...')
# get {file: checksum} from the server
try:
    # checksums might not exist on server if this is an initial run
    remote_files = {
        k: v
        for k, v in (
            # the csv file is file,checksum
            # split by , to get file and checksum in tuple
            j.split(',')
            for j in (
                # remove the newline
                i.decode('UTF-8').strip()
                for i in urlopen(base_url+'checksums.csv')
            )
        )
    }
except HTTPError:
    remote_files = {}

print('Creating local checksums...')
local_files = {
    f: md5(f)
    for f in files
}

# keep the updater hash if unchanged
if UPD not in local_files.keys():
    try:
        local_files[UPD] = remote_files[UPD]
    except KeyError:
        print('Updater not in local files and not in remote checksums.csv')
        print('Please run the server updater with include_all at least once')
        input('--- END ---')
        sys.exit()

with open('checksums.csv', mode='w', newline='') as f:
    for k, v in local_files.items():
        f.write(f'{k},{v}\n')

# get the list of changed files
mismatched = [
    fn
    for fn, md5 in local_files.items()
    if fn not in ignored_files
    and (
        fn not in remote_files
        or md5 != remote_files[fn]
    )
]

if include_all:
    mismatched = list(local_files.keys())

if not len(mismatched):
    # no files changed, don't update the server
    print('No files changed')
    os.remove('checksums.csv')
    if os.path.exists(UPD):
        os.remove(UPD)
    sys.exit()

# always include the latest checksums
mismatched.append('checksums.csv')

print('Creating archive...')
for i in tqdm(mismatched):
    cmd(f'7z -y -mx9 a files.7z {i}', out=False)
os.remove('checksums.csv')
if os.path.exists(UPD):
    os.remove(UPD)

upload()
