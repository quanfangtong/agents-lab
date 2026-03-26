#!/usr/bin/env python3
"""
Multi-Solution Benchmark Runner — 全并行版
4 方案 × N 模型 × 37 题，每个 (方案, 模型, 题目) 独立并行

用法:
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --solutions A,B,C,D --models gpt5 --concurrency 20
"""

import sys
import json
import time
import argparse
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.llm import get_llm_client, ModelType
from solutions.baseline_text2sql import Text2SQLSolution
from solutions.graph_kuzu import KuzuSolution

SOLUTIONS_MAP = {
    "A": Text2SQLSolution,
    "B": KuzuSolution,
}


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

    keep_ids = {'Q01','Q02','Q03','Q04','Q05','Q06','Q07','Q08','Q09','Q10','Q11','Q12','Q13','Q14','Q16','Q17','Q18','Q19','Q20','Q22','Q23','Q25','Q26','Q27','Q28','Q29','Q30','Q31','Q32','Q33','Q34','Q35','Q37','Q42','Q43','Q47','Q48'}
    questions = [q for q in questions if q['id'] in keep_ids]

    if limit > 0:
        questions = questions[:limit]
    return questions


def load_golden_answers(questions: list[dict]) -> dict:
    """跑 expected_sql 生成 golden answers"""
    import pymysql
    conn = pymysql.connect(host='127.0.0.1', port=3307, user='root', password='chatbi2024', database='qft_datamart')
    cur = conn.cursor(pymysql.cursors.DictCursor)

    golden = {}
    for q in questions:
        try:
            cur.execute(q['expected_sql'])
            rows = cur.fetchall()
            for row in rows:
                for k, v in row.items():
                    if type(v).__name__ == 'Decimal': row[k] = float(v)
                    elif hasattr(v, 'isoformat'): row[k] = str(v)
                    elif isinstance(v, bytes): row[k] = v.decode()
                    elif not isinstance(v, (str, int, float, bool, type(None))): row[k] = str(v)
            golden[q['id']] = rows
        except Exception:
            golden[q['id']] = None
    conn.close()
    return golden


def compare_results(golden: list, actual: list) -> dict:
    """对比 golden answer 和 actual result"""
    if golden is None:
        return {"match": False, "reason": "no_golden_answer"}
    if not actual:
        return {"match": False, "reason": "empty_result"}

    def extract_values(rows):
        vals = set()
        for row in rows:
            for v in row.values():
                if isinstance(v, (int, float)):
                    vals.add(round(float(v), 2))
                elif isinstance(v, str) and v.replace('.','',1).replace('-','',1).isdigit():
                    try: vals.add(round(float(v), 2))
                    except: pass
        return vals

    golden_vals = extract_values(golden)
    actual_vals = extract_values(actual)

    if not golden_vals:
        return {"match": len(golden) == len(actual), "reason": f"row_count: golden={len(golden)} actual={len(actual)}"}

    overlap = golden_vals & actual_vals
    recall = len(overlap) / len(golden_vals) if golden_vals else 0
    return {
        "match": recall >= 0.5,
        "value_recall": round(recall, 2),
        "golden_values": sorted(golden_vals)[:10],
        "actual_values": sorted(actual_vals)[:10],
        "reason": f"value_recall={recall:.0%}",
    }


def run_single_question(sol, model, question, golden_answers) -> dict:
    """独立运行单个 (方案, 模型, 题目) 组合"""
    llm = get_llm_client()
    qid = question["id"]
    q_text = question["question"]

    try:
        result = sol.run(q_text, llm, model)
    except Exception as e:
        result = {
            "solution": sol.name, "question": q_text,
            "model": model.display_name, "success": False,
            "error": str(e)[:300],
        }

    result["question_id"] = qid
    result["category"] = question.get("category", "")
    result["difficulty"] = question.get("difficulty", "")
    result["domain"] = question.get("domain", "")
    result["expected_tables"] = question.get("expected_tables", [])

    # 表召回率
    if result.get("schema_tables") and result.get("expected_tables"):
        found = set(result["schema_tables"])
        expected = set(result["expected_tables"])
        result["table_recall"] = len(found & expected) / len(expected) if expected else 0
    else:
        result["table_recall"] = None

    # Golden answer 验证
    if golden_answers and qid in golden_answers and result.get("success"):
        comparison = compare_results(golden_answers[qid], result.get("execution_result", []))
        result["result_match"] = comparison["match"]
        result["match_detail"] = comparison.get("reason", "")
        result["value_recall"] = comparison.get("value_recall")
        result["verified_success"] = comparison["match"]
    else:
        result["verified_success"] = False
        result["result_match"] = False if result.get("success") else None

    status = "✓" if result.get("verified_success") else ("SQL_OK" if result.get("success") else "FAIL")
    ms = result.get("total_ms", 0)
    logger.info(f"[{sol.name}/{model.value}] [{qid}] {q_text[:25]}... -> {status} ({ms}ms)")

    return result


