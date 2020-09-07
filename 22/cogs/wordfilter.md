---
wb-category: kaztron-2.2.0-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.2.0
wb-subcategory: Moderator
title: "WordFilter"
last_updated: 07 September 2020
summary: "Watch for words or expressions in user messages, and either warn moderators or auto-delete messages on detection."
---

The WordFilter cog is a moderation tool. It watches all messages on the server for the use
of certain words, expressions or other strings. The bot has two separate lists of filter
strings, both fully configurable using bot commands:

* `del` list: Any messages that match will be auto-deleted. Moderators are notified.
* `warn` list: Moderators are notified of the matching message.

Moderator notifications are output to either #bot-output or #mods; this
can be switched using the <a href="./wordfilter.html#filter-switch">filter switch</a> command.

## Filter string syntax

The special character `%` will match a word boundary (any non-letter character).
Each word/expression in the list can be matched in four  different ways:

* `foo` : Matches any sub-string `foo`, even if inside a word; for example, the words
  `foobar`, `zoboomafoo`, and `afoot` inside a message will all be caught.
* `%foo` : Matches any word that *starts* with `foo`. For example, `fooing` will match, but
  `zoboomafoo` will *not* match.
* `foo%` : Matches any word that *ends* with `foo`. For example, `zoboomafoo` will match,
  but *not* `foobar`.
* `%foo%` : Matches whole words only.

You can also refer to the table below to see examples of which method will catch which
sub-strings.

|           | foo | %foo | foo% | %foo% |
|:----------|:---:|:----:|:----:|:-----:|
| foo       | <i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |
| foobar    | <i class="fas fa-check text-success"></i> | <i class="fas fa-check text-success"></i> | | |
| barfoo    |<i class="fas fa-check text-success"></i> | | <i class="fas fa-check text-success"></i> | |
| barfoobar | <i class="fas fa-check text-success"></i> | | | |

{% include tip.html content='Filters are always case insensitive.' %}

## 1. filter
{: #filter }

Command group to manages the filter lists.

For all sub-commands except <a href="./wordfilter.html#filter-switch">filter switch</a>, you need to specify the filter list,
either `del` (auto-delete list) or `warn` (warn-only list). You can also use the
shorthand `d` or `w`.

{% include tip.html content='For convenience, all sub-commands support a single-letter shorthand. Check each
command&#x27;s Usage section.' %}

**Usage**: `.filter`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 1.1. filter list (l)
{: #filter-list }

Lists the current filters.

If `filter_type` is not given, lists all filters; otherwise, lists the specified filter.

**Usage**: `.filter [list|l] [filter_type]`

**Parameters**

[filter_type]
: Optional. Filter list: `del` or `warn` (shorthand: `d` or `w`). Default: both




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.filter list` - Shows both auto-warn and auto-delete lists.
* `.filter list warn` - Shows warn filter list.
* `.filter list del` - Shows auto-delete filter list.
* `.filter l w` - Shorthand version of `.filter list warn`.

### 1.2. filter add (a)
{: #filter-add }

Adds a new filter word/expression.

**Usage**: `.filter [add|a] <filter_type> <word>`

**Parameters**

&lt;filter_type&gt;
: Filter list: `del` or `warn` (shorthand: `d` or `w`).


&lt;word&gt;
: string. The word or expression to filter. **If it has spaces, use quotation marks.** See
  <a href="./wordfilter.html">WordFilter</a> (or `.help WordFilter` in-bot) for information on matching syntax.



**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.filter add warn %word%` - Adds "word" (as an exact word match) to the auto-warning list.
* `.filter add del "%pink flamingo%"` - Add "pink flamingo" (exact expression) to the auto-delete list.
* `filter a w %talk` - Shorthand. Add "%talk" to the warning list - this will match any words that start with "talk".

### 1.3. filter rem (r, remove)
{: #filter-rem }

Remove a filter word/expression by word.

**Usage**: `.filter [rem|r|remove] <filter_type> <word>`

**Parameters**

&lt;filter_type&gt;
: Filter list: `del` or `warn` (shorthand: `d` or `w`).


&lt;word&gt;
: string. The word or expression to remove. **If it has spaces, use quotation marks.**




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.filter rem warn %word%` - Remove "%word%" from the auto-warning list.
* `.filter r d "%pink flamingo%"` - Shorthand. Remove "%pink flamingo%" from the auto-delete list.

### 1.4. filter rnum
{: #filter-rnum }

Remove a filter word/expression by list index.

**Usage**: `.filter rnum <filter_type> <index>`

**Parameters**

&lt;filter_type&gt;
: Filter list: `del` or `warn` (shorthand: `d` or `w`).


&lt;index&gt;
: number. The index number of the filter to remove. You can get this index number using the
  <a href="./wordfilter.html#filter-list">filter list</a> command.



**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.filter rnum del 5` - Removes the 5th rule in the auto-delete filter.
* `.filter rnum w 3` - Shorthand. Removes the 3rd rule in the warning-only filter.

### 1.5. filter switch (s, sw)
{: #filter-switch }

Change the bot output channel for WordFilter warnings.

Switches between the #bot-output and #mods channels.

**Usage**: `.filter [switch|s|sw]`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


## 2. switch
{: #switch }

DEPRECATED.

**Usage**: `.switch`

**Details**

Members
: Moderators, Administrators.
