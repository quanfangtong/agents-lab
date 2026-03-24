#!/usr/bin/env python3
"""
Multi-Solution Benchmark Runner
5 方案 × 2 模型 × 30 题 = 300 次 LLM 调用

用法:
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --solutions A,B --models gpt5 --questions 5
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.llm import get_llm_client, ModelType
from solutions.baseline_text2sql import BaselineSolution
from solutions.static_metadata import StaticMetadataSolution
from solutions.graph_kuzu import KuzuSolution

SOLUTIONS_MAP = {
    "A": BaselineSolution,
    "B": KuzuSolution,
    "E": StaticMetadataSolution,
}

# Neo4j 和 FalkorDB 需要 Docker 运行，动态导入
def load_optional_solutions():
    try:
        from solutions.graph_neo4j import Neo4jSolution
        SOLUTIONS_MAP["C"] = Neo4jSolution
        logger.info("Neo4j solution loaded")
    except Exception as e:
        logger.warning(f"Neo4j solution unavailable: {e}")

    try:
        from solutions.graph_falkordb import FalkorDBSolution
        SOLUTIONS_MAP["D"] = FalkorDBSolution
        logger.info("FalkorDB solution loaded")
    except Exception as e:
        logger.warning(f"FalkorDB solution unavailable: {e}")


def load_questions(limit: int = 0) -> list[dict]:
    qfile = Path(__file__).parent / "test_cases" / "chatbi_questions_datamart.json"
    with open(qfile) as f:
        questions = json.load(f)
    if limit > 0:
        questions = questions[:limit]
    return questions


def run_solution_batch(sol_key: str, models: list[ModelType], questions: list[dict]) -> list[dict]:
    """跑单个方案的全部题目（用于并行）"""
    if sol_key not in SOLUTIONS_MAP:
        logger.warning(f"Solution {sol_key} not available")
        return []

    llm = get_llm_client()
    sol = SOLUTIONS_MAP[sol_key]()
    logger.info(f"[{sol.name}] Setting up...")
    try:
        sol.setup()
    except Exception as e:
        logger.error(f"[{sol.name}] Setup failed: {e}")
        return []
    logger.info(f"[{sol.name}] Setup complete")

    results = []
    for model in models:
        for q in questions:
            qid = q["id"]
            question = q["question"]
            logger.info(f"[{sol.name}/{model.value}] [{qid}] {question[:35]}...")

            try:
                result = sol.run(question, llm, model)
            except Exception as e:
                result = {
                    "solution": sol.name, "question": question,
                    "model": model.display_name, "success": False,
                    "error": str(e)[:300],
                }

            result["question_id"] = qid
            result["category"] = q.get("category", "")
            result["difficulty"] = q.get("difficulty", "")
            result["domain"] = q.get("domain", "")
            result["expected_tables"] = q.get("expected_tables", [])

            if result.get("schema_tables") and result.get("expected_tables"):
                found = set(result["schema_tables"])
                expected = set(result["expected_tables"])
                result["table_recall"] = len(found & expected) / len(expected) if expected else 0
            else:
                result["table_recall"] = None

            status = "OK" if result.get("success") else "FAIL"
            ms = result.get("total_ms", 0)
            logger.info(f"[{sol.name}/{model.value}] [{qid}] -> {status} ({ms}ms)")
            results.append(result)

    return results


def run_benchmark(solutions: list[str], models: list[ModelType], questions: list[dict]):
    """全部方案并行跑"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import shutil

    total = len(solutions) * len(models) * len(questions)
    logger.info(f"Running {len(solutions)} solutions ALL PARALLEL ({total} total calls)")

    # Kuzu 需要独立的数据库副本（嵌入式锁限制）
    kuzu_src = Path(__file__).resolve().parents[1] / "data" / "kuzu_datamart_graph"
    kuzu_copy = Path(__file__).resolve().parents[1] / "data" / "kuzu_datamart_graph_bench"
    if "B" in solutions and kuzu_src.exists():
        if kuzu_copy.exists():
            if kuzu_copy.is_dir():
                shutil.rmtree(kuzu_copy)
            else:
                kuzu_copy.unlink()
        shutil.copy2(kuzu_src, kuzu_copy)
        from solutions import graph_kuzu
        graph_kuzu.KUZU_DB_PATH = str(kuzu_copy)
        logger.info(f"Kuzu DB copied to {kuzu_copy} for parallel access")

    all_results = []
    with ThreadPoolExecutor(max_workers=min(5, len(solutions))) as executor:
        futures = {
            executor.submit(run_solution_batch, sol_key, models, questions): sol_key
            for sol_key in solutions
        }
        for future in as_completed(futures):
            sol_key = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                logger.info(f"[{sol_key}] Completed: {len(results)} results")
            except Exception as e:
                logger.error(f"[{sol_key}] Failed: {e}")

    # 清理 Kuzu 副本
    if kuzu_copy.exists():
        if kuzu_copy.is_dir():
            shutil.rmtree(kuzu_copy, ignore_errors=True)
        else:
            kuzu_copy.unlink(missing_ok=True)

    return all_results


