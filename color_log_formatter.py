import logging
from logging import Formatter, LogRecord


class ColorLogFormatter(Formatter):
    """Formatter that outputs logs in a colored format"""

    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    YELLOW = "\033[33m"

    def format(self, record: LogRecord) -> str:
        super_format = super().format(record)
        match record.levelno:
            case logging.CRITICAL:
                return self.BOLD + self.RED + super_format + self.RESET
            case logging.ERROR:
                return self.RED + super_format + self.RESET
            case logging.WARNING:
                return self.YELLOW + super_format + self.RESET
            case logging.DEBUG:
                return self.DIM + super_format + self.RESET
            case _:
                return super_format
