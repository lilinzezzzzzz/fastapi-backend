import argparse
import asyncio

import uvicorn

from internal.app import create_app

app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FastAPI Application")
    parser.add_argument("--port", type=int, default=8090, help="Port to run the server on")
    args = parser.parse_args()

    config = uvicorn.Config("main:app", host="0.0.0.0", port=args.port, reload=False)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
