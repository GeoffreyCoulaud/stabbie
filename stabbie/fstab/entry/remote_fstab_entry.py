from dataclasses import dataclass, field
import logging

from stabbie.fstab.entry.fstab_entry import FstabEntry
from stabbie.fstab.entry.service import Service


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
