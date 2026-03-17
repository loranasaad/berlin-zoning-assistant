"""
eval/run_tool_eval.py — Tool calling evaluation for the Berlin Zoning Assistant.

Two complementary evaluation approaches:
  1. Deterministic — tool selection accuracy + parameter accuracy (free, instant)
  2. LLM-as-judge  — RAGAs DiscreteMetric judges whether each tool choice was reasonable

The side-by-side comparison is the most revealing part: deterministic checks are strict
(binary match), while LLM-as-judge can recognise that a "wrong" tool choice was
actually reasonable given ambiguous phrasing, or flag a technically "correct" match
as dubious.

Usage:
	cd <project_root>

	# Full evaluation (runs agent + LLM judge)
	python -m eval.run_tool_eval

	# Deterministic only (no LLM judge — fast, cheap)
	python -m eval.run_tool_eval --no-judge

	# Filter by difficulty
	python -m eval.run_tool_eval --difficulty EASY
	python -m eval.run_tool_eval --difficulty EDGE_CASE

Output:
	eval/tool_results.json — full results with per-case scores and summary
"""

import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.tool_questions import TOOL_TEST_CASES
from rag.embeddings import get_or_create_vector_store
from chain.agent import run_agent
from config import MODELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_MODEL  = "GPT-4.1 mini (OpenAI)"
RESULTS_PATH   = Path(__file__).parent / "tool_results.json"


# ── Step 1: Run agent on each test case ───────────────────────────────────────

def run_agent_on_case(test_case: dict, vector_store, model_name: str) -> dict:
	"""Run the agent and capture which tools were called and with what parameters."""
	logger.info(f"[{test_case['difficulty']}] {test_case['question'][:80]}")

	result = run_agent(
		user_input=test_case["question"],
		model_name=model_name,
		language="en",
		chat_history=[],
		vector_store=vector_store,
	)

	# Extract tool calls as {tool_name: params_dict}
	actual_tools = [tc["tool"] for tc in result["tool_calls"]]
	actual_params = {tc["tool"]: tc["input"] for tc in result["tool_calls"]}

	return {
		"question":      test_case["question"],
		"difficulty":    test_case["difficulty"],
		"note":          test_case["note"],
		"expected_tools": test_case["expected_tools"],
		"expected_params": test_case["expected_params"],
		"actual_tools":  actual_tools,
		"actual_params": actual_params,
		"answer":        result["answer"],
	}


# ── Step 2: Deterministic evaluation ─────────────────────────────────────────

def evaluate_deterministic(run_result: dict) -> dict:
	"""
	Check tool selection and parameter accuracy deterministically.

	Tool selection: did the agent call exactly the expected tools?
	  - Correct set but wrong order → pass (order doesn't matter)
	  - Extra tool called           → fail
	  - Missing tool                → fail

	Parameter accuracy: for each expected tool, are the expected params present
	and correct in the actual call? Only checks keys listed in expected_params —
	extra keys in the actual call are ignored.
	"""
	expected = set(run_result["expected_tools"])
	actual   = set(run_result["actual_tools"])

	tool_selection_correct = expected == actual

	# Parameter check — only for tools that were correctly called
	param_results = {}
	for tool_name, expected_p in run_result["expected_params"].items():
		if tool_name not in run_result["actual_params"]:
			param_results[tool_name] = {
				"correct": False,
				"reason": "Tool was not called",
			}
			continue

		actual_p = run_result["actual_params"][tool_name]
		mismatches = []
		for key, expected_val in expected_p.items():
			actual_val = actual_p.get(key)
			# ✅ CHANGED: try numeric comparison first to avoid false failures
			# e.g. expected 1200.0, got 1200 → should pass
			try:
				match = float(actual_val) == float(expected_val)
			except (TypeError, ValueError):
				match = str(actual_val).strip().lower() == str(expected_val).strip().lower()
			if not match:
				mismatches.append(
					f"  '{key}': expected {expected_val!r}, got {actual_val!r}"
				)
		if mismatches:
			param_results[tool_name] = {
				"correct": False,
				"reason": "Parameter mismatch:\n" + "\n".join(mismatches),
			}
		else:
			param_results[tool_name] = {"correct": True, "reason": ""}

	params_all_correct = all(r["correct"] for r in param_results.values()) if param_results else True

	return {
		"tool_selection_correct": tool_selection_correct,
		"params_correct":         params_all_correct,
		"param_details":          param_results,
		"unexpected_tools":       list(actual - expected),
		"missing_tools":          list(expected - actual),
	}


