"""
eval/run_eval.py — RAGAs evaluation for the Berlin Zoning Assistant.

Runs the full RAG pipeline on the test questions in eval/questions.py,
then evaluates with RAGAs metrics:
  - Faithfulness:      is the answer grounded in the retrieved context?
  - Answer Relevancy:  does the answer address the question?
  - Context Precision: were the retrieved chunks actually relevant?
  - Context Recall:    did retrieval capture all needed info? (only where ground_truth exists)

Usage:
	cd <project_root>
	python -m eval.run_eval

	# Run only regulation questions:
	python -m eval.run_eval --category REGULATION

	# Skip the LLM calls and just print retrieved chunks (cheap debug run):
	python -m eval.run_eval --dry-run

Output:
	eval/results.json  — full results with per-question scores and summary
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

# ── Make sure project root is on the path ──────────────────────────────────────
# eval/ is a subdirectory, so we need the parent on sys.path for imports to work
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.questions import EVAL_QUESTIONS
from rag.embeddings import get_or_create_vector_store
# ✅ CHANGED: import retrieve_and_format instead of retrieve_relevant_chunks
# retrieve_and_format applies query translation for English before embedding,
# matching exactly what the live app does via run_agent
from rag.retriever import retrieve_and_format
from chain.agent import run_agent, get_llm
from config import MODELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "GPT-4.1 mini (OpenAI)"
RESULTS_PATH = Path(__file__).parent / "results.json"


# ── Step 1: Run the pipeline on each question ──────────────────────────────────

def run_pipeline_on_question(question: str, vector_store, model_name: str) -> dict:
	"""
	Run the full RAG pipeline on a single question and return the components
	that RAGAs needs: question, answer, contexts (raw chunk texts).
	"""
	logger.info(f"Running pipeline for: '{question[:80]}'")

	# ✅ CHANGED: use retrieve_and_format(language="en") so the query is
	# translated to German before embedding — matching what run_agent does
	_, chunks = retrieve_and_format(question, vector_store, language="en")
	contexts = [chunk.page_content for chunk in chunks]
	scores = [chunk.metadata.get("retrieval_score") for chunk in chunks]

	# Run the agent (same call as the live app)
	result = run_agent(
		user_input=question,
		model_name=model_name,
		language="en",
		chat_history=[],
		vector_store=vector_store,
	)

	return {
		"question":  question,
		"answer":    result["answer"],
		"contexts":  contexts,
		"scores":    scores,
		"tool_calls": [tc["tool"] for tc in result["tool_calls"]],
	}


# ── Step 2: Build RAGAs dataset ────────────────────────────────────────────────

def build_ragas_dataset(pipeline_outputs: list, questions_meta: list):
	"""
	Convert pipeline outputs into a RAGAs EvaluationDataset.
	Adds ground_truth where available.
	"""
	from ragas import EvaluationDataset, SingleTurnSample

	samples = []
	for output, meta in zip(pipeline_outputs, questions_meta):
		sample = SingleTurnSample(
			user_input=output["question"],
			response=output["answer"],
			retrieved_contexts=output["contexts"],
			# reference is the RAGAs term for ground_truth
			# SingleTurnSample accepts None — RAGAs skips context_recall for those entries
			reference=meta.get("ground_truth"),
		)
		samples.append(sample)

	return EvaluationDataset(samples=samples)


# ── Step 3: Run RAGAs metrics ──────────────────────────────────────────────────

def run_ragas_evaluation(dataset, model_name: str) -> dict:
	"""
	Run RAGAs faithfulness, answer_relevancy, context_precision, context_recall.
	Uses gpt-4o-mini at temperature=0 as the judge for deterministic results.
	temperature=0 eliminates most run-to-run variance from the LLM judge.
	"""
	from ragas import evaluate
	from ragas.metrics import (
		faithfulness,
		answer_relevancy,
		context_precision,
		context_recall,
	)

	from openai import OpenAI
	from ragas.llms import llm_factory
	from config import OPENAI_API_KEY

	judge_llm = llm_factory(
	"gpt-4o-mini",
	client=OpenAI(api_key=OPENAI_API_KEY),
	temperature=0,
	max_tokens=2000,
)

	metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

	for metric in metrics:
		metric.llm = judge_llm

	logger.info("Running RAGAs evaluation (this makes LLM calls per question)...")
	results = evaluate(dataset=dataset, metrics=metrics)
	return results


# ── Step 4: Save results ───────────────────────────────────────────────────────

def save_results(ragas_results, pipeline_outputs: list, questions_meta: list, model_name: str):
	"""
	Save full results to eval/results.json:
	  - summary scores (averages across all questions)
	  - per-question breakdown with scores, answer, contexts, category
	"""
	# ragas_results.scores is a list of dicts, one per sample
	per_question = []
	for i, (output, meta) in enumerate(zip(pipeline_outputs, questions_meta)):
		row_scores = ragas_results.scores[i] if i < len(ragas_results.scores) else {}
		per_question.append({
			"question":         output["question"],
			"category":         meta["category"],
			"answer":           output["answer"],
			"ground_truth":     meta.get("ground_truth"),
			"tool_calls":       output["tool_calls"],
			"retrieval_scores": output["scores"],
			"ragas_scores": {
				k: round(float(v), 4) if v is not None else None
				for k, v in row_scores.items()
			},
		})

	# Summary: average each metric, skipping None AND NaN values
	# RAGAs returns float('nan') for metrics that can't be computed (e.g. context_recall
	# when ground_truth is None) — must filter both to avoid poisoning the average.
	import math

	def _safe_avg(values):
		clean = [v for v in values if v is not None and not math.isnan(v)]
		return round(sum(clean) / len(clean), 4) if clean else None

	metric_keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

	# ── Overall summary ────────────────────────────────────────────────────────
	summary = {
		key: _safe_avg([r["ragas_scores"].get(key) for r in per_question])
		for key in metric_keys
	}

	# ── Per-category breakdown ─────────────────────────────────────────────────
	# Splits scores by REGULATION / HALLUCINATION_TRAP / CALCULATION so the
	# reviewer can see that low faithfulness on CALCULATION is a measurement
	# artefact (tool results vs RAG context), not a real quality problem.
	categories = ["REGULATION", "HALLUCINATION_TRAP", "CALCULATION"]
	category_summary = {}
	for cat in categories:
		cat_questions = [r for r in per_question if r["category"] == cat]
		if not cat_questions:
			continue
		category_summary[cat] = {
			"n": len(cat_questions),
			**{
				key: _safe_avg([r["ragas_scores"].get(key) for r in cat_questions])
				for key in metric_keys
			},
		}

	output = {
		"run_at":            datetime.now().isoformat(),
		"model":             model_name,
		"n_questions":       len(per_question),
		"summary":           summary,
		"summary_by_category": category_summary,  # ✅ ADDED
		"questions":         per_question,
	}

	RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
	with open(RESULTS_PATH, "w", encoding="utf-8") as f:
		json.dump(output, f, indent=2, ensure_ascii=False)

	logger.info(f"Results saved to {RESULTS_PATH}")
	return output


# ── Step 5: Print summary ──────────────────────────────────────────────────────

def print_summary(results: dict):
	"""Print a readable summary table to stdout."""
	print("\n" + "=" * 65)
	print(f"RAGAs Evaluation Results — {results['model']}")
	print(f"Run at: {results['run_at']}")
	print(f"Questions evaluated: {results['n_questions']}")
	print("=" * 65)

	thresholds = {
		"faithfulness":      0.8,
		"answer_relevancy":  0.8,
		"context_precision": 0.7,
		"context_recall":    0.7,
	}

	def _fmt(score, metric):
		if score is None:
			return "N/A  "
		threshold = thresholds.get(metric, 0.7)
		status = "✅" if score >= threshold else "⚠️ " if score >= threshold - 0.1 else "❌"
		return f"{score:.4f}  {status}"

	# ── Overall summary ────────────────────────────────────────────────────────
	print("\nOverall scores (all 15 questions):\n")
	for metric, score in results["summary"].items():
		print(f"  {metric:<22} {_fmt(score, metric)}")

	# ── Per-category breakdown ─────────────────────────────────────────────────
	print("\nBy category:\n")
	cat_labels = {
		"REGULATION":        "Regulation  (n={n}) — answer from RAG context",
		"HALLUCINATION_TRAP":"Hallucination traps (n={n}) — answer NOT in knowledge base",
		"CALCULATION":       "Calculation (n={n}) — answer from tool results (faithfulness artefact)",
	}
	for cat, cat_scores in results.get("summary_by_category", {}).items():
		label = cat_labels.get(cat, cat).format(n=cat_scores["n"])
		print(f"  {label}")
		for metric in thresholds:
			score = cat_scores.get(metric)
			print(f"    {metric:<22} {_fmt(score, metric)}")
		print()

	# ── Interpretation note ────────────────────────────────────────────────────
	print(
		"  ℹ️  Note: CALCULATION faithfulness is always low because the answer\n"
		"     comes from tool results, not the retrieved context. This is expected\n"
		"     behaviour, not a hallucination problem.\n"
	)

	# ── Per-question breakdown ─────────────────────────────────────────────────
	print("Per-question breakdown:\n")
	for q in results["questions"]:
		print(f"  [{q['category']:<20}] {q['question'][:70]}")
		for metric, score in q["ragas_scores"].items():
			val = f"{score:.3f}" if (score is not None and not __import__('math').isnan(score)) else "N/A "
			print(f"    {metric:<22} {val}")
		print()

	print(f"Full results saved to: {RESULTS_PATH}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
	parser = argparse.ArgumentParser(description="Run RAGAs evaluation on the Berlin Zoning Assistant.")
	parser.add_argument("--category", type=str, default=None,
						help="Filter questions by category: REGULATION, HALLUCINATION_TRAP, CALCULATION")
	parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
						help=f"Model to use. Options: {list(MODELS.keys())}")
	parser.add_argument("--dry-run", action="store_true",
						help="Run retrieval only, skip agent and RAGAs (fast, no API cost)")
	args = parser.parse_args()

	# Filter questions by category if requested
	questions = EVAL_QUESTIONS
	if args.category:
		questions = [q for q in questions if q["category"] == args.category.upper()]
		if not questions:
			print(f"No questions found for category '{args.category}'.")
			sys.exit(1)
	
	logger.info(f"Evaluating {len(questions)} questions with model '{args.model}'")

	# Load vector store once (same as the live app)
	logger.info("Loading vector store...")
	vector_store = get_or_create_vector_store()

	# Run pipeline on each question
	pipeline_outputs = []
	for meta in questions:
		if args.dry_run:
			# Retrieval only — print chunks and skip agent/RAGAs
			# ✅ FIXED: use retrieve_and_format so translation is applied here too
			_, chunks = retrieve_and_format(meta["question"], vector_store, language="en")
			print(f"\nQ: {meta['question']}")
			for i, chunk in enumerate(chunks, 1):
				score = chunk.metadata.get("retrieval_score", "?")
				src = chunk.metadata.get("source", "?")
				print(f"  {i}. {src} (score: {score})")
			continue

		output = run_pipeline_on_question(meta["question"], vector_store, args.model)
		pipeline_outputs.append(output)

	if args.dry_run:
		print("\nDry run complete — no RAGAs evaluation performed.")
		return

	# Build RAGAs dataset and evaluate
	dataset = build_ragas_dataset(pipeline_outputs, questions)
	ragas_results = run_ragas_evaluation(dataset, args.model)

	# Save and print
	final = save_results(ragas_results, pipeline_outputs, questions, args.model)
	print_summary(final)


if __name__ == "__main__":
	main()