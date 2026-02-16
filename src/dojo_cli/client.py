import errno
import mfusepy as fuse
from pathlib import Path
from paramiko.client import AutoAddPolicy, SSHClient
from paramiko.sftp_client import SFTPClient
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
        key_filename = kwargs.get('key_filename', ssh_config['IdentityFile'])
        self.project_path = Path(kwargs.get('project_path', ssh_config['project_path']))

        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(AutoAddPolicy())
        self.ssh.connect(hostname, port, username, key_filename=key_filename)
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

    @fuse.overrides(fuse.Operations)
    def mkdir(self, path: str, mode: int) -> int:
        return self.sftp.mkdir(path, mode)

    @fuse.overrides(fuse.Operations)
    def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
        with self.sftp.open(path) as f:
            f.seek(offset, 0)
            return f.read(size)

    @fuse.overrides(fuse.Operations)
    def readdir(self, path: str, fh: int) -> fuse.ReadDirResult:
        return ['.', '..'] + self.sftp.listdir(path)

    @fuse.overrides(fuse.Operations)
    def readlink(self, path: str) -> str:
        return self.sftp.readlink(path)

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
