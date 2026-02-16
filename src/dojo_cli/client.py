import errno
import mfusepy as fuse
from pathlib import Path
from paramiko.channel import Channel
from paramiko.client import AutoAddPolicy, SSHClient
from paramiko.sftp_client import SFTPClient
import stat
from typing import Optional

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
        key_filename = Path(kwargs.get('key_filename', ssh_config['IdentityFile'])).expanduser().resolve()
        self.project_path = Path(kwargs.get('project_path', ssh_config['project_path']))

        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(AutoAddPolicy())
        self.ssh.connect(hostname, port, username, key_filename=str(key_filename))
        self.sftp: SFTPClient = self.ssh.open_sftp()
        self.sftp.chdir(str(self.project_path))
        self.use_ns = True

    @fuse.overrides(fuse.Operations)
    def chmod(self, path: str, mode: int) -> int:
        return self.sftp.chmod(path, mode)

    @fuse.overrides(fuse.Operations)
    def chown(self, path: str, uid: int, gid: int) -> int:
        return self.sftp.chown(path, uid, gid)

    @fuse.overrides(fuse.Operations)
    def create(self, path: str, mode, fi=None) -> int:
        with self.sftp.open(path, 'w') as f:
            f.chmod(mode)
            return 0

    @fuse.overrides(fuse.Operations)
    def destroy(self, path: str) -> None:
        self.sftp.close()
        self.ssh.close()

    def get(self, remotepath: str, localpath: str):
        self.sftp.get(remotepath, localpath)

    def get_channel(self) -> Channel:
        return self.ssh.get_transport().open_session()

    @fuse.overrides(fuse.Operations)
    def getattr(self, path: str, fh: Optional[int] = None):
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
            stat_result = self.sftp.stat(path)
            if stat.S_ISDIR(stat_result.st_mode):
                return sum(self.getsize(str(Path(path) / child)) for child in self.sftp.listdir(path))
            elif stat.S_ISREG(stat_result.st_mode):
                return stat_result.st_size
            else:
                return -1
        except FileNotFoundError:
            return -1

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
        """This is identical to running 'mkdir -p <path>' remotely."""

        for parent in map(str, Path(path).parents[::-1]):
            if not self.is_dir(parent):
                self.mkdir(parent, 0o755)
        if not self.is_dir(path):
            self.mkdir(path, 0o755)

    @fuse.overrides(fuse.Operations)
    def mkdir(self, path: str, mode: int) -> int:
        return self.sftp.mkdir(path, mode)

    def put(self, localpath: str, remotepath: str):
        self.sftp.put(localpath, remotepath)

    @fuse.overrides(fuse.Operations)
    def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
        with self.sftp.open(path) as f:
            f.seek(offset, 0)
            return f.read(size)

    def read_bytes(self, path: str) -> bytes:
        with get_remote_client().sftp.open(path) as f:
            return f.read()

    @fuse.overrides(fuse.Operations)
    def readdir(self, path: str, fh: int) -> fuse.ReadDirResult:
        return ['.', '..'] + self.sftp.listdir(path)

    @fuse.overrides(fuse.Operations)
    def readlink(self, path: str) -> str:
        return self.sftp.readlink(path)

    def remove(self, path: str):
        """This is identical to running 'rm -r <path>' remotely."""

        if self.is_dir(path):
            for child in self.listdir(path):
                child_path = str(Path(path) / child)
                if self.is_dir(child_path):
                    self.remove(child_path)
                else:
                    self.unlink(child_path)
            self.rmdir(path)
        elif self.is_file(path):
            self.unlink(path)

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
    def truncate(self, path: str, length: int, fh: Optional[int] = None) -> int:
        return self.sftp.truncate(path, length)

    @fuse.overrides(fuse.Operations)
    def unlink(self, path: str) -> int:
        return self.sftp.unlink(path)

    @fuse.overrides(fuse.Operations)
    def utimens(self, path: str, times: Optional[tuple[int, int]] = None) -> int:
        if self.use_ns and times:
            times = (times[0] // 1_000_000_000, times[1] // 1_000_000_000)
        return self.sftp.utime(path, times)

    @fuse.overrides(fuse.Operations)
    def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
        with self.sftp.open(path, 'r+') as f:
            f.seek(offset, 0)
            f.write(data)
            return len(data)

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
