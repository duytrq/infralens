"""Application-only logging with a handler safe for repeated CLI invocations."""

import logging

import typer

logger = logging.getLogger("infralens")


class StderrHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        typer.echo(self.format(record), err=True, color=False)


def configure_logging(verbose: bool) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = StderrHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
