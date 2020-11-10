---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Moderator
title: "UserStats"
last_updated: 10 November 2020
summary: "Collect and analyse activity statistics."
---

Collects and analyses activity statistics.

No messages or personally identifiable information are stored by this module, only event
counts such as number of messages in each channel on an hour-by-hour basis.

## Operation

This module counts various events like messages, voice time, server
join/parts, etc. This information is aggregated by anonymous user hash (see below),
channel, and hour, in order to allow obtaining statistics like number of unique users per
channel, most active hours of the day, etc.

Unique users are recorded on a month-by-month basis, using a cryptographic hash algorithm
and a salt in order to ensure this data cannot be traced backwards to a specific user during
the collection  period.

At the end of each month, all user hashes are replaced with random tokens generated from a
cryptographically strong pseudorandom algorithm, ensuring that no connection to the original
user (even cryptographically obfuscated) can be made. Furthermore, the salt is regenerated
for the next month's data collection, ensuring that a user cannot be tracked month-to-month
even if data is accessed prior to the end of the month. The salt is never made available to
moderators or users, and automatically destroyed once it is no longer needed.


## File format

### userstats

Raw user data is provided as a file attachment in a gzip-compressed Excel-compatible CSV
format, containing the following columns:

|  # | Column name | Type               | Description |
|---:| ----------- |:------------------:| ----------- |
|  1 | Period      | datetime (ISO8601) | The hour during which these events were recorded, in the UTC timezone. |
|  2 | Event       | str                | Event name. One of: msg, join, part, voice, total_users. |
|  3 | User hash   | hex                | A string representing a unique user. Rows with the same user hash, recorded in the same month, indicate the same user. |
|  4 | Channel     | '#' + str          | The name of the channel in which the event was recorded. |
|  5 | Count       | int                | The number of times (or, for voice events, number of seconds) an event was recorded. |

### reports

Full reports are provided as a a Discord embed, as shown below. The data contained is the
same as the CSV columns, as shown in the table below.

{% include image.html file="kaztron/report.png" alt="Full report example"
caption="Full report." %}

Weekday and hourly reports are provided as a file attachment in a gzip-compressed
Excel-compatible CSV format, containing the columns described in the following table.

|  # | Column name      | Type               | Description |
|---:| ---------------- |:------------------:| ----------- |
|  1 | Case             | str                | For weekday reports, Monday through Sunday. For hourly reports, the hour of the day (in UTC). |
|  2 | Total users      | int                | Total number of users on the server at the end of the report period. |
|  3 | Active users     | int                | Number of unique users who sent any messages during the report period. |
|  4 | Voice users      | int                | Number of unique users who spent at least 1 second in voice chat. |
|  5 | Joins            | int                | Number of users who joined the server. This includes users who part and re-join in the report period. |
|  6 | Parts            | int                | Number of users who left the server. |
|  7 | Messages         | int                | Total number of text messages sent. |
|  8 | Messages/user    | float              | Number of messages sent per active user. |
|  9 | (stdev)          | float              | Standard deviation for column 8. |
| 10 | Voice man-hours  | float (hours)      | Total collective time, in man-hours, spent in voice channels. |
| 11 | Voice hours/user | float (hours)      | Time spent, in hours, per user in voice channels. |
| 12 | (stdev)          | float (hours)      | Standard deviation for column 11. |

## 1. userstats
{: #userstats }

Retrieve a CSV dump of stats for a date or range of dates.

If a range of dates is specified, the data retrieved is up to and *excluding* the second
date. A day starts at midnight UTC.

Note that if the range crosses month boundaries (e.g. March to April), then the unique
user IDs can be correlated between each other only within the same month. The same
user will have different IDs in different months. This is used as a anonymisation
method, to avoid long-term tracking of a unique user while allowing monthly trend
analyses.

This will generate and upload a CSV file, and could take some time. Please avoid calling
this function multiple times for the same data or requesting giant ranges.

The file is compressed using gzip. Windows users should use a modern archiving programme
like [7zip](https://www.7-zip.org/download.html); macOS users can open these files
natively. Linux users know the drill.

**Usage**: `.userstats [daterange]`

**Parameters**

[daterange]
: Optional. The period to retrieve stats for. Can be a single date (period of 24 hours is assumed), or a range of dates in the form `date1 to date2`. Each date can be specified in the ISO format (2018-01-12), in English with or without abbreviations (12 Jan 2018), or as a relative date (5 days ago). Default: last month




**Details**

{% include tip.html content='A day starts at midnight UTC.' %}

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.userstats 2018-01-12`
* `.userstats yesterday`
* `.userstats 2018-01-12 to 2018-01-14`
* `.userstats 3 days ago to yesterday`
* `.userstats 2018-01-01 to 7 days ago`

### 1.1. userstats report
{: #userstats-report }

Generate and show a statistics report for a date or range of dates.

If a range of dates is specified, the data retrieved is up to and **excluding** the
second date. A day starts at midnight UTC.

The date range cannot cross the boundary of one month, as it is not possible to
calculate per-user statistics across multiple months.

This will read and process the raw data to generate stats, and could take some time.
Please avoid calling this function multiple times for the same data or requesting giant
ranges.

The file is compressed using gzip. Windows users should use a modern archiving programme
like [7zip](https://www.7-zip.org/download.html); macOS users can open these files
natively. Linux users know the drill.

**Usage**: `.userstats report <type_> <channel> [daterange]`

**Parameters**

&lt;type&gt;
: "full", "weekday" or "hourly". Report type. "full" calculates overall stats; "weekday" generates stats for each day of the week (Monday, etc.); "hourly" generates stats for each hour of the day across the entire period.


&lt;channel&gt;
: string or "all". The name of a channel on the server, or "all".


[daterange]
: string. Optional. The range of dates to generate the report from. Same format as in <a href="./userstats.html#userstats">userstats</a>.




**Details**

Members
: Moderators, Administrators.


Channels
: Mod channels.


**Examples**

* `.report full all 2018-01-12`
* `.report full all yesterday`
* `.report full`
* `.report weekday all 3 days ago to yesterday`
* `.report hourly`