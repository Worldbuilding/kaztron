---
wb-category: kaztest---deployed-2.4.0-manual
kaz-manual-title: KazTest - Deployed Manual
kaz-version: 2.4.0
wb-subcategory: Commands
title: "RoleManager"
last_updated: 10 November 2020
summary: "Allows the creation of commands that allow users to join and leave specific roles on"
---

This cog provides generalised capabilities for creating commands that allow users to add and
remove themselves from a role, using custom command names. This allows users to opt into
certain features, events or programmes on the Discord server, such as getting notifications
for special-interest news or live events.

These commands can be defined either via the config file, or programmatically (e.g. from
within a cog). They **cannot** dynamically be defined via commands.

## Programmatic

Within a `KazCog`-derived cog class, it is possible to access `self.roleman` anytime after
calling `super().on_ready()` in the `on_ready()` event.

An example is shown below. In this example, the current cog has a command group called
`sprint` already defined. The commands `.sprint follow` and `.sprint unfollow` would allow
any user to join and leave the "Sprinters" role (this role must already be configured on the
Discord server).

To add checks like `mod_only()`, pass a list of checks as a `checks` keyword argument to
`add_managed_role()`.

```python
try:
    self.rolemanager.add_managed_role(
        role_name="Sprinters",
        join_name="follow",
        leave_name="unfollow",
        join_msg="You will now receive notifications when others start a sprint. "
                 "You can stop getting notifications by using the `.w unfollow` command.",
        leave_msg="You will no longer receive notifications when others start a sprint. "
                  "You can get notifications again by using the `.w follow` command.",
        join_err="Oops! You're already receiving notifications for sprints. "
                 "Use the `.w unfollow` command to stop getting notifications.",
        leave_err="Oops! You're not currently getting notifications for sprints. "
                  "Use the `.w follow` command if you want to start getting notifications.",
        join_doc="Get notified when sprints are happening.",
        leave_doc="Stop getting notifications about sprints.\n\n"
                  "You will still get notifications for sprints you have joined.",
        delete=True,
        pm=True,
        group=self.sprint,
        cog_instance=self,
        ignore_extra=False
    )
except discord.ClientException:
    logger.warning("add_managed_role failed - this is fine on bot reconnect")
```

### Arguments

* `role_name`: The role to manage.
* `join_name`: The join command name. If `group` is passed, this command is a subcommand of
    that group.
* `leave_name`: The leave command name. If `group` is passed, this command is a subcommand
    of that group.
* `join_aliases`: Optional. A sequence of join command aliases.
* `leave_aliases`: Optional. An sequence of leave command aliases.
* `join_msg`: Message to send when the user successfully joins the role.
* `leave_msg`: Message to send when the user successfully leaves the role.
* `join_err`: Message when the user tries to join but is already member of the role.
* `leave_err`: Message when the user tries to leave but is not a role member.
* `join_doc`: Help string for the join command.
* `leave_doc`: Help string for the leave command.
* `delete`: Optional. If True, delete the requesting command. Default: True.
* `pm`: Optional. If True, PM the response to the user. Otherwise, respond in the same
    channel. Default: True.
* `group`: The group to add this command to. Optional.
* `cog_instance`: Optional. Cog to group this command under in the help. Default: the
    RoleManager cog.
* `checks`: Check objects to apply to the command
* Further keyword arguments can be passed. These will be passed transparently to the
    `discord.ext.commands.command` decorator. Do not include `name`, `aliases`, or
    `pass_context`, as these are handled internally.

## Configuration file

It is also possible to do this in the `config.json` file. In this case, the commands will
always appear in `.help` under RoleManager. Please see `config.example.json` for an example
of the structure, and refer to section above for documentation on the parameters.

## 1. checkin
{: #checkin }

**Usage**: `.checkin`

<pre>[MOD ONLY] Mark self as on-duty and willing to receive notifications about events needing moderator attention.</pre>

## 2. checkout
{: #checkout }

**Usage**: `.checkout`

<pre>[MOD ONLY] Mark self as off-duty. You will not receive notifications regarding events needing moderator attention.</pre>