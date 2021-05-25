---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Automation
title: "Subwatch"
last_updated: 25 May 2021
summary: "Announce new reddit posts in a channel."
---

This module monitors one or more subreddits and announces new posts to Discord channels.

It is configured to check every 1 minute. It will post a maximum of
2 posts at a time every 5 minutes, to avoid flooding
a Discord channel; otherwise, it will queue posts.

## 1. subwatch
{: #subwatch }

Show the current subwatch configuration.

**Usage**: `.subwatch`

**Details**

Members
: Moderators, Administrators.


### 1.1. subwatch add
{: #subwatch-add }

Add or change subreddits to watch and post into a channel.

**Usage**: `.subwatch add [channel] [subreddits]`

**Parameters**

&lt;channel&gt;
: string. Discord channel to output the watched subreddits into.


[subreddits]
: string. Optional. Subreddits to watch and post in the channel. Can be separated by commas, spaces or `+`.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.subwatch add #general askreddit askscience` - Watch the subreddits AskReddit and AskScience and post new posts to #general.

### 1.2. subwatch reset
{: #subwatch-reset }

Reset a channel's subwatch state, clearing the queue and "last checked" data.
This will cause subwatch to ignore older posts and only post new posts from the time
this command is issued onward.

**Usage**: `.subwatch reset <channel>`

**Parameters**

&lt;channel&gt;
: string. Discord channel to output the watched subreddits into.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.subwatch reset #general`

### 1.3. subwatch rem
{: #subwatch-rem }

Stop watching subreddits in a channel.

**Usage**: `.subwatch rem [channel]`

**Parameters**

&lt;channel&gt;
: string. Discord channel.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.subwatch rem #general` - Stop watching subreddits in #general.