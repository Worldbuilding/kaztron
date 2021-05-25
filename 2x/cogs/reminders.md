---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Commands
title: "Reminders"
last_updated: 25 May 2021
summary: "Get reminders for later."
---

The Reminder cog allows you to ask the bot to send you a reminder message in a certain
amount of time. Reminders are personal and PMed to you.

{% include important.html content='While we want this module to be useful and reliable, we can&#x27;t guarantee that
you&#x27;ll get the reminder on time. Don&#x27;t rely on this module for anything critical!' %}

This cog also allows moderators to schedule messages in-channel at a later time.

## 1. reminder (remind)
{: #reminder }

Sends you a personal reminder by PM at some point in the future. This function can also
set up recurring reminders.

Each user can have a maximum of 10 reminders. Recurring reminders can
repeat up to 25 times, and cannot repeat more often than every
5 minutes.

{% include tip.html content='Make sure you&#x27;ve enabled &quot;Allow direct messages from server members&quot; for the server
the bot is on.' %}

{% include tip.html content='You should double-check the reminder time in the confirmation PM, to make sure your
timespec was interpreted correctly.' %}

**Usage**: `.[reminder|remind] <args>`

**Parameters**

&lt;args&gt;
: Multi-part argument consists of `<timespec> ["every" <intervalspec> ["limit" <limit>|"until" <limit_timespec>]: <message>`.


&lt;timespec&gt;
: timespec. A time in the future to send you a reminder, followed by
  a colon and a space. This can be an absolute date and time `2018-03-07 12:00:00`,
  a relative time `in 2h 30m` (the "in" **and** the spaces are important), or
  combinations of the two (`tomorrow at 1pm`). If giving an absolute time, you can
  specify a time zone (e.g. `1pm UTC-5` or `13:05 EST`); if none specified, default
  is UTC.

[intervalspec]
: timespec. Optional. How often the reminder should repeat after the `timespec`. Can take any relative
  time specification accepted by `timespec`, e.g., `every 1 hour`, `every 4h 30m`,
  etc.

[limit]
: int. Optional. How many times the reminder will repeat. Only one of `limit` or `limitspec` may be used.


[limitspec]
: timespec. Optional. The latest time at which the reminder will repeat. Accepts the same values  as `timespec`. Only one of `limit` or `limitspec` may be used.


&lt;message&gt;
: string. The message you want to be reminded with.




**Examples**

* `.remind on 24 december at 4:50pm: Grandma's Christmas call` - Date and time. Assumes nearest future date. Time is interpreted as UTC.
* `.remind in 2 hours: Feed the dog` - Relative time.
* `.remind tomorrow at 8am PST: start spotlight` - Relative date, absolute time, time zone specified.
* `.remind in 2 hours every 1 hour limit 8: drink water, you dehydrated prune` - Reminder starting in 2 hours, repeating every 1 hour, 8 times total.
* `.remind 22:00 EDT every 1 hour until 08:00 EDT: Remember to sleep` - Reminder every hour between 10PM tonight and 8AM tomorrow.

### 1.1. reminder list
{: #reminder-list }

List all your future reminders. The list is sent by PM.

**Usage**: `.reminder list`



### 1.2. reminder remove (rem)
{: #reminder-remove }

Remove a reminder.

{% include warning.html content='This command cannot be undone.' %}

**Usage**: `.reminder [remove|rem] <index>`

**Parameters**

&lt;index&gt;
: int. The number of the reminder to remove. See the <a href="./reminders.html#reminder-list">reminder list</a> command for the numbered list.




**Example**

* `.reminder rem 4` - Removes reminder number 4.

### 1.3. reminder clear
{: #reminder-clear }

Remove all your future reminders.

{% include warning.html content='This command cannot be undone.' %}

**Usage**: `.reminder clear`



## 2. saylater
{: #saylater }

Schedule a message for the bot to send in-channel later. Can also set up recurring
messages (static messages only). Messages can also be pinned.

Recurring messages can repeat up to 25 times, and cannot repeat more often
than every 5 minutess.

{% include tip.html content='You should double-check the time in the response message to make sure your timespec
was interpreted correctly.' %}

**Usage**: `.saylater <channel> <args>`

**Parameters**

&lt;channel&gt;
: The channel to post the message in.


&lt;args&gt;
: Same as <a href="./reminders.html#reminder">reminder</a>. You can also include the word `pin` before the colon.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.saylater #community-programs at 12:00: Welcome to our AMA with philosopher Aristotle!` - Single message at noon UTC.
* `.saylater #announcements at 12:00 every 1 hour limit 24: Attention, citizens. For the duration of gremlin season, all citizens must be on the lookout for crown-stealing gremlins. Any sightings or incidents must be reported to your nearest moderator immediately.` - Recurring message every hour starting at noon UTC.
* `.saylater #general at 15:00 pin: Karaoke hour for the next hour! Check out #karaoke for more info.` - Single message at 15:00 UTC, auto-pinned.

### 2.1. saylater list
{: #saylater-list }

List all future scheduled messages.

**Usage**: `.saylater list`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 2.2. saylater remove (rem)
{: #saylater-remove }

Remove a scheduled message.

{% include warning.html content='This command cannot be undone.' %}

**Usage**: `.saylater [remove|rem] <index>`

**Parameters**

&lt;index&gt;
: int. The number of the reminder to remove. See the <a href="./reminders.html#saylater-list">saylater list</a> command for the numbered list.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.saylater rem 4` - Removes message number 4.

### 2.3. saylater clear
{: #saylater-clear }

Remove all scheduled messages.

{% include warning.html content='This removes scheduled messages created by other users, too.' %}

{% include warning.html content='This command cannot be undone.' %}

**Usage**: `.saylater clear`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.
