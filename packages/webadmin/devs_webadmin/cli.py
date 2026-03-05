"""CLI entry point for webadmin."""

import click
import uvicorn

from .config import config


@click.group()
def cli() -> None:
    """Devs Web Admin - manage devcontainers from a web UI."""
    pass


@cli.command()
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", default=None, type=int, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the web admin server."""
    host = host or config.host
    port = port or config.port

    click.echo(f"Starting devs-webadmin on {host}:{port}")
    uvicorn.run(
        "devs_webadmin.app:app",
        host=host,
        port=port,
        reload=reload,
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
