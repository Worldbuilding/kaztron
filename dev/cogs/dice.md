---
title: "Dice"
last_updated: 02 August 2019
summary: "Various dice rolls and other randomness-based commands."
---


## 1. choose
{: #choose }

Need some help making a decision? Let the bot choose for you! This command
randomly chooses from a list of items.

**Usage**: `.choose <choices>`

**Arguments**

&lt;choices&gt;
: string. Two or more choices, separated by commas `,`.




**Example**

* `.choose a, b, c`

## 2. roll (rolls)
{: #roll }

Rolls dice.

**Usage**: `.[roll|rolls] <dice>`

**Arguments**

&lt;dice&gt;
: string. `ndm` format, where `n` is the number of dice to roll, and `m` is the number of sides on each die. Do not add spaces.




**Details**

Rolls an `m`-sided die `n` times, and reports the rolls and total.

Channels
: #specific.


**Example**

* `.roll 2d6` - Roll three six-sided dice.

## 3. rollf
{: #rollf }

Rolls four dice for the FATE tabletop roleplaying game system.

**Usage**: `.rollf`

**Details**

Channels
: #specific.
