from os import makedirs, chdir, walk, remove, startfile, rename, system, stat
from multiprocessing import Lock, Manager, cpu_count, freeze_support
from os.path import exists, dirname, abspath, basename
from multiprocessing.pool import ThreadPool, Pool
from urllib.request import urlopen, urlretrieve
from multiprocessing.managers import ListProxy
from urllib.error import HTTPError
from hashlib import md5 as hmd5
from functools import partial
from typing import Optional
from time import sleep
from tqdm import tqdm
import sys
system('')


# --- USER VARIABLES ---
# the remote folder where program files are located
# http(s) and the trailing slash are REQUIRED
# the checksums.csv and updater.exe files need to be available at this location
base_url: str = 'https://example.com/'
# the folder name that will be created for the program
base_dir: str = 'example'
# the exe name to run after updated, set to empty to not start anything
main_exe: str = ''
# a list of local files to never update
ignored_files: list[str] = []
# a list of local files to never delete
needed_files: list[str] = ignored_files
# maximum amount of checksums calculated at once (cpu intensive)
# capped by the amount of CPU cores
max_hs_threads: int = 8
# maximum amount of parallel downloads (bandwidth intensive)
# capped at 32 because the progress bars would break otherwise
# if your server has a restrictive rate limit, decrease this and increase the backoff
max_dl_threads: int = 8
# the base to use for exponential backoff
# wait [base ^ n] seconds before a retry in case of errors
# mostly applies to rate limiting, but also includes other time-based errors
backoff_base: int = 3
# disables selfupdate, autostart and enables some additional logging
debug = False


# --- CODE, HOPEFULLY NO NEED TO CHANGE ANYTHING BELOW HERE ---
def parallel_hash(params, /, *, slots: ListProxy, lock: Lock) -> Optional[str]:
    """
    Args:
        params: A Sequence of: file to check and known file hash.
        slots: A shared list of progress bar slots.
        lock: A shared mutex.
    Returns:
         The filename if the hash mismatched, None otherwise.
    """
    fn, md = params
    if exists(fn):
        with lock:
            # find unoccupied slot for the progress bar
            index = slots.index(False)
            # mark the slot as occupied
            slots[index] = True
        # make the progress bar
        t = tqdm(
            desc='\033[93m' + fn.split('\\')[-1] + '\033[0m',
            leave=False,
            position=index,
            miniters=1,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            bar_format='|{bar:50}| {percentage:3.0f}% [{rate_fmt}] {desc}',
            total=stat(fn).st_size
        )
        # calculate the hash
        md5_hash = hmd5()
        with open(fn, 'rb') as f:
            ncalls = 0
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
                if not ncalls:  # only update the bar every 10 iterats, slows progress a lot
                    with lock: t.update(40960)
                ncalls += 1
                ncalls %= 10
        with lock:
            # finish the progress bar
            t.close()
            # mark the progress bar slot as unoccupied
            slots[index] = False
        # return file name if mismatched and None otherwise
        # None is falsy and strings are truthy so this still works in an IF
        if md5_hash.hexdigest() == md: return None
    return fn


def parallel_dl(params, /, *, slots: ListProxy, lock: Lock) -> Optional[str]:
    """
    A function to multithread download with progress bars for each thread.
    Args:
        params: A Sequence of: file name to save into and URL to download.
        slots: A shared list of progress bar slots.
        lock: A shared mutex.
    Returns:
        The filename, if did not succeed.
    """
    fn, url = params
    with lock:
        index = slots.index(False)
        slots[index] = True
    # create the directory structure if it does not exist yet
    if d := '\\'.join(fn.split('\\')[:-1]): makedirs(d, exist_ok=True)
    # make a progress bar
    t = tqdm(
        desc='\033[93m' + fn.split('\\')[-1] + '\033[0m',
        leave=False,
        position=index,
        miniters=1,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
        bar_format='|{bar:50}| {percentage:3.0f}% [{rate_fmt}] {desc}'
    )

    ncalls = 0

    def hook(b: int = 1, bsize: int = 1, tsize: int = None) -> None:
        nonlocal ncalls
        ncalls += 1
        ncalls %= 30
        if not ncalls:  # only update bar every 30 iters, slows progress a lot
            if tsize is not None: t.total = tsize
            with lock: t.update(b * bsize - t.n)

    def dl_try(n: int) -> Optional[str]:
        """
        Args:
            n: The current retry number.
        Returns:
            The filename, if did not succeed.
        """
        if n > 5: return fn
        try:
            urlretrieve(url, filename=fn, reporthook=hook)
            return None
        except HTTPError as e:
            match e.code:
                # 408 Request Timeout
                # 425 Too Early
                # 429 Too Many Requests
                # 504 Gateway Timeout
                case 408 | 425 | 429 | 504:
                    # use exponential backoff for the retries
                    sleep(max(2, backoff_base) ** n)
                    return dl_try(n + 1)
                # don't handle errors which cannot be fixed by waiting
                case _:
                    return fn
    res = dl_try(1)
    with lock:
        t.close()
        slots[index] = False
    return res


