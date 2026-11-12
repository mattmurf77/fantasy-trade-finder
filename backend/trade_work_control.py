"""Internal cooperative stop signal: never an empty successful trade result."""

# The founders' rule-waterfall run (server._rule_waterfall_job) stops its private job with these
# two: "diagnostic_complete" once the waterfall is measured at the construction inputs (nothing is
# built or served), "diagnostic_timed_out" at its 60-second cap.
_REASONS = {"inputs_changed", "interactive_work", "preparation_disabled", "preparation_claim_changed",
            "preparation_check_unavailable", "diagnostic_complete", "diagnostic_timed_out"}


class TradeWorkCancelled(RuntimeError):
    def __init__(self, reason="inputs_changed"):
        if reason not in _REASONS:
            raise ValueError("unknown trade cancellation reason")
        self.reason = reason
        super().__init__(reason)
