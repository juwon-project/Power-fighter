"""Ability Duel online site + WebSocket room relay.

Runs the uploaded single-file HTML unchanged, at the same origin as /ws.
Protocol matches the online lobby already implemented in the original game.

This is a hobby deployment server, not an authoritative anti-cheat game server.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

BASE_DIR = Path(__file__).resolve().parent
MAX_CLIENTS = int(os.environ.get("MAX_CLIENTS", "100"))
MAX_ROOMS = int(os.environ.get("MAX_ROOMS", "60"))
ALLOWED_RELAY_TYPES = {
    "pick", "start", "again", "in", "hash", "rpick", "rboss", "rstart", "ragain"
}
LOG = logging.getLogger("ability-duel")


def safe_name(value: object, limit: int = 24) -> str:
    if not isinstance(value, str):
        return "플레이어"
    # Names are rendered inside game HTML templates; remove markup delimiters.
    value = re.sub(r"[<>\"'&\x00-\x1f\x7f]", "", value).strip()
    return value[:limit] or "플레이어"


@dataclass(eq=False)
class Player:
    uid: str
    ws: web.WebSocketResponse
    name: str = "플레이어"
    room_id: str | None = None
    tokens: float = 300.0
    last_refill: float = field(default_factory=time.monotonic)

    def accept_message(self) -> bool:
        now = time.monotonic()
        self.tokens = min(300.0, self.tokens + (now - self.last_refill) * 180.0)
        self.last_refill = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


@dataclass
class Room:
    id: str
    name: str
    mode: str
    members: list[Player]
    playing: bool = False

    @property
    def capacity(self) -> int:
        return 4 if self.mode == "raid" else 2

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "host": self.members[0].name,
            "n": len(self.members),
            "max": self.capacity,
            "full": len(self.members) >= self.capacity,
            "playing": self.playing,
        }


class GameHub:
    def __init__(self) -> None:
        self.clients: dict[str, Player] = {}
        self.rooms: dict[str, Room] = {}

    async def send(self, player: Player, msg: dict) -> None:
        if not player.ws.closed:
            try:
                await player.ws.send_json(msg, dumps=lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
            except (ConnectionResetError, RuntimeError):
                pass

    async def error(self, player: Player, msg: str) -> None:
        await self.send(player, {"t": "error", "msg": msg})

    async def rooms_to_all(self) -> None:
        msg = {"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]}
        for player in tuple(self.clients.values()):
            await self.send(player, msg)

    async def members_to_all(self, room: Room) -> None:
        msg_members = [{"uid": p.uid, "name": p.name} for p in room.members]
        for player in tuple(room.members):
            await self.send(player, {
                "t": "members", "list": msg_members,
                "you": player.uid, "host": room.members[0].uid,
            })

    def generate_room_id(self) -> str:
        for _ in range(20):
            code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
            if code not in self.rooms:
                return code
        raise RuntimeError("Unable to generate unique room ID")

    def current_room(self, player: Player) -> Room | None:
        return self.rooms.get(player.room_id or "")

    async def leave(self, player: Player) -> None:
        room = self.current_room(player)
        player.room_id = None
        if not room:
            return
        was_host = room.members[0] is player
        room.members = [m for m in room.members if m is not player]
        room.playing = False
        if was_host:
            self.rooms.pop(room.id, None)
            for other in tuple(room.members):
                other.room_id = None
                await self.send(other, {"t": "left", "why": "host", "name": player.name})
        else:
            reason = "member" if room.mode == "raid" else "guest"
            for other in tuple(room.members):
                await self.send(other, {"t": "left", "why": reason, "name": player.name})
            if room.mode == "raid":
                await self.members_to_all(room)
        await self.rooms_to_all()

    async def command(self, player: Player, data: object) -> None:
        if not isinstance(data, dict):
            return
        typ = data.get("t")
        # Lightweight round-trip-time diagnostic. Does not affect game input relay.
        if typ == "ping":
            stamp = data.get("ts")
            if isinstance(stamp, (int, float)) and 0 <= stamp <= 10**15:
                await self.send(player, {"t": "pong", "ts": stamp})
            return
        if typ == "hello":
            player.name = safe_name(data.get("name"), 16)
            room = self.current_room(player)
            if room:
                await self.members_to_all(room) if room.mode == "raid" else self.rooms_to_all()
            else:
                await self.send(player, {"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]})
            return
        if typ == "list":
            await self.send(player, {"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]})
            return
        if typ == "leave":
            await self.leave(player)
            return
        if typ == "create":
            if player.room_id:
                await self.error(player, "먼저 현재 방에서 나가 주세요.")
                return
            if len(self.rooms) >= MAX_ROOMS:
                await self.error(player, "방이 가득 찼어요. 잠시 뒤 시도해 주세요.")
                return
            mode = data.get("mode")
            if mode not in ("duel", "raid"):
                await self.error(player, "지원하지 않는 게임 모드입니다.")
                return
            room = Room(
                id=self.generate_room_id(),
                name=safe_name(data.get("name"), 40),
                mode=mode,
                members=[player],
            )
            self.rooms[room.id] = room
            player.room_id = room.id
            await self.send(player, {
                "t": "created", "id": room.id, "name": room.name,
                "mode": room.mode, "you": player.uid,
            })
            if mode == "raid":
                await self.members_to_all(room)
            await self.rooms_to_all()
            return
        if typ == "join":
            if player.room_id:
                await self.error(player, "먼저 현재 방에서 나가 주세요.")
                return
            room_id = str(data.get("id") or "").upper()
            room = self.rooms.get(room_id)
            if not room:
                await self.error(player, "방을 찾을 수 없어요. 목록을 새로고침해 주세요.")
                return
            if room.playing or len(room.members) >= room.capacity:
                await self.error(player, "이미 시작했거나 가득 찬 방이에요.")
                return
            room.members.append(player)
            player.room_id = room.id
            await self.send(player, {
                "t": "joined", "id": room.id, "name": room.name,
                "mode": room.mode, "host": False,
                "peer": room.members[0].uid, "you": player.uid,
            })
            if room.mode == "duel":
                await self.send(room.members[0], {
                    "t": "joined", "id": room.id, "name": room.name,
                    "mode": room.mode, "host": True,
                    "peer": player.uid, "you": room.members[0].uid,
                })
            else:
                await self.members_to_all(room)
            await self.rooms_to_all()
            return
        room = self.current_room(player)
        if typ == "playing":
            if room is not None:
                room.playing = data.get("on") is True
                await self.rooms_to_all()
            return
        if typ == "relay":
            if not room or len(room.members) < 2:
                return
            payload = data.get("d")
            if not isinstance(payload, dict) or payload.get("t") not in ALLOWED_RELAY_TYPES:
                return
            for other in tuple(room.members):
                if other is not player:
                    await self.send(other, {"t": "relay", "from": player.uid, "d": payload})

    async def connect(self, request: web.Request) -> web.StreamResponse:
        # Browser game and WebSocket use the same hostname.
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            raise web.HTTPForbidden(text="Please connect from the game website itself.")
        if len(self.clients) >= MAX_CLIENTS:
            raise web.HTTPServiceUnavailable(text="Server is full.")
        ws = web.WebSocketResponse(heartbeat=25.0, max_msg_size=64 * 1024)
        await ws.prepare(request)
        uid = secrets.token_hex(5)
        player = Player(uid=uid, ws=ws)
        self.clients[uid] = player
        LOG.info("connected %s (online=%d)", uid, len(self.clients))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if not player.accept_message():
                        await self.error(player, "초당 전송 제한을 초과했습니다.")
                        continue
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    await self.command(player, data)
                elif msg.type == WSMsgType.ERROR:
                    LOG.warning("WebSocket error %s: %s", uid, ws.exception())
        finally:
            await self.leave(player)
            self.clients.pop(uid, None)
            LOG.info("disconnected %s (online=%d)", uid, len(self.clients))
        return ws


hub = GameHub()


async def index(_: web.Request) -> web.FileResponse:
    response = web.FileResponse(BASE_DIR / "index.html")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


async def health(_: web.Request) -> web.Response:
    return web.json_response({
        "ok": True, "players_connected": len(hub.clients), "rooms": len(hub.rooms)
    })


app = web.Application(client_max_size=64 * 1024)
app.router.add_get("/", index)
app.router.add_get("/index.html", index)
app.router.add_get("/health", health)
app.router.add_get("/ws", hub.connect)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
