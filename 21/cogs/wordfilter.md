---
title: "Cogs: WordFilter"
last_updated: 21 February 2018
summary: "The WordFilter cog watches for configurable words or expressions in user messages, and either warns moderators or auto-deletes the message when it detects a watched word."
---

The **WordFilter** cog is intended to be used as a moderating tool to watch the server for the use of certain words, expressions or other strings. The bot has two separate lists of filter strings:

* `delete` list: Any messages that match will be auto-deleted, and moderators are notified.
* `warn` list: Moderators are notified of the matching message, but no further action is taken.

Moderator notifications are output to either #mods or #bot-output. The output can be changed between these two channels with the `.filter switch` command.

## 1. Filter string syntax

The special character `%` will match a word boundary (any non-letter character - this means punctuation is considered, so don't worry about that!). Consequently, each word/expression in the list can be matched in four different ways:

* `foo` : Matches any sub-string `foo`, even if inside a word; for example, the words `foobar`, `zoboomafoo`, and `afoot` inside a message will all be caught.
* `%foo` : Matches any word that *starts* with `foo`. For example, `fooing` will match, but `zoboomafoo` will *not* match.
* `foo%` : Matches any word that *ends* with `foo`. For example, `zoboomafoo` will match, but `foobar` will *not*.
* `%foo%` : Matches whole words only.

You can also refer to the table below to see examples of which method will catch which sub-strings.

|           | foo | %foo | foo% | %foo% |
|:----------|:---:|:----:|:----:|:-----:|
| foo       | <i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |
| foobar    | <i class="fas fa-check text-success"></i> | <i class="fas fa-check text-success"></i> | | |
| barfoo    |<i class="fas fa-check text-success"></i> | | <i class="fas fa-check text-success"></i> | |
| barfoobar | <i class="fas fa-check text-success"></i> | | | |

{% include tip.html content="Filters are always case insensitive." %}

## 2. filter

For all sub-commands except `.filter switch`, you usually need to specify the filter type, either `del` (the auto-delete filter list) or `warn` (the warn-only filter list). You can also use the shorthand `w` or `d`.

{% include tip.html content="For convenience, all sub-commands support a single-letter shorthand. Check each command's Usage section." %}

## 2.1 list (shorthand: l)

Lists the current filters.

If `filter_type` is not given, lists all filters; otherwise, lists the specified filter.

**Usage**:
* `.filter list [filter_type]`
* `.filter l [filter_type]`

**Arguments**:
* `filter_type`: Optional. One of [`warn`, `del`, `w`, `d`]

**Users:** Moderators only

**Channels:** Mod and bot channels only

**Examples:**
* `.filter list` - Shows both auto-warn and auto-delete lists.
* `.filter list warn` - Shows warn filter list.
* `.filter list del` - Shows auto-delete filter list.
* `.filter l w` - Shows warn filter list (shorthand).

## 2.2 add (shorthand: a)

Add a new filter word/expression.

**Usage**:
* `.filter add [filter_type] [word]`
* `.filter a [filter_type] [word]`

**Arguments**:
* `filter_type`: One of `warn`, `del`, `w`, `d`
* `word`: The word or expression to filter. **If it has spaces, use quotation marks.** Use `%` at the beginning/end of the word to match word boundaries (otherwise substring matching is used).

**Users:** Moderators only

**Channels:** Mod and bot channels only

**Examples:**
* `.filter add warn %word%` - Adds "word" (as an exact word match) to the auto-warning list.
* `.filter add del "%pink flamingo%"` - Add "pink flamingo" (exact expression) to the auto-delete list.
* `.filter a w %talk` - Shorthand. Add "%talk" to the warning list - this will match any words that start with "talk".

## 3.3 rem (shorthand: r)

Remove a filter word/expression by word.

**Usage**:
* `.filter rem [filter_type] [word]`
* `.filter r [filter_type] [word]`
* `.filter remove [filter_type] [word]`

**Arguments**:
* `filter_type`: One of `warn`, `del`, `w`, `d`
* `word`: The word or expression to remove from the filter list. **If it has spaces, use quotation marks.**

**Users:** Moderators only

**Channels:** Mod and bot channels only

**Examples:**
* `.filter rem warn %word%` - Remove "%word%" from the auto-warning list.
* `.filter rem del "%pink flamingo%"` - Remove "%pink flamingo%" from the auto-delete list.


## 3.4 rnum

Remove a filter word/expression by list index.

**Usage**:
* `.filter rid [filter_type] [index]`

**Arguments**:
* `filter_type`: One of `warn`, `del`, `w`, `d`
* `index`: The index number of the filter to remove. You can get this index number using the `list` command.

**Users:** Moderators only

**Channels:** Mod and bot channels only

**Examples:**
* `.filter rem del 5` - Removes the 5th rule in the auto-delete filter.
* `.filter r w 3` - Shorthand. Removes the 3rd rule in the warning-only filter.

## 3.5 switch (shorthand: s)

Change the bot output channel for wordfilter warnings.

Switches between the configured filter warning channel and the general bot output channel (#mods and #bot-output at time of writing).

**Usage:**
* `.filter switch`
* `.filter s`

**Arguments:** None

**Users:** Moderators only

**Channels:** Mod and bot channels only
