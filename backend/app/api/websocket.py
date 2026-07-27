import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from app.core.database import async_session
from app.models.models import Proxy

logger = logging.getLogger(__name__)
router = APIRouter()

connected_clients: set[WebSocket] = set()


async def get_live_stats() -> dict:
    """Fetch current stats for WebSocket broadcast."""
    async with async_session() as session:
        total = await session.scalar(select(func.count(Proxy.id))) or 0
        alive = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.is_alive == True)
        ) or 0
        dead = total - alive

        http_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.proxy_type == "http", Proxy.is_alive == True)
        ) or 0
        https_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.proxy_type == "https", Proxy.is_alive == True)
        ) or 0
        socks4_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks4", Proxy.is_alive == True)
        ) or 0
        socks5_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks5", Proxy.is_alive == True)
        ) or 0
        elite_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.anonymity_level == "elite", Proxy.is_alive == True)
        ) or 0
        anonymous_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.anonymity_level == "anonymous", Proxy.is_alive == True)
        ) or 0
        transparent_count = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.anonymity_level == "transparent", Proxy.is_alive == True)
        ) or 0
        avg_latency = await session.scalar(
            select(func.avg(Proxy.latency)).where(Proxy.is_alive == True, Proxy.latency.isnot(None))
        ) or 0.0

        newest = await session.scalar(select(func.max(Proxy.first_seen)))
        last_update = await session.scalar(select(func.max(Proxy.last_checked)))

    return {
        "type": "stats_update",
        "data": {
            "total_proxies": total,
            "alive_proxies": alive,
            "dead_proxies": dead,
            "http_count": http_count,
            "https_count": https_count,
            "socks4_count": socks4_count,
            "socks5_count": socks5_count,
            "elite_count": elite_count,
            "anonymous_count": anonymous_count,
            "transparent_count": transparent_count,
            "avg_latency": round(avg_latency, 2),
            "newest_proxy": newest.isoformat() if newest else None,
            "last_update": last_update.isoformat() if last_update else None,
        },
    }


async def broadcast_stats():
    """Broadcast stats to all connected WebSocket clients every 10 seconds."""
    while True:
        if connected_clients:
            try:
                stats = await get_live_stats()
                message = json.dumps(stats, default=str)
                disconnected = set()
                for client in connected_clients:
                    try:
                        await client.send_text(message)
                    except Exception:
                        disconnected.add(client)
                connected_clients.difference_update(disconnected)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
        await asyncio.sleep(10)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live stats updates."""
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")

    try:
        # Send initial stats
        stats = await get_live_stats()
        await websocket.send_text(json.dumps(stats, default=str))

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connected_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")
