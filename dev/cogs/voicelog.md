---
title: "Cogs: Voice Log"
summary: "Voice chat support features."
last_updated: 25 March 2018
---

This cog has the following features:

* Shows a log of users joining/leaving voice channels. Now you can avoid the "wait, who
joined? / who'd we lose?" conversation!
* Voice role management. Allows people in voice to be assigned a role: for example, to let
voice users see a voice-only text channel, or change their colour when in voice, etc.

This cog has no commands. It is fully configured in the config.json file (see [config.example.json](https://github.com/Worldbuilding/KazTron/blob/master/config.example.json)).

This cog does **not** depend on [role_man](role_man.html).

## Voice user logging

This feature replicates the join/part logging available in TeamSpeak, mumble and similar, mainly to avoid the "wait, who joined?" and "who'd we lose?" conversations while in voice chat on Discord. KazTron will log voice join and parts in #voice like this:

```
[07:40] KazTron: JaneDoe has joined voice channel #general
[07:40] KazTron: JaneDoe has moved from voice channel #general to #tabletop
[07:41] KazTron: JaneDoe has left voice channel #tabletop
```

KazTron will only log for configured voice channels (normally all the public channels).

## Voice state update

This cog monitors users' voice channel state. When a user is in a configured voice channel (normally all the public channels), they will be given the `in_voice` role (configurable)—this is generally used to allow only users in voice access to a voice-specific text channel.

Currently, this functionality supports any number of voice channels but only one role. This could be extended if needed—mods, talk to DevOps.
