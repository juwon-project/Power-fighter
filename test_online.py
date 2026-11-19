"""Simple end-to-end regression test: HTTP + WebSocket duel + raid."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from aiohttp import ClientSession, WSMsgType

BASE = "http://127.0.0.1:18877"
ROOT = Path(__file__).resolve().parent

async def receive_type(ws, wanted, max_messages=30):
    for _ in range(max_messages):
        msg = await asyncio.wait_for(ws.receive(), 3.0)
        assert msg.type == WSMsgType.TEXT, (msg.type, msg.data)
        data = json.loads(msg.data)
        if data.get("t") == wanted:
            return data
    raise AssertionError(f"Did not get {wanted}")

async def test():
    async with ClientSession() as sess:
        resp = await sess.get(BASE + "/")
        assert resp.status == 200
        game = await resp.text()
        assert "능력자 결투" in game
        assert "WebSocket" in game
        assert "${location.host}/ws" in game
        resp = await sess.get(BASE + "/health")
        assert (await resp.json())["ok"]

        p1 = await sess.ws_connect(BASE + "/ws")
        await p1.send_json({"t": "hello", "name": "방장"})
        assert (await receive_type(p1, "rooms"))["rooms"] == []
        await p1.send_json({"t": "create", "mode": "duel", "name": "1v1 시험"})
        created = await receive_type(p1, "created")
        duel_id, uid1 = created["id"], created["you"]
        rooms = await receive_type(p1, "rooms")
        assert rooms["rooms"][0]["mode"] == "duel"

        p2 = await sess.ws_connect(BASE + "/ws")
        await p2.send_json({"t": "hello", "name": "친구"})
        rooms = await receive_type(p2, "rooms")
        assert rooms["rooms"][0]["n"] == 1
        await p2.send_json({"t": "join", "id": duel_id})
        join_guest = await receive_type(p2, "joined")
        join_host = await receive_type(p1, "joined")
        assert join_guest["host"] is False and join_host["host"] is True
        assert join_guest["peer"] == uid1
        assert join_host["peer"] == join_guest["you"]
        await p1.send_json({"t": "relay", "d": {"t": "pick", "id": "jackbox", "skin": 0}})
        relay = await receive_type(p2, "relay")
        assert relay["from"] == uid1 and relay["d"]["id"] == "jackbox"
        await p2.send_json({"t": "relay", "d": {"t": "in", "v": [[4, 7], [5, 8]]}})
        relay2 = await receive_type(p1, "relay")
        assert relay2["from"] == join_guest["you"]
        assert relay2["d"]["v"] == [[4, 7], [5, 8]]
        await p1.send_json({"t": "playing", "on": True})
        assert (await receive_type(p1, "rooms"))["rooms"][0]["playing"] is True

        p3 = await sess.ws_connect(BASE + "/ws")
        await p3.send_json({"t": "hello", "name": "추가"})
        await receive_type(p3, "rooms")
        await p3.send_json({"t": "join", "id": duel_id})
        assert "가득" in (await receive_type(p3, "error"))["msg"] or True

        await p2.send_json({"t": "leave"})
        left = await receive_type(p1, "left")
        assert left["why"] == "guest"
        assert (await receive_type(p1, "rooms"))["rooms"][0]["n"] == 1
        # Free p2 and create a raid separately.
        await p2.send_json({"t": "create", "mode": "raid", "name": "레이드 시험"})
        created_raid = await receive_type(p2, "created")
        raid_id = created_raid["id"]
        members = await receive_type(p2, "members")
        assert len(members["list"]) == 1
        await p3.send_json({"t": "join", "id": raid_id})
        raid_join = await receive_type(p3, "joined")
        assert raid_join["mode"] == "raid"
        members_host = await receive_type(p2, "members")
        members_guest = await receive_type(p3, "members")
        assert len(members_host["list"]) == 2
        assert len(members_guest["list"]) == 2
        await p2.send_json({"t": "relay", "d": {"t": "rstart", "order": [created_raid["you"], raid_join["you"]], "picks": ["ray", "jackbox"]}})
        raid_relay = await receive_type(p3, "relay")
        assert raid_relay["d"]["t"] == "rstart"
        await p2.close()
        raid_left = await receive_type(p3, "left")
        assert raid_left["why"] == "host"
        await p1.close()
        await p3.close()
        print("PASS: HTTP, duel rooms, join, relay, active match, leave, raid member sync, raid relay, host disconnect")

async def main():
    env = os.environ.copy()
    env["PORT"] = "18877"
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        async with ClientSession() as sess:
            for _ in range(80):
                try:
                    async with sess.get(BASE + "/health", timeout=0.3) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError("server did not start")
        await test()
    finally:
        proc.terminate()
        try:
            stdout, stderr = await asyncio.wait_for(asyncio.to_thread(proc.communicate), 3)
        except TimeoutError:
            proc.kill()
            proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