def run_benchmark(solutions: list[str], models: list[ModelType], questions: list[dict], concurrency: int = 20):
    """全并行：每个 (方案, 模型, 题目) 独立一个线程"""

    # 加载 golden answers
    logger.info("Loading golden answers from expected_sql...")
    golden = load_golden_answers(questions)
    logger.info(f"Golden answers loaded: {sum(1 for v in golden.values() if v is not None)}/{len(golden)}")

    # Setup 所有方案（每个方案一个实例，跨模型共享）
    sol_instances = {}
    for sol_key in solutions:
        if sol_key not in SOLUTIONS_MAP:
            logger.warning(f"Solution {sol_key} not available, skipping")
            continue
        sol = SOLUTIONS_MAP[sol_key]()
        logger.info(f"Setting up {sol_key} ({sol.name})...")
        try:
            sol.setup()
            sol_instances[sol_key] = sol
        except Exception as e:
            logger.error(f"Setup failed for {sol_key}: {e}")

    # 展平所有任务
    tasks = [
        (sol_key, model, q)
        for sol_key in sol_instances
        for model in models
        for q in questions
    ]
    total = len(tasks)
    logger.info(f"Running {total} tasks with concurrency={concurrency}")

    all_results = []
    completed = [0]
    progress_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for sol_key, model, q in tasks:
            sol = sol_instances[sol_key]
            future = executor.submit(run_single_question, sol, model, q, golden)
            futures[future] = (sol_key, model, q['id'])

        for future in as_completed(futures):
            sol_key, model_type, qid = futures[future]
            try:
                result = future.result()
                with progress_lock:
                    all_results.append(result)
                    completed[0] += 1
                    c = completed[0]
                if c % 20 == 0 or c == total:
                    logger.info(f"Progress: {c}/{total} ({c*100//total}%)")
            except Exception as e:
                logger.error(f"[{sol_key}/{model_type.value}] [{qid}] Exception: {e}")
                with progress_lock:
                    completed[0] += 1

    return all_results


def summarize(results: list[dict]) -> dict:
    """生成汇总统计"""
    from collections import defaultdict
    summary = defaultdict(lambda: defaultdict(lambda: {"total": 0, "sql_ok": 0, "verified": 0, "total_ms": 0, "total_tokens": 0}))

    for r in results:
        key = (r.get("solution", "?"), r.get("model", "?"))
        s = summary[key[0]][key[1]]
        s["total"] += 1
        if r.get("success"):
            s["sql_ok"] += 1
        if r.get("verified_success"):
            s["verified"] += 1
        s["total_ms"] += r.get("total_ms", 0)
        s["total_tokens"] += r.get("schema_token_estimate", 0)

    output = {}
    for sol, models in summary.items():
        output[sol] = {}
        for model, stats in models.items():
            t = stats["total"]
            output[sol][model] = {
                "total": t,
                "sql_ok": stats["sql_ok"],
                "sql_ok_rate": f"{stats['sql_ok']}/{t} ({stats['sql_ok']/t*100:.1f}%)" if t else "N/A",
                "verified": stats["verified"],
                "verified_rate": f"{stats['verified']}/{t} ({stats['verified']/t*100:.1f}%)" if t else "N/A",
                "success": stats["verified"],
                "success_rate": f"{stats['verified']}/{t} ({stats['verified']/t*100:.1f}%)" if t else "N/A",
                "avg_ms": stats["total_ms"] // t if t else 0,
                "avg_tokens": stats["total_tokens"] // t if t else 0,
            }

    return output


def main():
    parser = argparse.ArgumentParser(description="Multi-Solution Benchmark (Full Parallel)")
    parser.add_argument("--solutions", default="A,B,C,D", help="Comma-separated solution keys (A,B,C,D)")
    parser.add_argument("--models", default="gpt5", help="Comma-separated: gpt5,gpt5mini,opus,sonnet")
    parser.add_argument("--questions", type=int, default=0, help="Limit number of questions (0=all)")
    parser.add_argument("--concurrency", type=int, default=20, help="Max parallel LLM calls")
    args = parser.parse_args()

    load_optional_solutions()

    sol_keys = [s.strip() for s in args.solutions.split(",")]
    model_map = {"gpt5": ModelType.GPT5, "gpt5mini": ModelType.GPT5_MINI, "opus": ModelType.OPUS, "sonnet": ModelType.SONNET}
    models = [model_map[m.strip()] for m in args.models.split(",") if m.strip() in model_map]
    questions = load_questions(args.questions)

    total = len(sol_keys) * len(models) * len(questions)
    logger.info(f"Benchmark: {len(sol_keys)} solutions × {len(models)} models × {len(questions)} questions = {total} tasks (concurrency={args.concurrency})")

    results = run_benchmark(sol_keys, models, questions, args.concurrency)
    summary = summarize(results)

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "config": {
            "solutions": sol_keys,
            "models": [m.value for m in models],
            "question_count": len(questions),
            "concurrency": args.concurrency,
        },
        "summary": summary,
        "results": results,
    }

    outdir = Path(__file__).parent / "results"
    outdir.mkdir(exist_ok=True)
    outfile = outdir / "benchmark_latest.json"
    with open(outfile, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"\nResults saved to: {outfile}")
    logger.info(f"\nSummary:")
    for sol, models_data in summary.items():
        for model, stats in models_data.items():
            logger.info(f"  {sol} / {model}: SQL可执行={stats.get('sql_ok_rate','?')} | 结果正确={stats.get('verified_rate','?')} | avg {stats['avg_ms']}ms")


if __name__ == "__main__":
    main()