if __name__ == '__main__':
    # mark this as the main thread of an executable
    freeze_support()

    # check if this is an executable file
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # get the executable path
        self_path = dirname(abspath(sys.executable))
        self_name = basename(sys.executable)
    else:
        print('Only run the executable file created from this script')
        sys.exit()
    chdir(self_path)

    # never delete the updater
    needed_files.append('updater.exe')

    print('Fetching list of latest files...')
    # get {file: checksum} from the server
    remote_files = {
        k: v
        for k, v in (
            # the csv file is file,checksum
            # split by , to get file and checksum in tuple
            j.split(',')
            for j in (
                # remove whitespace
                i.decode('UTF-8').strip()
                for i in urlopen(base_url+'checksums.csv')
            )
        )
    }

    print('Checking for new version of updater...')
    if exists('updater.exe.old'):
        remove('updater.exe.old')

    # replace the updater with a newer version if available
    if not debug:
        # calculate without using parallel function
        md5_hash = hmd5()
        with open('updater.exe', 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
        if not md5_hash.hexdigest() == remote_files['updater.exe']:
            print('Updating self...')
            urlretrieve(base_url+'updater.exe', filename='updater.exe.new')
            rename(self_name, 'updater.exe.old')
            rename('updater.exe.new', 'updater.exe')
            startfile('updater.exe')
            sys.exit()

    # make base_dir if it does not exist yet and move updater
    print('Checking directory structure...')
    if base_dir not in self_path.split('\\')[-1]:
        makedirs(base_dir, exist_ok=True)
        rename(self_name, base_dir + '\\' + self_name)
        startfile(base_dir + '\\' + self_name)
        sys.exit()

    print('Gathering local files...')
    local_files = set()
    for root, _, fs in walk('.'):
        for i in fs: local_files.add((root+'\\'+i).removeprefix('.\\'))

    hs_threads = max(1, min(cpu_count() - 1, max_hs_threads))
    dl_threads = max(1, min(max_dl_threads, 32))
    # create shared storage for threads
    manager = Manager()
    lock = manager.Lock()
    slots = manager.list(list(False for _ in range(max(hs_threads, dl_threads))))

    print('Comparing checksums (in parallel)...')
    with Pool(hs_threads) as hs_pool:
        outdated = [
            i
            for i in hs_pool.imap_unordered(
                partial(
                    parallel_hash,
                    slots=slots,
                    lock=lock
                ),
                remote_files.items()
            )
            if i  # ignore "None" which marks success
            and i not in ignored_files
        ]
    if debug: print(f'outdated: {outdated}')

    # the threads close too quickly to go back to the beginning of line, go back manually
    print('\rUpdating files (in parallel)...')
    outdated_urls = [
        base_url + i.replace('\\', '/')  # replace Windows paths to URLs ( \ -> / )
        for i in outdated
    ]
    with ThreadPool(dl_threads) as dl_pool:
        failed = [
            i
            for i in dl_pool.imap_unordered(
                partial(
                    parallel_dl,
                    slots=slots,
                    lock=lock
                ),
                zip(outdated, outdated_urls)
            )
            if i  # ignore "None" which marks success
        ]

    if len(failed):
        print(f'\033[91mFailed\033[0m to download {len(failed)} files, please try again later')
        if debug:
            for i in failed: print(f'Failed: {i}')
        sleep(5)

    print('Cleaning up unneeded files...')
    # delete the files on local disk that are not on the server
    # but keep needed files (user configs...)
    for f in set(
        i
        for i in local_files
        if i not in remote_files
    ).difference(needed_files):
        remove(f)

    # start the main program
    if main_exe and not failed and not debug: startfile(main_exe)
