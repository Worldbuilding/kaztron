---
wb-category: kaztron-2.4.0-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.4.0
wb-subcategory: Commands
title: "CoreCog"
last_updated: 26 October 2020
summary: "Essential internal KazTron functionality, plus bot information and control commands."
---

Essential KazTron functionality: core setup and configuration tasks, general-purpose error
handling for other cogs and commands, etc. It also includes commands for general bot
information and control. The Core cog cannot be disabled.

## 1. info
{: #info }

Provides bot info and useful links.

This command provides the version of the KazTron instance currently running, the latest
changelog summary, and links to documentation, the GitHub repository, and other
resources for operators and moderators.

{% include tip.html content='*For mods.* If KazTron ever seems unresponsive, try this command first.' %}

**Usage**: `.info`

**Details**

Members
: Moderators, Administrators.


## 2. request (bug, issue)
{: #request }

Submit a bug report or feature request to the KazTron bot team.

**Usage**: `.[request|bug|issue] <content>`

**Details**

Everyone can use this command, but please make sure that:

* Your issue is clear and sufficiently detailed.
* You submit **one issue per command**. Do not include multiple issues in one command,
  or split up one issue into multiple commands. Otherwise the bot team will get mad at
  you =P

If you're reporting a bug, include the answers to the questions:

* What were you trying to do? Include the *exact* command you tried to use, if any.
* What error messages were given by the bot? *Exact* message.
* Where and when did this happen? Ideally, link the message itself (message menu >
  Copy Link).

{% include important.html content='Any submissions made via this system may be tracked publicly. By submitting
a request via this system, you give us permission to post your username and message,
verbatim or altered, to a public database for the purpose of project management.' %}

{% include important.html content='Abuse of this command may be treated as channel spam, and enforced
accordingly.' %}

{% include note.html content='The three command names do not differ from each other. They are defined purely
for convenience.' %}

**Example**

* ```
  .request When trying to use the `.roll 3d20` command, I get the message:
  "An error occurred! Details have been logged. Let a mod know so we can investigate."

  This only happens with d20, I've tried d12 and d6 with no problems.
  The last time this happened in #tabletop on 2018-01-31 at 5:24PM PST.
  ```

## 3. jekyllate
{: #jekyllate }

Generate Jekyll-compatible markdown documentation for all loaded cogs.

**Usage**: `.jekyllate`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.
