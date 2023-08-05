#!/bin/python3

import logging
import os
import sys
from logging.config import dictConfig as logging_dict_config

from stabbie.fstab.entry.mount_point import MountError, UnmountError
from stabbie.fstab.entry.fstab_entry import FstabEntry
from stabbie.fstab.entry.remote_fstab_entry import RemoteFstabEntry
from stabbie.fstab.fstab import FstabBuilder


class Application:
    """Class representing the stabbie application"""

    stabbie_mount_option = "x-stabbie"
    stabbie_version = (1, 0, 0)
    stabbie_expected_python_version = (3, 11)

    def __check_python_version(self) -> None:
        major, minor, *_rest = sys.version_info
        expected_major, expected_minor = self.stabbie_expected_python_version
        message = f"Expects python {expected_major}.{expected_minor} or newer"
        assert major == expected_major and minor >= expected_minor, message

    def __check_mount_permissions(self) -> None:
        assert os.geteuid() == 0, "Insufficient privileges to mount and unmout"

    def __setup_logging(self) -> None:
        """Setup logging for the app"""

        # Get log level from env vars
        valid_log_levels = logging.getLevelNamesMapping().keys()
        env_log_level = os.getenv("LOG_LEVEL", "INFO")
        log_level = env_log_level if env_log_level in valid_log_levels else "INFO"

        # Get colored logs preference
        color_fomatter = "stabbie.logging.color_log_formatter.ColorLogFormatter"
        base_formatter = "logging.Formatter"
        color_logs = os.getenv("COLOR_LOGS", "0") == "1"
        formatter_qualified_name = color_fomatter if color_logs else base_formatter

        # Configure logging
        logging_dict_config(
            {
                "version": 1,
                "formatters": {
                    "color_formatter": {
                        "format": "[{levelname}] {message}",
                        "style": "{",
                        "class": formatter_qualified_name,
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

    def fstab_entries_filter_key(self, entry: FstabEntry):
        """Consider only remote entries with a custom mount option"""
        return (
            isinstance(entry, RemoteFstabEntry)
            and self.stabbie_mount_option in entry.mount_options
        )

    def run(self):
        self.__check_python_version()
        self.__check_mount_permissions()
        self.__setup_logging()

        # Load fstab
        logging.info("Reading fstab")
        fstab = FstabBuilder().from_file()

        # Refresh mount points for the remote entries of the fstab file
        # - Services with the same host and port are reused
        # - Connection checks are cached per service
        logging.info("Refreshing remote filesystem mount points")
        errors: dict[str, Exception] = {}
        for entry in filter(self.fstab_entries_filter_key, fstab):
            logging.info("Refreshing %s", entry.name)
            try:
                entry.refresh_mount_point()
            except (MountError, UnmountError) as error:
                errors[entry.mount_point.path] = error

        # Errors summary
        if len(errors) > 0:
            exception_group = ExceptionGroup("Mount point errors", errors)
            logging.warning(
                "Some mount points couldn't be mounted or unmounted",
                exc_info=exception_group,
            )

        logging.info("Done")


if __name__ == "__main__":
    app = Application()
    app.run()
    sys.exit(0)
