from collections.abc import Callable, Collection, Generator, Iterable, Iterator, Mapping, Sequence
import logging
from os import PathLike
from typing import Any, ClassVar, TypeAlias

_PathLike: TypeAlias = str | bytes | PathLike[str] | PathLike[bytes]
# Yields None when primed with next(), then attributes for each path sent.
_CheckGitAttrGen: TypeAlias = Generator[dict[str, bytes] | None, _PathLike, None]

__version__: str

def git_fsdecode(filename: bytes) -> str: ...

def git_fsencode(filename: str) -> bytes: ...

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
               compresslevel: int | None = None,
               *,
               archive_kwargs: Mapping[str, Any] | None = None) -> None: ...

    def is_file_excluded(self, repo_abspath: str, file_repopath: str) -> bool: ...

    def archive_all_files(self, archiver: Callable[[str, str], object]) -> None: ...

    def walk_git_files(self, repo_mainpath: str = '', env: Mapping[str, str] | None = None) -> Generator[str, None, None]: ...

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

def main(argv: Sequence[str] | None = None) -> int: ...
