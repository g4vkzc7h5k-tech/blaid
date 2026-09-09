"""
Makes the bot APPEAR to be connected from a mobile client (shows the
phone icon next to its status dot instead of the normal desktop
circle) - purely cosmetic, no functional effect.

HONEST NOTE: this is an unofficial trick, not something Discord or
discord.py officially supports for bots - it works by overriding the
"$browser"/"$device" fields discord.py sends when it first connects
to the gateway, claiming to be the iOS app instead of a generic
library client. Discord decides which icon to show based on that
self-reported value, with no verification. This is widely used and
has been stable for a long time, but since it relies on private
library internals (discord.gateway.DiscordWebSocket.identify), a
future discord.py update could change that method's shape and break
this - if the mobile icon stops appearing after a library upgrade,
this file is the first thing to check.

Usage: call patch_for_mobile_status() once, before the bot logs in
(e.g. at the top of main.py, right after your imports).
"""

from __future__ import annotations

import discord.gateway


def patch_for_mobile_status() -> None:
    original_identify = discord.gateway.DiscordWebSocket.identify

    async def _mobile_identify(self):
        payload = {
            "op": self.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": {
                    "os": "Discord iOS",
                    "browser": "Discord iOS",
                    "device": "Discord iOS",
                },
                "compress": True,
                "large_threshold": 250,
            },
        }

        if self.shard_id is not None and self.shard_count is not None:
            payload["d"]["shard"] = [self.shard_id, self.shard_count]

        state = self._connection
        if state._activity is not None or state._status is not None:
            payload["d"]["presence"] = {
                "status": state._status,
                "game": state._activity,
                "since": 0,
                "afk": False,
            }

        if state._intents is not None:
            payload["d"]["intents"] = state._intents.value

        await self.call_hooks("before_identify", self.shard_id, initial=self._initial_identify)
        await self.send_as_json(payload)

    discord.gateway.DiscordWebSocket.identify = _mobile_identify
