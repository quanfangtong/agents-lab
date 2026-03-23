"""Benchmark the Graph-enhanced Text-to-SQL pipeline.

Reads test cases from benchmarks/test_cases/chatbi_questions.json,
runs the full pipeline for each question with both GPT-5.4 and Claude Opus,
and writes results to benchmarks/results/g2_kuzu_results.json.
"""

import json
import sys
import time
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.llm.models import ModelType
from solutions.graph_schema_kuzu.text_to_sql import TextToSQL

TEST_CASES_PATH = PROJECT_ROOT / "benchmarks" / "test_cases" / "chatbi_questions.json"
RESULTS_PATH = PROJECT_ROOT / "benchmarks" / "results" / "g2_kuzu_results.json"


def load_test_cases() -> list[dict]:
    """Load benchmark test cases."""
    with open(TEST_CASES_PATH) as f:
        return json.load(f)


def run_benchmark(models: list[ModelType] = None) -> dict:
    """Run benchmark across all test cases and models.

    Returns:
        Full benchmark results dict.
    """
    if models is None:
        models = [ModelType.GPT5, ModelType.OPUS]

    test_cases = load_test_cases()
    pipeline = TextToSQL()

    all_results = {
        "benchmark_info": {
            "solution": "G2: Kuzu Embedded Schema Graph",
            "test_cases_count": len(test_cases),
            "models": [m.display_name for m in models],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "results_by_model": {},
        "summary": {},
    }

    for model in models:
        model_name = model.display_name
        logger.info(f"\n{'='*60}\nRunning benchmark with {model_name}")

        model_results = []
        success_count = 0
        total_latency = 0

        for tc in test_cases:
            qid = tc["id"]
            question = tc["question"]
            logger.info(f"[{qid}] {question}")

            try:
                result = pipeline.run(question, model=model)

                record = {
                    "id": qid,
                    "question": question,
                    "category": tc["category"],
                    "difficulty": tc["difficulty"],
                    "expected_tables": tc["expected_tables"],
                    "generated_sql": result["sql"],
                    "schema_tables_found": result["schema_tables"],
                    "execution_result": {
                        "success": result["success"],
                        "row_count": result["execution_result"]["row_count"],
                        "error": result["execution_result"]["error"],
                        "sample_data": result["execution_result"]["data"][:5],
                        "columns": result["execution_result"]["columns"],
                    },
                    "latency_ms": result["total_time_ms"],
                    "graph_time_ms": result["graph_time_ms"],
                    "llm_time_ms": result["llm_time_ms"],
                    "model": model_name,
                    "success": result["success"],
                }

                if result["success"]:
                    success_count += 1
                total_latency += result["total_time_ms"]

                logger.info(
                    f"  -> {'OK' if result['success'] else 'FAIL'} "
                    f"({result['total_time_ms']}ms)"
                )

            except Exception as e:
                logger.error(f"  -> ERROR: {e}")
                record = {
                    "id": qid,
                    "question": question,
                    "category": tc["category"],
                    "difficulty": tc["difficulty"],
                    "expected_tables": tc["expected_tables"],
                    "generated_sql": None,
                    "schema_tables_found": [],
                    "execution_result": {
                        "success": False,
                        "row_count": 0,
                        "error": str(e),
                        "sample_data": [],
                        "columns": [],
                    },
                    "latency_ms": 0,
                    "graph_time_ms": 0,
                    "llm_time_ms": 0,
                    "model": model_name,
                    "success": False,
                }

            model_results.append(record)

        # Model summary
        total = len(test_cases)
        avg_latency = total_latency // total if total > 0 else 0

        all_results["results_by_model"][model_name] = model_results
        all_results["summary"][model_name] = {
            "total": total,
            "success": success_count,
            "fail": total - success_count,
            "success_rate": f"{success_count/total*100:.1f}%",
            "avg_latency_ms": avg_latency,
        }

        logger.info(
            f"\n{model_name} Summary: {success_count}/{total} "
            f"({success_count/total*100:.1f}%), avg latency: {avg_latency}ms"
        )

    return all_results


def save_results(results: dict):
    """Save benchmark results to JSON."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Convert any non-serializable types
    def default_serializer(obj):
        if hasattr(obj, "__str__"):
            return str(obj)
        return obj

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=default_serializer)

    logger.info(f"Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt5", "opus", "both"], default="both")
    args = parser.parse_args()

    if args.model == "gpt5":
        models = [ModelType.GPT5]
    elif args.model == "opus":
        models = [ModelType.OPUS]
    else:
        models = [ModelType.GPT5, ModelType.OPUS]

    logger.info(f"Starting G2 Kuzu benchmark with model(s): {[m.display_name for m in models]}")
    results = run_benchmark(models=models)
    save_results(results)
    logger.info("Benchmark complete!")

    # Print summary
    for model, summary in results["summary"].items():
        print(f"\n{model}:")
        print(f"  Success: {summary['success']}/{summary['total']} ({summary['success_rate']})")
        print(f"  Avg latency: {summary['avg_latency_ms']}ms")
