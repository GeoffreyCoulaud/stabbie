import socket
from functools import cache, lru_cache


class Service:
    host: str
    port: int

    check_timeout_seconds: int = 3

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    @classmethod
    @cache
    def new_cached(cls, *args, **kwargs) -> "Service":
        return Service(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"

    def __eq__(self, other: "Service") -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    @lru_cache(maxsize=1)
    def check_is_connectable(self) -> bool:
        """
        Check if the service is connectable.

        Cached because the program is short lived and a service is assumed to
        not change state during a run.
        """
        try:
            with socket.create_connection(
                (self.host, self.port), self.check_timeout_seconds, all_errors=True
            ) as _server_socket:
                return True
        except ExceptionGroup:
            return False
