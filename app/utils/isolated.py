"""Run a function in a separate process with a time limit and, on Linux, a memory limit.

Used for parsing uploaded PDFs: a malformed or hostile file can make a parser
loop or allocate without bound. In a child process that can be killed, such a
file costs one bounded attempt instead of stalling the worker thread.
"""
import multiprocessing

# A fresh interpreter: the child does not inherit the parent's threads, locks
# or loaded embedding model.
_CONTEXT = multiprocessing.get_context("spawn")


class IsolationTimeout(Exception):
    """The function did not finish within the time limit."""


class IsolationCrashed(Exception):
    """The child process exited without returning a result."""


def _limit_memory(limit_bytes):
    try:
        import resource
    except ImportError:  # Not available on Windows; only the time limit applies.
        return
    # RLIMIT_DATA counts heap and anonymous mappings, which is what a runaway
    # parser allocates. RLIMIT_AS would also count the large virtual
    # reservations numerical libraries make at import, and reject normal files.
    resource.setrlimit(resource.RLIMIT_DATA, (limit_bytes, limit_bytes))


def _child(connection, func, args, kwargs, memory_limit_bytes):
    try:
        if memory_limit_bytes:
            _limit_memory(memory_limit_bytes)
        connection.send(("ok", func(*args, **kwargs)))
    except MemoryError:
        connection.send(("memory", ""))
    except ValueError as exc:
        connection.send(("value", str(exc)))
    except Exception as exc:
        connection.send(("error", type(exc).__name__))
    finally:
        connection.close()


def run_isolated(func, *args, timeout: float, memory_limit_bytes: int | None = None, **kwargs):
    """Return func(*args, **kwargs) computed in a child process.

    func must be importable at module level. ValueError and MemoryError from
    the child are raised again here with the same message; other errors are
    raised as RuntimeError naming the original type.
    """
    receiver, sender = _CONTEXT.Pipe(duplex=False)
    process = _CONTEXT.Process(
        target=_child,
        args=(sender, func, args, kwargs, memory_limit_bytes),
        daemon=True,
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise IsolationTimeout()
        try:
            outcome, value = receiver.recv()
        except EOFError:
            raise IsolationCrashed() from None
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        receiver.close()

    if outcome == "ok":
        return value
    if outcome == "value":
        raise ValueError(value)
    if outcome == "memory":
        raise MemoryError()
    raise RuntimeError(f"{value} raised in the isolated process.")
