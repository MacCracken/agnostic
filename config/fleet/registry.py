"""Fleet registry — Redis-backed node inventory with heartbeat and groups.

Every node writes its state to a Redis hash on a periodic interval.
The registry reads all node hashes to build the fleet inventory.
Nodes that miss their heartbeat TTL are marked offline.

Redis key layout
----------------
fleet:node:{node_id}        — JSON blob of FleetNode
fleet:nodes                 — SET of active node IDs (for fast enumeration)
fleet:group:{group}         — SET of node IDs in this group
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from config.fleet.node import (
    FLEET_ENABLED,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TTL,
    FleetNode,
)

logger = logging.getLogger(__name__)


class FleetRegistry:
    """Manages fleet node registration, heartbeat, and discovery."""

    def __init__(self) -> None:
        self._local_node: FleetNode | None = None
        self._heartbeat_task: asyncio.Task | None = None  # type: ignore[type-arg]

    @property
    def enabled(self) -> bool:
        return FLEET_ENABLED

    @property
    def local_node(self) -> FleetNode | None:
        return self._local_node

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, redis_client: Any | None = None) -> FleetNode:
        """Register this node in the fleet and start heartbeating."""
        if not FLEET_ENABLED:
            raise RuntimeError("Fleet is not enabled (AGNOS_FLEET_ENABLED=false)")

        client = redis_client or await self._get_redis()
        node = FleetNode.local()
        self._local_node = node

        await self._write_node(client, node)

        # Add to global set and group set
        await asyncio.gather(
            client.sadd("fleet:nodes", node.node_id),
            client.sadd(f"fleet:group:{node.group}", node.node_id),
        )

        logger.info(
            "Fleet node registered: %s (group=%s, url=%s, gpu=%d)",
            node.node_id,
            node.group,
            node.external_url,
            node.capabilities.gpu_count,
        )

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(client))
        return node

    async def deregister(self, redis_client: Any | None = None) -> None:
        """Gracefully remove this node from the fleet."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if not self._local_node:
            return

        client = redis_client or await self._get_redis()
        node_id = self._local_node.node_id

        await asyncio.gather(
            client.delete(f"fleet:node:{node_id}"),
            client.srem("fleet:nodes", node_id),
            client.srem(f"fleet:group:{self._local_node.group}", node_id),
        )

        logger.info("Fleet node deregistered: %s", node_id)
        self._local_node = None

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self, client: Any) -> None:
        """Periodically update this node's heartbeat in Redis."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self._local_node:
                    self._local_node.last_heartbeat = time.time()
                    # Refresh capabilities (GPU VRAM may change)
                    from config.fleet.node import NodeCapabilities

                    self._local_node.capabilities = NodeCapabilities.probe_local()
                    await self._write_node(client, self._local_node)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Fleet heartbeat failed: %s", exc)

    async def heartbeat(self, redis_client: Any | None = None) -> None:
        """Manual one-shot heartbeat (for testing or on-demand refresh)."""
        if not self._local_node:
            return
        client = redis_client or await self._get_redis()
        self._local_node.last_heartbeat = time.time()
        await self._write_node(client, self._local_node)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def get_all_nodes(self, redis_client: Any | None = None) -> list[FleetNode]:
        """Return all registered nodes (alive and dead)."""
        client = redis_client or await self._get_redis()
        node_ids = await client.smembers("fleet:nodes")
        if not node_ids:
            return []

        nodes = []
        for node_id in node_ids:
            raw = await client.get(f"fleet:node:{node_id}")
            if raw:
                nodes.append(FleetNode.from_dict(json.loads(raw)))
        return nodes

    async def get_alive_nodes(self, redis_client: Any | None = None) -> list[FleetNode]:
        """Return only nodes with a valid heartbeat."""
        all_nodes = await self.get_all_nodes(redis_client)
        return [n for n in all_nodes if n.is_alive]

    async def get_group_nodes(
        self, group: str, redis_client: Any | None = None
    ) -> list[FleetNode]:
        """Return alive nodes in a specific group."""
        client = redis_client or await self._get_redis()
        node_ids = await client.smembers(f"fleet:group:{group}")
        if not node_ids:
            return []

        nodes = []
        for node_id in node_ids:
            raw = await client.get(f"fleet:node:{node_id}")
            if raw:
                node = FleetNode.from_dict(json.loads(raw))
                if node.is_alive:
                    nodes.append(node)
        return nodes

    async def get_node(
        self, node_id: str, redis_client: Any | None = None
    ) -> FleetNode | None:
        """Get a specific node by ID."""
        client = redis_client or await self._get_redis()
        raw = await client.get(f"fleet:node:{node_id}")
        if not raw:
            return None
        return FleetNode.from_dict(json.loads(raw))

    async def list_groups(
        self, redis_client: Any | None = None
    ) -> list[dict[str, Any]]:
        """Return all groups with their node counts."""
        all_nodes = await self.get_all_nodes(redis_client)
        groups: dict[str, list[FleetNode]] = {}
        for node in all_nodes:
            groups.setdefault(node.group, []).append(node)

        return [
            {
                "group": group,
                "node_count": len(nodes),
                "alive_count": sum(1 for n in nodes if n.is_alive),
                "gpu_count": sum(n.capabilities.gpu_count for n in nodes),
                "total_vram_mb": sum(n.capabilities.gpu_vram_total_mb for n in nodes),
            }
            for group, nodes in sorted(groups.items())
        ]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def evict_dead_nodes(self, redis_client: Any | None = None) -> list[str]:
        """Remove nodes that have exceeded the heartbeat TTL."""
        client = redis_client or await self._get_redis()
        all_nodes = await self.get_all_nodes(client)
        evicted = []

        for node in all_nodes:
            if not node.is_alive:
                await asyncio.gather(
                    client.delete(f"fleet:node:{node.node_id}"),
                    client.srem("fleet:nodes", node.node_id),
                    client.srem(f"fleet:group:{node.group}", node.node_id),
                )
                evicted.append(node.node_id)

        if evicted:
            logger.info("Evicted %d dead fleet node(s): %s", len(evicted), evicted)
        return evicted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _write_node(self, client: Any, node: FleetNode) -> None:
        """Write a node's state to Redis with TTL."""
        key = f"fleet:node:{node.node_id}"
        await client.setex(key, HEARTBEAT_TTL * 3, json.dumps(node.to_dict()))

    async def _get_redis(self) -> Any:
        from config.environment import config

        return config.get_async_redis_client()


# Singleton
fleet_registry = FleetRegistry()
