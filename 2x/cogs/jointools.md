---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Moderator
title: "JoinTools"
last_updated: 25 May 2021
summary: "Mod notes tools to help keep track of when users join and leave the guild."
---

Mod notes tools to help keep track of when users join and parts the guild. This cog depends
on the <a href="./modnotes.html">ModNotes</a> module.

Join/part records are displayed when looking up a user's history using <a href="./modnotes.html#notes">notes</a>. They are
not logged on Discord otherwise. If join/part logging is desired, use the <a href="./welcome.html">Welcome</a>
module.

## 1. jointools
{: #jointools }

Command group. Utilities for managing the JoinTools functionality.

**Usage**: `.jointools`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 1.1. jointools purge (a)
{: #jointools-purge }

Purges join/part records of users who a) haven't been seen in at least 30 days; b) have
no modnotes.

**Usage**: `.jointools [purge|a]`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.
