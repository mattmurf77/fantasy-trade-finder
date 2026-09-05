"""Concurrent user-work leases and exclusive account deletion.

Capture before reading work inputs or beginning external identity proof.
The deployed web service has one worker; this is not a distributed lock.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time


class UserDataBusy(RuntimeError):
    """Deletion could not drain active work before its bounded deadline."""


@dataclass
class _State:
    condition: object = field(default_factory=threading.Condition)
    generation: int = 0
    deleted_revision: int = 0
    readers: dict = field(default_factory=dict)
    deleting: bool = False
    owner: int | None = None
    depth: int = 0


_states: dict[str, _State] = {}
_registry_lock = threading.Lock()
_revision = 0
_work_revision = ContextVar("user_data_work_revision", default=None)


def _state(user_id: str) -> _State:
    with _registry_lock:
        return _states.setdefault(str(user_id), _State())


def snapshot() -> int:
    """Mark when a batch/auth operation began, before its DB/upstream reads."""
    with _registry_lock:
        return _revision


@dataclass(frozen=True)
class Lease:
    state: _State
    generation: int
    revision: int

    @contextmanager
    def active(self):
        state = self.state
        ident = threading.get_ident()
        admitted = False
        with state.condition:
            # Nested synchronous work is part of its already-admitted parent.
            # A new thread waits for deletion, then fails its stale generation.
            while state.deleting and not state.readers.get(ident) and state.owner != ident:
                state.condition.wait()
            if self.generation == state.generation:
                state.readers[ident] = state.readers.get(ident, 0) + 1
                admitted = True
        prior = _work_revision.get()
        token = _work_revision.set(min(prior, self.revision) if prior is not None else self.revision) if admitted else None
        try:
            yield admitted
        finally:
            if admitted:
                _work_revision.reset(token)
                with state.condition:
                    state.readers[ident] -= 1
                    if not state.readers[ident]:
                        del state.readers[ident]
                    state.condition.notify_all()


def capture(user_id: str, *, started: int | None = None) -> Lease:
    inherited = _work_revision.get()
    if inherited is not None:
        started = min(started, inherited) if started is not None else inherited
    if started is None:
        started = snapshot()
    state = _state(user_id)
    with state.condition:
        generation = state.generation
        if started is not None and state.deleted_revision > started:
            generation = -1
        return Lease(state, generation, started)


@contextmanager
def hold(user_ids, timeout: float = 10.0):
    """Stop new admissions and drain aliases in order; timeout changes no data."""
    states = [_state(uid) for uid in sorted(set(user_ids))]
    acquired = []
    deadline = time.monotonic() + timeout
    ident = threading.get_ident()
    try:
        for state in states:
            with state.condition:
                if state.owner == ident:
                    state.depth += 1
                    acquired.append(state)
                    continue
                while state.deleting:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise UserDataBusy("account deletion is already in progress")
                    state.condition.wait(remaining)
                state.deleting = True
                acquired.append(state)
                while state.readers:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise UserDataBusy("active user work did not finish before deletion deadline")
                    state.condition.wait(remaining)
                state.owner = ident
                state.depth = 1
        yield
    finally:
        for state in reversed(acquired):
            with state.condition:
                state.depth -= 1
                if state.depth <= 0:
                    state.depth = 0
                    state.deleting = False
                    state.owner = None
                    state.condition.notify_all()


def invalidate(user_ids):
    """Caller holds every alias exclusively and has committed deletion."""
    global _revision
    with _registry_lock:
        _revision += 1
        revision = _revision
    for uid in user_ids:
        state = _state(uid)
        with state.condition:
            state.generation += 1
            state.deleted_revision = revision
