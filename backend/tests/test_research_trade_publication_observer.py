"""Research timing observes direct writes and terminal dictionary updates."""
from scripts.research_trade_pipeline import ObservedJob


def test_observer_sees_atomic_update_and_terminal_helper():
    class Clock:
        def __init__(self):
            self.value = 0

        def elapsed_ms(self):
            self.value += 1
            return self.value

    job = ObservedJob(Clock(), status="running", final_checks_pending=True)
    job.update(cards=[{"impression_id": "first"}])
    assert job.first_cards_ms == 1
    assert job.first_actionable_ms is None
    job.update(final_checks_pending=False)
    assert job.first_actionable_ms == 2
    job.update({"status": "complete"}, finished_at=123)
    assert job.complete_ms == 3
    assert job["finished_at"] == 123