# ── Step 3: LLM-as-judge via RAGAs DiscreteMetric ─────────────────────────────

def evaluate_with_judge(run_results: list, model_name: str) -> list:
	"""
	Use RAGAs DiscreteMetric to judge whether each tool selection was reasonable.
	Returns a verdict ('correct' / 'incorrect') and written reasoning per case.

	Compatible with ragas 0.4.3:
	  - DiscreteMetric(name, prompt, allowed_values)
	  - metric.score(llm=llm, **prompt_kwargs) → result.value, result.reason
	"""
	from ragas.metrics import DiscreteMetric
	from openai import OpenAI
	from ragas.llms import llm_factory
	from config import OPENAI_API_KEY

	judge_llm = llm_factory("gpt-4o-mini", client=OpenAI(api_key=OPENAI_API_KEY))

	TOOL_DESCRIPTIONS = (
		"Available tools:\n"
		"- get_full_zoning_report: Use when the user provides a Berlin address.\n"
		"- calculate_buildable_area: Use when zone type and plot area (m²) are known but no address is given.\n"
		"- calculate_parking_requirements: Use for parking space calculations.\n"
		"- get_demographics: Use for district demographics.\n"
		"- estimate_construction_cost: Use for cost estimates when no address is given.\n"
		"- get_construction_price_index: Use for construction price trends.\n"
		"- (none): Use no tool for general knowledge, definitions, or out-of-domain queries.\n"
	)

	# ✅ CHANGED: use prompt= with placeholders, allowed_values= (no rubric/values/definition)
	judge_metric = DiscreteMetric(
		name="tool_selection_reasonable",
		prompt=(
			"You are evaluating an AI assistant for Berlin building regulations.\n\n"
			+ TOOL_DESCRIPTIONS + "\n"
			"User question: {user_input}\n"
			"Agent response: {response}\n\n"
			"Was the agent's tool selection reasonable for this question? "
			"Return 'correct' if the tool choice makes sense, "
			"'incorrect' if the wrong tool was called, a tool was called unnecessarily, "
			"or a required tool was skipped."
		),
		allowed_values=["correct", "incorrect"],
	)

	judge_outputs = []
	for result in run_results:
		tools_called = result["actual_tools"] if result["actual_tools"] else ["(none)"]
		response_text = (
			f"Tools called: {', '.join(tools_called)}\n"
			f"Agent answer: {result['answer'][:500]}"
		)
		try:
			score_result = judge_metric.score(
				llm=judge_llm,
				user_input=result["question"],
				response=response_text,
			)
			judge_outputs.append({
				"verdict":   score_result.value,
				"reasoning": getattr(score_result, "reason", ""),
			})
		except Exception as e:
			logger.warning(f"Judge failed for '{result['question'][:60]}': {e}")
			judge_outputs.append({"verdict": "error", "reasoning": str(e)})

	return judge_outputs


# ── Step 4: Save and print results ────────────────────────────────────────────

def save_results(run_results: list, det_results: list, judge_outputs: list | None, model_name: str) -> dict:
	"""Combine all results and save to eval/tool_results.json."""
	per_case = []
	for i, (run, det) in enumerate(zip(run_results, det_results)):
		judge = judge_outputs[i] if judge_outputs else None
		per_case.append({
			"question":               run["question"],
			"difficulty":             run["difficulty"],
			"note":                   run["note"],
			"expected_tools":         run["expected_tools"],
			"actual_tools":           run["actual_tools"],
			"tool_selection_correct": det["tool_selection_correct"],
			"params_correct":         det["params_correct"],
			"param_details":          det["param_details"],
			"unexpected_tools":       det["unexpected_tools"],
			"missing_tools":          det["missing_tools"],
			"judge_verdict":          judge["verdict"] if judge else None,
			"judge_reasoning":        judge["reasoning"] if judge else None,
			"answer_preview":         run["answer"][:200],
		})

	# Summary by difficulty
	difficulties = ["EASY", "MEDIUM", "HARD", "EDGE_CASE"]
	summary = {}
	for diff in difficulties:
		cases = [c for c in per_case if c["difficulty"] == diff]
		if not cases:
			continue
		tool_acc   = sum(1 for c in cases if c["tool_selection_correct"]) / len(cases)
		param_acc  = sum(1 for c in cases if c["params_correct"]) / len(cases)
		judge_acc  = None
		if judge_outputs:
			judge_correct = [c for c in cases if c.get("judge_verdict") == "correct"]
			judge_acc = len(judge_correct) / len(cases)
		summary[diff] = {
			"n":                     len(cases),
			"tool_selection_acc":    round(tool_acc, 3),
			"param_accuracy":        round(param_acc, 3),
			"judge_accuracy":        round(judge_acc, 3) if judge_acc is not None else None,
		}

	# Overall
	total = len(per_case)
	overall_tool = sum(1 for c in per_case if c["tool_selection_correct"]) / total
	overall_param = sum(1 for c in per_case if c["params_correct"]) / total
	summary["OVERALL"] = {
		"n":                  total,
		"tool_selection_acc": round(overall_tool, 3),
		"param_accuracy":     round(overall_param, 3),
	}

	output = {
		"run_at":   datetime.now().isoformat(),
		"model":    model_name,
		"summary":  summary,
		"cases":    per_case,
	}

	RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
	with open(RESULTS_PATH, "w", encoding="utf-8") as f:
		json.dump(output, f, indent=2, ensure_ascii=False)

	logger.info(f"Results saved to {RESULTS_PATH}")
	return output


