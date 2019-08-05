---
category: 2.2
version: v2.2b3
subcategory: Commands
title: "Spotlight"
last_updated: 05 August 2019
summary: "Management of the World Spotlight community feature: applications, upcoming, reminders and timing."
---

The Spotlight cog provides functionality which manages the World Spotlight community
feature. A number of functions are bundled in this cog:

* Applications review and management (mod only)
* Announcing a project in the World Spotlight channel (mod only)
* Management of a queue of upcoming World Spotlight events (mod only)
* Following or unfollowing World Spotlight notifications (everyone)
* Starting a World Spotlight, timing and reminders (Spotlight Host only)

## 1. spotlight
{: #spotlight }

World Spotlight commands group. See sub-commands.

{% include tip.html content='For convenience, most sub-commands support a single-letter shorthand. Check each
command&#x27;s Usage section.' %}

**Usage**: `.spotlight`



### 1.1. spotlight join
{: #spotlight-join }

**Usage**: `.spotlight join`

<pre>Join the World Spotlight Audience. This allows you to be pinged by moderators or the Host for news like the start of a new World Spotlight or a newly released schedule.

To leave the Audience, use `.spotlight leave`.</pre>

### 1.2. spotlight leave
{: #spotlight-leave }

**Usage**: `.spotlight leave`

<pre>Leave the World Spotlight Audience. See `.help spotlight join` for more information.

To join the World Spotlight Audience, use `.spotlight join`.</pre>

### 1.3. spotlight start
{: #spotlight-start }

Start the World Spotlight. For use by the Spotlight Host.

KazTronQA will announce the start of your World Spotlight and start counting down
your remaining time. You will get periodic reminders about the time remaining, as well
as an announcement about the end of your World Spotlight.

You can stop the World Spotlight early by calling <a href="./spotlight.html#spotlight-stop">spotlight stop</a>.

**Usage**: `.spotlight start`

**Details**

Members
: Spotlight Host, Moderators, Administrators.


Channels
: #specific.


### 1.4. spotlight stop
{: #spotlight-stop }

Stop an ongoing World Spotlight previously started with <a href="./spotlight.html#spotlight-start">spotlight start</a>.

**Usage**: `.spotlight stop`

**Details**

Members
: Spotlight Host, Moderators, Administrators.


Channels
: #specific.


### 1.5. spotlight time
{: #spotlight-time }

Check the remaining time for the current World Spotlight.

**Usage**: `.spotlight time`

**Details**

Channels
: #specific.


### 1.6. spotlight list (l)
{: #spotlight-list }

List all the World Spotlight applications in summary form.

**Usage**: `.spotlight [list|l]`

**Details**

Members
: Moderators, Administrators.


### 1.7. spotlight current (c)
{: #spotlight-current }

Show the currently selected application.

The "current application" is selected by <a href="./spotlight.html#spotlight-roll">spotlight roll</a> or <a href="./spotlight.html#spotlight-select">spotlight select</a>,
and is the application used by <a href="./spotlight.html#spotlight-showcase">spotlight showcase</a> and <a href="./spotlight.html#spotlight-queue-add">spotlight queue add</a>.

**Usage**: `.spotlight [current|c]`

**Details**

Members
: Moderators, Administrators.


### 1.8. spotlight select (s)
{: #spotlight-select }

Set the currently selected application.

**Usage**: `.spotlight [select|s] <list_index>`

**Arguments**

&lt;list_index&gt;
: number. The numerical index of an application, as shown by <a href="./spotlight.html#spotlight-list">spotlight list</a>.




**Details**

Members
: Moderators, Administrators.


**Example**

* `.spotlight set 5` - Set the current application to entry

### 1.9. spotlight roll (r)
{: #spotlight-roll }

Select a World Spotlight application at random, and set it as the currently selected
application. Only applications that are marked 'ready for Spotlight' will be selected.

**Usage**: `.spotlight [roll|r]`

**Details**

Members
: Moderators, Administrators.


### 1.10. spotlight showcase
{: #spotlight-showcase }

Announce the next World Spotlight from the currently selected application in the configured public World Spotlight channel. Also switches the Spotlight Host  role to the applicant (if a valid user).

**Usage**: `.spotlight showcase`

**Details**

Members
: Moderators, Administrators.


### 1.11. spotlight queue (q)
{: #spotlight-queue }

Command group containing subcommands that allow managing the queue of upcoming World Spotlight events. See sub-commands for more information.

**Usage**: `.spotlight [queue|q]`

**Details**

Members
: Moderators, Administrators.


#### 1.11.1. spotlight queue list (l)
{: #spotlight-queue-list }

Lists the current queue of upcoming World Spotlight events.

The queue is always ordered chronologically. If two queue items have the exact same
date, the order between them is undefined.

**Usage**: `.spotlight queue [list|l]`

**Details**

Members
: Moderators, Administrators.


#### 1.11.2. spotlight queue showcase (s)
{: #spotlight-queue-showcase }

Lists the queued World Spotlight events for a given month. This is sent as markdown
in a code block, suitable for copy-pasting so that a mod can use it to prepare an
announcement.

**Usage**: `.spotlight queue [showcase|s] [month]`

**Arguments**

[month]
: date. Optional. The month for which to list queued applications. Default: next month




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.spotlight q s 2018-03`
* `.spotlight q s March 2018`

#### 1.11.3. spotlight queue add (a)
{: #spotlight-queue-add }

Add a World Spotlight application scheduled for a given date range.

The currently selected application will be added. Use <a href="./spotlight.html#spotlight-select">spotlight select</a> or
<a href="./spotlight.html#spotlight-roll">spotlight roll</a> to change the currently selected application.

**Usage**: `.spotlight queue [add|a] <daterange>`

**Arguments**

&lt;daterange&gt;
: string. A string in the form of `date1 to date2`. Each of the two dates can be in any
  of these formats:
  
  * An exact date: `2017-12-25`, `25 December 2017`, `December 25, 2017`.
  * A partial date: `April 23` (nearest future date)
  * A time expression: `tomorrow`, `next week`, `in 5 days`. You **cannot** use
  days of the week (e.g. "next Tuesday").



**Details**

{% include note.html content='KazTronQA will not take any action on the scheduled date. The date is used to order
the queue and as an informational tool to the moderators responsible for the
World Spotlight.' %}

{% include tip.html content='You can add the same World Spotlight application to the queue multiple times
(e.g. on different dates). To edit the date instead, use <a href="./spotlight.html#spotlight-queue-edit">spotlight queue edit</a>.' %}

Members
: Moderators, Administrators.


**Examples**

* `.spotlight queue add 2018-01-25 to 2018-01-26`
* `.spotlight queue add april 3 to april 5`

#### 1.11.4. spotlight queue edit (e)
{: #spotlight-queue-edit }

Change the scheduled date of a World Spotlight in the queue.

{% include important.html content='This command takes a **queue index**, as shown by <a href="./spotlight.html#spotlight-queue-list">spotlight queue list</a>.' %}

**Usage**: `.spotlight queue [edit|e] <queue_index> <daterange>`

**Arguments**

&lt;queue_index&gt;
: number. The queue position to edit, as shown with <a href="./spotlight.html#spotlight-queue-list">spotlight queue list</a>.


&lt;daterange&gt;
: string. A daterange in the form `date1 to date2`. The same kind of dates are accepted as for <a href="./spotlight.html#spotlight-queue-add">spotlight queue add</a>.




**Details**

{% include note.html content='KazTronQA will not take any action on the scheduled date. The date is used to order
the queue and as an informational tool to the moderators responsible for the
World Spotlight.' %}

Members
: Moderators, Administrators.


**Example**

* `.spotlight queue edit 3 april 3 to april 6`

#### 1.11.5. spotlight queue next (n)
{: #spotlight-queue-next }

Pop the next World Spotlight in the queue and set it as the currently selected
application. This is a useful shortcut to announce the next World Spotlight in queue,
and is usually followed by a call to <a href="./spotlight.html#spotlight-showcase">spotlight showcase</a>.

**Usage**: `.spotlight queue [next|n]`

**Details**

Members
: Moderators, Administrators.


#### 1.11.6. spotlight queue rem (r, remove)
{: #spotlight-queue-rem }

Remove a World Spotlight application from the queue.

{% include important.html content='This command takes a **queue index**, as shown by <a href="./spotlight.html#spotlight-queue-list">spotlight queue list</a>.' %}

**Usage**: `.spotlight queue [rem|r|remove] [queue_index]`

**Arguments**

[queue_index]
: number. Optional. The queue position to remove, as shown with <a href="./spotlight.html#spotlight-queue-list">spotlight queue list</a>. If not specified, then the last item in the queue is removed.




**Details**

Members
: Moderators, Administrators.


**Examples**

* `.spotlight queue rem` - Remove the last spotlight in the queue.
* `.spotlight queue rem 3` - Remove the third spotlight in the queue.

#### 1.11.7. spotlight queue insert (i)
{: #spotlight-queue-insert }

**Unsupported** as of v2.1.

**Usage**: `.spotlight queue [insert|i]`

**Details**

Members
: Moderators, Administrators.
