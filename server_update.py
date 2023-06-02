import subprocess
import hashlib
import sys
import os

# --- USER VARIABLES ---
# a list of local files to exclude from the archive
ignored_files = []

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
        print('Moving archive...')
        cmd('mv -f /tmp/files.7z files.7z', ssh=True, sudo=True, cd=root_dir)
        print('Unpacking archive...')
        cmd('7z -aoa x files.7z', ssh=True, sudo=True, cd=root_dir)
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
def md5(fn):
    hash_md5 = hashlib.md5()
    with open(fn, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def cmd(s: str, ssh: bool = False, cd: str = None, sudo: bool = False):
    if ssh:
        s = f'stdbuf -oL {s}'
        if sudo:
            sudocmd = f'echo {passwd} | sudo -S' if passwd else 'sudo'
            s = f'{sudocmd} {s}'
        if cd: s = f'cd {cd}; {s}'
        s = f'ssh {ssh_conn}"{s}"'
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
with open('checksums.csv', mode='w') as f:
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
