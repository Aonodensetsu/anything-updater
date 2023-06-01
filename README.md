# anything-updater
A not-so-simple updater for all manner of things (currently for Windows).

### User-friendly
Run the generated exe and everything will be up-to-date pronto!

### Fast
Parallelized hashing and downloading allows for downloads of only changed files, as fast as your server can handle.  
Does not currently support patch files because of the difficulty associated with maintaining them.

### Small
The codebase is tiny, the created executables weigh no more than a photo, and the [requirements](requirements.txt) border on 'None'.  
You only need Python (pip) and virtualenv installed, and the packaging process will set up and clean after itself.

### Pretty
Uses tqdm to show progress bars for all currently downloading files in real time.

### Developer-friendly
Fill out the variables in [updater.py](updater.py) and run the packaging script, you're done!  
For more automation, include this project in your project files and run the server packaging script.  
For even more automation, fill out the update function in [server_update.py](server_update.py).

### What is checksums.csv?
As the name suggests, the file tracks files and their MD5 hashes, keeping track of changes.  
This means, that you can simply place your program files, the updater, and checksums on any web server for this updater to work.  
This file is automatically created by the server packager, but you can supply it by yourself.  
The format is simply {filename,md5hash} for each tracked file, including the updater itself, [example](checksums-example.csv).  
