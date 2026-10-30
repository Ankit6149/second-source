"""Host-neutral bounded ASGI process entry; never provisions infrastructure."""
import os
import uvicorn


def main():
    try:
        port = int(os.environ.get("PORT", "8000"))
        if not 1024 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError("PORT must be between 1024 and 65535") from None
    uvicorn.run("second_source.backend.asgi:create_application", factory=True,
                host="0.0.0.0", port=port, workers=1, access_log=False,
                timeout_keep_alive=5, limit_concurrency=16,
                timeout_graceful_shutdown=110)


if __name__ == "__main__":
    main()
