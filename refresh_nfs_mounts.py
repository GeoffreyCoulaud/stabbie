#!/bin/python

import logging
import json
import socket
import subprocess
import sys
from pathlib import Path
from subprocess import SubprocessError
from typing import Sequence


class MountError(Exception):
    """Error raised when a mount point couldn't be mounted"""


class UnmountError(Exception):
    """Error raised when a mount point couldn't be unmounted"""


class MountPoint:
    """Class that defines a mount point"""

    mount_point_path: str
    unmount_force: bool = True
    unmount_lazy: bool = True

    def __init__(self, mount_point_path: str) -> None:
        self.mount_point_path = mount_point_path

    def __str__(self) -> str:
        return str(self.mount_point_path)

    @property
    def mount_command(self) -> Sequence[str]:
        return ["mount", self.mount_point_path]

    @property
    def unmount_command(self) -> Sequence[str]:
        command = ["umount"]
        if self.unmount_force:
            command.append("-f")
        if self.unmount_lazy:
            command.append("-l")
        command.append(self.mount_point_path)
        return command

    def check_is_mounted(self) -> bool:
        """Check if the mount point is already mounted"""
        try:
            return Path(self.mount_point_path).is_mount()
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
    """Class representing a distant service"""

    host: str
    port: int
    check_timeout_seconds: int = 3

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"

    def check_connection(self) -> bool:
        """Check if the service is connectable to"""
        try:
            with socket.create_connection(
                (self.host, self.port), self.check_timeout_seconds, all_errors=True
            ) as _server_socket:
                return True
        except ExceptionGroup:
            return False


class NfsServer:
    """Class representing a NFS server with local mount points"""

    service: Service
    mount_points: Sequence[MountPoint]

    def __init__(self, host: str, mount_points: Sequence[str | MountPoint]) -> None:
        self.service = Service(host, 2049)
        self.mount_points = [
            mount_point
            if isinstance(mount_point, MountPoint)
            else MountPoint(mount_point)
            for mount_point in mount_points
        ]

    def refresh_mount_points(self) -> None:
        """
        Mount the mount points if the nfs server is connectable, else unmount them

        :raise ExceptionGroup:
            Will try every mount point independently and wrap SubprocessError-s.
        """
        errors = []

        # Check server state
        server_ok = self.service.check_connection()
        server_state = "OK" if server_ok else "AWAY"
        logging.info("NFS service at %s checked: %s", self.service, server_state)

        # Update mount points
        for mount_point in self.mount_points:
            mounted = mount_point.check_is_mounted()
            if server_ok:
                # Mounting
                if mounted:
                    logging.info("%s skipped, already mounted", mount_point)
                    continue
                try:
                    mount_point.mount()
                except MountError as error:
                    logging.error("%s couldn't be mounted", mount_point, exc_info=error)
                    errors.append(error)
                else:
                    logging.info("%s mounted", mount_point)
            else:
                # Unmounting
                if not mounted:
                    logging.info("%s skipped, already unmounted", mount_point)
                    continue
                try:
                    mount_point.unmount()
                except UnmountError as error:
                    logging.error(
                        "%s couldn't be unmounted", mount_point, exc_info=error
                    )
                    errors.append(error)
                else:
                    logging.info("%s unmounted", mount_point)

        # Final report
        if len(errors) > 0:
            raise ExceptionGroup("Error while refreshing the mount points", errors)


def main():
    """Program entry point"""

    # Ensure python version
    major, minor, *_rest = sys.version_info
    if not (major >= 3 and minor >= 11):
        print("This script expects python 3.11 or newer")
        sys.exit(1)

    # Configure logging
    logging.basicConfig(level="INFO")

    # Get the raw server and mount points json
    script_path = Path(__file__)
    servers_json_path = script_path.parent / "servers.json"
    servers_json = json.load(servers_json_path.open("r", encoding="utf-8"))

    # Create the server items
    servers: list[NfsServer] = []
    for entry in servers_json:
        server = NfsServer(entry["address"], entry["mount_points"])
        servers.append(server)

    # Refresh the mount points
    for server in servers:
        server.refresh_mount_points()


if __name__ == "__main__":
    main()
