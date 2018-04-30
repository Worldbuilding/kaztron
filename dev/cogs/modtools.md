---
title: "Cogs: ModTools"
last_updated: 21 April 2018
summary: "The ModTools cog provides miscellaneous tools for moderators."
---

## 1. up

Colours a moderator's username.

This command colours the moderator's username by applying a special role to it. This is used for moderators to be able to signal when they are speaking or intervening officially in their role as moderator.

**Usage:** `.up`

**Arguments:** None

**Channels:** Any

**Usable by:** Moderators only


## 2. down

Uncolours a moderator's username.

This command undoes the `.up` command.

**Usage:** `.down`

**Arguments:** None

**Channels:** Any

**Usable by:** Moderators only


## 3. tempban

Tempban a user.

This method will automatically create a modnote. It will not communicate with the user.

This module integrates with modnotes, and will automatically enforce "temp" notes, giving a role to users with unexpired "temp" notes and removing that role when the note expires. This command is shorthand for `.notes add <user> temp expires="[expires]" [Reason]`.

**Usage:** `.tempban <user> [expires=datespec] [reason]`

**Arguments:**
* `<user>`: The user to ban. See [modnotes: .notes](modnotes.html#1-notes) for more information.
* `[expires=datespec]`: Optional. The datespec for the tempban's expiration. Use quotation marks if the datespec has spaces in it. See [modnotes: .notes add](modnotes.html#11-add) for more information on accepted syntaxes. Default is `expires="in 7 days"`.
* `[reason]`: Optional, but highly recommended to specify. The reason to record in the modnote

**Channels:** Mod and bot channels

**Usable by:** Moderators only

**Examples:**
* `.tempban @BlitheringIdiot#1234 Was being a blithering idiot.` - Issues a 7-day ban.
* `.tempban @BlitheringIdiot#1234 expires="in 3 days" Was being a slight blithering idiot only.` - Issues a 3-day ban.


## 4. whois

Finds a Discord user from their ID, name, or name with discriminator.

If an exact match isn't found, then this tool will do a substring search on all visible users' names and nicknames.

{% include warning.html content="If the user is in the channel where you use this command, the user will receive a notification." %}

**Usage:** `.whois <user>`

**Arguments:**
* `user`: An ID number, name, name with discriminator, etc. of a user to find.

**Channels:** Any

**Usable by:** Moderators only

**Example:**
* `.whois 1234567890` will find user 1234567890.
* `.whois JaneDoe#0921` will find a user called JaneDoe with discriminator #0921.
* `.whois JaneDoe` will find a user called JaneDoe. 


## 5. wb

Shows a "Please talk about worldbuilding" image.
        
For mod intervention, when discussions get off-topic.

**Usage:** `.wb [index]`
        
**Arguments:**
* index: Optional. If specified, the index of the image to show (starting at `0`). If not specified, a random image is shown.

**Channels:** Any

**Usable by:** Moderators only

**Examples:**
* `.wb` - Show a random image.
* `.wb 3` - Show image at index 3 (4th image).
