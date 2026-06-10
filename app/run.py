import argparse
import logging
import sys

from app.manager import run_architecture


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dynamic-LR — deterministic and agentic literature review pipeline"
    )
    parser.add_argument(
        "--architecture",
        required=True,
        choices=["baseline", "single-agent", "multi-agent"],
        help="Pipeline architecture to run",
    )
    parser.add_argument(
        "--config",
        default="data/survey_config.json",
        help="Path to survey_config.json (default: data/survey_config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the run without writing output files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    )

    result = run_architecture(
        architecture=args.architecture,
        config_path=args.config,
        dry_run=args.dry_run,
    )

    print()
    print(f"Architecture      : {result.architecture}")
    print(f"Dry run           : {result.dry_run}")
    print(f"Queries generated : {result.queries_generated}")
    print(f"Sources queried   : {', '.join(result.sources_queried)}")
    print(f"Candidates found  : {result.candidates_found}")
    print(f"After dedup       : {result.candidates_after_dedupe}")
    print(f"Accepted          : {result.papers_accepted}")
    print(f"Rejected          : {result.candidates_rejected}")
    print(f"Errors            : {len(result.errors)}")
    for e in result.errors:
        print(f"  ! {e}")
    print(f"Started           : {result.started_at}")
    print(f"Finished          : {result.finished_at}")

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
