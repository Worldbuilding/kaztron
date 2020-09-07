---
wb-category: kaztron-2.2.0-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.2.0
wb-subcategory: Moderator
title: "ModNotes"
last_updated: 07 September 2020
summary: "Store moderation notes about users."
---

The ModNotes cog implements the storage of records for use by moderators in the course
of their duty, and as a tool of communication between moderators. It allows arbitrary text
records to be recorded, alongside with the author and timestamp, associated to various
community users.

## 1. notes (note)
{: #notes }

Access a user's moderation logs.

**Usage**: `.[notes|note] <user> [page]`

**Parameters**

&lt;user&gt;
: @user. The user for whom to retrieve moderation notes. This can be an `@mention`, a Discord ID (numerical only), or a KazTron ID (starts with `*`).


[page]
: number. Optional. The page number to show, if there are more than 1 page of notes. Default: last page (latest notes)




**Details**

10 notes are shown per page. This is partly due to Discord message length limits, and
partly to avoid too large a data dump in a single request.

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.notes @User#1234`
* `.notes 330178495568436157 3`

### 1.1. notes finduser
{: #notes-finduser }

Deprecated as of version 2.2. Use <a href="./modtools.html#whois">whois</a>.

**Usage**: `.notes finduser`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 1.2. notes add (a)
{: #notes-add }

Add a new note.

**Usage**: `.notes [add|a] <user> <type_> <note_contents>`

**Parameters**

&lt;user&gt;
: @user. User. See <a href="./modnotes.html#notes">notes</a>.


&lt;type_&gt;
: string. Type of record. One of:
  
  * `note`: Miscellaneous note
  * `good`: Positive contributions
  * `watch`: Behaviours to monitor
  * `int`: Moderator intervention
  * `warn`: Formal warning
  * `temp`: Temporary ban (enforced by bot)
  * `perma`: Permanent ban (not auto-enforced)
  * `appeal`: Formal appeal received, decisions, etc.

&lt;note_contents&gt;
: string. Complex field of the form: `[timestamp="timespec"] [expires="timespec"] <contents>`


[timestamp|starts|start|time]
: timespec. Optional. Set the note's time (e.g. of an incident). The timespec is "smart", and can accept a date/time (`3 Dec 2017 5PM` - default timezone is UTC), or relative times (`10 minutes ago`, `in 2 days`, `now`). For relative times, make sure to use the keywords `ago` or `in`, or the result might not be as expected. Quotation marks required. Do not use days of the week (e.g. Monday). Default: now


[expires|expire|ends|end]
: timespec. Optional. Set when a note expires. Affects tempbans and the <a href="./modnotes.html#notes-watches">notes watches</a> function, otherwise is a remark for moderators. See above for timespec formats. Default: never


&lt;contents&gt;
: string. The note text to store.




**Details**

Attachments in the same message as the command are saved to the note.

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.notes add @BlitheringIdiot#1234 perma Repeated plagiarism.` - Create a permanent ban record with no expiry date.
* `.notes add @BlitheringIdiot#1234 temp expires="in 7 days" Insulted @JaneDoe#0422` - Create a temp ban record that expires in 7 days.
* `.notes add @CalmPerson#4187 good timestamp="2 hours ago" Helped keep an argument in check` - Create a record for an incident 2 hours ago.

### 1.3. notes expires (x, expire)
{: #notes-expires }

Change the expiration time of an existing note.

**Usage**: `.notes [expires|x|expire] <note_id> [timespec=now]`

**Parameters**

&lt;note_id&gt;
: number. The ID of the note to edit. See <a href="./modnotes.html#notes">notes</a>.


[timespec]
: timespec. Optional. The time that the note will expire. Format is the same as <a href="./modnotes.html#notes-add">notes add</a> (but quotation marks not required). Default: now




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.notes expires 122 tomorrow` - Change the expiration time of note
* `.notes expires 138 2018-01-24` - Change the expiration time of note

### 1.4. notes rem (r, remove)
{: #notes-rem }

Remove an existing note.

**Usage**: `.notes [rem|r|remove] <note_id>`

**Parameters**

&lt;note_id&gt;
: number. The ID of the note to remove. See <a href="./modnotes.html#notes">notes</a>.




**Details**

To prevent accidental data deletion, the removed note can be viewed and restored by admin users.

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.notes rem 122` - Remove note number 122.

### 1.5. notes watches (watch)
{: #notes-watches }

Show all watches currently in effect (i.e. all `watch`, `int` and `warn` records that are not expired).

**Usage**: `.notes [watches|watch] [page]`

**Parameters**

[page]
: number. Optional. The page number to show, if there are more than 1 page of notes. Default: last page (latest notes)




**Details**

10 notes are shown per page. This is partly due to Discord message length limits, and
partly to avoid too large a data dump in a single request.

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 1.6. notes temps (temp)
{: #notes-temps }

Show all tempbans currently in effect (i.e. non-expired `temp` records).

**Usage**: `.notes [temps|temp] [page]`

**Parameters**

[page]
: number. Optional. The page number to show, if there are more than 1 page of notes. Default: last page (latest notes)




**Details**

10 notes are shown per page. This is partly due to Discord message length limits, and
partly to avoid too large a data dump in a single request.

Members
: Moderators, Administrators.


Channels
: Mod channels.


### 1.7. notes name
{: #notes-name }

Set the primary name for a user. This replaces the old name; to add aliases, use <a href="./modnotes.html#notes-alias">notes alias</a>.

**Usage**: `.notes name <user> <new_name>`

**Parameters**

&lt;user&gt;
: @user. The user to modify. See <a href="./modnotes.html#notes">notes</a> for user format.


&lt;new_name&gt;
: string. The new primary name for the user. Max 32 characters, no newlines.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.notes name @BlitheringIdiot#1234 Blathers`

### 1.8. notes alias
{: #notes-alias }

Command group. Set or remove user's aliases.

**Usage**: `.notes alias <addrem> <user> <alias>`

**Parameters**

&lt;addrem&gt;
: `add` or `rem`. Whether to add or remove an alias.


&lt;user&gt;
: @user. The user to modify. See <a href="./modnotes.html#notes">notes</a> for user format.


&lt;alias&gt;
: string. The alias to add or remove. Max 32 characters, no newlines.




**Details**

Recommended usage:

* Reddit usernames: `/u/RedditUsername`
* IRC NickServ accounts: `R:Nickname`
* Unregistered IRC users: `nick!username@hostname` masks
* Known previous names or nicknames the user's known by in the community.

**For other Discord accounts**, use <a href="./modnotes.html#notes-group">notes group</a> instead to group the accounts and their
modnotes together.

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.notes alias add @FireAlchemist#6543 The Flame Alchemist`

### 1.9. notes group
{: #notes-group }

Command group. Group accounts belonging to the same user.

A group identifiers different Discord accounts that are all considered to be the same
individual. The <a href="./modnotes.html#notes">notes</a> command will show the user info and records for both
simultaneously when either user account is looked up.

The users' notes remain separate and can be removed from the group later.

**Usage**: `.notes group`

**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


#### 1.9.1. notes group add (a)
{: #notes-group-add }

Group two users together.

If one user is already in a group, the other user is added to that group.

If both users are in separate groups, both groups are merged. This is irreversible.

See <a href="./modnotes.html#notes-group">notes group</a> for more information on grouping.

**Usage**: `.notes group [add|a] <user1> <user2>`

**Parameters**

&lt;user1, user2&gt;
: @user. The users to group. See <a href="./modnotes.html#notes">notes</a> for user format.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.notes group add @FireAlchemist#1234 @TinyMiniskirtEnthusiast#4444`

#### 1.9.2. notes group rem (r, remove)
{: #notes-group-rem }

Remove a user from the group.

See <a href="./modnotes.html#notes-group">notes group</a> for more information on grouping.

{% include note.html content='You only need to specify 1 user, who will be disassociated from all other users
in the group. The other users will remain grouped together.' %}

**Usage**: `.notes group [rem|r|remove] <user>`

**Parameters**

&lt;user&gt;
: @user. The user to modify. See <a href="./modnotes.html#notes">notes</a> for user format.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Example**

* `.notes group rem`

### 1.10. notes removed
{: #notes-removed }

Show all removed notes, optionally filtered by user.

**Usage**: `.notes removed <user> [page]`

**Parameters**

&lt;user&gt;
: @user. The user to filter by, or `all`. See <a href="./modnotes.html#notes">notes</a> for user format.


[page]
: number. Optional. The page number to show, if there are more than 1 page of notes. Default: last page (latest notes)




**Details**

Members
: Administrators.


Channels
: Admin channels.


### 1.11. notes restore
{: #notes-restore }

Restore a removed note.

**Usage**: `.notes restore <note_id>`

**Parameters**

&lt;note_id&gt;
: number. The ID of the note to remove. See <a href="./modnotes.html#notes">notes</a>.




**Details**

Members
: Administrators.


Channels
: Mod channels.


### 1.12. notes purge
{: #notes-purge }

Permanently destroy a removed note.

{% include note.html content='This function intentionally does not include a mass purge, to prevent broad data
loss, accidental or malicious.' %}

**Usage**: `.notes purge <note_id>`

**Parameters**

&lt;note_id&gt;
: number. The ID of the note to remove. See <a href="./modnotes.html#notes">notes</a>.




**Details**

Members
: Administrators.


Channels
: Mod channels.
