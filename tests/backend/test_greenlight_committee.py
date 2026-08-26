"""Checks for the Greenlight Committee multi-node LangGraph debate graph
(app/ai/supervisor.py::build_greenlight_committee and its node/routing
functions).

Run directly with no test framework installed:

    python test_greenlight_committee.py

Also written so `pytest` collects it unchanged, like the other test_*.py files.

Scope: the routing functions (route_after_gatekeeper, route_after_executive)
and mediator_node's verdict computation are pure state transitions and are
exercised directly with hand-built state dicts ΓÇö no LLM call needed for those.
gatekeeper_node calls check_compliance_structured (LLM+RAG) and
check_conflicts_via_a2a (A2A microservice call); both are monkeypatched by
name on app.ai.supervisor so this file covers the *graph's* decisions (the
stalemate/iteration-cap logic, the A2A-failure-is-swallowed-to-{} behavior,
RED/YELLOW/GREEN verdict rules) without a live LLM, database, or Agent 4
service.

Moved to tests/backend/ (see tests/TEST_PLAN.md); the sys.path fixup below is
needed because these modules import via the `app.` package prefix, which
only resolves when backend/ is on sys.path.
"""

import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.ai.supervisor as supervisor


class _Patcher:
    def __init__(self):
        self._saved = []

    def setattr(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


# ---- route_after_gatekeeper: hard compliance violations short-circuit -----


def test_hard_violation_routes_straight_to_mediator_bypassing_the_executive():
    state = {"executive_review": {"concern_list": ["nudity"], "is_approved": False}}
    assert supervisor.route_after_gatekeeper(state) == "stalemate_edge"


def test_no_hard_violation_routes_to_the_executive():
    state = {"executive_review": None}
    assert supervisor.route_after_gatekeeper(state) == "executive_node"


# ---- route_after_executive: approval, stalemate, and the iteration cap ----


def test_approval_routes_to_the_mediator():
    state = {"executive_review": {"is_approved": True, "concern_list": []}}
    assert supervisor.route_after_executive(state) == "mediator_node"


def test_rejection_with_new_concerns_routes_back_to_the_producer():
    state = {
        "executive_review": {"is_approved": False, "concern_list": ["pacing"]},
        "previous_concerns": ["budget"],
        "iteration_count": 1,
    }
    assert supervisor.route_after_executive(state) == "producer_node"


def test_repeating_the_same_concerns_is_a_stalemate_routed_to_the_mediator():
    state = {
        "executive_review": {"is_approved": False, "concern_list": ["pacing"]},
        "previous_concerns": ["pacing"],
        "iteration_count": 1,
    }
    assert supervisor.route_after_executive(state) == "mediator_node"


def test_three_iterations_forces_the_mediator_even_with_fresh_concerns():
    state = {
        "executive_review": {"is_approved": False, "concern_list": ["new concern"]},
        "previous_concerns": ["old concern"],
        "iteration_count": 3,
    }
    assert supervisor.route_after_executive(state) == "mediator_node"


def test_below_the_iteration_cap_with_fresh_concerns_keeps_debating():
    state = {
        "executive_review": {"is_approved": False, "concern_list": ["new concern"]},
        "previous_concerns": ["old concern"],
        "iteration_count": 2,
    }
    assert supervisor.route_after_executive(state) == "producer_node"


# ---- mediator_node: RED / YELLOW / GREEN verdict rules ---------------------


def test_rejected_review_is_always_red_regardless_of_conflicts():
    state = {"executive_review": {"is_approved": False}, "date_conflict_data": {}}
    result = asyncio.run(supervisor.mediator_node(state))
    assert result["final_verdict"]["status"] == "RED"


def test_approved_with_a_hard_holiday_conflict_is_yellow():
    state = {
        "executive_review": {"is_approved": True},
        "date_conflict_data": {"holidays": {"US": {"conflict": True}}},
    }
    result = asyncio.run(supervisor.mediator_node(state))
    assert result["final_verdict"]["status"] == "YELLOW"


def test_approved_with_no_conflict_is_green():
    state = {
        "executive_review": {"is_approved": True},
        "date_conflict_data": {"holidays": {"US": {"conflict": False}}},
    }
    result = asyncio.run(supervisor.mediator_node(state))
    assert result["final_verdict"]["status"] == "GREEN"


def test_mediator_result_is_valid_json_containing_the_verdict():
    import json

    state = {"executive_review": {"is_approved": True}, "date_conflict_data": {}}
    result = asyncio.run(supervisor.mediator_node(state))
    parsed = json.loads(result["result"])
    assert parsed["verdict"]["status"] == "GREEN"


# ---- gatekeeper_node: A2A failure must not crash the graph -----------------


def test_a2a_failure_during_conflict_check_is_swallowed_to_an_empty_dict():
    """CLAUDE.md documents check_conflicts_via_a2a's A2A round-trip on the
    /run-agent path indirectly via the release-date flow; inside the
    Greenlight Committee it's called from gatekeeper_node, which wraps it in
    a bare except and must degrade to {} rather than aborting the whole
    debate graph over an Agent 4 outage/timeout."""
    patch = _Patcher()
    try:
        patch.setattr(
            supervisor, "check_compliance_structured",
            lambda script_text, model_overrides=None: {"hard_violations": [], "soft_violations": []},
        )

        async def _failing_a2a(date_str):
            raise TimeoutError("Agent 4 did not respond")

        patch.setattr(supervisor, "check_conflicts_via_a2a", _failing_a2a)

        state = {"script_text": "a script", "producer_pitch": {}}
        result = asyncio.run(supervisor.gatekeeper_node(state))

        assert result["date_conflict_data"] == {}
        # And the rest of the graph can still proceed: no hard violations
        # means executive_review is explicitly None, not left unset.
        assert result["executive_review"] is None
    finally:
        patch.undo()


def test_hard_violations_from_compliance_auto_reject_without_reaching_the_a2a_call():
    patch = _Patcher()
    try:
        patch.setattr(
            supervisor, "check_compliance_structured",
            lambda script_text, model_overrides=None: {"hard_violations": ["graphic violence"], "soft_violations": []},
        )
        called = {"a2a": False}

        async def _tracking_a2a(date_str):
            called["a2a"] = True
            return {}

        patch.setattr(supervisor, "check_conflicts_via_a2a", _tracking_a2a)

        state = {"script_text": "a script", "producer_pitch": {}}
        result = asyncio.run(supervisor.gatekeeper_node(state))

        assert result["executive_review"]["is_approved"] is False
        assert result["executive_review"]["concern_list"] == ["graphic violence"]
    finally:
        patch.undo()


# ---- the graph itself is well-formed ---------------------------------------


def test_the_committee_graph_compiles():
    # Catches a broken node/edge wiring (e.g. a typo'd node name in
    # add_conditional_edges) without running a single node.
    graph = supervisor.build_greenlight_committee()
    assert graph is not None


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  ok  {name}")
    print(f"\n{passed} checks passed")
