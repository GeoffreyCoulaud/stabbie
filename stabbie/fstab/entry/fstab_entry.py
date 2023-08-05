from dataclasses import dataclass
from typing import Sequence

from stabbie.fstab.entry.mount_point import MountPoint


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
