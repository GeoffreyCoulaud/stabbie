from dataclasses import dataclass, field
import logging

from stabbie.fstab.entry.remote_fstab_entry import RemoteFstabEntry
from stabbie.fstab.entry.service import Service


@dataclass
class NfsFstabEntry(RemoteFstabEntry):
    remote_path: str = field(init=False)

    def __post_init__(self) -> None:
        """Generate the values specific to NFS entries from its values"""

        # Get host and remote path
        # Split once from the right to allow raw IPv6 hosts
        host, remote_path = self.name.rsplit(":", maxsplit=1)

        # Get the NFS specific mount options
        options = NfsMountOptions.from_entry(self)

        self.service = Service.new_cached(host, options.port)
        self.remote_path = remote_path


@dataclass
class NfsMountOptions:
    version: int
    port: int

    @classmethod
    def from_entry(cls, entry: NfsFstabEntry) -> "NfsMountOptions":
        """Create nfs mount options from a raw options string"""

        # Get the options that are in key=value format
        options_mapping = {}
        for option in entry.mount_options:
            try:
                key, value = option.split("=", maxsplit=1)
            except ValueError:
                continue
            options_mapping[key] = value

        # Get nfs specific options
        version = int(options_mapping.get("version", 3))
        default_port = 2049 if version == 4 else 0
        port = int(options_mapping.get("port", default_port))
        if port == 0:
            logging.warning("RPC discovery of NFS port is not implemented")
        return NfsMountOptions(version, port)
