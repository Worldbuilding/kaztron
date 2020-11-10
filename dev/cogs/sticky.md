---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Moderator
title: "Sticky"
last_updated: 10 November 2020
summary: "Maintain a sticky message at the bottom of a channel."
---

This module allows a moderator to set a "sticky" message to be maintained at the end
of a channel. This can be used for special-purpose or static channels, such as a
resource-sharing or feedback-sharing channel, to ensure that critical information about
the channel's purpose or rules are always visible to users.

## 1. sticky
{: #sticky }

Command group. Maintain an informational message at the bottom of a channel.

This module allows a moderator to set an informational message to be maintained at the
end of a channel. This can be used for special-purpose or static channels, such as a
resource-sharing or feedback-sharing channel, to ensure that critical information about
the channel's purpose or rules are always visible to users.

**Usage**: `.sticky`

**Details**

Members
: Moderators, Administrators.


### 1.1. sticky add
{: #sticky-add }

Add or update the sticky message for a channel.

This will immediately update the sticky message.

By default, the sticky message will be updated 5 seconds after a message is
posted to the channel. If multiple messages are posted before the delay elapses,
the timer is reset. Use <a href="./sticky.html#sticky-delay">sticky delay</a> to change the delay for this channel.

**Usage**: `.sticky add <channel> <msg>`

**Parameters**

&lt;channel&gt;
: channel. Channel to change


&lt;msg&gt;
: str. The message contents.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.sticky add #meta To contact the moderators, [...]` - Add or update the #meta sticky with a message about how to contact moderators.

### 1.2. sticky delay
{: #sticky-delay }

Set a non-default delay for updating the sticky message in a channel.

If a sticky message update is already scheduled, the delay will not be updated until
the next event that would trigger a delayed update.

**Usage**: `.sticky delay <channel> <delay>`

**Parameters**

&lt;channel&gt;
: channel. Channel to change


&lt;delay&gt;
: int. Delay before updating the sticky message (seconds)




**Details**

Members
: Moderators, Administrators.


**Example**

* `.sticky delay #meta 300` - Set the sticky to update after 300 seconds in

### 1.3. sticky remove (rem)
{: #sticky-remove }

Disables the sticky message in the specified channel. This will delete any
existing sticky message in that channel.

**Usage**: `.sticky [remove|rem] <channel>`

**Parameters**

&lt;channel&gt;
: channel. Channel to change




**Details**

Members
: Moderators, Administrators.


**Example**

* `.sticky rem #resources` - Disables the sticky message in the #resources channel and removes any existing messages.

### 1.4. sticky list
{: #sticky-list }

List all configured sticky messages.

**Usage**: `.sticky list`

**Details**

Members
: Moderators, Administrators.


### 1.5. sticky refresh
{: #sticky-refresh }

Immediately refresh all sticky messages in all channels.

**Usage**: `.sticky refresh`

**Details**

Members
: Moderators, Administrators.
