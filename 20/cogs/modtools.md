---
title: "Cogs: ModTools"
last_updated: 21 February 2018
summary: "The ModTools cog provides miscellaneous tools for moderators."
---

# 1. up

Colours a moderator's username.

This command colours the moderator's username by applying a special role to it. This is used for moderators to be able to signal when they are speaking or intervening officially in their role as moderator.

**Usage:** `.up`

**Arguments:** None

**Channels:** Any

**Usable by:** Moderators only

# 2. down

Uncolours a moderator's username.

This command undoes the `.up` command.

**Usage:** `.down`

**Arguments:** None

**Channels:** Any

**Usable by:** Moderators only

# 3. whois

Finds a Discord user from their ID.

{% include warning.html content="This will send the user a notification. You should probably only use this in mod-restricted channels like #mods or #bot-test to avoid disturbing users unnecessarily." %}

**Usage:** `.whois <user_id>`

**Arguments:**
* `user_id`: The ID number of the user.

**Channels:** Mod and bot channels only

**Usable by:** Moderators only

**Example:**
* `.finduser 1234567890` will find user 1234567890.

# 4. wb

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
