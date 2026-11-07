"""Unwired owned pricing-domain execution; never a proof-reuse certificate.

Tier/age/roster/code/source reads remain unbound. Capture is not atomic, and
materialized kwargs do not restore provider-bound provenance. Both operations
still run their full existing evaluator with independent search state.
"""
from dataclasses import dataclass, field
import hashlib
import math
from types import MappingProxyType

from . import owner_evaluation_inputs as inputs


VERSION = "owner-pricing-execution-1"


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class PackagePricingPolicy:
    config: object = field(repr=False)
    crown_asset: bool
    first_round_by_id: object = field(repr=False)
    mode: str = field(default="market", init=False)

    def __post_init__(self):
        from . import trade_service as ts
        if (type(self.config) is not dict or not set(ts._DEFAULT_CFG) <= self.config.keys()
                or any(type(k) is not str or not _finite_number(v)
                       for k, v in self.config.items())):
            raise inputs.UnsupportedOwnerInput("unsupported_pricing_config", "pricing.config")
        if type(self.crown_asset) is not bool:
            raise inputs.UnsupportedOwnerInput("unsupported_pricing_flag", "pricing.crown_asset")
        if (type(self.first_round_by_id) is not dict
                or any(type(k) is not str or type(v) is not bool for k, v in self.first_round_by_id.items())):
            raise inputs.UnsupportedOwnerInput("unsupported_pick_classification", "pricing.first_round_by_id")
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
        object.__setattr__(self, "first_round_by_id", MappingProxyType(dict(self.first_round_by_id)))

    def mask(self, ids):
        ids = tuple(ids)
        if any(type(pid) is not str or pid not in self.first_round_by_id for pid in ids):
            raise inputs.UnsupportedOwnerInput("uncaptured_pricing_asset", "pricing.offer")
        return [self.first_round_by_id[pid] for pid in ids]

    def observation(self):
        return {"config": dict(self.config), "crown_asset": self.crown_asset,
                "mode": self.mode, "first_round_by_id": dict(self.first_round_by_id)}


@dataclass(frozen=True)
class OwnerPricingExecution:
    envelope: inputs.OwnerInputEnvelope = field(repr=False)
    pricing_policy: PackagePricingPolicy = field(repr=False)
    fingerprint: str

    def _run(self, cards, *, generate):
        from . import trade_service as ts, trade_gen_owner as owner
        module = inputs._models()[self.envelope.model_version]
        kwargs = self.envelope.evaluator_kwargs()
        kwargs["config"] = dict(self.pricing_policy.config)
        kwargs["_pricing_policy"] = self.pricing_policy
        # The original owner constructor's raw-limit precedence is already
        # resolved in kwargs.config. Full overlays also bind constructor reads
        # outside the owner's inner config scopes. No global value is changed.
        with ts._cfg_override(kwargs["config"]):
            if generate:
                fn = module.generate_owner_trades if module is owner else module.generate_bilateral_trades
                return fn(**kwargs)
            fn = module.evaluate_owner_trades if module is owner else module.evaluate_bilateral_trades
            return fn(cards, **kwargs)

    def generate(self):
        return self._run(None, generate=True)

    def evaluate(self, cards):
        return self._run(cards, generate=False)


@dataclass(frozen=True)
class PricingCaptureResult:
    execution: OwnerPricingExecution | None = None
    reason: str | None = None
    path: str | None = None


def capture_owner_pricing(context, *, model_version):
    """Capture supported owned values, without atomic/currentness authority.

    Pick masks record the actual classifier's effective values, including its
    existing memo semantics. They do not certify that a source table is fresh.
    No serialized user context can supply the private policy argument.
    """
    from . import trade_service as ts
    try:
        ambient = inputs.observe_ambient_inputs()
        captured = inputs.capture_owner_inputs(context, model_version=model_version, ambient=ambient)
        if captured.envelope is None:
            return PricingCaptureResult(reason=captured.reason, path=captured.path)
        envelope = captured.envelope
        kwargs = envelope.evaluator_kwargs()
        if type(kwargs.get("config")) not in (dict, type(None)):
            raise inputs.UnsupportedOwnerInput("unsupported_pricing_config", "context.config")
        # Preserve the existing constructor's precedence, including raw limit
        # lookups overriding effective thread-local values before request config.
        config = {**ambient["effective_trade_config"], **ambient["raw_owner_limits"],
                  **(kwargs.get("config") or {})}
        ids = list(kwargs["players"])
        masks = ts.first_round_pick_mask(ids)
        if type(masks) is not list or len(masks) != len(ids):
            raise inputs.UnsupportedOwnerInput("unsupported_pick_classification", "pricing.first_round_by_id")
        policy = PackagePricingPolicy(config, ambient["feature_flags"]["trade.crown_asset"],
                                     dict(zip(ids, masks)))
        encoded = inputs._json({"version": VERSION, "envelope": envelope.fingerprint,
                               "pricing": inputs._freeze(policy.observation(), "pricing", set(), {})})
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        return PricingCaptureResult(OwnerPricingExecution(envelope, policy, fingerprint))
    except inputs.UnsupportedOwnerInput as exc:
        return PricingCaptureResult(reason=exc.reason, path=exc.path)
