"""Synthetic caller-priority clipping, fractional weights only; no optimization or orders."""

from __future__ import annotations

import json
import sys
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.evaluation.integrity import to_hashable  # noqa: E402
from lib.portfolio_construction import construct_portfolio, make_construction_request  # noqa: E402
from lib.portfolio_risk import make_request  # noqa: E402
from scripts.d0112_demo import synthetic_request  # noqa: E402


def synthetic_construction_request():
    old = synthetic_request()
    kwargs = {field.name: getattr(old, field.name) for field in fields(old) if field.name != "record_hash"}
    kwargs["policy"] = replace(old.policy, max_company=Decimal("0.3"), max_sector=Decimal("0.3"))
    desired = make_request(**kwargs)
    return make_construction_request(
        request_id="SYNTHETIC_CONSTRUCTION",
        desired=desired,
        priority=tuple(p.position_id for p in desired.positions),
        allocation_quantum=Decimal("0.01"),
        policy_ref="EXPLICIT_CALLER_PRIORITY_AND_DOWNWARD_GRID",
        policy_available_at=desired.decision_cutoff,
        calculated_at=desired.calculated_at,
    )


def run_demo():
    request = synthetic_construction_request()
    return {"synthetic": True, "empirical_validation": False, "result": to_hashable(construct_portfolio(request))}


if __name__ == "__main__":
    print(json.dumps(run_demo(), sort_keys=True, ensure_ascii=False))
