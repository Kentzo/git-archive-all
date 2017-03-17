import re
from setuptools import setup

# Parse the version from the file.
verstrline = open('git_archive_all.py', "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in git_archive_all.py")

setup(
    version=verstr,
    py_modules=['git_archive_all'],
    entry_points={'console_scripts': 'git-archive-all=git_archive_all:main'}
)
