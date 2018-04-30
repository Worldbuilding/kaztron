---
title: "Cogs: Sprint"
last_updated: 5 April 2018
summary: "The Sprint cog allows users to hold writing sprint events, in which several users get together to work on a writing project for a fixed amount of time and compete on productivity."
---

Welcome to writing sprints, where everything's made up and the words don't matter!

In writing sprints (a.k.a. word wars), you get together with a group of other server members
and write for a fixed amount of time, usually 15 or 30 minutes, on whatever project you
choose.

At the end of the sprint, you report your word count, and whoever wrote the most wins!
Not that they matter. Because you got some writing done. So you're always a winner.

Writing sprints are a great way of getting you to focus on your writing with a group of
other people. And, y'know, not just chatting with them the entire time when you told
yourself you'd get some writing done this evening.

Get writing!

## 1. sprint (shorthand: w)

{% include tip.html content="For convenience, most sub-commands support a single-letter shorthand. Check each command's Usage section." %}

### 1.1. status (shorthand: ?)

Get the current status of the sprint.

**Usage:**
* `.w status`
* `.w ?`

**Arguments:**
* None

**Channels:** #writing only

**Usable by:** Everyone

### 1.2. start (shorthand: s)

Start a new sprint.

After starting the sprint, you need to join the sprint with `.w join` in order to specify your initial wordcount.

You cannot use this command if a sprint is currently running. In this case, join the ongoing sprint or wait until it's over.

**Usage:**
* `.w start [duration [delay]]`
* `.w s [duration [delay]]`

**Arguments:**
* `[duration]`: Optional. The amount of time, in minutes, for the sprint to last. Default: 25 minutes.
* `[delay]`: Optional. The amount of time, in minutes, to wait before starting the sprint. Default: 5 minutes.

**Channels:** #writing only

**Usable by:** Everyone

**Example:**
* `.w start` - Create a 25 minute sprint, starting in 5 minutes.
* `.w start 15` - Create a 15-minute sprint, starting in 5 minutes.
* `.w start 25 1` - Create a 25-minute sprint, starting in 1 minute.

### 1.3. stop (shorthand: x)

Cancel the current sprint.

This can only be done by the creator of the sprint or moderators, and only if a sprint is ongoing or is about to start.

**Usage:**
* `.w stop`
* `.w x`

**Arguments:**
* None

**Channels:** #writing only

**Usable by:** Everyone (will only function for the creator of the sprint and moderators)

### 1.4. join (shorthand: j)

Join a sprint and set your initial wordcount.

You can also use this command to fix your initial wordcount, if you made a mistake when initially joining the sprint.

This will only work if a sprint is ongoing or has been created with `.w start`.

**Usage:**
* `.w join <wordcount>`
* `.w j <wordcount>`

**Arguments:**
* `<wordcount>`: Required. Your initial wordcount, before the start of the sprint. When you report your wordcount at the end of the sprint, your total words written during the sprint will automatically be calculated.

**Channels:** #writing only

**Usable by:** Everyone

**Example:**
* `.w join 12044` - Join the sprint with an initial wordcount of 12,044 words.

### 1.5. leave (shorthand: l)

Leave a sprint you previously joined.

You should normally only need to use this if you realise you can't stay for the entire sprint, or otherwise can't participate in the sprint.

**Usage:**
* `.w leave`
* `.w l`

**Arguments:**
* None

**Channels:** #writing only

**Usable by:** Everyone

**Example:**
* `.w leave`

### 1.6. wordcount (shorthand: c, wc)

Report your wordcount at the end of the sprint.

**Usage:**
* `.w wordcount <wordcount>`
* `.w wc <wordcount>`
* `.w c <wordcount>`

**Arguments:**
* `<wordcount>`: Required. Your final wordcount at the end of the sprint. The bot will automatically calculate your total words written during the sprint.

**Channels:** #writing only

**Usable by:** Everyone

**Example:**
* `.w c 12888` - Report that your wordcount at the end of the sprint is 12888.

### 1.7. follow

Get notified when sprints are happening.

**Usage:** `.w follow`

**Arguments:**
* None

**Channels:** All channels

**Usable by:** Everyone

### 1.8. unfollow

Stop getting notifications about sprints, unless you've already joined that sprint.

**Usage:** `.w unfollow`

**Arguments:**
* None

**Channels:** All channels

**Usable by:** Everyone

### 1.9. leader

Show the leaderboards.

**Usage:** `.w leader [date]`

**Arguments:**
* `[date]`: Optional. Various date formats are accepted like `2018-03-14`, `14 Mar 2018`, `yesterday`. If not given, shows leaderboard for all time; if specified, shows leaderboard for the week that includes the given date.

**Channels:** #writing only

**Usable by:** Everyone

**Examples:**
* `.w leader` - All-time leaderboard.
* `.w leader 2018-03-14` - Leaderboard for the week that contains 14 March 2018.

### 1.10. stats

Show stats, either global or per-user.

**Usage:** `.w stats <user> [date]`

**Arguments:**
* `<user>`: An @mention of the user to look up, or "all" for global stats.
* `[date]`: Optional. Various date formats are accepted like `2018-03-14`, `14 Mar 2018`, `yesterday`. If not given, shows stats for all time; if specified, shows stats for the week that includes the given date.

**Channels:** #writing only

**Usable by:** Everyone

**Examples:**
* `.w stats all` - Global stats for all time.
* `.w stats @JaneDoe` - Stats for JaneDoe for all time.
* `.w stats all 2018-03-14` - Global stats for the week including 14 March.

### 1.11. statreset

Reset your own stats (or any user's stats, for mods).

{% include warning.html content="This command cannot be undone!" %}

{% include tip.html content="Resetting one user's stats will not affect global stats." %}

**Usage:** `.w statreset [user]`

**Arguments:**
* `[user]`: Optional, for mods only. Reset another user's stats. Can be an @mention of another user, "global" or "all".

**Channels:** #writing only

**Usable by:** Everyone (some options are mod-only)

**Examples:**
* `.w statreset` - Reset your own stats.
* `.w statreset @JaneDoe` - Reset Jane Doe's stats (mods only).
* `.w statsreset global` - Reset global stats only (user stats are preserved).
