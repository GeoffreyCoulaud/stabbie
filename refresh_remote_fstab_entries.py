#!/bin/python

import re
import logging
import socket
import subprocess
import sys
from pathlib import Path
from subprocess import SubprocessError
from typing import NamedTuple, Sequence
from functools import lru_cache


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
        """
        Mount the mount points already described in /etc/fstab

        :raises SubprocessError: if an error happens during the `mount` command
        """
        try:
            subprocess.run(self.mount_command, check=True)
        except SubprocessError as error:
            raise MountError() from error

    def unmount(self):
        """
        Unmount the given mount points

        :raises SubprocessError: if an error happens during the `umount` command
        """
        try:
            subprocess.run(self.unmount_command, check=True)
        except SubprocessError as error:
            raise UnmountError() from error


class Service:
    host: str
    port: int

    check_timeout_seconds: int = 3

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"

    def __eq__(self, other: "Service") -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    @lru_cache(maxsize=1)
    def check_is_connectable(self) -> bool:
        """
        Check if the service is connectable to

        Cached because the program is short lived and a service is assumed to
        not change state during a run.
        """
        try:
            with socket.create_connection(
                (self.host, self.port), self.check_timeout_seconds, all_errors=True
            ) as _server_socket:
                return True
        except ExceptionGroup:
            return False


class FstabEntry(NamedTuple):
    name: str
    mount_point: MountPoint
    fs_type: str
    mount_options: list[str]
    dump_frequency: int = 0
    fsck_pass_number: int = 0

    def __str__(self) -> str:
        return " ".join(self)


class RemoteFstabEntry(FstabEntry):
    __class_service_cache: dict[str, Service] = {}
    service: Service

    def __init__(self, *args, service: Service, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.service = (
            cached_service
            if (cached_service := self.__class_service_cache.get(str(service)))
            is not None
            else service
        )

    def refresh_mount_point(self) -> None:
        """
        Mount the mount point if the server is connectable, else unmount them.
        If the mounted state is already achieved, doesn't change it.
        """

        service_ok = self.service.check_is_connectable()
        logging.info("Service %s: %s", self.service, "OK" if service_ok else "AWAY")
        mounted = self.mount_point.check_is_mounted()

        # Easy cases, nothing to do
        if service_ok and mounted:
            logging.info("%s skipped, already mounted", self.mount_point.path)
            return
        if not service_ok and not mounted:
            logging.info("%s skipped, already unmounted", self.mount_point.path)
            return

        # Needs to be mounted
        if service_ok and not mounted:
            self.mount_point.mount()
            logging.info("%s mounted", self.mount_point.path)
            return

        # Needs to be unmounted
        if not service_ok and mounted:
            self.mount_point.unmount()
            logging.info("%s unmounted", self.mount_point.path)
            return


class NfsFstabEntry(RemoteFstabEntry):
    remote_path: str

    def __init__(self, *args, **kwargs) -> None:
        host, remote_path = self.name.split(":")
        service = Service(host, 2049)
        super().__init__(*args, service=service, **kwargs)
        self.remote_path = remote_path


class FstabEntryBuilder:
    def from_line(self, line: str) -> FstabEntry:
        """Create a fstab entry object from a fstab file line"""

        # Split the fields as strings
        separator_pattern = "\t "
        segments = [
            segment for segment in re.split(separator_pattern, line) if len(segment) > 0
        ]

        # Get the different items
        name, mount_point_path, fs_type, *optionals = segments
        mount_options = optionals[0].split(",") if len(optionals) > 0 else []
        dump_frequency = int(optionals[1]) if len(optionals) > 1 else 0
        fsck_pass_number = int(optionals[2]) if len(optionals) > 2 else 0
        mount_point = MountPoint(mount_point_path)

        # Build the fstab entry
        klass = NfsFstabEntry if fs_type == "nfs" else FstabEntry
        return klass(
            name=name,
            mount_point=mount_point,
            fs_type=fs_type,
            mount_options=mount_options,
            dump_frequency=dump_frequency,
            fsck_pass_number=fsck_pass_number,
        )


class Fstab:
    entries: list[FstabEntry]

    def __init__(self, entries: list[FstabEntry]) -> None:
        self.entries = entries

    def __str__(self) -> str:
        return "\n".join(self.entries)

    def __iter__(self):
        yield from self.entries


class FstabBuilder:
    def __clean_line(self, line: str) -> str:
        # Remove comment
        line = line.split("#")[0]
        # Remove leading and trailing whitespace
        return line.strip()

    def from_file(self, fstab_path: str = "/etc/fstab") -> "Fstab":
        """Create a fstab object from the local fstab file"""
        entry_builder = FstabEntryBuilder()
        with open(fstab_path, "r", encoding="utf-8") as file:
            return Fstab(
                entries=[
                    entry_builder.from_line(clean_line)
                    for line in file
                    if (clean_line := self.__clean_line(line)) != ""
                ]
            )


def main():
    """Program entry point"""

    # Ensure python version
    major, minor, *_rest = sys.version_info
    if not (major >= 3 and minor >= 11):
        print("This script expects python 3.11 or newer")
        sys.exit(1)

    # Configure logging
    logging.basicConfig(level="INFO")

    # Refresh mount points for the remote entries of the fstab file
    # - Services with the same host and port are reused
    # - Connection checks are cached per service
    fstab = FstabBuilder().from_file()
    for entry in (entry for entry in fstab if isinstance(entry, RemoteFstabEntry)):
        try:
            entry.refresh_mount_point()
        except MountError as error:
            logging.error(
                "%s couldn't be mounted", entry.mount_point.path, exc_info=error
            )
        except UnmountError as error:
            logging.error(
                "%s couldn't be unmounted", entry.mount_point.path, exc_info=error
            )


if __name__ == "__main__":
    main()
