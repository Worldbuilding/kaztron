---
wb-category: kaztron-2.2.0-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.2.0
wb-subcategory: Commands
title: "Reminders"
last_updated: 07 September 2020
summary: "Get reminders for later."
---

The Reminder cog allows you to ask the bot to send you a reminder message in a certain
amount of time. Reminders are personal and PMed to you.

{% include important.html content='While we want this module to be useful and reliable, we can&#x27;t guarantee that
you&#x27;ll get the reminder on time. Don&#x27;t rely on this module for anything critical!' %}

## 1. reminder (remind)
{: #reminder }

Sends you a personal reminder by PM at some point in the future.

{% include tip.html content='Make sure you&#x27;ve enabled &quot;Allow direct messages from server members&quot; for the server
the bot is on.' %}

{% include tip.html content='You should double-check the reminder time in the confirmation PM, to make sure your
timespec was interpreted correctly.' %}

**Usage**: `.[reminder|remind] <args>`

**Parameters**

&lt;args&gt;
: Consists of `<timespec>: <message>`.


&lt;timespec&gt;
: timespec. A time in the future to send you a reminder, followed by a colon and a
  space. This can be an absolute date and time `2018-03-07 12:00:00`, a relative
  time `in 2h 30m` (the "in" **and** the spaces are important), or combinations of
  the two (`tomorrow at 1pm`). If giving an absolute time, you can specify a time
  zone (e.g. `1pm UTC-5` or `13:05 EST`); if none specified, default is UTC.

&lt;message&gt;
: string. The message you want to be reminded with.




**Examples**

* `.remind in 2 hours: Feed the dog`
* `.remind on 24 december at 4:50pm: Grandma's Christmas call`
* `.remind tomorrow at 8am PST: start spotlight`

### 1.1. reminder list
{: #reminder-list }

Lists all future reminders you've requested.

The list is sent by PM.

**Usage**: `.reminder list`



### 1.2. reminder clear
{: #reminder-clear }

Remove all future reminders you've requested.

{% include warning.html content='This command cannot be undone.' %}

**Usage**: `.reminder clear`

