Creates archive from the current state using `git ls-files --cached --full-name --no-empty-directory`. Supports for any level of submodules tree. Files from submodules are extracted using the same command.

*Usage:* git-archive-all.py --output OUTPUTFILE [--format FORMAT] [-v] [--prefix PREFIX]

*Options:*

  **--version**             show program's version number and exit
  
  **-h, --help**            show this help message and exit
  
  **--format=FORMAT**       format of the resulting archive: tar or zip. The default output format is tar
  
  **--prefix=PREFIX**       prepend PREFIX to each filename in the archive
  
  **-o OUTPUT_FILE, --output=OUTPUT_FILE** Output file
  
  **-v, --verbose**         enabel verbose mode
