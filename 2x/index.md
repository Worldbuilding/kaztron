---
title: "KazTron - Introduction"
last_updated: 25 May 2021
---

{% assign page_url_split = page.url | split: '/' %}
{% capture data_name %}{{page_url_split[1]}}{% endcapture %}
{% assign data = site.data[data_name] %}

KazTron is the /r/worldbuilding Discord server's resident helper bot! It mostly helps the moderators manage the community and run features like the World Spotlight, with a few automation features that happen behind the scenes, and a few commands of use to our members.

This website documents the usage of the various commands, organised by module. Note that not all modules may be loaded, depending on needs as judged by the moderation team.

{% include note.html content="Setting up a copy of KazTron is outside the scope of this manual. For any inquiries, you can get in touch with us via [Reddit modmail](https://www.reddit.com/message/compose?to=%2Fr%2Fworldbuilding&subject=KazTron&message=I%27m%20writing%20to%20you%20about%20KazTron.%0D%0D%3CType%20your%20comments%20here%3E) or the #meta channel of our Discord server." %}

{% include important.html content="KazTron is designed for use on one Discord server at a time. It is not possible to invite it to other Discord servers: you would need to host it yourself on a separate bot account and on your own server/VPS." %}

## How to use KazTron commands

KazTron is mostly a command-based bot: in a Discord text channel, you send a command starting with `.` and KazTron will pick up on the command and respond to you. As an example, a command to add three numbers together could look like this (this is an illustrative example and doesn't really exist):

```
.add 4 191 33
```

The command is `add`, and there are three arguments, `4`, `191` and `33`.

{% include tip.html content="If you see your command message instantly disappear, don't panic&mdash;check your PMs! For *some* commands, this is done to avoid channel spam." %}


### Examples

If you want to be notified about World Spotlight events and updates, you can type this command *in any channel*:

```
.info
```

If you want to roll dice, say three 20-sided dice, you could type the following message in any channel:

```
.roll 3d20
```

## Getting Help

In addition to this manual, you can always get contextual help from within Discord. To get a list of commands you can use, type `.help` into any channel on the server. To get help on specific commands, you can type `.help <command>`, or even get help with subcommands using `.help <command> <subcommand>`.

For example, `.help spotlight` will give you general information on the spotlight bot features, whereas `.help spotlight join` will specifically tell you about the "join" subcommand and its syntax. (In this case, the commands are both very simple, though!)

You can always ask us for help in the #meta channel of the Discord server.

### Command syntax and design

This is a more technical version of the above how-to, and may be useful to people familiar with the Linux/\*nix command line or programmers. You can feel free to skip this section.

The structure of a command is formally defined as follows:

```
.<command_name> [subcommand1 [subcommand2 [...]]] [arg1 [arg2 [arg3...]]]
```

The `.` prefix differentiates KazTron commands from normal Discord messages.

Commands in KazTron are often hierarchical, so one or more level of subcommands may be present. For example, the `.quote` command has subcommands `.quote add`, `.quote grab`, `.quote rem`, which are all operations that affect the Quote Database feature. In general, KazTron's design philosophy is to try and keep this hierarchy limited to two levels (the command indicates the module/feature, the subcommand indicates the specific operation).

Subcommands and arguments are all space-separated. In the case that an argument needs to contain a space, you should enclose it in double quotation marks to ensure it is treated as a single argument; for example:

```
.command arg1 "arg2 has spaces in it" arg3
```

As a general design philosophy, if a command only takes one argument and that argument is expected to be textual, quotation marks are not required. (If you notice commands that don't follow this, it may be a bug; please feel free to report it on our repository.)

In some rare cases, optional keyword arguments are allowed after positional arguments, and a "free text" argument may be allowed at the very end. This is the case with the ModNotes module, for example. This kind of construction is not user-friendly and highly discouraged; at present, it is generally limited to more complex features intended for moderator or administrator use. For these commands, the syntax would be:

```
.<command_name> [subcommand1 [subcommand2 [...]]] [arg1 [arg2 [arg3...]]] [keyword1="arg_value" [keyword2="arg_value" [...]]] [full_text]
```

As an example,

```
.notes add @SomeUser watch timestamp="2016-01-01" expires="2016-03-01" A full-text description of the note here.
```

This is somewhat analogous to command-line positional arguments and options (dash arguments), such as `notes add --timestamp=2016-01-01 --expires=2016-03-03 SomeUser watch "A full-text description of the note here."` if the above example were for a CLI tool.

## The Team

KazTron is developed and operated by:

{%  assign team = site.data["kaztron-dev"].authors %}

<div class="row">
    {% for author in data.authors.authors %}
    <div class="col-md-4 col-sm-6">
        <div class="panel panel-default nav-panel text-center">
            <div class="panel-heading">
                <!-- TODO: user icons -->
                <span class="fa-stack fa-5x">
                      <i class="fas fa-circle fa-stack-2x text-primary"></i>
                      <i class="fas fa-user fa-stack-1x fa-inverse"></i>
                </span>
            </div>
            <div class="panel-body">
                <h4 class="no-toc no-anchor">{{ author.name }}</h4>
                <p>{{ author.role }}</p>
                {% if author.github != null %}
                <div><a class="icon-link" href="https://github.com/{{ author.github | downcase }}"><i class="fab fa-github"></i> {{author.github}}</a></div>
                {% endif %}
                {% if author.reddit != null %}
                <div><a class="icon-link" href="https://reddit.com/u/{{ author.reddit | downcase }}"><i class="fab fa-reddit-alien"></i> /u/{{author.reddit}}</a></div>
                {% endif %}
                {% if author.discord != null %}
                <div><i class="fab fa-discord"></i> {{author.discord}}</div>
                {% endif %}
            </div>
         </div>
    </div>
    {% endfor %}
</div>

### Former members

<div class="row">
    {% for author in data.authors.former %}
    <div class="col-md-4 col-sm-6">
        <div class="panel panel-default nav-panel text-center">
            <div class="panel-heading">
                <!-- TODO: user icons -->
                <!--span class="fa-stack fa-5x">
                      <i class="fas fa-circle fa-stack-2x text-primary"></i>
                      <i class="fas fa-user fa-stack-1x fa-inverse"></i>
                </span-->
            </div>
            <div class="panel-body">
                <h4 class="no-toc no-anchor">{{ author.name }}</h4>
                <p>{{ author.role }}</p>
                {% if author.github != null %}
                <div><a class="icon-link" href="https://github.com/{{ author.github | downcase }}"><i class="fab fa-github"></i> {{author.github}}</a></div>
                {% endif %}
                {% if author.reddit != null %}
                <div><a class="icon-link" href="https://reddit.com/u/{{ author.reddit | downcase }}"><i class="fab fa-reddit-alien"></i> /u/{{author.reddit}}</a></div>
                {% endif %}
                {% if author.discord != null %}
                <div><i class="fab fa-discord"></i> {{author.discord}}</div>
                {% endif %}
            </div>
         </div>
    </div>
    {% endfor %}
</div>

### Contributors

{% for contributor in data.authors.contributors %}
* **{{ contributor.name }}** {% for link in contributor.links %}<a class="icon-link" href="{{link.url}}" target="_blank" title="{{link.title}}"><i class="{{link.icon}}"></i></a>{% endfor %}: {{contributor.role}}
{% endfor %}

{% include links.html %}
