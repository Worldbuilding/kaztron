---
title: "Troubleshooting KazTron"
summary: "A guide to troubleshooting and reporting bugs/problems."
last_updated: 26 February 2018
---

## Bugs

If you think you've discovered a bug in KazTron:

1. Verify that your command syntax is correct by reading the error message and checking `.help <command>`.
2. Copy the exact error message, *with* the timestamp (date + time), that was sent either in the same channel as your command or by PM.
3. **Mods only:** Gather any messages in `#bot-output` that happened at the same time as your attempted command.
4. Check if the bug is already reported on our [issue tracker](https://github.com/Worldbuilding/KazTron/issues). If yes, don't submit a new issue: comment on the old one if you think you have additional useful information.
4. Prepare a bug report with enough information for us to track it down:
    1. Who are you on the Discord? Some commands depend on user roles.
    2. What were you trying to do? What is the *exact* command you tried to use, and what channel did you try to use it in?
    3. What did you expect the command to do?
    4. What did the command actually do? Also provide any error messages output in the channel, by PM or in `#bot-output`, as gathered earlier.
5. Send us the bug report: if you have a GitHub account, you can submit an issue to the [issue tracker](https://github.com/Worldbuilding/KazTron/issues). Otherwise, you can submit it in #meta on the Discord server. **Mods:** Ping `@Bot DevOps Team` in #bot-issues.

## Unresponsive bot

If KazTron is not responding to your commands, please follow this troubleshooting procedure:

1. Check if the bot is online in the user list.
2. If the bot is online:
    1. Check for error messages in the `#bot-output` channel. If there is an error message, copy and save it for later, **including the exact timestamp** (date + time). This is important to be able to trace any errors back in the logs!
    2. Use the `.info` command to test if the bot is responding in general. If `.info` works, you know a specific command is at fault. If it doesn't, you know KazTron seems to be generally unresponsive.
    3. Ask another moderator to test the same commands you tried using originally. Check for messages in `#bot-output` again, and note down if any behaviours changed (including the error message/output if any).
    4. Ask a regular user to test commands they normally should be able to invoke. Again, gather `#bot-output` messages and any observed behaviours.
    5. **Non-mods:** Message collected information in #meta, or use the `.request` command if it's working. If it's urgent, PM or @mention an active mod.
    6. **Mods:** Message collected information to `@Bot DevOps Team` in #bot-issues.
3. If the bot is offline:
    1. **Non-mods:** Contact us in #meta and let us know that the bot is down. If it's urgent, PM or @mention an active mod.
    2. **Mods:** Ping the `@Bot DevOps Team`, or specific members, in #bot-issues. You know the drill.
