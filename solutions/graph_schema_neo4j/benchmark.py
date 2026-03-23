"""Benchmark runner for Neo4j Schema Graph solution.

Reads test cases from benchmarks/test_cases/chatbi_questions.json,
runs each through the text-to-SQL pipeline with GPT5 and Opus,
and saves results to benchmarks/results/g3_neo4j_results.json.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.llm import ModelType
from solutions.graph_schema_neo4j.text_to_sql import TextToSQLPipeline

TEST_CASES_PATH = PROJECT_ROOT / "benchmarks" / "test_cases" / "chatbi_questions.json"
RESULTS_PATH = PROJECT_ROOT / "benchmarks" / "results" / "g3_neo4j_results.json"


def run_benchmark():
    """Run the full benchmark suite."""
    # Load test cases
    with open(TEST_CASES_PATH) as f:
        test_cases = json.load(f)

    logger.info(f"Loaded {len(test_cases)} test cases")

    pipeline = TextToSQLPipeline()
    all_results = []
    models = [ModelType.GPT5, ModelType.OPUS]

    try:
        for model in models:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running benchmark with model: {model.display_name}")
            logger.info(f"{'='*60}")

            for tc in test_cases:
                qid = tc["id"]
                question = tc["question"]
                logger.info(f"\n[{qid}] {question}")

                result = pipeline.run(question, model=model, execute=True)

                record = {
                    "question_id": qid,
                    "question": question,
                    "category": tc.get("category", ""),
                    "difficulty": tc.get("difficulty", ""),
                    "expected_tables": tc.get("expected_tables", []),
                    "model": model.value,
                    "relevant_tables_found": result["relevant_tables_found"],
                    "generated_sql": result["generated_sql"],
                    "sql_executable": result["sql_executable"],
                    "execution_result": _serialize_result(result["execution_result"]),
                    "latency_ms": result["latency_ms"],
                    "tokens_used": result.get("tokens_used", 0),
                    "graph_traversal_ms": result["graph_traversal_ms"],
                    "success": result["success"],
                    "error": result["error"],
                }
                all_results.append(record)

                status = "OK" if result["success"] else "FAIL"
                logger.info(
                    f"  [{status}] {model.value} | "
                    f"tables={result['relevant_tables_found'][:5]} | "
                    f"exec={result['sql_executable']} | "
                    f"{result['latency_ms']}ms"
                )

                # Small delay to avoid rate limiting
                time.sleep(1)

    finally:
        pipeline.close()

    # Compute summary
    summary = compute_summary(all_results, test_cases)

    output = {
        "solution": "G3-Neo4j-Schema-Graph",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": all_results,
        "summary": summary,
    }

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\nResults saved to {RESULTS_PATH}")
    logger.info(f"Summary: {json.dumps(summary, indent=2)}")

    return output


def compute_summary(results: list, test_cases: list) -> dict:
    """Compute benchmark summary statistics."""
    gpt5_results = [r for r in results if r["model"] == "gpt5"]
    opus_results = [r for r in results if r["model"] == "opus"]

    gpt5_success = sum(1 for r in gpt5_results if r["success"])
    opus_success = sum(1 for r in opus_results if r["success"])

    gpt5_exec = sum(1 for r in gpt5_results if r["sql_executable"])
    opus_exec = sum(1 for r in opus_results if r["sql_executable"])

    all_latencies = [r["latency_ms"] for r in results]
    graph_latencies = [r["graph_traversal_ms"] for r in results]

    # Table recall: check if expected tables were found
    gpt5_table_recall = _compute_table_recall(gpt5_results)
    opus_table_recall = _compute_table_recall(opus_results)

    return {
        "total_questions": len(test_cases),
        "success_gpt5": gpt5_success,
        "success_opus": opus_success,
        "executable_gpt5": gpt5_exec,
        "executable_opus": opus_exec,
        "success_rate_gpt5": round(gpt5_success / max(len(gpt5_results), 1) * 100, 1),
        "success_rate_opus": round(opus_success / max(len(opus_results), 1) * 100, 1),
        "avg_latency_ms": round(sum(all_latencies) / max(len(all_latencies), 1)),
        "avg_graph_traversal_ms": round(sum(graph_latencies) / max(len(graph_latencies), 1)),
        "table_recall_gpt5": round(gpt5_table_recall * 100, 1),
        "table_recall_opus": round(opus_table_recall * 100, 1),
    }


def _compute_table_recall(results: list) -> float:
    """Compute average table recall rate."""
    if not results:
        return 0.0
    recalls = []
    for r in results:
        expected = set(r.get("expected_tables", []))
        found = set(r.get("relevant_tables_found", []))
        if expected:
            recall = len(expected & found) / len(expected)
            recalls.append(recall)
    return sum(recalls) / max(len(recalls), 1)


def _serialize_result(result):
    """Ensure execution result is JSON serializable."""
    if result is None:
        return None
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return str(result)


if __name__ == "__main__":
    logger.info("Starting Neo4j Schema Graph benchmark...")
    output = run_benchmark()
    logger.info("Benchmark complete!")
