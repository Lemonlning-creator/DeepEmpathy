import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="DeepEmpathy mini-app simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--demo", action="store_true", help="Enable clearly marked scripted demo sessions")
    args = parser.parse_args()
    if args.demo:
        os.environ["DEMO_ENABLED"] = "true"
    import uvicorn

    from deep_empathy.api.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
