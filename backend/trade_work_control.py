"""Internal cooperative stop signal: never an empty successful trade result."""


class TradeWorkCancelled(RuntimeError):
    def __init__(self, reason="inputs_changed"):
        if reason not in {"inputs_changed", "interactive_work", "preparation_disabled", "preparation_claim_changed", "preparation_check_unavailable"}:
            raise ValueError("unknown trade cancellation reason")
        self.reason = reason
        super().__init__(reason)
