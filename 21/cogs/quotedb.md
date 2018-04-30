---
title: "Cogs: Quotes Database"
last_updated: 21 March 2018
summary: "The Quotes Database helps you capture the best moments on the server!"
---

The Quotes Database helps you capture the best moments on the server! Store your fellow members' funniest moments so that you can revisit them time and time again.


## quote

Retrieve a quote.

If a quote number isn't given, find a random quote.

**Usage:** `.quote <user> [number]`

**Arguments:**
* `<user>`: Required. The user to find a quote for. Example formats:
    * `@mention` of the user (make sure it actually links them)
    * User's name + discriminator: `JaneDoe#0921`
    * Discord ID number: `123456789012345678`
* `[number]`: Optional. The ID number of the quote to delete (starting from 1), as shown by
    the .quote or [.quote list](#quote-list) commands.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.quote @JaneDoe` - Find a random quote by JaneDoe.
* `.quote @JaneDoe 4` - Find the 4th quote by JaneDoe.


### quote find

Find the most recent quote matching a user and/or text search.

**Usage:** `.quote find <user> [search]`

**Channels:** Any

**Usable by:** Anyone

**Arguments:**
* `<user>`: Required. The user to find a quote for, or part of their name or nickname to search,
    or `all`. For exact user matches, see [.quote](#quote) for valid formats.
* `[search]`: Optional. Text to search in the quote.

**Examples:**
* `.quote find Jane` - Find a quote for a user whose user/nickname contains "Jane".
* `.quote find @JaneDoe flamingo` - Find a quote containing "flamingo" by JaneDoe.
* `.quote find Jane flamingo` - Find a quote matching user "Jane" and containing "flamingo".


### quote list

Retrieve a list of quotes. Reply is always PMed.

**Usage:** `.quotes list <user> [page]`

**Arguments:**
* `<user>`: Required. The user to find a quote for. See [.quote](#quote) for valid formats.
* `[page]`: Optional. The page number to access, if there are more than 1 pages of notes. Default: last page.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.quote list @JaneDoe` - List all quotes by JaneDoe (page 1 if multiple pages)..
* `.quote list @JaneDoe 4` - List the 4th page of quotes by JaneDoe.


### quote add

Add a new quote manually.

{% include tip.html content="You can use [.quote grab](#quote-grab) instead to automatically grab a recent message." %}

**Usage:** `.quote add <user> <message>`

**Arguments:**
* `<user>`: Required. The user to find a quote for. See [.quote](#quote) for valid formats.
* `<message>`: Required. The quote text to add.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.quote add @JaneDoe Ready for the mosh pit, shaka brah.`


### quote grab

Find the most recent matching message and add it as a quote.

This command searches the most recent messages (default 100 messages). The most recent
message matching both the user and (if specified) search text is added as a quote.

{% include tip.html content="You can use [.quote add](#quote-add) instead to manually add a quote." %}

**Usage:** `.quote grab <user> [search]`

**Arguments:**
* `<user>`: Required. The user to find a quote for. See [.quote](#quote) for valid formats.
* `[search]`: Optional. The quote text to find among the user's recent messages.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.quote grab @JaneDoe` - Quote the most recent message from @JaneDoe.
* `.quote grab @JaneDoe mosh pit` - Quote the most recent message from @JaneDoe containing "mosh pit".


### quote rem

Remove one of your own quotes.

{% include warning.html content="This command cannot be undone!" %}

{% include tip.html content="This command is limited to quotes attributed to you. For any other situations, please contact the moderators to delete quotes." %}

**Usage:** `.quote rem [number]`

**Arguments:**
* number: Optional. The ID number of the quote to delete (starting from 1), as shown by
    the `.quote` or `.quote list` commands.

**Channels:** Any

**Usable by:** Anyone

**Examples:**
* `.quote del 4` - Delete the 4th quote attributed to you.


### quote undo

Remove the last quote you added.

{% include warning.html content="This command cannot be undone!" %}

{% include tip.html content="This command only undoes `.quote add` or `.quote grab` actions. It does NOT undo `.quote rem` actions." %}

**Usage:** `.quote undo`

**Arguments:** None

**Channels:** Any

**Usable by:** Anyone


### quote del

Delete one or all quotes attributed to a user. Moderator command (regular users should use [.quote undo](#quote-undo) or [.quote rem](#quote-rem)).

**Usage:** `.quote del <user> <number>`

**Arguments:**
* `<user>`: Required. The user to find a quote for. See [.quote](#quote) for valid formats.
* `<number>`: Required. The ID number of the quote to delete (starting from 1), or "all".

**Channels:** Any

**Usable by:** Mods only

Examples:
* `.quote rem @JaneDoe 4` - Delete the 4th quote by JaneDoe.
* `.quote rem @JaneDoe all` - Remove all quotes by JaneDoe.
