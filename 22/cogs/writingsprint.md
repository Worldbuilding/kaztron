---
wb-category: kaztron-2.2.0-manual
kaz-manual-title: KazTron Manual
kaz-version: 2.2.0
wb-subcategory: Commands
title: "WritingSprint"
last_updated: 07 September 2020
summary: "Hold writing sprints, where a group of writers get together to work on their writing projects for a fixed amount of time and compete on word count."
---


## 1. sprint (w)
{: #sprint }

Welcome to writing sprints, where everything's made up and the words don't matter!

In writing sprints (a.k.a. word wars), you get together with a group of other writers,
agree on a time limit, and then write together!

At the end of the sprint, you report your word count, and whoever wrote the most wins!
Not that it matters. Because you got some writing done, so you're always a winner!

Writing sprints are a great way of getting you to focus on your writing and get some
words down on your page. And, y'know, not just chatting with them the entire time when
you told yourself you'd make some progress tonight.

Get writing!

{% include tip.html content='Most sub-commands support a single-letter shorthand for convenience. Check each
command&#x27;s Usage section for more information.' %}

**Usage**: `.[sprint|w]`

**Details**

Channels
: #writing-and-music.


### 1.1. sprint status (?)
{: #sprint-status }

Get the current status of the sprint.

**Usage**: `.sprint [status|?]`

**Details**

Channels
: #writing-and-music.


### 1.2. sprint start (s)
{: #sprint-start }

Start a new sprint.

You will also need to join the sprint with `.w j` (<a href="./writingsprint.html#sprint-join">sprint join</a>), in order to set
your starting wordcount.

{% include tip.html content='Only one sprint can happen at once. If a sprint is currently running, join the
ongoing sprint or wait until it&#x27;s over.' %}

**Usage**: `.sprint [start|s] [duration] [delay]`

**Parameters**

&lt;duration&gt;
: number in minutes. The amount of time the sprint will last.


&lt;delay&gt;
: number in minutes. The amount of time to wait before starting the sprint.




**Details**

Channels
: #writing-and-music.


**Examples**

* `.w start` - Create a 25 minute sprint, starting in 5 minutes.
* `.w start 15` - Create a 15-minute sprint, starting in 5 minutes.
* `.w start 25 1` - Create a 25-minute sprint, starting in 1 minute.

### 1.3. sprint stop (x, cancel)
{: #sprint-stop }

Cancel the current sprint.
This can only be done by the creator of the sprint or moderators.

**Usage**: `.sprint [stop|x|cancel]`

**Details**

Channels
: #writing-and-music.


### 1.4. sprint join (j)
{: #sprint-join }

Join the current sprint and set your starting wordcount.

You can also use this command to edit your starting wordcount, e.g. if you made a
mistake.

If no sprint is running, first start one with `.w s` (<a href="./writingsprint.html#sprint-start">sprint start</a>).

{% include tip.html content='You can join a sprint even if it has started.' %}

**Usage**: `.sprint [join|j] <wordcount>`

**Parameters**

[wordcount]
: number in words. Optional. Your starting wordcount, before the start of the sprint. When you later report your wordcount at the end of the sprint, your total words written during the sprint will automatically be calculated.




**Details**

Channels
: #writing-and-music.


**Example**

* `.w j 12044` - Join the sprint with an initial wordcount of 12,044 words.

### 1.5. sprint leave (l)
{: #sprint-leave }

Leave a sprint you previously joined.

Note that, if you can't stay for the entire sprint, you can also use `.w wc`
(<a href="./writingsprint.html#sprint-wordcount">sprint wordcount</a>) and `.w final` (<a href="./writingsprint.html#sprint-final">sprint final</a>) to enter your current
wordcount during the sprint.

**Usage**: `.sprint [leave|l]`

**Details**

Channels
: #writing-and-music.


### 1.6. sprint wordcount (wc, c)
{: #sprint-wordcount }

Report your wordcount at the end of a sprint.

**Usage**: `.sprint [wordcount|wc|c] <wordcount>`

**Parameters**

[wordcount]
: number in words. Optional. Your final total wordcount. Your total words written during the sprint will automatically be calculated from your starting and final wordcount.




**Details**

Channels
: #writing-and-music.


**Example**

* `.w wc 13012` - Report that your total wordcount at the end of the sprint was 13,012.

### 1.7. sprint final
{: #sprint-final }

Finalize your wordcount. Use this when you're sure you're done and that you've correctly entered your wordcount.

**Usage**: `.sprint final`

**Details**

Channels
: #writing-and-music.


### 1.8. sprint follow
{: #sprint-follow }

**Usage**: `.sprint follow`

<pre>Get notified when sprints are happening.</pre>

### 1.9. sprint unfollow
{: #sprint-unfollow }

**Usage**: `.sprint unfollow`

<pre>Stop getting notifications about sprints.

You will still get notifications for sprints you have joined.</pre>

### 1.10. sprint leader
{: #sprint-leader }

Show the leaderboards, either all-time or weekly.

If no date is specified, shows leaderboard for all time. If a date is specified, shows
the leaderboard for the week that contains that date.

**Usage**: `.sprint leader [date]`

**Parameters**

[date]
: date. Optional. Specifies the leaderboard week to show. Various date formats are accepted like 2018-03-14, 14 Mar 2018, three days ago, etc. Default: None (all time)




**Details**

Channels
: #writing-and-music.


**Examples**

* `.w leader` - All-time leaderboard.
* `.w leader 2018-03-14` - Leaderboard for the week that contains 14 March 2018.

### 1.11. sprint stats
{: #sprint-stats }

Show stats, either global or per-user and either all-time or weekly.

If no date is specified, shows stats for all time. If a date is specified, shows stats
for the week that contains that date.

**Usage**: `.sprint stats <user> [date]`

**Parameters**

&lt;user&gt;
: @user or "all". An @mention of the user to look up, or "all" for global stats.


[date]
: date. Optional. Specifies the stats week to show. Various date formats are accepted like 2018-03-14, 14 Mar 2018, three days ago, etc. Default: None (all time)




**Details**

Channels
: #writing-and-music.


**Examples**

* `.w stats all` - Global stats for all time.
* `.w stats @JaneDoe#0921` - Stats for JaneDoe for all time.
* `.w stats all 2018-03-14` - Global stats for the week including 14 March.

### 1.12. sprint statreset
{: #sprint-statreset }

Reset your own stats. Mods can reset any stats.

Resetting your own stats will not change your contribution to the global stats.

{% include important.html content='This cannot be undone.' %}

**Usage**: `.sprint statreset [user]`

**Parameters**

&lt;user&gt;
: @user, "global" or "all". Mods only. An @mention of the user whose stats are to be deleted. "global" deletes the global stats, but does not touch individual user stats. "all" deletes global stats and all user stats.




**Details**

Channels
: #writing-and-music.


**Examples**

* `.w statreset` - Reset your own stats.
* `.w statreset @JaneDoe#0921` - Reset Jane Doe's stats. Mods only.
* `.w statreset global` - Reset global stats only (user stats are preserved). Mods only.