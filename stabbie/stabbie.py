#!/bin/python3

import logging
import os
import sys
from logging.config import dictConfig as logging_dict_config
from multiprocessing import Pool

from stabbie.fstab.entry.fstab_entry import FstabEntry
from stabbie.fstab.entry.remote_fstab_entry import RemoteFstabEntry
from stabbie.fstab.fstab import FstabBuilder


class Application:
    """Class representing the stabbie application"""

    stabbie_mount_option = "x-stabbie"

    __refresh_errors: list[Exception]

    def __init__(self) -> None:
        self.__refresh_errors = []

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

    @classmethod
    def refresh_remote_fstab_entry(cls, entry: RemoteFstabEntry) -> None:
        logging.info("Refreshing %s", entry.name)
        entry.refresh_mount_point()

    def refresh_error_callback(self, error: Exception) -> None:
        self.__refresh_errors.append(error)

    def run(self):
        self.__check_mount_permissions()
        self.__setup_logging()

        # Load fstab
        logging.info("Reading fstab")
        fstab = FstabBuilder().from_file()

        # Refresh mount points for the remote entries of the fstab file
        # - Services with the same host and port are reused
        # - Connection checks are cached per service
        logging.info("Refreshing remote filesystem mount points")
        with Pool() as pool:
            pool.map_async(
                Application.refresh_remote_fstab_entry,
                filter(self.fstab_entries_filter_key, fstab),
            )
            pool.close()
            pool.join()

        # Errors summary
        errors = self.__refresh_errors
        if len(errors) > 0:
            logging.warning(
                "Some mount points couldn't be refreshed",
                exc_info=ExceptionGroup("Refresh errors", errors),
            )

        logging.info("Done")


def main():
    app = Application()
    app.run()
    sys.exit(0)


if __name__ == "__main__":
    main()
