import re

from stabbie.fstab.entry.fstab_entry import FstabEntry
from stabbie.fstab.entry.mount_point import MountPoint
from stabbie.fstab.entry.nfs_fstab_entry import NfsFstabEntry


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
