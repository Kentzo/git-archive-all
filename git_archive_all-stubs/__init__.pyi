from os import PathLike as _PathLike
import logging
from typing import Callable, Collection, ClassVar, Dict, Generator, Iterable, Iterator, List, Optional, Tuple, Union

PathLike = Union[str, bytes, _PathLike]
PathStr = Union[str, bytes]
CheckGitAttrGen = Generator[Dict[str, bytes], PathStr, None]

__version__: str

def fsdecode(filename: PathLike) -> str: ...

def fsencode(filename: PathLike) -> bytes: ...

def git_fsdecode(filename: bytes) -> str: ...

def git_fsencode(filename: str) -> bytes: ...

def fspath(filename: PathLike,
           decoder: Callable[[PathLike], str] = ...,
           encoder: Callable[[PathLike], bytes] = ...) -> PathStr: ...

def git_fspath(filename: bytes) -> PathStr: ...

class GitArchiver(object):
    TARFILE_FORMATS: ClassVar[Dict[str, str]]
    ZIPFILE_FORMATS: ClassVar[Tuple[str, ...]]
    LOG: ClassVar[logging.Logger]

    _check_attr_gens: Dict[str, CheckGitAttrGen]
    _ignored_paths_cache: Dict[PathStr, Dict[PathStr, bool]]

    git_version: Optional[Tuple[int, ...]]
    main_repo_abspath: PathStr
    prefix: PathStr
    exclude: bool
    extra: List[PathStr]
    force_sub: bool
    git_submodule_clear_vars: List[str]

    def __init__(self,
                 prefix: PathLike = '',
                 exclude: bool = True,
                 force_sub: bool = False,
                 extra: Optional[Iterable[PathLike]] = None,
                 main_repo_abspath: Optional[PathLike] = None,
                 git_version: Optional[Tuple[int, ...]] = None) -> None: ...

    def create(self,
               output_path: PathLike,
               dry_run: bool = False,
               output_format: Optional[str] = None,
               compresslevel: Optional[int] = None) -> None: ...

    def is_file_excluded(self, repo_abspath: PathStr, repo_file_path: PathStr) -> bool: ...

    def archive_all_files(self, archiver: Callable[[PathStr, PathStr], None]) -> None: ...

    def walk_git_files(self, repo_path: PathStr = ..., env: Optional[Dict[str, str]] = None) -> Generator[PathStr, None, None]: ...

    def check_git_attr(self, repo_abspath: PathStr, attrs: Collection[str], env: Optional[Dict[str, str]] = None) -> CheckGitAttrGen: ...

    def resolve_git_main_repo_abspath(self, abspath: PathLike) -> PathStr: ...

    @classmethod
    def git_env(cls) -> Dict[str, str]: ...

    @classmethod
    def run_git_shell(cls, cmd: str, cwd: Optional[PathStr] = None, env: Optional[Dict[str, str]] = None) -> bytes: ...

    @classmethod
    def get_git_version(cls) -> Optional[Tuple[int, ...]]: ...

    @classmethod
    def get_git_local_env_vars(cls) -> List[str]: ...

    @classmethod
    def list_repo_files(cls, repo_abspath: PathStr, env: Optional[Dict[str, str]] = None) -> Iterator[PathStr]: ...

    @classmethod
    def list_repo_submodules(cls, repo_abspath: PathStr, env: Optional[Dict[str, str]] = None) -> Iterator[PathStr]: ...

def main(argv: Optional[List[str]] = None) -> int: ...
