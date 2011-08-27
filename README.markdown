Creates archive from the current state using `git ls-files --cached --full-name --no-empty-directory`. Supports for any level of submodules tree. Files from submodules are extracted using the same command.

*Usage:* git-archive-all.py [-v] [--prefix PREFIX] [--no-exclude] OUTPUT_FILE

*Options:*

  **--version**             show program's version number and exit
  
  **-h, --help**            show this help message and exit
  
  **--prefix=PREFIX**       prepend PREFIX to each filename in the archive
  
  **-v, --verbose**         enable verbose mode

  **--no-exclude**         Dont read .gitattributes files for patterns containing export-ignore attrib

