from setuptools import setup
# you may need setuptools instead of distutils

setup(
    name='git-archive-all',
    version='1.7',
    description='wrapper for git-archive that archives a git superproject and its submodules',
    author='Ilya Kulakov',
    url='https://github.com/Kentzo/git-archive-all',
    scripts = ['git-archive-all'],
)
