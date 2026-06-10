import logging

from app.state.schemas import ManagerRunResult

logger = logging.getLogger(__name__)

_ARCHITECTURES = ["baseline", "single-agent", "multi-agent"]


def run_architecture(
    architecture: str,
    config_path: str,
    dry_run: bool,
) -> ManagerRunResult:
    if architecture == "baseline":
        from app.architectures.baseline.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    if architecture == "single-agent":
        from app.architectures.single_agent.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    if architecture == "multi-agent":
        from app.architectures.multi_agent.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    raise ValueError(
        f"Unknown architecture {architecture!r}. "
        f"Choose from: {', '.join(_ARCHITECTURES)}"
    )
