"""TCP payload sender for PS5 Payload Sender."""

import asyncio
import os
from pathlib import Path
from typing import Optional


PAYLOAD_DIR = Path(os.environ.get("PAYLOAD_DIR", "/data/payloads"))
DEFAULT_LUA_PORT = int(os.environ.get("LUA_PORT", 9026))
DEFAULT_ELF_PORT = int(os.environ.get("ELF_PORT", 9021))
DEFAULT_JAR_PORT = int(os.environ.get("JAR_PORT", 9025))

# Chunk size for sending large payloads
CHUNK_SIZE = 4096


def resolve_port(filename: str, port: Optional[int] = None) -> int:
    """
    Resolve the target port for a payload.

    If port is explicitly given, use it.
    Otherwise derive from file extension:
      .lua         -> DEFAULT_LUA_PORT (9026, Remote Lua Loader)
      .jar         -> DEFAULT_JAR_PORT (9025, BD-UN-JB loader)
      .elf / .bin  -> DEFAULT_ELF_PORT (9021, ELF Loader)
    Defaults to DEFAULT_ELF_PORT for unknown extensions.
    """
    if port is not None:
        return port
    ext = Path(filename).suffix.lower()
    if ext == ".lua":
        return DEFAULT_LUA_PORT
    if ext == ".jar":
        return DEFAULT_JAR_PORT
    return DEFAULT_ELF_PORT


def get_payload_path(filename: str) -> Path:
    """Return the absolute path for a payload file, preventing path traversal."""
    # Strip any directory components – only the basename is allowed
    safe_name = Path(filename).name
    return PAYLOAD_DIR / safe_name


async def send_payload(
    host: str,
    port: int,
    filename: str,
    progress_callback=None,
    connect_timeout: float = 10.0
) -> dict:
    """
    Send a single payload file to host:port over TCP.

    Args:
        host: PS5 IP address
        port: Target TCP port
        filename: Payload filename (looked up in PAYLOAD_DIR)
        progress_callback: Optional async callable(bytes_sent, total_bytes)
        connect_timeout: Connection timeout in seconds

    Returns:
        dict with keys: success (bool), message (str), bytes_sent (int)
    """
    path = get_payload_path(filename)
    if not path.exists():
        return {
            "success": False,
            "message": f"Payload not found: {filename}",
            "bytes_sent": 0
        }

    file_size = path.stat().st_size
    bytes_sent = 0

    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=connect_timeout)
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": f"Connection timeout to {host}:{port}",
            "bytes_sent": 0
        }
    except (ConnectionRefusedError, OSError) as exc:
        return {
            "success": False,
            "message": f"Connection to {host}:{port} failed: {exc}",
            "bytes_sent": 0
        }

    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
                bytes_sent += len(chunk)
                if progress_callback:
                    try:
                        await progress_callback(bytes_sent, file_size)
                    except Exception:
                        pass

        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        return {
            "success": True,
            "message": (
                f"Payload '{filename}' sent successfully "
                f"({bytes_sent} bytes to {host}:{port})"
            ),
            "bytes_sent": bytes_sent
        }

    except (OSError, BrokenPipeError) as exc:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {
            "success": False,
            "message": f"Error sending '{filename}': {exc}",
            "bytes_sent": bytes_sent
        }
