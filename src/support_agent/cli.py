"""Command line helpers.

support-agent ask "my thermostat says E74" --user u-1001
support-agent search "doorbell battery drains fast"
support-agent chunks
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from support_agent.config import load_config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="support-agent")
    p.add_argument("--config")
    sub = p.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="run the full agent (needs GCP credentials)")
    ask.add_argument("message")
    ask.add_argument("--user", default="u-1001")

    search = sub.add_parser("search", help="retrieval only, no LLM")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    search.add_argument("--dense", action="store_true", help="also use Vertex embeddings")

    sub.add_parser("chunks", help="list ingested chunk ids")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    cfg = load_config(args.config)

    if args.cmd == "ask":
        from support_agent.agent import serialize_result
        from support_agent.factory import build_agent

        result = build_agent(cfg).run(args.message, user_id=args.user, session_id="cli")
        print(json.dumps(serialize_result(result), indent=2))
        return 0

    if args.cmd == "search":
        from support_agent.factory import build_embedder
        from support_agent.retrieval import build_retriever

        retriever = build_retriever(cfg, embedder=build_embedder(cfg) if args.dense else None)
        for h in retriever.search(args.query, k=args.k):
            print(f"{h.score:.4f}  bm25={h.bm25:5.1f}  {h.chunk.id}")
        return 0

    if args.cmd == "chunks":
        from support_agent.ingest import load_manuals

        for c in load_manuals(cfg.path(cfg.retrieval["manuals_dir"])):
            print(f"{c.id:45s} {len(c.text):5d} chars")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
