import subprocess
from pathlib import Path
from subprocess import SubprocessError
from typing import Sequence


class MountError(Exception):
    """Error raised when a mount point couldn't be mounted"""


class UnmountError(Exception):
    """Error raised when a mount point couldn't be unmounted"""


class MountPoint:
    path: str
    unmount_force: bool = True
    unmount_lazy: bool = True

    def __init__(self, path: str) -> None:
        self.path = path

    def __str__(self) -> str:
        return self.path

    @property
    def mount_command(self) -> Sequence[str]:
        return ["mount", self.path]

    @property
    def unmount_command(self) -> Sequence[str]:
        command = ["umount"]
        if self.unmount_force:
            command.append("-f")
        if self.unmount_lazy:
            command.append("-l")
        command.append(self.path)
        return command

    def check_is_mounted(self) -> bool:
        """Check if the mount point is already mounted"""
        try:
            return Path(self.path).is_mount()
        except OSError:
            return False

    def mount(self):
        try:
            subprocess.run(self.mount_command, check=True)
        except SubprocessError as error:
            raise MountError() from error

    def unmount(self):
        try:
            subprocess.run(self.unmount_command, check=True)
        except SubprocessError as error:
            raise UnmountError() from error
