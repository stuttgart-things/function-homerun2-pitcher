"""The function's CLI entrypoint."""

import os
import sys

import click
from crossplane.function import logging, runtime

from function import fn
from function.fn import AUTH_TOKEN_ENV


@click.command()
@click.option("--debug", "-d", is_flag=True, help="Emit debug logs.")
@click.option(
    "--address",
    default="0.0.0.0:9443",
    show_default=True,
    help="Address at which to listen for gRPC connections.",
)
@click.option(
    "--tls-certs-dir",
    help="Serve using mTLS certificates.",
    envvar="TLS_SERVER_CERTS_DIR",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Run without mTLS credentials. If supplied, --tls-certs-dir is ignored.",
)
@click.option(
    "--skip-token-check",
    is_flag=True,
    help=f"Skip the startup check for {AUTH_TOKEN_ENV}. Useful for local "
    "development with `hatch run development`.",
)
def cli(  # noqa: FBT001, PLR0913
    debug: bool,
    address: str,
    tls_certs_dir: str,
    insecure: bool,
    skip_token_check: bool,
) -> None:
    """Run the function-homerun2-pitcher gRPC server."""
    level = logging.Level.DEBUG if debug else logging.Level.INFO
    logging.configure(level=level)
    log = logging.get_logger()

    token = os.environ.get(AUTH_TOKEN_ENV, "")
    if not token and not skip_token_check:
        click.echo(
            f"FATAL: {AUTH_TOKEN_ENV} env var is required (mount the Secret "
            "via DeploymentRuntimeConfig). Pass --skip-token-check to bypass "
            "for local development.",
            err=True,
        )
        sys.exit(1)
    log.info(
        "Auth token loaded" if token else "Auth token check skipped",
        token_len=len(token) if token else 0,
    )

    try:
        runtime.serve(
            fn.FunctionRunner(),
            address,
            creds=runtime.load_credentials(tls_certs_dir),
            insecure=insecure,
        )
    except Exception as e:  # noqa: BLE001
        click.echo(f"Cannot run function: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
