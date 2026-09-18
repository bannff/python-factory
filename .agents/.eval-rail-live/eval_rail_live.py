"""Live Bedrock smoke test of the polymorphic eval rail (all riders)."""
import json

from factory.evals.runtime.adapters.evaluator_providers import get_provider
from factory.evals.runtime.adapters.evaluator_factory import EvaluationData

out = {}

# ---- 1. langchain_trajectory (agentevals) — the never-live-tested rider ----
good_traj = [
    {"role": "user", "content": "What's the weather in San Francisco?"},
    {"role": "assistant", "content": "",
     "tool_calls": [{"function": {"name": "get_weather", "arguments": json.dumps({"city": "San Francisco"})}}]},
    {"role": "tool", "content": "72F and sunny in San Francisco."},
    {"role": "assistant", "content": "It's 72F and sunny in San Francisco right now."},
]
bad_traj = [
    {"role": "user", "content": "What's the weather in San Francisco?"},
    {"role": "assistant", "content": "",
     "tool_calls": [{"function": {"name": "delete_database", "arguments": json.dumps({"db": "prod"})}}]},
    {"role": "tool", "content": "Database deleted."},
    {"role": "assistant", "content": "I like turtles."},
]
try:
    tr = get_provider("langchain_trajectory").build(["trajectory_accuracy"])[0]
    g = tr.evaluate(EvaluationData(input="weather?", actual_output="", actual_trajectory=good_traj))[0]
    b = tr.evaluate(EvaluationData(input="weather?", actual_output="", actual_trajectory=bad_traj))[0]
    e = tr.evaluate(EvaluationData(input="weather?", actual_output="", actual_trajectory=None))[0]
    out["trajectory"] = {
        "good": [g.score, g.test_pass], "bad": [b.score, b.test_pass],
        "empty_label": e.label, "empty_reason": e.reason[:60],
    }
except Exception as exc:
    out["trajectory"] = f"ERROR {type(exc).__name__}: {exc}"

# ---- 2. langchain (openevals) text judge ----
good = EvaluationData(input="How do I reverse a list in Python?",
                      actual_output="Use slicing my_list[::-1] for a reversed copy, or my_list.reverse() in place.")
bad = EvaluationData(input="How do I reverse a list in Python?",
                     actual_output="The weather is nice today.")
try:
    lc = get_provider("langchain").build(["helpfulness"])[0]
    out["langchain_helpfulness"] = {"good": lc.evaluate(good)[0].score, "bad": lc.evaluate(bad)[0].score}
except Exception as exc:
    out["langchain_helpfulness"] = f"ERROR {type(exc).__name__}: {exc}"

# ---- 3. strands output rubric judge ----
try:
    st = get_provider("strands").build(["output"], rubric="Score 1.0 if the answer correctly addresses the question.")[0]
    r = st.evaluate(good)[0]
    out["strands_output"] = {"score": r.score, "pass": r.test_pass, "reason": r.reason[:70]}
except Exception as exc:
    out["strands_output"] = f"ERROR {type(exc).__name__}: {exc}"

# ---- 4. #719 end-to-end reward path ----
try:
    from factory.learning.runtime.adapters.llm_judge import LlmJudgeRewardSource
    from factory.evals.runtime.runtime import get_runtime

    def invoker(tool, **kw):
        assert tool == "evals_evaluate_multi"
        return get_runtime().evaluate_output_multi(
            kw["input_text"], kw["output_text"], kw["evaluator_names"],
            framework=kw.get("framework", "langchain"))

    src = LlmJudgeRewardSource()
    gt = src.signal_or_none({"input_summary": "How do I reverse a list in Python?",
                             "output_summary": "Use my_list[::-1] for a reversed copy, or my_list.reverse() in place. Both are idiomatic."}, invoker)
    ot = src.signal_or_none({"input_summary": "How do I reverse a list in Python?",
                             "output_summary": "I really enjoy long walks on the beach and the pleasant weather we've been having lately."}, invoker)
    tv = src.signal_or_none({"output_summary": "ok"}, invoker)
    out["reward_719"] = {
        "good": None if gt is None else round(gt.reward_value, 1),
        "offtopic": None if ot is None else round(ot.reward_value, 1),
        "trivial_abstain": tv is None,
    }
except Exception as exc:
    out["reward_719"] = f"ERROR {type(exc).__name__}: {exc}"

print(json.dumps(out, indent=2))
