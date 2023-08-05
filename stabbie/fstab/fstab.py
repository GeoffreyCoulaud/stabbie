import logging

from stabbie.fstab.entry.fstab_entry import FstabEntry
from stabbie.fstab.entry.fstab_entry_builder import FstabEntryBuilder


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
