---
title: "Cogs: RoleManager"
summary: "The RoleManager cog provides role management functionality for users. It is intended to allow users to join and leave specific roles on their own through bot commands, in order to participate or not participate in certain features (for example, to be able to get highlighted for special-interest news)."
last_updated: 25 March 2018
---


## Role Management

{% include important.html content="This section covers pre-release documentation on the v2.1 roadmap. It may not be implemented or production-ready and is subject to change." %}

This cog has generalised capabilities for public and mod-only commands that allow users to add and remove themselves from a role, using custom command names. This can be covered either via the config file or programmatically (e.g. if another cog wants to use this functionality).

### Programmatic

This can be configured either programmatically, generally in the `on_ready` event handler of other cogs:

```python
        roleman = self.bot.get_cog("RoleManager")  # type: RoleManager
        if roleman:
            roleman.add_managed_role(
                role_name=self.role_follow_name,
                join="follow",
                leave="unfollow",
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

### Configuration file

It is also possible to do this in the `config.json` file. In this case, the commands will always appear in `.help` under RoleManager. Please see `config.example.json` for an example of the structure, and also refer to the docstring for `RoleManager.add_managed_role()` for most of the parameters.

{% include links.html %}