def summarize(results: list[dict]) -> dict:
    """生成汇总统计"""
    from collections import defaultdict
    summary = defaultdict(lambda: defaultdict(lambda: {"total": 0, "success": 0, "total_ms": 0, "total_tokens": 0}))

    for r in results:
        key = (r.get("solution", "?"), r.get("model", "?"))
        s = summary[key[0]][key[1]]
        s["total"] += 1
        if r.get("success"):
            s["success"] += 1
        s["total_ms"] += r.get("total_ms", 0)
        s["total_tokens"] += r.get("schema_token_estimate", 0)

    output = {}
    for sol, models in summary.items():
        output[sol] = {}
        for model, stats in models.items():
            output[sol][model] = {
                "total": stats["total"],
                "success": stats["success"],
                "success_rate": f"{stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)" if stats["total"] else "N/A",
                "avg_ms": stats["total_ms"] // stats["total"] if stats["total"] else 0,
                "avg_tokens": stats["total_tokens"] // stats["total"] if stats["total"] else 0,
            }

    return output


def main():
    parser = argparse.ArgumentParser(description="Multi-Solution Benchmark")
    parser.add_argument("--solutions", default="A,B,E", help="Comma-separated solution keys (A,B,C,D,E)")
    parser.add_argument("--models", default="gpt5", help="Comma-separated: gpt5,opus")
    parser.add_argument("--questions", type=int, default=0, help="Limit number of questions (0=all)")
    args = parser.parse_args()

    load_optional_solutions()

    sol_keys = [s.strip() for s in args.solutions.split(",")]
    model_map = {"gpt5": ModelType.GPT5, "opus": ModelType.OPUS}
    models = [model_map[m.strip()] for m in args.models.split(",") if m.strip() in model_map]
    questions = load_questions(args.questions)

    logger.info(f"Benchmark: {len(sol_keys)} solutions × {len(models)} models × {len(questions)} questions = {len(sol_keys)*len(models)*len(questions)} runs")

    results = run_benchmark(sol_keys, models, questions)
    summary = summarize(results)

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "config": {
            "solutions": sol_keys,
            "models": [m.value for m in models],
            "question_count": len(questions),
        },
        "summary": summary,
        "results": results,
    }

    outdir = Path(__file__).parent / "results"
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"benchmark_{timestamp}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"\nResults saved to: {outfile}")
    logger.info(f"\nSummary:")
    for sol, models_data in summary.items():
        for model, stats in models_data.items():
            logger.info(f"  {sol} / {model}: {stats['success_rate']} (avg {stats['avg_ms']}ms, ~{stats['avg_tokens']} tokens)")


if __name__ == "__main__":
    main()
