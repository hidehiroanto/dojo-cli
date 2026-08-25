"""This file contains the implementation of the RemoteClient class."""

import errno
import os
import stat
from itertools import count
from pathlib import Path
from threading import RLock
from typing import Self

import mfusepy as fuse
from paramiko.channel import Channel
from paramiko.client import RejectPolicy, SSHClient
from paramiko.sftp_client import SFTPClient
from paramiko.sftp_file import SFTPFile

from .config import load_user_config


class RemoteClient(fuse.Operations):
    """
    A simple SFTP filesystem.
    You need to be able to login to remote host without entering a password.
    """

    def __init__(self, **kwargs):
        ssh_config = load_user_config()['ssh']
        hostname = kwargs.get('hostname', ssh_config['HostName'])
        port = kwargs.get('port', ssh_config['Port'])
        username = kwargs.get('username', ssh_config['User'])
        key_filename = (
            Path(kwargs.get('key_filename', ssh_config['IdentityFile']))
            .expanduser()
            .resolve()
        )
        self.project_path = Path(kwargs.get('project_path', ssh_config['project_path']))

        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(RejectPolicy())
        self.ssh.connect(hostname, port, username, key_filename=str(key_filename))
        self._sftp: SFTPClient | None = None
        self.handles: dict[int, SFTPFile] = {}
        self.handle_ids = count(1)
        self.handle_lock = RLock()
        self.use_ns = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.close()

    @property
    def sftp(self) -> SFTPClient:
        if self._sftp is None:
            self._sftp = self.ssh.open_sftp()
            self._sftp.chdir(str(self.project_path))
        return self._sftp

    def close(self):
        global remote_client
        with self.handle_lock:
            handles = list(self.handles.values())
            self.handles.clear()
        for handle in handles:
            handle.close()
        if self._sftp is not None:
            self._sftp.close()
        self.ssh.close()
        if remote_client is self:
            remote_client = None

    @fuse.overrides(fuse.Operations)
    def chmod(self, path: str, mode: int) -> int:
        return self.sftp.chmod(path, mode)

    @fuse.overrides(fuse.Operations)
    def chown(self, path: str, uid: int, gid: int) -> int:
        return self.sftp.chown(path, uid, gid)

    @fuse.overrides(fuse.Operations)
    def create(self, path: str, mode, fi=None) -> int:
        handle = self.sftp.open(path, 'w+')
        registered = False
        try:
            handle.chmod(mode)
            handle_id = self.register_handle(handle)
            registered = True
            return handle_id
        finally:
            if not registered:
                handle.close()

    @fuse.overrides(fuse.Operations)
    def destroy(self, path: str) -> None:
        self.close()

    def get(self, remotepath: str, localpath: str):
        self.sftp.get(remotepath, localpath)

    def get_channel(self) -> Channel:
        return self.ssh.get_transport().open_session()

    @fuse.overrides(fuse.Operations)
    def getattr(self, path: str, fh: int | None = None):
        try:
            stat_result = self.sftp.lstat(path)
            keys = ('st_mode', 'st_uid', 'st_gid', 'st_size', 'st_atime', 'st_mtime')
            stat_dict = {key: getattr(stat_result, key) for key in keys}
            if self.use_ns:
                stat_dict['st_atime'] = int(stat_dict['st_atime']) * 1_000_000_000
                stat_dict['st_mtime'] = int(stat_dict['st_mtime']) * 1_000_000_000
            return stat_dict
        except OSError:
            raise fuse.FuseOSError(errno.ENOENT)

    def getsize(self, path: str) -> int:
        try:
            stat_result = self.sftp.lstat(path)
            if stat.S_ISDIR(stat_result.st_mode):
                return sum(
                    self.getsize(str(Path(path) / child))
                    for child in self.sftp.listdir(path)
                )
            elif stat.S_ISREG(stat_result.st_mode) or stat.S_ISLNK(stat_result.st_mode):
                return stat_result.st_size
            else:
                return 0
        except FileNotFoundError:
            return -1

    @staticmethod
    def mode_for_flags(flags: int) -> str:
        """Convert POSIX open flags to a Paramiko file mode."""
        access_mode = flags & os.O_ACCMODE
        if flags & os.O_APPEND:
            return 'a+' if access_mode == os.O_RDWR else 'a'
        if flags & os.O_TRUNC:
            return 'w+' if access_mode == os.O_RDWR else 'w'
        if access_mode in (os.O_WRONLY, os.O_RDWR):
            return 'r+'
        return 'r'

    def register_handle(self, handle: SFTPFile) -> int:
        """Register an open SFTP file and return its FUSE handle ID."""
        with self.handle_lock:
            handle_id = next(self.handle_ids)
            self.handles[handle_id] = handle
        return handle_id

    @fuse.overrides(fuse.Operations)
    def open(self, path: str, flags: int) -> int:
        return self.register_handle(self.sftp.open(path, self.mode_for_flags(flags)))

    def is_dir(self, path: str) -> bool:
        try:
            return stat.S_ISDIR(self.sftp.stat(path).st_mode)
        except FileNotFoundError:
            return False

    def is_file(self, path: str) -> bool:
        try:
            return stat.S_ISREG(self.sftp.stat(path).st_mode)
        except FileNotFoundError:
            return False

    def listdir(self, path: str) -> list[str]:
        if self.is_dir(path):
            return self.sftp.listdir(path)
        return []

    def makedirs(self, path: str):
        """This is identical to running: mkdir -p <path>"""

        for parent in map(str, Path(path).parents[::-1]):
            if not self.is_dir(parent):
                self.sftp.mkdir(parent, 0o755)
        if not self.is_dir(path):
            self.sftp.mkdir(path, 0o755)

    @fuse.overrides(fuse.Operations)
    def mkdir(self, path: str, mode: int) -> int:
        return self.sftp.mkdir(path, mode)

    def put(self, localpath: str, remotepath: str):
        self.sftp.put(localpath, remotepath)

    @fuse.overrides(fuse.Operations)
    def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
        with self.handle_lock:
            handle = self.handles[fh]
            handle.seek(offset, 0)
            return handle.read(size)

    def read_bytes(self, path: str, limit: int | None = None) -> bytes:
        with self.sftp.open(path) as f:
            return f.read() if limit is None else f.read(limit)

    @fuse.overrides(fuse.Operations)
    def readdir(self, path: str, fh: int) -> fuse.ReadDirResult:
        return ['.', '..'] + self.sftp.listdir(path)

    @fuse.overrides(fuse.Operations)
    def readlink(self, path: str) -> str:
        return self.sftp.readlink(path)

    def remove(self, path: str):
        """This is identical to running: rm -r <path>"""

        try:
            stat_result = self.sftp.lstat(path)
        except FileNotFoundError:
            return
        if stat.S_ISDIR(stat_result.st_mode):
            for child in self.sftp.listdir(path):
                self.remove(str(Path(path) / child))
            self.sftp.rmdir(path)
        else:
            self.sftp.unlink(path)

    @fuse.overrides(fuse.Operations)
    def rename(self, old: str, new: str) -> int:
        return self.sftp.rename(old, new)

    @fuse.overrides(fuse.Operations)
    def rmdir(self, path: str) -> int:
        return self.sftp.rmdir(path)

    @fuse.overrides(fuse.Operations)
    def symlink(self, target: str, source: str) -> int:
        return self.sftp.symlink(source, target)

    @fuse.overrides(fuse.Operations)
    def truncate(self, path: str, length: int, fh: int | None = None) -> int:
        if fh is None:
            self.sftp.truncate(path, length)
        else:
            with self.handle_lock:
                self.handles[fh].truncate(length)
        return 0

    @fuse.overrides(fuse.Operations)
    def unlink(self, path: str) -> int:
        return self.sftp.unlink(path)

    @fuse.overrides(fuse.Operations)
    def utimens(self, path: str, times: tuple[int, int] | None = None) -> int:
        if self.use_ns and times:
            times = (times[0] // 1_000_000_000, times[1] // 1_000_000_000)
        return self.sftp.utime(path, times)

    @fuse.overrides(fuse.Operations)
    def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
        with self.handle_lock:
            handle = self.handles[fh]
            handle.seek(offset, 0)
            handle.write(data)
        return len(data)

    @fuse.overrides(fuse.Operations)
    def flush(self, path: str, fh: int) -> int:
        with self.handle_lock:
            self.handles[fh].flush()
        return 0

    @fuse.overrides(fuse.Operations)
    def fsync(self, path: str, datasync: int, fh: int) -> int:
        return self.flush(path, fh)

    @fuse.overrides(fuse.Operations)
    def release(self, path: str, fh: int) -> int:
        with self.handle_lock:
            handle = self.handles.pop(fh)
        handle.close()
        return 0

    def write_bytes(self, path: str, data: bytes) -> int:
        with self.sftp.open(path, 'w') as f:
            f.write(data)
            return len(data)


remote_client = None


def get_remote_client() -> RemoteClient:
    global remote_client
    if not remote_client:
        remote_client = RemoteClient()
    return remote_client
