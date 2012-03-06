Creates archive from the current state using `git ls-files --cached --full-name --no-empty-directory`. Supports for any level of submodules tree. Files from submodules are extracted using the same command.

*License:* MIT

*Usage:* git-archive-all [-v] [--prefix PREFIX] [--no-exclude] [--force-submodules] OUTPUT_FILE

*Options:*

  **--version**             show program's version number and exit
  
  **-h, --help**            show this help message and exit
  
  **--prefix=PREFIX**       prepend PREFIX to each filename in the archive

  **--force-submodules**    Force a git submodule init && git submodule update at each level before iterating submodules
  
  **-v, --verbose**         enable verbose mode

  **--no-exclude**         Dont read .gitattributes files for patterns containing export-ignore attrib
