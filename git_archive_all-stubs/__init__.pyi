from collections.abc import Callable, Collection, Generator, Iterable, Iterator, Mapping
from os import PathLike
import logging
from typing import ClassVar

_PathLike = str | bytes | PathLike[str] | PathLike[bytes]
_CheckGitAttrGen = Generator[dict[str, bytes], _PathLike, None]

__version__: str

def fsdecode(filename: _PathLike) -> str: ...

def fsencode(filename: _PathLike) -> bytes: ...

def git_fsdecode(filename: bytes) -> str: ...

def git_fsencode(filename: str) -> bytes: ...

def fspath(filename: _PathLike) -> str: ...

class GitArchiver:
    TARFILE_FORMATS: ClassVar[dict[str, str]]
    ZIPFILE_FORMATS: ClassVar[tuple[str, ...]]
    LOG: ClassVar[logging.Logger]

    _check_attr_gens: dict[str, _CheckGitAttrGen]
    _ignored_paths_cache: dict[str, dict[str, bool]]

    git_version: tuple[int, ...] | None
    main_repo_abspath: str
    prefix: str
    exclude: bool
    extra: list[str]
    force_sub: bool
    git_submodule_clear_vars: list[str]

    def __init__(self,
                 prefix: _PathLike = '',
                 exclude: bool = True,
                 force_sub: bool = False,
                 extra: Iterable[_PathLike] | None = None,
                 main_repo_abspath: _PathLike | None = None,
                 git_version: tuple[int, ...] | None = None) -> None: ...

    def create(self,
               output_path: _PathLike,
               dry_run: bool = False,
               output_format: str | None = None,
               compresslevel: int | None = None) -> None: ...

    def is_file_excluded(self, repo_abspath: str, repo_file_path: str) -> bool: ...

    def archive_all_files(self, archiver: Callable[[str, str], None]) -> None: ...

    def walk_git_files(self, repo_path: str = '', env: Mapping[str, str] | None = None) -> Generator[str, None, None]: ...

    def check_git_attr(self, repo_abspath: str, attrs: Collection[str], env: Mapping[str, str] | None = None) -> _CheckGitAttrGen: ...

    def resolve_git_main_repo_abspath(self, abspath: _PathLike) -> str: ...

    @classmethod
    def git_env(cls) -> dict[str, str]: ...

    @classmethod
    def run_git_shell(cls, cmd: str, cwd: _PathLike | None = None, env: Mapping[str, str] | None = None) -> bytes: ...

    @classmethod
    def get_git_version(cls) -> tuple[int, ...] | None: ...

    @classmethod
    def get_git_local_env_vars(cls) -> list[str]: ...

    @classmethod
    def list_repo_files(cls, repo_abspath: str, env: Mapping[str, str] | None = None) -> Iterator[str]: ...

    @classmethod
    def list_repo_submodules(cls, repo_abspath: str, env: Mapping[str, str] | None = None) -> Iterator[str]: ...

def main(argv: list[str] | None = None) -> int: ...
