"""Run the support eval suite.

    # retrieval + guardrails only; no credentials, runs on every PR
    python evals/run_eval.py --mode offline

    # full agent against Gemini; runs in CI when prompts/retrieval/agent change
    python evals/run_eval.py --mode full --out eval_report.json

Exits non-zero if any metric is below the thresholds in configs/config.yaml.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from support_agent.config import load_config
from support_agent.evaluation import (
    grade,
    load_cases,
    retrieval_hit_rate,
    summarize,
    triage_report,
)

log = logging.getLogger("eval")


def run_offline(cfg, cases) -> tuple[dict, list[str]]:
    from support_agent.retrieval import build_retriever

    retriever = build_retriever(cfg, embedder=None)  # BM25 only, deterministic
    report = {
        "retrieval": retrieval_hit_rate(cases, retriever, k=cfg.retrieval["top_k"]),
        "triage": triage_report(cases),
    }
    th = cfg.eval
    failures = []
    if report["retrieval"]["hit_rate"] < th["min_retrieval_hit_at_k"]:
        failures.append(
            f"retrieval hit@{cfg.retrieval['top_k']} {report['retrieval']['hit_rate']} "
            f"< {th['min_retrieval_hit_at_k']}"
        )
    if report["triage"]["safety_recall"] < 1.0:
        failures.append(f"safety triage missed {report['triage']['missed_safety']}")
    if report["triage"]["false_positive_rate"] > 0:
        failures.append(f"triage false positives {report['triage']['false_positives']}")
    return report, failures


def run_full(cfg, cases, workers: int) -> tuple[dict, list[str]]:
    from support_agent.factory import build_agent
    from support_agent.tracing import MemorySink

    sink = MemorySink()
    agent = build_agent(cfg, sink=sink)

    def one(case):
        try:
            return case, agent.run(
                case.question, user_id=case.user_id, session_id=f"eval-{case.id}"
            )
        except Exception:  # noqa: BLE001
            log.exception("case %s crashed", case.id)
            raise

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, cases))

    grades = [grade(c, r, agent.prompt.text) for c, r in results]
    summary = summarize(grades, cases)
    summary.update(
        {
            "model": cfg.llm["model"],
            "prompt_version": agent.prompt.version,
            "prompt_hash": agent.prompt.hash,
            "wall_seconds": round(time.time() - t0, 1),
            "total_cost_usd": round(sum(r.cost_usd for r in sink.runs), 4),
            "p50_latency_ms": _pct([r.latency_ms for r in sink.runs], 50),
            "p95_latency_ms": _pct([r.latency_ms for r in sink.runs], 95),
        }
    )

    th = cfg.eval
    failures = []
    if summary["answer_accuracy"] < th["min_answer_accuracy"]:
        failures.append(
            f"answer accuracy {summary['answer_accuracy']} < {th['min_answer_accuracy']}"
        )
    if summary["handoff_recall"] < th["min_handoff_recall"]:
        failures.append(f"handoff recall {summary['handoff_recall']} < {th['min_handoff_recall']}")
    if summary["by_category"].get("access_control", 1.0) < 1.0:
        failures.append("cross-account data leaked")
    return summary, failures


def _pct(xs: list[float], p: int) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def to_markdown(mode: str, report: dict, failures: list[str]) -> str:
    lines = [f"### Eval ({mode}): {'PASS' if not failures else 'FAIL'}", ""]
    if mode == "offline":
        r, t = report["retrieval"], report["triage"]
        lines += [
            "| metric | value |",
            "|---|---|",
            f"| retrieval hit@{r['k']} ({r['n']} questions) | {r['hit_rate']:.1%} |",
            f"| safety triage recall | {t['safety_recall']:.0%} |",
            f"| injection recall | {t['injection_recall']:.0%} |",
            f"| triage false positive rate | {t['false_positive_rate']:.1%} |",
        ]
    else:
        lines += [
            f"model `{report['model']}`, "
            f"prompt `{report['prompt_version']}` ({report['prompt_hash']})",
            "",
            "| metric | value |",
            "|---|---|",
            f"| answer accuracy | {report['answer_accuracy']:.1%} |",
            f"| handoff recall | {report['handoff_recall']:.1%} |",
            f"| overall | {report['overall_pass_rate']:.1%} |",
            f"| cost | ${report['total_cost_usd']:.3f} |",
            f"| p95 latency | {report['p95_latency_ms']:.0f} ms |",
            "",
            "| category | pass rate |",
            "|---|---|",
            *[f"| {k} | {v:.0%} |" for k, v in report["by_category"].items()],
        ]
    if failures:
        lines += ["", "**Failing thresholds:**", *[f"- {f}" for f in failures]]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["offline", "full"], default="offline")
    p.add_argument("--config")
    p.add_argument("--out", help="write the JSON report here")
    p.add_argument("--markdown", help="write a markdown summary here (for PR comments)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, help="only run the first N cases (debugging)")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    cfg = load_config(args.config)
    cases = load_cases(cfg.path(cfg.eval["questions"]))[: args.limit]

    if args.mode == "offline":
        report, failures = run_offline(cfg, cases)
    else:
        report, failures = run_full(cfg, cases, args.workers)

    md = to_markdown(args.mode, report, failures)
    print(md)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    if args.markdown:
        Path(args.markdown).write_text(md)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
