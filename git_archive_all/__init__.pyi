from os import PathLike as _PathLike
import logging
from typing import Callable, Collection, ClassVar, Dict, Generator, Iterable, List, Optional, Tuple, Union

PathLike = Union[str, bytes, _PathLike]
PathStr = Union[str, bytes]
CheckGitAttrGen = Generator[Dict[str, bytes], PathStr, None]

def fsdecode(filename: PathLike) -> str: ...

def fsencode(filename: PathLike) -> bytes: ...

def git_fsdecode(filename: bytes) -> str: ...

def git_fsencode(filename: str) -> bytes: ...

def fspath(filename: PathLike, decoder=Callable[[PathLike], str], encoder=Callable[[PathLike], bytes]) -> PathStr: ...

def git_fspath(filename: bytes) -> PathStr: ...

class GitArchiver(object):
    TARFILE_FORMATS: ClassVar[Dict[str, str]]
    ZIPFILE_FORMATS: ClassVar[Tuple[str]]
    LOG: ClassVar[logging.Logger]

    _check_attr_gens: Dict[str, CheckGitAttrGen]
    _ignored_paths_cache: Dict[PathStr, Dict[PathStr, bool]]

    git_version: Optional[Tuple[int]]
    main_repo_abspath: PathStr
    prefix: PathStr
    exclude: bool
    extra: List[PathStr]
    force_sub: bool

    def __init__(self,
                 prefix: PathLike,
                 exclude: bool,
                 force_sub: bool,
                 extra: Iterable[PathLike] = None,
                 main_repo_abspath: PathLike = None,
                 git_version: Tuple[int] = None) -> None: ...

    def create(self,
               output_path: PathLike,
               dry_run: bool,
               output_format: str = None,
               compresslevel: int = None) -> None: ...

    def is_file_excluded(self, repo_abspath: PathStr, repo_file_path: PathStr) -> bool: ...

    def archive_all_files(self, archiver: Callable[[PathStr, PathStr], None]) -> None: ...

    def walk_git_files(self, repo_path: PathStr = None) -> Generator[PathStr, None, None]: ...

    def check_git_attr(self, repo_abspath: PathStr, attrs: Collection[str]) -> CheckGitAttrGen: ...

    def resolve_git_main_repo_abspath(self, abspath: PathLike) -> PathStr: ...

    @classmethod
    def run_git_shell(cls, cmd: str, cwd: PathStr = None) -> bytes: ...

    @classmethod
    def get_git_version(cls) -> Optional[Tuple[int]]: ...

    @classmethod
    def list_repo_files(cls, repo_abspath: PathStr) -> Generator[PathStr, None, None]: ...

    @classmethod
    def list_repo_submodules(cls, repo_abspath: PathStr) -> Generator[PathStr, None, None]: ...
