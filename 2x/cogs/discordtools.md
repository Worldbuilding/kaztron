---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Commands
title: "DiscordTools"
last_updated: 25 May 2021
summary: "Various tools to help with Discord."
---


## 1. kaztime (now, time)
{: #kaztime }

Gets the current KazTron Time (UTC, GMT). Can be used to help convert community programme schedules to your timezone.

**Usage**: `.[kaztime|now|time]`

**Example**

* `.kaztime` - Shows the current time.

## 2. id
{: #id }

Gets your own user ID.

**Usage**: `.id`

**Example**

* `.id` - Gets your own user ID.

## 3. rchid
{: #rchid }

Convert channel IDs to channel links.

**Usage**: `.rchid <ids>`

**Parameters**

&lt;ids&gt;
: str. A list of channel IDs. They may be comma- or line-separated and may or may not be quoted, using either double or single quotes.




**Details**

This command is primarily intended for bot operators to help in validating the configuration file.

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.rchid "123456789012345678", "876543210987654321"
` - Translates these two IDs into channel names, e.g.,