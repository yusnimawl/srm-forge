import argparse
import dataclasses

from srmweb.config import check_exposure, load_settings


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="srmweb")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    a = p.parse_args(argv)
    s = load_settings()
    s = dataclasses.replace(
        s, host=a.host or s.host, port=a.port if a.port is not None else s.port)
    check_exposure(s)
    import uvicorn

    from srmweb.api import create_app

    # An open event stream must not hold shutdown (and the runner stop) forever.
    uvicorn.run(create_app(s), host=s.host, port=s.port, timeout_graceful_shutdown=5)


if __name__ == "__main__":
    main()
