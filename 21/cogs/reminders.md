---
title: "Cogs: Reminders"
summary: "The Reminder cog allows any user to request a reminder in a certain amount of time."
last_updated: 5 March 2018
---

## reminder (remind)

Sends you a personal reminder by PM at some point in the future.

{% include tip.html content="Make sure you've enabled &quot;Allow direct messages from server members&quot; for the server the bot is on." %}

{% include tip.html content="You should double-check the reminder time in the confirmation PM, to make sure your timespec was interpreted correctly." %}

**Usage:** `.remind <timespec>: <message>`

**Arguments:**
* `<timespec>: `: A time in the future to send you a reminder, followed by a colon and a space. This can be an absolute date and time `2018-03-07 12:00:00`, a relative time `in 2h 30m` (the space between hours and minutes, or other different units, is important), or combinations of the two (`tomorrow at 1pm`). If giving an absolute time, you can specify a time zone (e.g. `1pm UTC-5` or `13:05 EST`); if none specified, default is UTC.
* `<message>`: The message to include with the reminder.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.remind in 2 hours: Feed the dog`
* `.remind on 24 december at 4:50pm PST: Grandma's Christmas call`
* `.remind tomorrow at 8am UTC-4: Start Spotlight`


### reminder list

Lists all future reminders you've requested.

**Usage:** `.reminder list`

**Arguments:** None

**Channels:** Any

**Usable by:** Anyone


### reminder clear

Remove all future reminders you've requested.

**Usage:** `.reminder clear`

**Arguments:** None

**Channels:** Any

**Usable by:** Anyone
