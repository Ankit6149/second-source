"""Spending-limit guard: no paid call without a fresh owner packet check."""
from __future__ import annotations
from typing import Literal
from pydantic import Field
from second_source.contracts import StrictModel
from second_source.backend.contracts import BackendError

class SpendPacketV1(StrictModel):
    schema_version: Literal["1"] = "1"
    packet_id: str = Field(min_length=1, max_length=80)
    owner_id: str = Field(min_length=1, max_length=80)
    investigation_id: str = Field(min_length=1, max_length=80)
    max_spend_usd: float = Field(ge=0, le=1000, allow_inf_nan=False)
    max_model_calls: int = Field(ge=0, le=10000)
    fresh: bool = False
    # Gate A default: mock/$0 only. Paid requires fresh=True explicitly.
    mode: Literal["mock", "paid"] = "mock"

class SpendingGuard:
    """Fail-closed guard reusing Budgets semantics (reserve-before-call)."""

    def __init__(self) -> None:
        self._spent: dict[str, float] = {}
        self._calls: dict[str, int] = {}

    def check(self, packet: SpendPacketV1 | None, *, estimated_usd: float,
              investigation_id: str) -> None:
        if estimated_usd < 0:
            raise BackendError("SPEND_INVALID", "Estimated spend is invalid", 422)
        if estimated_usd == 0:
            return  # mock/$0 always allowed, no packet needed
        if packet is None:
            raise BackendError("SPEND_PACKET_REQUIRED", "No paid call without packet check", 409)
        if not packet.fresh:
            raise BackendError("SPEND_PACKET_STALE", "Spend packet is not fresh", 409)
        if packet.mode != "paid":
            raise BackendError("SPEND_PACKET_REQUIRED", "Packet does not authorize paid calls", 409)
        if packet.investigation_id != investigation_id:
            raise BackendError("SPEND_PACKET_MISMATCH", "Packet investigation mismatch", 409)
        spent = self._spent.get(investigation_id, 0.0)
        if spent + estimated_usd > packet.max_spend_usd:
            raise BackendError("SPEND_LIMIT_EXCEEDED", "Spending limit exceeded", 409)
        if self._calls.get(investigation_id, 0) + 1 > packet.max_model_calls:
            raise BackendError("SPEND_LIMIT_EXCEEDED", "Model call limit exceeded", 409)

    def commit(self, packet: SpendPacketV1 | None, *, estimated_usd: float,
               investigation_id: str) -> None:
        if estimated_usd == 0:
            return
        self.check(packet, estimated_usd=estimated_usd, investigation_id=investigation_id)
        assert packet is not None
        self._spent[investigation_id] = self._spent.get(investigation_id, 0.0) + estimated_usd
        self._calls[investigation_id] = self._calls.get(investigation_id, 0) + 1

    def spent(self, investigation_id: str) -> float:
        return self._spent.get(investigation_id, 0.0)
