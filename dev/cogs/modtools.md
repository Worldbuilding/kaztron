---
title: "ModTools"
last_updated: 02 August 2019
summary: "Miscellaneous tools for moderators."
---

Various tools for moderators to help them in their day-to-day! Some commands are
dependent on the <a href="./modnotes.html">ModNotes</a> module.

This module will automatically enforce modnotes of type "temp", at startup and every hour
hence. Use <a href="./modtools.html#tempban">tempban</a> in order to immediately apply and enforce a new tempban. (Using
<a href="./modnotes.html#notes-add">notes add</a> to add a "temp" record will not enforce it until the next hourly check.)

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

**Arguments**

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


## 4. tempban
{: #tempban }

Tempban a user.

This command will immediately tempban (mute) the user, and create a modnote. It will not
communicate with the user.

The user will be unbanned (unmuted) when the tempban expires.

Note that the ModTools module automatically enforces all tempban modules. See the
<a href="./modtools.html">ModTools</a> introduction or `.help ModTools` for more info.

This command is shorthand for `.notes add <user> temp expires="[expires]" [reason]`.

**Usage**: `.tempban <user> [reason]`

**Arguments**

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

* `.tempban @BlitheringIdiot#1234 Was being a blithering idiot.` - Issues a 7-day ban.
* `.tempban @BlitheringIdiot#1234 expires="in 3 days" Was being a slight blithering idiot only.` - Issues a 3-day ban.

## 5. whois
{: #whois }

Finds a Discord user from their ID, name, or name with discriminator. If modnotes is
enabled, will also search the name and alias fields of modnotes users.

If an exact match isn't found, then this tool will do a substring search on all visible
users' names and nicknames.

**Usage**: `.whois <user>`

**Arguments**

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

**Arguments**

[index]
: string. Optional. If specified, the index of the image to show (starting at `0`). If not specified, a random image is shown.




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.wb` - Show a random image.
* `.wb 3` - Show image at index 3 (the 4th image).