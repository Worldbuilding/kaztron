---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Automation
title: "Subwatch"
last_updated: 10 November 2020
summary: "Announce new reddit posts in a channel."
---

This module monitors one or more subreddits and announces new posts to Discord channels.

It is configured to check every 30 seconds. It will post a maximum of
2 posts at a time every 5 minutes, to avoid flooding
a Discord channel; otherwise, it will queue posts.

## 1. subwatch
{: #subwatch }

Add or remove subreddits to watch and post into channels, or show the current configuration.

**Usage**: `.subwatch [channel] [subreddits]`

**Parameters**

&lt;channel&gt;
: string. Discord channel to output the watched subreddits into.


[subreddits]
: string. Optional. Subreddits to watch and post in the channel. Can be separated by commas, spaces or `+`.If `off` or `none`, turns off Subwatch for that channel. If not specified, lists current subreddits watched.




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.subwatch #general askreddit askscience` - Watch the subreddits AskReddit and AskScience and post new posts to #general.
* `.subwatch #general off` - Stop watching subreddits in #general.
* `.subwatch` - Show what subreddits are being watched and what channels they're being output to.