def print_summary(results: dict):
	"""Print a readable summary table."""
	print("\n" + "=" * 70)
	print(f"Tool Calling Evaluation — {results['model']}")
	print(f"Run at: {results['run_at']}")
	print("=" * 70)
	print(f"\n{'Difficulty':<14} {'N':>3}  {'Tool sel.':>10}  {'Params':>10}  {'LLM judge':>10}")
	print("-" * 56)

	for diff, s in results["summary"].items():
		tool_acc  = f"{s['tool_selection_acc']:.0%}"
		param_acc = f"{s['param_accuracy']:.0%}"
		judge_acc = f"{s['judge_accuracy']:.0%}" if s.get("judge_accuracy") is not None else "N/A"
		print(f"{diff:<14} {s['n']:>3}  {tool_acc:>10}  {param_acc:>10}  {judge_acc:>10}")

	print("\nPer-case breakdown:\n")
	for c in results["cases"]:
		tool_ok  = "✅" if c["tool_selection_correct"] else "❌"
		param_ok = "✅" if c["params_correct"] else "❌"
		judge_icon = {"correct": "✅", "incorrect": "❌", "error": "⚠️ "}.get(
			c.get("judge_verdict", ""), "—"
		)
		print(f"  [{c['difficulty']:<10}] {tool_ok} tool  {param_ok} params  {judge_icon} judge")
		print(f"             Q: {c['question'][:70]}")
		if c["missing_tools"]:
			print(f"             Missing:    {c['missing_tools']}")
		if c["unexpected_tools"]:
			print(f"             Unexpected: {c['unexpected_tools']}")
		if c.get("judge_reasoning"):
			print(f"             Judge: {c['judge_reasoning'][:120]}")
		print()

	print(f"Full results saved to: {RESULTS_PATH}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
	parser = argparse.ArgumentParser(description="Run tool calling evaluation.")
	parser.add_argument("--difficulty", type=str, default=None,
						help="Filter by difficulty: EASY, MEDIUM, HARD, EDGE_CASE")
	parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
						help=f"Model to use. Options: {list(MODELS.keys())}")
	parser.add_argument("--no-judge", action="store_true",
						help="Skip LLM-as-judge step (deterministic only, much cheaper)")
	args = parser.parse_args()

	cases = TOOL_TEST_CASES
	if args.difficulty:
		cases = [c for c in cases if c["difficulty"] == args.difficulty.upper()]
		if not cases:
			print(f"No cases found for difficulty '{args.difficulty}'.")
			sys.exit(1)

	logger.info(f"Evaluating {len(cases)} tool calling cases with model '{args.model}'")

	vector_store = get_or_create_vector_store()

	# Step 1: Run agent on all cases
	run_results = []
	for case in cases:
		result = run_agent_on_case(case, vector_store, args.model)
		run_results.append(result)

	# Step 2: Deterministic evaluation
	det_results = [evaluate_deterministic(r) for r in run_results]

	# Step 3: LLM-as-judge (optional)
	judge_outputs = None
	if not args.no_judge:
		logger.info("Running LLM-as-judge evaluation...")
		judge_outputs = evaluate_with_judge(run_results, args.model)

	# Step 4: Save and print
	final = save_results(run_results, det_results, judge_outputs, args.model)
	print_summary(final)


if __name__ == "__main__":
	main()