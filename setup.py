import re
import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand

# Parse the version from the file.
verstrline = open('git_archive_all.py', "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in git_archive_all.py")


class PyTest(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to pytest")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ""

    def run_tests(self):
        import shlex

        # import here, cause outside the eggs aren't loaded
        import pytest

        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


setup(
    version=verstr,
    py_modules=['git_archive_all'],
    entry_points={'console_scripts': 'git-archive-all=git_archive_all:main'},
    cmdclass={"test": PyTest},
)
