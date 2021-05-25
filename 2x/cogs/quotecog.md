---
wb-category: kaztron-2.5.1-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.5.1
wb-subcategory: Commands
title: "QuoteCog"
last_updated: 25 May 2021
summary: "Capture the best moments on the server!"
---

The Quotes Database helps you capture the best moments on the server! Store your fellow
members' funniest moments so that you can revisit them time and time again.

## 1. quote (quotes)
{: #quote }

Retrieve a quote matching a user and/or text search. Returns a random quote among all matching results.
TIP: To search for a quote by index number, use <a href="./quotecog.html#quote-get">quote get</a>.

**Usage**: `.[quote|quotes] [user] [search]`

**Parameters**

[user]
: @user or string or "all". Optional. The user to find a quote for. This can be an @mention, user ID, part of their name or nickname to search, or the special string "all" to find any user (i.e. search only by keyword).


[search]
: string. Optional. The text to search.




**Examples**

* `.quote` - Find a random quote.
* `.quote Jane` - Find a quote from any user whose name/nickname contains "Jane".
* `.quote @JaneDoe#0921 flamingo` - Find a quote by JaneDoe containing "flamingo".
* `.quote Jane flamingo` - Find a quote both matching user "Jane" and containing "flamingo".

### 1.1. quote get
{: #quote-get }

Retrieve a quote by index.

**Usage**: `.quote get <user> <number>`

**Parameters**

&lt;user&gt;
: @user. The user to find a quote for. Should be an @mention or a discord ID.


[number]
: number. Optional. The ID number of the quote to find (starting from 1), as shown by the <a href="./quotecog.html#quote">quote</a> and <a href="./quotecog.html#quote-list">quote list</a> commands.




**Examples**

* `.quote @JaneDoe#0921` - Find a random quote by JaneDoe.
* `.quote @JaneDoe#0921 4` - Find the 4th quote by JaneDoe.

### 1.2. quote list
{: #quote-list }

Retrieve a list of quotes. Always PMed.

**Usage**: `.quote list <user> [page]`

**Parameters**

&lt;user&gt;
: @user. The user to find a quote for. Should be an @mention or a discord ID.


[page]
: number. Optional. The page number to show, if there are more than 1 page of quotes. Default: last page (most recent)




**Examples**

* `.quote list @JaneDoe#0921` - List all quotes by JaneDoe.
* `.quote list @JaneDoe#0921 4` - List the 4th page of quotes by JaneDoe.

### 1.3. quote add
{: #quote-add }

Add a new quote manually.

{% include tip.html content='To automatically find and add a recent message, use <a href="./quotecog.html#quote-grab">quote grab</a>.' %}

**Usage**: `.quote add <user> <message>`

**Parameters**

&lt;user&gt;
: @user. The user being quoted. Should be an @mention or a discord ID.


&lt;message&gt;
: string. The quote text to add.




**Example**

* `.quote add @JaneDoe#0921 Ready for the mosh pit, shaka brah.`

### 1.4. quote grab
{: #quote-grab }

Find the most recent matching message and add it as a quote.

This command searches the 100 most recent messages in the channel. The
most recent message matching both the user and (if specified) search text is added as a
quote.

{% include tip.html content='To manually add a quote, use <a href="./quotecog.html#quote-add">quote add</a>.' %}

**Usage**: `.quote grab <user> [search]`

**Parameters**

&lt;user&gt;
: @user. The user being quoted. Should be an @mention or a discord ID.


[search]
: string. Optional. The quote text to find.




**Examples**

* `.quote grab @JaneDoe#0921` - Quote the most recent message from JaneDoe.
* `.quote grab @JaneDoe#0921 mosh pit` - Finds the most recent message from @JaneDoe containing "mosh pit".

### 1.5. quote stats
{: #quote-stats }

Get quote statistics.

**Usage**: `.quote stats`



### 1.6. quote rem
{: #quote-rem }

Remove one of your own quotes.

{% include warning.html content='This command cannot be undone!' %}

{% include important.html content='If you are being harassed via quotes, or quote are otherwise being abused,
please report this to the mods.' %}

{% include tip.html content='To delete a quote you quoted (instead of a quote attributed to you), use
<a href="./quotecog.html#quote-undo">quote undo</a> to remove the most recent one. For any other situation, contact the
mods.' %}

**Usage**: `.quote rem <number>`

**Parameters**

&lt;number&gt;
: number. The ID number of the quote to delete (starting from 1), as shown by the <a href="./quotecog.html#quote">quote</a>, <a href="./quotecog.html#quote-get">quote get</a> and <a href="./quotecog.html#quote-list">quote list</a> commands.




**Example**

* `.quote del 4` - Delete the 4th quote attributed to you.

### 1.7. quote undo
{: #quote-undo }

Remove the last quote you added.

{% include warning.html content='This command cannot be undone!' %}

{% include tip.html content='This command only undoes your own calls to <a href="./quotecog.html#quote-add">quote add</a> or <a href="./quotecog.html#quote-grab">quote grab</a>. It
does **not** undo <a href="./quotecog.html#quote-rem">quote rem</a>, and does not undo quote commands by other users.' %}

{% include tip.html content='To delete quotes attributed to you, use <a href="./quotecog.html#quote-rem">quote rem</a>.' %}

**Usage**: `.quote undo`



### 1.8. quote del
{: #quote-del }

Delete one or all quotes attributed to a user. This is a moderative command; regular users should use <a href="./quotecog.html#quote-undo">quote undo</a> or <a href="./quotecog.html#quote-rem">quote rem</a>.

**Usage**: `.quote del <user> <number>`

**Parameters**

&lt;user&gt;
: @user. The user whose quote to delete. Can be an @mention or discord ID.


&lt;number&gt;
: number or "all". The ID number of the quote to delete (starting from 1), or "all".




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.quote rem @JaneDoe#0921 4` - Delete the 4th quote by JaneDoe.
* `.quote rem @JaneDoe#0921 all` - Remove all quotes by JaneDoe.