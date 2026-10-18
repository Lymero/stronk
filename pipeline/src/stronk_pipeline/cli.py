"""`stronk-pipeline`: dispatches registered commands. Also the composition root."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated

import httpx
import typer

from stronk_pipeline.adapters.json_estimates import JsonEstimateStore
from stronk_pipeline.adapters.json_report import JsonReportWriter
from stronk_pipeline.adapters.lightgbm_winprob import LightGbmLearner
from stronk_pipeline.adapters.local_publisher import LocalPublisher
from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.minisign import MinisignKeys
from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore, ParquetFrameStore
from stronk_pipeline.adapters.recording import PlaybackTransport, RecordingTransport, Scrubber
from stronk_pipeline.adapters.riot.client import RiotApiSource
from stronk_pipeline.adapters.riot.payloads import parse_quarantined
from stronk_pipeline.adapters.riot.rate_limit import RateLimiter
from stronk_pipeline.adapters.winprob_store import JsonWinProbStore
from stronk_pipeline.application.crawl import CrawlParams, SourceFactory, crawl_command
from stronk_pipeline.application.extract import extract_command
from stronk_pipeline.application.publish import publish_command
from stronk_pipeline.application.registry import CommandError, CommandRegistry
from stronk_pipeline.application.signing_keygen import signing_keygen_command
from stronk_pipeline.application.winprob_train import winprob_train_command
from stronk_pipeline.application.wpa_estimate import wpa_estimate_command
from stronk_pipeline.config import Settings
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import LogisticLearner
from stronk_pipeline.domain.wpa.overlap_weighted import OverlapWeightedEstimator
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1
from stronk_pipeline.ports import MatchSource

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

HTTP_TIMEOUT_SECONDS = 15.0


def build_registry(settings: Settings | None = None) -> CommandRegistry:
    settings = settings if settings is not None else Settings()
    decisions, frames, reports = ParquetDecisionStore(), ParquetFrameStore(), JsonReportWriter()
    learners, models = (LogisticLearner(), LightGbmLearner()), JsonWinProbStore()
    estimators = {e.id: e for e in (ReferenceEstimatorV1(), OverlapWeightedEstimator())}
    return CommandRegistry(
        [
            crawl_command(riot_sources(settings), FileMatchStore),
            extract_command(FileMatchStore, parse_quarantined, decisions, frames, reports),
            winprob_train_command(frames, learners, models, reports),
            wpa_estimate_command(decisions, estimators, models, JsonEstimateStore(), frames),
            signing_keygen_command(MinisignKeys()),
            publish_command(JsonEstimateStore(), FileMatchStore, MinisignKeys(), LocalPublisher),
        ]
    )


def riot_sources(settings: Settings) -> SourceFactory:
    """Live Riot API (optionally recording), or playback of a recording."""

    def make(params: CrawlParams) -> Result[MatchSource, CommandError]:
        if params.replay is not None:
            directory = Path(params.replay)
            if not directory.is_dir():
                return Err(CommandError(code="not_found", message=f"no recording at {directory}"))
            client = httpx.AsyncClient(transport=PlaybackTransport(directory))
            source = RiotApiSource(
                client=client, platform=params.platform, api_key="replay", limiter=None
            )
            return Ok(source)
        if settings.riot_api_key is None:
            message = "RIOT_API_KEY is not set; put it in .env (see .env.example)"
            return Err(CommandError(code="unauthorized", message=message))
        transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport()
        if params.record is not None:
            transport = RecordingTransport(transport, Path(params.record), Scrubber())
        client = httpx.AsyncClient(transport=transport, timeout=HTTP_TIMEOUT_SECONDS)
        source = RiotApiSource(
            client=client,
            platform=params.platform,
            api_key=settings.riot_api_key.get_secret_value(),
            limiter=RateLimiter(),
        )
        return Ok(source)

    return make


@app.command("commands")
def list_commands() -> None:
    """List registered commands."""
    for command in build_registry().commands():
        typer.echo(f"{command.id}\t{command.summary}")


@app.command()
def run(
    command_id: Annotated[str, typer.Argument(help="Command id, for example wpa.estimate")],
    params: Annotated[str, typer.Option(help="Parameters as a JSON object")] = "{}",
) -> None:
    """Run a command and print its JSON result. Errors go to stderr as JSON, exit code 1."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request otherwise
    match build_registry().dispatch(command_id, params):
        case Ok(value=result):
            typer.echo(result.model_dump_json(indent=2))
        case Err(error=error):
            sys.stderr.write(error.model_dump_json() + "\n")
            raise typer.Exit(code=1)


def main() -> None:
    app()
