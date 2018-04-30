---
title: "Cogs: RoleManager"
summary: "The RoleManager cog provides role management functionality for users. It is intended to allow users to join and leave specific roles on their own through bot commands, in order to participate or not participate in certain features (for example, to be able to get highlighted for special-interest news)."
last_updated: 18 April 2018
---

## Role Management

This cog has generalised capabilities for public and mod-only commands that allow users to add and remove themselves from a role, using custom command names. This can be covered either via the config file or programmatically (e.g. if another cog wants to use this functionality).

### Programmatic

This can be configured either programmatically, generally in the `on_ready` event handler of other cogs. As an example:

```python
        roleman = self.bot.get_cog("RoleManager")  # type: RoleManager
        if roleman:
            roleman.add_managed_role(
                role_name=self.role_follow_name,
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
        else:
            err_msg = "Cannot find RoleManager - is it enabled in config?"
            logger.error(err_msg)
            try:
                await self.bot.send_message(self.dest_output, err_msg)
            except discord.HTTPException:
                logger.exception("Error sending error to {}".format(self.dest_output_id))
```

This would allow users to join and leave the role with `.sprint follow` and `.sprint unfollow`. To add checks, e.g. `mod_only()`, pass a list of checks to the `checks` kwarg. In this case, if `cog_instance` is passed, then the commands will appear under that cog's name in the `.help` output; if it is not passed, the command will appear under RoleManager. Please see the docstring for `RoleManager.add_managed_role()` for more information.

**Arguments**

* `role_name`: The role to manage.
* `join_name`: The join command name.
* `leave_name`: The leave command name.
* `join_aliases`: An iterable of join command aliases. Optional.
* `leave_aliases`: An iterable of leave command aliases. Optional.
* `join_msg`: Message to send when the user successfully joins the role.
* `leave_msg`: Message to send when the user successfully leaves the role.
* `join_err`: Message when the user tries to join but is already member of the role.
* `leave_err`: Message when the user tries to leave but is not a role member.
* `join_doc`: Help string for the join command.
* `leave_doc`: Help string for the leave command.
* `delete`: Optional. If True, delete the requesting command. Default: True.
* `pm`: Optional. If True, PM the response to the user. Otherwise, respond in the same channel. Default: True.
* `group`: The group to add this command to. Optional.
* `cog_instance`: Cog to group this command under in the help. Optional, defaults to the RoleManager cog.
* `checks`: Check objects to apply to the command
* `kwargs`: Keyword args to pass the ``discord.ext.commands.command`` decorator. Do not include `name`, `aliases`, or `pass_context`. Can also include checks here, e.g., for if only certain users should be able to use these commands.

### Configuration file

It is also possible to do this in the `config.json` file. In this case, the commands will always appear in `.help` under RoleManager. Please see `config.example.json` for an example of the structure, and also refer to section above for documentation on the other parameters.

{% include links.html %}
