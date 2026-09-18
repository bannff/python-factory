"""Edge-case Hypothesis property tests for the recon factory.

Sister file: ``test_factories_recon.py`` (implementer-authored,
covers shape / DAG / pure-determinism over filled ctx). This file
pins recon-specific properties the implementer's 50-example purity
test doesn't fuzz (bd python-factory-s5ev qa-tester):

  - ``build_recon_tasks()`` does NOT mutate the caller's ctx dict
    (factory takes ``_ctx: dict`` and ignores it; verify nothing
    drifts back through aliasing).
  - Concurrent recon factory invocation from many threads returns
    equivalent task lists (pure constant — bd python-factory-uffq
    ``_LazyRegistry`` had a known concurrent-resolution bug).
  - Recon factory output is structurally stable across arbitrary
    ctx shapes — extra keys, None values, large payloads — recon
    reads NOTHING from ctx by design.
  - Recon registration round-trips through Pydantic JSON schema
    (model_dump → model_validate ⇒ identity), pinning that the
    string factory key survives serialization.

Both this file and the sister are <200 LOC per repo tenet.
"""
from __future__ import annotations

import threading

from hypothesis import given, settings, strategies as st

from factory.agent.registry.defaults_recon_graph import (
    RECON_REGISTRATION, build_recon_tasks,
)
from factory.agent.registry.factories import get_factory
from factory.agent.runtime.registry_contracts import WorkflowConfig


# Strategy for arbitrary ctx values — covers what a real run might
# pass through (envelope_scope merges principal/tenant + run_id +
# target_app + arbitrary user data).
_CTX_VALUE: st.SearchStrategy = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.text(max_size=200),
    st.lists(st.text(max_size=20), max_size=10),
)


# --- Ctx mutation immunity --------------------------------------------

@settings(max_examples=30, deadline=None)
@given(
    extra=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=_CTX_VALUE,
        max_size=10,
    ),
)
def test_recon_factory_does_not_mutate_caller_ctx(
    extra: dict,
) -> None:
    """Recon factory ignores ctx — must not write back through aliasing.

    Important because ``WorkflowExecutor._build_tasks`` passes the
    runtime context dict in directly without copying. A factory
    that mutated ctx would silently leak into the executor's view.
    """
    base = {"run_id": "x", "target_app": "y"}
    base.update(extra)
    snapshot = {k: (list(v) if isinstance(v, list) else v)
                for k, v in base.items()}
    factory = get_factory("recon")
    factory(base)
    # All scalar/list values must equal their pre-call snapshot.
    assert set(base.keys()) == set(snapshot.keys())
    for k, v in snapshot.items():
        assert base[k] == v, f"factory mutated ctx[{k!r}]"


# --- Structural stability across arbitrary ctx ------------------------

@settings(max_examples=40, deadline=None)
@given(
    ctx=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=_CTX_VALUE,
        max_size=8,
    ),
)
def test_recon_factory_output_stable_across_arbitrary_ctx(
    ctx: dict,
) -> None:
    """Recon takes NO inputs from ctx — output must equal the
    canonical baseline regardless of what's in ctx."""
    factory = get_factory("recon")
    baseline = factory({})
    out = factory(ctx)
    assert out == baseline, "recon factory leaked ctx into output"
    # Spot-check the contract surface.
    assert len(out) == 4
    assert [t["task_id"] for t in out] == [
        "recon-lead", "recon-verify", "recon-summary", "eval-scorer",
    ]


# --- Concurrent factory invocation (uffq regression sniff) -----------

@settings(max_examples=15, deadline=None)
@given(
    n_threads=st.integers(min_value=4, max_value=24),
)
def test_recon_factory_is_threadsafe(n_threads: int) -> None:
    """Many threads call get_factory('recon') and the factory.

    bd python-factory-uffq's ``_LazyRegistry`` had a documented
    lazy-resolution path (``defaults_recon_graph`` import on first
    ``get_factory('recon')`` call). This test pins that concurrent
    callers all see equivalent task lists.
    """
    factory = get_factory("recon")
    serial = factory({})

    results: dict[int, list[dict]] = {}
    lock = threading.Lock()
    barrier = threading.Barrier(n_threads)

    def call(idx: int) -> None:
        # Re-resolve through the registry on every call to exercise
        # the LazyRegistry path under contention.
        f = get_factory("recon")
        barrier.wait()
        out = f({"run_id": f"r-{idx}", "target_app": f"a-{idx}"})
        with lock:
            results[idx] = out

    threads = [
        threading.Thread(target=call, args=(i,))
        for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(n_threads):
        assert results[i] == serial, (
            f"concurrent recon call {i} drifted from serial baseline"
        )


# --- Registration JSON round-trip (factory key survives) -------------

def test_recon_registration_json_round_trip_preserves_factory_key() -> None:
    """``WorkflowConfig`` round-trips through model_dump → validate.

    Pre-condition (ii) of the strands-expert verdict: the factory
    key is a STRING, not an embedded callable, precisely so the
    registration can be JSON-dumped and re-loaded without import-
    time side effects. Pin it.
    """
    dumped = RECON_REGISTRATION.model_dump()
    assert dumped["factory"] == "recon"
    assert dumped["kind"] == "workflow"
    rebuilt = WorkflowConfig.model_validate(dumped)
    assert rebuilt == RECON_REGISTRATION
    assert rebuilt.factory == "recon"


def test_recon_registration_json_dump_is_pure_data() -> None:
    """No callables in the dumped representation — pre-condition (i).

    Walk the dumped tree and assert every leaf is a JSON-native type.
    A leaked callable here would mean ``factory`` slipped past the
    string-key contract.
    """
    dumped = RECON_REGISTRATION.model_dump()

    def is_pure_data(value: object) -> bool:
        if value is None or isinstance(value, (bool, int, float, str)):
            return True
        if isinstance(value, list):
            return all(is_pure_data(v) for v in value)
        if isinstance(value, dict):
            return all(
                isinstance(k, str) and is_pure_data(v)
                for k, v in value.items()
            )
        return False

    assert is_pure_data(dumped), f"non-pure-data leaf in {dumped!r}"
