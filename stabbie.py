#!/bin/python3

import logging
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache, lru_cache
from logging.config import dictConfig as logging_dict_config
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


class Service:
    host: str
    port: int

    check_timeout_seconds: int = 3

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    @classmethod
    @cache
    def new_cached(cls, *args, **kwargs) -> "Service":
        return Service(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"

    def __eq__(self, other: "Service") -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    @lru_cache(maxsize=1)
    def check_is_connectable(self) -> bool:
        """
        Check if the service is connectable.

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


@dataclass
class FstabEntry:
    name: str
    mount_point: MountPoint
    fs_type: str
    mount_options: Sequence[str]
    dump_frequency: int = 0
    fsck_pass_number: int = 0

    def __str__(self) -> str:
        return " ".join(
            (
                self.name,
                str(self.mount_point),
                self.fs_type,
                ",".join(self.mount_options),
                str(self.dump_frequency),
                str(self.fsck_pass_number),
            )
        )


@dataclass
class RemoteFstabEntry(FstabEntry):
    """
    Abstract class representing an fstab entry pointing to a remote filesystem.
    Instanciate one of the child classes, not this one.
    """

    service: Service = field(init=False)

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


@dataclass
class NfsMountOptions:
    version: int
    port: int

    @classmethod
    def from_options_sequence(cls, options: Sequence[str]) -> "NfsMountOptions":
        """Create nfs mount options from a raw options string"""

        # Get the options that are in key=value format
        options_mapping = {}
        for option in options:
            try:
                key, value = option.split("=", maxsplit=1)
            except ValueError:
                continue
            options_mapping[key] = value

        # Get nfs specific options
        version = int(options_mapping.get("version", 3))
        default_port = 2049 if version == 4 else 0
        port = int(options_mapping.get("port", default_port))
        return NfsMountOptions(version, port)


@dataclass
class NfsFstabEntry(RemoteFstabEntry):
    remote_path: str = field(init=False)

    def __post_init__(self) -> None:
        """Generate the values specific to NFS entries from its values"""

        # Get host and remote path
        # Split once from the right to allow raw IPv6 hosts
        host, remote_path = self.name.rsplit(":", maxsplit=1)

        # Get the NFS specific mount options
        options = NfsMountOptions.from_options_sequence(self.mount_options)

        self.service = Service.new_cached(host, options.port)
        self.remote_path = remote_path


class FstabEntryBuilder:
    def from_line(self, line: str) -> FstabEntry:
        """Create a fstab entry object from a fstab file line"""

        # Split the fields as strings
        separator_pattern = "\t| "
        segments: list[str] = []
        for segment in re.split(separator_pattern, line):
            if len(segment) == 0:
                continue
            segments.append(segment)

        # Get the different items
        name, mount_point_path, fs_type, *optionals = segments
        mount_options = optionals[0].split(",") if len(optionals) > 0 else ""
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
    def cleanup_line(self, line: str) -> str:
        # Remove comment
        line = line.split("#")[0]
        # Remove leading and trailing whitespace
        return line.strip()

    def from_file(self, fstab_path: str = "/etc/fstab") -> Fstab:
        """Create a fstab object from the local fstab file"""
        entry_builder = FstabEntryBuilder()
        entries: list[FstabEntry] = []
        with open(fstab_path, "r", encoding="utf-8") as file:
            for i, line in enumerate(file):
                cleaned_line = self.cleanup_line(line)
                if len(cleaned_line) == 0:
                    continue
                entry = entry_builder.from_line(cleaned_line)
                logging.debug("[%s:%d] Parsed fstab entry: %s", fstab_path, i, entry)
                entries.append(entry)
        fstab = Fstab(entries)
        logging.debug("Loaded fstab from %s with %d entries", fstab_path, len(entries))
        return fstab


def main():
    """Program entry point"""

    # Ensure python version
    major, minor, *_rest = sys.version_info
    if not (major >= 3 and minor >= 11):
        print("This script expects python 3.11 or newer")
        sys.exit(1)

    # Ensure that we have mount/unmount rights
    if os.geteuid() != 0:
        print("Insufficient privileges to mount and unmout")
        sys.exit(1)

    # Get log level from env vars
    valid_log_levels = logging.getLevelNamesMapping().keys()
    env_log_level = os.getenv("LOG_LEVEL", "INFO")
    log_level = env_log_level if env_log_level in valid_log_levels else "INFO"

    # Get colored logs preference
    color_logs = os.getenv("COLOR_LOGS", "0") == "1"
    formatter_name = (
        "color_log_formatter.ColorLogFormatter" if color_logs else "logging.Formatter"
    )

    # Configure logging
    logging_dict_config(
        {
            "version": 1,
            "formatters": {
                "color_formatter": {
                    "format": "[{levelname}] {message}",
                    "style": "{",
                    "class": formatter_name,
                }
            },
            "handlers": {
                "console_handler": {
                    "class": "logging.StreamHandler",
                    "level": log_level,
                    "formatter": "color_formatter",
                }
            },
            "root": {
                "level": logging.NOTSET,
                "handlers": ["console_handler"],
            },
        }
    )

    def filter_predicate(entry):
        """Consider only remote entries with a custom mount option"""
        x_option = "x-connectable-check"
        return isinstance(entry, RemoteFstabEntry) and x_option in entry.mount_options

    # Load fstab
    logging.info("Reading fstab")
    fstab = FstabBuilder().from_file()

    # Refresh mount points for the remote entries of the fstab file
    # - Services with the same host and port are reused
    # - Connection checks are cached per service
    logging.info("Refreshing remote filesystem mount points")
    for entry in fstab:
        # Skip unwanted entries
        if not filter_predicate(entry):
            logging.debug("Skipped %s", entry.name)
            continue
        # Refresh the entry's mount point
        logging.info("Refreshing %s", entry.name)
        path = entry.mount_point.path
        try:
            entry.refresh_mount_point()
        except MountError as error:
            logging.error("%s couldn't be mounted", path, exc_info=error)
        except UnmountError as error:
            logging.error("%s couldn't be unmounted", path, exc_info=error)
    logging.info("Done")


if __name__ == "__main__":
    main()
