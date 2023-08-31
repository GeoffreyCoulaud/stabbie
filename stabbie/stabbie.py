#!/bin/python3

from argparse import ArgumentParser
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
    use_color_logs: bool = True
    log_level: str = "INFO"

    __refresh_errors: list[Exception]

    def __parse_cli_args(self) -> None:
        """Parse cli args with argparse to configure the app"""
        parser = ArgumentParser(
            prog="stabbie",
            description="A friendly fstab auto-mount script for remote filesystems",
        )
        parser.add_argument("--color", action="store_true", help="use color for logs")
        parser.add_argument(
            "--log-level",
            type=str,
            default=Application.log_level,
            help="logging level to use",
            choices=logging.getLevelNamesMapping().keys(),
        )
        args = parser.parse_args()
        self.use_color_logs = args.color
        self.log_level = args.log_level

    def __init__(self) -> None:
        self.__refresh_errors = []
        self.__parse_cli_args()

    def __check_mount_permissions(self) -> None:
        assert os.geteuid() == 0, "Insufficient privileges to mount and unmout"

    def __setup_logging(self) -> None:
        """Setup logging for the app"""

        # Configure logging
        logging_dict_config(
            {
                "version": 1,
                "formatters": {
                    "color_formatter": {
                        "format": "[{levelname}] {message}",
                        "style": "{",
                        "class": (
                            "stabbie.logging.color_log_formatter.ColorLogFormatter"
                            if self.use_color_logs
                            else "logging.Formatter"
                        ),
                    }
                },
                "handlers": {
                    "console_handler": {
                        "class": "logging.StreamHandler",
                        "level": self.log_level,
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
