---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Automation
title: "WikiChannel"
last_updated: 10 November 2020
summary: "Maintain a wiki page in a Discord channel."
---

This module mirrors one or more wiki pages in a Discord channel. Pages are updated upon a
call to `.wikichannel refresh`.

The raw wiki contents are interpreted as Discord message input, including Markdown.
Any Markdown supported by Discord is supported by this module.

The wiki page is automatically split in order to fit Discord message and embed limits.
However, for more control over appearance, it is possible to manually define a message break
within the wiki page.

In addition, the following features are supported:

* Headers. However, only one level of header is supported.
* `---` defines a message break.
* `IMG: <URL>`, as the only content in a message, where `<URL>` is the URL to an image file,
  will display that image in Discord. (This relies on the Discord client's image preview
  functionality.)

## 1. wikichannel
{: #wikichannel }

Set or change the wiki page that a channel mirrors.

**Usage**: `.wikichannel <channel> <subreddit> <page_name>`

**Parameters**

&lt;channel&gt;
: channel name. Discord channel to update.


&lt;subreddit&gt;
: string. Name of subreddit of wiki page.


&lt;page_name&gt;
: string. Name of wiki page.




**Example**

* `.wikichannel #rules mysubreddit rules` - set

### 1.1. wikichannel remove (rem)
{: #wikichannel-remove }

Disables wiki mirroring to a channel.

**Usage**: `.wikichannel [remove|rem] <channel>`

**Parameters**

&lt;channel&gt;
: channel name. Discord channel to update.




**Example**

* `.wikichannel rem #rules` - disable in

### 1.2. wikichannel refresh
{: #wikichannel-refresh }

Update the specified channel with the latest wiki page configured for this channel.

**Usage**: `.wikichannel refresh <channel>`

**Parameters**

&lt;channel&gt;
: channel name. Channel to update.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.wikichannel preview #rules` - Update the wiki page in

### 1.3. wikichannel preview
{: #wikichannel-preview }

Preview the latest wiki page that is normally configured for the given channel. The
preview is posted to the channel this command is issued in, not the specified channel.
Careful, this could be spammy!

**Usage**: `.wikichannel preview [channel]`

**Parameters**

&lt;channel&gt;
: channel name. Channel the wiki page would usually show up in.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.wikichannel preview #rules` - Shows a preview of the wiki page in #rules. This preview is shown in the same channel the command is issued in.

### 1.4. wikichannel testfile
{: #wikichannel-testfile }

Preview the output of this module based on a text file stored on the bot's server. The
bot administrator must be the one to install this file.

Primarily used for testing/demoing.

**Usage**: `.wikichannel testfile`

**Details**

Members
: Moderators, Administrators.
