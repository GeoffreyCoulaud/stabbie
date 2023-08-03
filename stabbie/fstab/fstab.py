import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from stabbie.fstab.mount_point import MountPoint
from stabbie.fstab.service import Service


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
