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
from solutions.baseline_text2sql import Text2SQLSolution
from solutions.graph_kuzu import KuzuSolution

SOLUTIONS_MAP = {
    "A": Text2SQLSolution,
    "B": KuzuSolution,
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



def run_single_combo(sol_key: str, model: ModelType, questions: list[dict]) -> list[dict]:
    """跑单个 (方案, 模型) 组合的全部题目"""
    if sol_key not in SOLUTIONS_MAP:
        logger.warning(f"Solution {sol_key} not available")
        return []

    llm = get_llm_client()
    sol = SOLUTIONS_MAP[sol_key]()
    logger.info(f"[{sol.name}/{model.value}] Setting up...")
    try:
        sol.setup()
    except Exception as e:
        logger.error(f"[{sol.name}/{model.value}] Setup failed: {e}")
        return []

    results = []
    for q in questions:
        qid = q["id"]
        question = q["question"]
        logger.info(f"[{sol.name}/{model.value}] [{qid}] {question[:35]}...")
        try:
            result = sol.run(question, llm, model)
        except Exception as e:
            result = {"solution": sol.name, "question": question, "model": model.display_name, "success": False, "error": str(e)[:300]}

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
    """全并行：每个 (方案, 模型) 组合一个线程"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import shutil

    combos = [(sol, model) for sol in solutions for model in models]
    total = len(combos) * len(questions)
    logger.info(f"Running {len(combos)} combos ALL PARALLEL ({total} total calls)")

    # Kuzu 需要每个 combo 一个独立的数据库副本
    kuzu_src = Path(__file__).resolve().parents[1] / "data" / "kuzu_datamart_graph"
    kuzu_copies = []
    kuzu_combos = [(s, m) for s, m in combos if s == "B"]
    for i, (sol_key, model) in enumerate(kuzu_combos):
        copy_path = Path(__file__).resolve().parents[1] / "data" / f"kuzu_bench_{i}"
        if copy_path.exists():
            shutil.rmtree(copy_path) if copy_path.is_dir() else copy_path.unlink()
        if kuzu_src.exists():
            if kuzu_src.is_dir():
                shutil.copytree(kuzu_src, copy_path)
            else:
                shutil.copy2(kuzu_src, copy_path)
            kuzu_copies.append(copy_path)

    # 为每个 Kuzu combo 设置独立路径
    kuzu_path_map = {}
    for i, (sol_key, model) in enumerate(kuzu_combos):
        if i < len(kuzu_copies):
            kuzu_path_map[(sol_key, model.value)] = str(kuzu_copies[i])

    all_results = []
    max_workers = min(4, len(combos))

    def run_combo(sol_key, model):
        # 如果是 Kuzu，临时修改路径
        if sol_key == "B" and (sol_key, model.value) in kuzu_path_map:
            from solutions import graph_kuzu
            graph_kuzu.KUZU_DB_PATH = kuzu_path_map[(sol_key, model.value)]
        return run_single_combo(sol_key, model, questions)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_combo, sol, model): (sol, model)
            for sol, model in combos
        }
        for future in as_completed(futures):
            sol, model = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                success = sum(1 for r in results if r.get("success"))
                logger.info(f"[{sol}/{model.value}] Done: {success}/{len(results)}")
            except Exception as e:
                logger.error(f"[{sol}/{model.value}] Failed: {e}")

    # 清理 Kuzu 副本
    for p in kuzu_copies:
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except Exception:
            pass

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
    parser.add_argument("--solutions", default="A,B,C,D", help="Comma-separated solution keys (A,B,C,D)")
    parser.add_argument("--models", default="gpt5", help="Comma-separated: gpt5,gpt5mini,opus,sonnet")
    parser.add_argument("--questions", type=int, default=0, help="Limit number of questions (0=all)")
    args = parser.parse_args()

    load_optional_solutions()

    sol_keys = [s.strip() for s in args.solutions.split(",")]
    model_map = {"gpt5": ModelType.GPT5, "gpt5mini": ModelType.GPT5_MINI, "opus": ModelType.OPUS, "sonnet": ModelType.SONNET}
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
