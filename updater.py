from multiprocessing import Pool, Lock, Manager, cpu_count, freeze_support
from os import makedirs, chdir, walk, remove, startfile, rename, system
from os.path import exists, dirname, abspath, basename
from urllib.request import urlopen, urlretrieve
from multiprocessing.managers import ListProxy
from multiprocessing.pool import ThreadPool
from urllib.error import HTTPError
from hashlib import md5 as hmd5
from functools import partial
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
max_cpu_threads: int = 8
# maximum amount of parallel downloads (bandwidth intensive)
# capped at 32 because the progress bars would break otherwise
# if your server has a restrictive rate limit, decrease this and increase the backoff
max_dl_threads: int = 8
# the base to use for exponential backoff
# wait [base ^ n] seconds before a retry in case of errors
# mostly applies to rate limiting, but also includes other time-based errors
backoff_base: int = 3


# --- CODE, HOPEFULLY NO NEED TO CHANGE ANYTHING BELOW HERE ---
def md5(fn: str) -> str:
    """
    Args:
        fn: The file name to calculate the hash for.
    Returns:
        The calculated MD5 hash.
    """
    hash_md5 = hmd5()
    with open(fn, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def md5mismatch(params) -> str | None:
    """
    Args:
        params: A Sequence (list, tuple...) of the file name to hash and known hash to compare against.
    Returns:
         The filename, if the hash mismatched.
    """
    fn, md = params
    # return file name if mismatched and None otherwise
    # None is falsy and strings are truthy so this still works in an IF
    if exists(fn) and md5(fn) == md:
        return None
    return fn


class TqdmUpTo(tqdm):
    """
    This is for making multithreaded downloads with progress bars.
    """
    def update_to(self, b: int = 1, bsize: int = 1, tsize: int = None, lock: Lock = None) -> None:
        """
        A wrapper to update the total file size if the server reports wrongly.
        Args:
            b: The current block number.
            bsize: The current block size.
            tsize: The total file size.
            lock: The shared mutex lock.
        """
        if tsize is not None:
            self.total = tsize
        # get the mutex
        with lock:
            self.update(b * bsize - self.n)


def download(params, /, *, slots: ListProxy = None, lock: Lock = None) -> bool:
    """
    A function to multithread download with progress bars for each thread.
    Args:
        params: A Sequence (list, tuple...) of the URL to download and file name to save into.
        slots: The shared storage for acquiring a progress bar slot.
            This needs to be a list of bools of at least the same length as the number of threads.
        lock: The shared mutex lock.
    Returns:
        The download success.
    """
    url, fn = params
    # get the mutex
    with lock:
        # find unoccupied slot for the progress bar
        index = slots.index(False)
        # mark the slot as occupied
        slots[index] = True
    # create the directory structure if it does not exist yet
    if d := '\\'.join(fn.split('\\')[:-1]):
        # ignore if another thread already created it after the check
        makedirs(d, exist_ok=True)
    # make a progress bar
    t = TqdmUpTo(
        desc='\033[93m' + fn.split('\\')[-1] + '\033[0m',
        leave=False,
        position=index,
        miniters=1,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
        bar_format='|{bar:50}| {percentage:3.0f}% [{rate_fmt}] {desc}'
    )
    # pass the same lock on every retry
    hook = partial(t.update_to, lock=lock)

    def dl_retry(n: int) -> bool:
        """
        Args:
            n: The current retry number.
        Returns:
            The download success.
        """
        if n > 5: return False
        try:
            # pass the same lock on every retry, on every thread
            urlretrieve(url, filename=fn, reporthook=hook)
            return True
        except HTTPError as e:
            match e.code:
                # 408 Request Timeout
                # 425 Too Early
                # 429 Too Many Requests
                # 504 Gateway Timeout
                case 408 | 425 | 429 | 504:
                    # use exponential backoff for the retries
                    sleep(max(2, backoff_base) ** n)
                    return dl_retry(n + 1)
                # don't handle errors which cannot be fixed by waiting
                case _: return False
    res = dl_retry(1)
    with lock:
        # finish the progress bar
        t.close()
        # mark the progress bar slot as unoccupied
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
    checksums = urlopen(base_url+'checksums.csv')
    remote_files = {
        k: v
        for k, v in (
            # the csv file is file,checksum
            # split by , to get file and checksum in tuple
            j.split(',')
            for j in (
                # remove the newline
                i.decode('UTF-8').rstrip()
                for i in checksums
            )
        )
    }

    print('Checking for new version of updater...')
    if exists('updater.exe.old'):
        remove('updater.exe.old')

    # replace the updater with a newer version if available
    if md5mismatch(('updater.exe', remote_files['updater.exe'])):
        print('Updating self...')
        urlretrieve(base_url+'updater.exe', filename='updater.exe.new')
        rename(self_name, 'updater.exe.old')
        rename('updater.exe.new', 'updater.exe')
        startfile('updater.exe')
        sys.exit()

    # make a directory if it does not exist yet and selfmove
    print('Checking directory structure...')
    if base_dir not in self_path.split('\\')[-1]:
        makedirs(base_dir, exist_ok=True)
        rename(self_name, base_dir + '\\' + self_name)
        startfile(base_dir + '\\' + self_name)
        sys.exit()

    print('Gathering local files...')
    local_files = set()
    for root, _, fs in walk('.'):
        for i in fs:
            local_files.add((root+'\\'+i).lstrip('.\\'))

    print('Comparing checksums (in parallel)...')
    cpu_thread_count = max(1, min(cpu_count() - 1, max_cpu_threads))
    with Pool(cpu_thread_count) as c_pool:
        outdated = [
            i
            for i in list(  # list() -> waits for everything to finish
                tqdm(  # make a progress bar
                    c_pool.imap_unordered(md5mismatch, remote_files.items()),  # hash in parallel
                    total=len(remote_files),
                    bar_format='|{bar:50}| {percentage:3.0f}% [{rate_fmt}] {desc}'
                )
            )
            if i  # ignore the 'None' results
            and i not in ignored_files  # ignore the files chosen by user
        ]
        c_pool.close()
        c_pool.join()

    print(f'Updating files (in parallel)...')
    dl_thread_count = max(1, min(max_dl_threads, 32))
    # create a mutex and shared storage
    lock = Lock()
    manager = Manager()
    # the list MUST be of at least the same length as the amount of threads used
    slots = manager.list(list(False for _ in range(dl_thread_count)))
    outdated_urls = [
        base_url + i.replace('\\', '/')  # replace Windows paths to URLs ( \ -> / )
        for i in outdated
    ]
    # make enough empty lines, this should be unnecessary but just in case
    print('\n' * dl_thread_count + '\033[1A' * dl_thread_count, end='', flush=True)
    with ThreadPool(dl_thread_count) as d_pool:
        r = d_pool.map_async(  # download in parallel
            partial(  # give all threads the same lock and storage
                download,
                lock=lock,
                slots=slots
            ),
            zip(outdated_urls, outdated)  # give changing parameters
        ).get()  # wait until done
        d_pool.close()
        d_pool.join()
    if z := r.count(False):
        print(f'\033[91mFailed to download {z} files\033[0m')

    print('Cleaning up unneeded files...')
    # delete the files on local disk that are not on the server
    # but keep needed files (user configs...)
    for f in set(x for x in local_files if x not in remote_files).difference(needed_files):
        print(f'\033[93m{f}\033[0m no longer required, deleting')
        remove(f)

    # start the main program
    if main_exe:
        startfile(main_exe)
