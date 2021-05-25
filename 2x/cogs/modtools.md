---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Moderator
title: "ModTools"
last_updated: 25 May 2021
summary: "Miscellaneous tools for moderators."
---

Various tools for moderators to help them in their day-to-day! Some commands depend on the
<a href="./modnotes.html">ModNotes</a> module.

## 1. report
{: #report }

Report an incident to the moderators confidentially.

Please remember to mention **who** is involved and **where** it's happening (i.e. the
channel). Your name and the time at which you sent your report are automatically
recorded.

{% include important.html content='This will send notifications to mods. Please use only for incidents that need
to be handled in a time-sensitive manner. For non-time-sensitive situations, ask in the
#meta channel (or ask there for an available mod to PM, if it&#x27;s confidential).' %}

**Usage**: `.report <text>`

**Parameters**

&lt;text&gt;
: string. The text you want to send the mod team. Make sure to mention the **who** and **where** (channel).




**Details**

Channels
: PM only.


**Example**

* `.report There's a heated discussion about politics in #worldbuilding, mostly between BlitheringIdiot and AggressiveDebater, that might need a mod to intervene.`

## 2. up
{: #up }

This command colours the moderator's username by applying a special role to it. This
allows moderators to clearly show when they are speaking in an official capacity as
moderators.

**Usage**: `.up`

**Details**

Members
: Moderators, Administrators.


## 3. down
{: #down }

Uncolours a moderator's username.

This command undoes the <a href="./modtools.html#up">up</a> command.

**Usage**: `.down`

**Details**

Members
: Moderators, Administrators.


## 4. say
{: #say }

Make the bot say something in a channel. If the <a href="./reminders.html">reminders</a> cog is enabled,
you can also schedule a message at a later time with <a href="./reminders.html#saylater">saylater</a>.

If the bot has pin permissions, prepending `pin:` to the beginning of the message will
allow it to auto-pin the message.

**Usage**: `.say <channel> <message>`

**Parameters**

&lt;channel&gt;
: string. The channel to say the message in.


&lt;message&gt;
: string. The message to say. This will be copied exactly. This includes any formatting, @mentions, commands that OTHER bots might react to, and @everyone/@here (if the bot is allowed to use them).




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.say #meta HELLO, HUMANS. I HAVE GAINED SENTIENCE.` - Says the message in the #meta channel.
* `.say #meta pin: REMEMBER TO KEEP HYDRATED.` - Says the message in the #meta channel and pin it.

## 5. whois
{: #whois }

Finds a Discord user from their ID, name, or name with discriminator. If modnotes is
enabled, will also search the name and alias fields of modnotes users.

If an exact match isn't found, then this tool will do a substring search on all visible
users' names and nicknames.

**Usage**: `.whois <user>`

**Parameters**

&lt;user&gt;
: string. An ID number, name, name with discriminator, etc. of a user to find. If this contains spaces, use quotation marks.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.whois 123456789012345678` - Find a user with ID 123456789012345678.
* `.whois JaneDoe#0921` - Find a user exactly matching @JaneDoe#0921.
* `.whois JaneDoe` - Find a user whose name matches JaneDoe, or if not found, a user whose name or nickname contains JaneDoe.

## 6. wb
{: #wb }

Show a "Please talk about worldbuilding" image.

For mod intervention, when discussions get off-topic.

**Usage**: `.wb [index]`

**Parameters**

[index]
: string. Optional. If specified, the index of the image to show (starting at `0`). If not specified, a random image is shown.




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.wb` - Show a random image.
* `.wb 3` - Show image at index 3 (the 4th image).