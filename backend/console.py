"""Console output must not interrupt evaluation when a terminal disconnects."""
import builtins
import errno


def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except OSError as exc:
        if exc.errno not in (errno.EIO, errno.EPIPE, errno.EBADF):
            raise
