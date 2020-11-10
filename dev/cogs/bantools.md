---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Moderator
title: "BanTools"
last_updated: 10 November 2020
summary: "Mod notes tools to help enforce and keep track of bans."
---

Various tools for moderators to help enforce and track bans! This cog depends on the
<a href="./modnotes.html">ModNotes</a> module.

This module can automatically enforce modnotes of type 'temp' and 'perma', at startup and
every 1 hour hence.

## 1. tempban
{: #tempban }

Tempban a user.

This command will immediately tempban (mute) the user, and create a modnote. It will not
communicate with the user.

The user will be unbanned (unmuted) when the tempban expires.

Note that the ModTools module automatically enforces all tempban modules. See the
<a href="./modtools.html">ModTools</a> introduction or `.help ModTools` for more info.

This command is shorthand for `.notes add <user> temp expires="[expires]" [reason]`.

**Usage**: `.tempban <user> [reason]`

**Parameters**

&lt;user&gt;
: string. The user to ban. See <a href="./modnotes.html#notes">notes</a> for more information.


[reason]
: string. Optional. Complex parameter of the format `[expires=[expires]] [reason]`. `reason` is the reason for the tempban, to be recorded as a modnote (optional but highly recommended).


[expires]
: datespec. Optional. The datespec for the tempban's expiration. Use quotation marks if the datespec has spaces in it. See <a href="./modnotes.html#notes-add">notes add</a> for more information on accepted syntaxes. Default: "in 7 days"




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.tempban @BlitheringIdiot#1234 Was being a blithering idiot.` - Issues a ban of default duration (in 7 days).
* `.tempban @BlitheringIdiot#1234 expires="in 3 days" Was being a slight blithering idiot only.` - Issues a 3-day ban.

### 1.1. tempban enforce
{: #tempban-enforce }

Immediately re-check and update all tempbans and permabans (if enforcement is enabled),
without waiting for the timer.

**Usage**: `.tempban enforce`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.
