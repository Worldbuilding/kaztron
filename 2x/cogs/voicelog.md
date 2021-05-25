---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Automation
title: "VoiceLog"
last_updated: 25 May 2021
summary: "Voice chat support features. No commands."
---

* Shows a log of users joining/leaving voice channels. Now you can avoid the "wait, who
  joined / who'd we lose?" conversation!
* Voice role management. Allows people in voice to be assigned a role, e.g. to let voice
  users see a voice-only text channel or change their colour while in voice.

**Channels**: #voice, #voice3-dont-delete-for-kaztron, #voice-too-dont-delete-for-kaztron

This cog has no commands. It is fully configured in the config.json file (see
[config.example.json](https://github.com/Worldbuilding/KazTron/blob/master/config.example.json)).

## Voice user logging

This feature replicates the join/part logging available in TeamSpeak, mumble and similar,
mainly to avoid the "wait, who joined?" and "who'd we lose?" conversations while in voice
chat on Discord. KazTron will log voice join and parts in the associated text channel like
this:

```
[07:40] KazTron: JaneDoe has joined voice channel #general
[07:40] KazTron: JaneDoe has moved from voice channel #general to #tabletop
[07:41] KazTron: JaneDoe has left voice channel #tabletop
```

## Voice state update

This cog monitors users' voice channel state. When a user is in a voice channel, they will
be given the in_voice role. This is normally used to allow only users currently
in voice to access a voice-specific text channel, but may be used for other purposes.

Currently, this functionality supports any number of voice channels but only one role.
This could be extended if needed—mods, talk to DevOps.