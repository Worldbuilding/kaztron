# coding=utf8

import asyncio
import discord
from discord.ext import commands
import random
import config
import wordfilter
import showcaser

## In the loving memory of my time as a moderator of r/worldbuilding network ##

## To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience. ##

client = commands.Bot(command_prefix='.', description='This an automated bot for r/worldbuilding discord server', pm_help= True)
Client = discord.Client()
version = "v1.2.1"
Changelog = "-Bug fixes and minor changes to the spotlight command. \n"
manual = "https://github.com/Kazandaki/KazTron/wiki"
github = "https://github.com/Kazandaki/KazTron"
roadmap = "https://docs.google.com/spreadsheets/d/1ScVRoondp50HoonVBTZz8WUmfkLnDlGaomJrG0pgGs0/edit?usp=sharing"


##init##
config.token, config.modteam, config.filterdelete, config.filterwarn, config.warnchannel, config.outputchannel, config.welcomechannel, config.dicechannel, config.testchannel, config.authorID, config.showcase = config.data_import()

filterdelete = config.filterdelete
filterwarn = config.filterwarn
warnCHID = config.warnchannel
showcaseChannel = discord.Object(id=config.showcase)




##main##

@client.event
async def on_ready():
    await client.change_presence(game=discord.Game(name='with the fate of humanity'))
    print('\n')
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('Discord API Version: ' + discord.__version__)
    print('Bot Version: ' + version)
    print('--------')

## gets a request made by a user and sends it to bot author ##
@client.command(pass_context = True, description= "Sends user requests for the bot to the bot author as PM. He's cool with it as long as it's not spam.")
async def request(ctx):
    try:
        await client.say("I forwarded your request.")
        request = str(ctx.message.content)
        author = ctx.message.author
        bot_author = discord.User(id=config.authorID)
        message = str(author) + " requested the feature " + "'" + str(request)[9:] + "' ."
        await client.send_message(bot_author,message)
    except:
        print("Error K100")

## checks messages to see if they contain specific phrases, if they do, removes the message and notifies the mod team ##
def checkmod(rolelist,message):
    ismod = False
    for role in rolelist:
        try:
            if discord.utils.get(message.server.roles, name=role) in message.author.roles:
                ismod = True
                return ismod
                break
            else:
                pass
        except:
            pass
    return ismod

## changes the bot warn channel between #mods and #bot_output ##
@client.command(pass_context = True, description="Mod only command, handles bot output")
async def switch(ctx):
    global warnCHID
    ch = warnCHID
    if checkmod(config.modteam,ctx.message)==True:
        if ch == config.warnchannel:
            warnCHID = config.outputchannel
            await client.say("Changed the auto-warning output directory to #bot_output")
        else:
            warnCHID = config.warnchannel
            await client.say("Changed the auto-warning output directory to #mods")

@client.event
async def on_message(message):
    if checkmod(config.modteam,message) == False:

        message_string = str(message.content)

        if wordfilter.filter_func(filterdelete,message_string) == True:

            await client.delete_message(message)

            usercolor = 0xff8080
            em = discord.Embed(color=usercolor)
            em.set_author(name="Auto-Delete Filter Trigger")
            em.add_field(name="User", value=message.author.mention, inline=True)
            em.add_field(name="Channel", value=message.channel.mention, inline=True)
            em.add_field(name="Timestamp", value=message.timestamp, inline=True)
            em.add_field(name="Content", value=message_string, inline=True)

            await client.send_message(discord.Object(id=warnCHID),embed=em)

        elif wordfilter.filter_func(filterwarn,message_string) == True:

            usercolor = 0xffbf80
            em = discord.Embed(color=usercolor)
            em.set_author(name="Auto-Warn Filter Trigger")
            em.add_field(name="User", value=message.author.mention, inline=True)
            em.add_field(name="Channel", value=message.channel.mention, inline=True)
            em.add_field(name="Timestamp", value=message.timestamp, inline=True)
            em.add_field(name="Content", value=message_string, inline=True)

            await client.send_message(discord.Object(id=warnCHID),embed=em)

        else:
            pass
    await client.process_commands(message)


## world spotlight, rolls for a user submitted world from the spreadsheet etc ##
@client.command(pass_context = True, description = "Mod only command for world spotlight")
async def spotlight(ctx):
        commandraw = str(ctx.message.content)
        command = commandraw[11:]
        if command == "join":
            server = ctx.message.server
            if discord.utils.get(ctx.message.server.roles, name='Spotlight Audience') in ctx.message.author.roles:
                await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Spotlight Audience'))
                await client.delete_message(ctx.message)
                await client.send_message(ctx.message.author, "You are no longer part of the world spotlight audience, this means you can not be mass pinged by the moderators or the host. You can use the same command to join the audience again.")
                print("Took audience role from " + str(ctx.message.author) + "\n")
            else:
                await client.add_roles(ctx.message.author, discord.utils.get(server.roles, name='Spotlight Audience'))
                await client.delete_message(ctx.message)
                await client.send_message(ctx.message.author, "You are now a part of the world spotlight audience, this means you can be mass pinged by the moderators or the host.. You can use the same command to leave the audience.")
                print("Gave audience role to " + str(ctx.message.author) + "\n")
        else:
            if checkmod(config.modteam, ctx.message) == True:

                if command[:6] == "choose":
                    try:
                        global lucky

                        list_nu = int(command[7:])-2

                        lucky = showcaser.choose(list_nu)

                        user = discord.User(id=lucky[2])

                        usercolor = 0x80AAFF

                        em = discord.Embed(color=usercolor)

                        em.add_field(name="Author", value=user.mention, inline=False)
                        em.add_field(name="Project Name", value=lucky[4], inline=False)
                        em.add_field(name="Project Description", value=lucky[11], inline=False)

                        if lucky[8] != "n/a":
                            em.add_field(
                                name="Are there any mature or controversial issues that you explore or discuss in your world?",
                                value=lucky[8], inline=False)
                        else:
                            pass

                        em.add_field(name="Keywords", value=lucky[5], inline=False)

                        if lucky[14] and lucky[14].lower() != "n/a":
                            em.add_field(name="Project Art", value="[Click Here](%s)" % lucky[14], inline=True)
                        else:
                            pass

                        if lucky[15] and lucky[14].lower() != "n/a":
                            em.add_field(name="Additional Content", value="[Click Here](%s)" % lucky[15], inline=True)
                        else:
                            pass

                        await client.say(embed=em)

                    except:
                        await client.say("Error choosing a specific candidate. "
                                         "The list number might be out of range or the message might be exceeding the character limit (2000).")

                elif command == "roll":

                    lucky = showcaser.roll()

                    user = discord.User(id=lucky[2])

                    usercolor = 0x80AAFF

                    em = discord.Embed(color=usercolor)

                    em.add_field(name="Author", value=user.mention, inline=False)
                    em.add_field(name="Project Name", value=lucky[4], inline=False)
                    em.add_field(name="Project Description", value=lucky[11], inline=False)

                    if lucky[8] != "n/a":
                        em.add_field(
                            name="Are there any mature or controversial issues that you explore or discuss in your world?",
                            value=lucky[8], inline=False)
                    else:
                        pass

                    em.add_field(name="Keywords", value=lucky[5], inline=False)

                    if lucky[14] != "":
                        em.add_field(name="Project Art", value="[Click Here](%s)" % lucky[14], inline=True)
                    else:
                        pass

                    if lucky[15] != "":
                        em.add_field(name="Additional Content", value="[Click Here](%s)" % lucky[15], inline=True)
                    else:
                        pass

                    await client.say(embed=em)


                elif command == "current":
                    if lucky:
                        user = discord.User(id=lucky[2])

                        usercolor = 0x80AAFF

                        em = discord.Embed(color=usercolor)

                        em.add_field(name="Author", value=user.mention, inline=False)
                        em.add_field(name="Project Name", value=lucky[4], inline=False)
                        em.add_field(name="Project Description", value=lucky[11], inline=False)

                        if lucky[8] != "n/a":
                            em.add_field(
                                name="Are there any mature or controversial issues that you explore or discuss in your world?",
                                value=lucky[8], inline=False)
                        else:
                            pass

                        em.add_field(name="Keywords", value=lucky[5], inline=False)

                        if lucky[14] != "":
                            em.add_field(name="Project Art", value="[Click Here](%s)" % lucky[14], inline=True)
                        else:
                            pass

                        if lucky[15] != "":
                            em.add_field(name="Additional Content", value="[Click Here](%s)" % lucky[15], inline=True)
                        else:
                            pass

                        await client.say(embed=em)
                    else:
                        await client.say("Currently no candidate for world showcasing.")

                elif command == "showcase":
                    if lucky:

                        user = discord.User(id=lucky[2])

                        usercolor = 0x80AAFF

                        em = discord.Embed(color=usercolor)

                        em.add_field(name="Author", value=user.mention, inline=False)
                        em.add_field(name="Project Name", value=lucky[4], inline=False)
                        em.add_field(name="Project Description", value=lucky[11], inline=False)

                        if lucky[8] != "n/a":
                            em.add_field(
                                name="Are there any mature or controversial issues that you explore or discuss in your world?",
                                value=lucky[8], inline=False)
                        else:
                            pass

                        em.add_field(name="Keywords", value=lucky[5], inline=False)

                        if lucky[14] != "":
                            em.add_field(name="Project Art", value="[Click Here](%s)" % lucky[14], inline=True)
                        else:
                            pass

                        if lucky[15] != "":
                            em.add_field(name="Additional Content", value="[Click Here](%s)" % lucky[15], inline=True)
                        else:
                            pass

                        message = "Here is the next spotlight host and a bit about their project:"

                        await client.send_message(showcaseChannel,message)
                        await client.send_message(showcaseChannel,embed=em)

                    else:
                        await client.say("No user world to showcase!")


                else:
                    await client.say("Command not recognized.")

def list_compiler(list):
    fmt = "{0: >3d}. {1:s}"
    text = "```"

    i = 1
    for item in list:
        to_add = fmt.format(i,item)
        text += "\n " + to_add
        i += 1

    text += "```"

    return text

@client.command(pass_context = True, description= "Admin only command, adds/removes strings to/from filter list. Commands are ad, rd, aw, rw and l, you can contact me anytime to make sense of the commands.")
async def filter(ctx):
    if checkmod(config.modteam,ctx.message) == True:
        commandraw = str(ctx.message.content)
        command = commandraw[8:]

        if command.startswith("ad "):
            filterdelete.append(command[3:])
            config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete, filterwarn)
            await client.say("Added **" + str(command[3:]) + "** to the auto-delete list.")

        elif command.startswith("rd "):
            try:
                if filterdelete[int(command[3:])-1]:
                    await client.say("Removed **" + str(filterdelete[int(command[3:])-1]) + "** from the auto-delete list.")
                    del filterdelete[int(command[3:])-1]
                    config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete,filterwarn)
            except:
                await client.say("Error during operation, index number might be out of list range.")

        elif command.startswith("aw "):
            filterwarn.append(command[3:])
            config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete, filterwarn)
            await client.say("Added **" + str(command[3:]) + "** to the auto-warn list.")

        elif command.startswith("rw "):
            try:
                if filterwarn[int(command[3:])-1]:
                    await client.say("Removed **" + str(filterwarn[int(command[3:])-1]) + "** from the auto-warn list.")
                    del filterwarn[int(command[3:])-1]
                    config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete,filterwarn)
            except:
                await client.say("Error during operation, index number might be out of list range.")

        elif command == "list warn":
            await client.say("Currently the auto-warn filter has these strings:")
            tosay = list_compiler(filterwarn)
            await client.say(tosay)

        elif command == "list delete":
            await client.say("Currently the auto-delete filter has these strings:")
            tosay = list_compiler(filterdelete)
            await client.say(tosay)
        else:
            await client.say("Recognised modifiers for the filter command are (ad, rd, aw, rw, list delete, list warn).")


## check if the bot is online & responding to commands##

@client.command(pass_context = True, description= "Tests the bot, admin/mod only command.")
async def info(ctx):
    if checkmod(config.modteam,ctx.message) == True:
        ver = version

        usercolor = 0x80AAFF
        em = discord.Embed(color=usercolor)
        em.set_author(name="KazTron %s" %ver)
        em.add_field(name="Changelog", value=Changelog, inline=False)
        em.add_field(name="Instruction Manual", value="[Click Here](%s)"%manual, inline=True)
        em.add_field(name="GitHub Page", value="[Click Here](%s)"%github, inline=True)
        em.add_field(name="Development Roadmap", value="[Click Here](%s)"%roadmap, inline=True)
        await client.say(embed=em)
    else:
        pass

## rolls a XdY dice in allowed channels ##
@client.command(pass_context = True, description= "Rolls X amount of Y sided dice on allowed channels.")
async def rolls(ctx, dice : str):
    try:
        if ctx.message.channel == client.get_channel(id=config.dicechannel) or ctx.message.channel == client.get_channel(id=config.testchannel) or ctx.message.channel == client.get_channel(id=config.warnchannel):
            try:
                rolls, limit = map(int, dice.split('d'))
            except Exception:
                await client.say('Format has to be in NdN.')
                return
            if rolls == 0:
                await client.say("You can't roll 0 dice.")
            elif limit == 1:
                await client.say("You can't roll a dice with just one side.")
            elif limit == 0:
                await client.say("The limit for dice number&sides per die is 100.")
            elif limit > 100:
                await client.say("The limit for dice number&sides per die is 100.")
            elif rolls > 100:
                await client.say("The limit for dice number&sides per die is 100.")
            else:
                result = []
                sum = 0
                i = 0
                while i < rolls:
                    x = random.randint(1,limit)
                    result.append(x)
                    sum += x
                    i +=1
                await client.say(result)
                await client.say("Sum of your roll is: " + str(sum))
                print("Rolled dice. \n")
        else:
            await client.say("This command is only available in #tabletop")
    except:
        print("Error K300")

## Rolls FATE dice in allowed channels ##
@client.command(pass_context = True, description = "Rolls FATE dice.")
async def rollf(ctx):
    try:
        if ctx.message.channel == client.get_channel(id=config.dicechannel) or ctx.message.channel == client.get_channel(id=config.testchannel) or ctx.message.channel == client.get_channel(id=config.warnchannel):
            dice = [-1,-1,0,0,1,1]
            rolls = []
            sum = 0
            i = 0
            while i <= 3:
                choice = random.choice(dice)
                if choice == -1:
                    i += 1
                    sum += choice
                    rolls.append("-")
                elif choice == 1:
                    i += 1
                    sum += choice
                    rolls.append("+")
                elif choice == 0:
                    i += 1
                    sum += choice
                    rolls.append("0")
            await client.say(rolls)
            await client.say("Sum of your roll is: " + str(sum))
            print("Rolled FATE dice. \n")
        else:
            await client.say("This command is only available in #tabletop")
    except:
        print("Error K400")

## Adds a spesific role to allowed users on command ##
@client.command(pass_context = True, description = "Gives a mod/admin the respective name color if needed")
async def up(ctx):
    try:
        server = ctx.message.server
        if discord.utils.get(ctx.message.server.roles, name='Senior Moderators') in ctx.message.author.roles:
            await client.add_roles(ctx.message.author,discord.utils.get(server.roles, name='Distinguish-SrM'))
            await client.delete_message(ctx.message)
            print("Colored " + str(ctx.message.author) + "\n")
        elif discord.utils.get(ctx.message.server.roles, name='Moderators') in ctx.message.author.roles:
            await client.add_roles(ctx.message.author,discord.utils.get(server.roles, name='Distinguish-Mod'))
            await client.delete_message(ctx.message)
            print("Colored " + str(ctx.message.author) + "\n")
        else:
            await client.say("This command is only available for mods and admins.")
    except:
        print("Error K500")

## Removes a spesific role from allowed users on command ##
@client.command(pass_context=True, description="Takes away the respective name color from a mod/admin.")
async def down(ctx):
    try:
        server = ctx.message.server
        if discord.utils.get(ctx.message.server.roles, name='Senior Moderators') in ctx.message.author.roles:
            await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Distinguish-SrM'))
            await client.delete_message(ctx.message)
            print("Uncolored " + str(ctx.message.author) + "\n")
        elif discord.utils.get(ctx.message.server.roles, name='Moderators') in ctx.message.author.roles:
            await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Distinguish-Mod'))
            await client.delete_message(ctx.message)
            print("Uncolored " + str(ctx.message.author) + "\n")
        else:
            await client.say("This command is only available for mods and admins.")
    except:
        print("Error K600")

## Adds a spesific role to allowed users on command ##
@client.command(pass_context=True, description="Gives a user the 'tabletop' role on demand, if the user already has the role, takes it away")
async def rp(ctx):
    try:
        server = ctx.message.server
        if discord.utils.get(ctx.message.server.roles, name='tabletop') in ctx.message.author.roles:
            await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='tabletop'))
            await client.say("Taketh 'tabletop' role away.")
            print("Took tabletop role from " + str(ctx.message.author) + "\n")
        else:
            await client.add_roles(ctx.message.author, discord.utils.get(server.roles, name='tabletop'))
            await client.say("Giveth 'tabletop' role.")
            print("Gave tabletop role to " + str(ctx.message.author) + "\n")
    except:
        print("Error K900")

## finds the user with the specific id ##
@client.command(pass_context=True, description="Finds user with given ID")
async def find(ctx):
    if checkmod(config.modteam, ctx.message) == True:
        commandraw = str(ctx.message.content)
        command = commandraw[6:]
        user = discord.User(id=command)
        fmt = 'The ID belongs to this user: {0.mention}'
        await client.send_message(ctx.message.channel, fmt.format(user) )
    else:
        pass

## Welcomes a newly joined member on #Worldbuilding and outputs on the output channel##
@client.event
async def on_member_join(member):
    try:
        WelcomeChannel = config.welcomechannel
        channel = discord.Object(id=WelcomeChannel)
        output_channel = discord.Object(id=config.outputchannel)
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at #welcome-rules-etc'
        out_fmt = "{0.mention} has joined the server."
        print("Welcomed %s \n" % str(member))
        await client.send_message(channel, fmt.format(member, server))
        await client.send_message(output_channel,out_fmt.format(member))
    except:
        print("Error K700")

## Assigns "in voice" role to members who join #voice voice channel ##
@client.event
async def on_voice_state_update(before, after):
    try:
        server = after.server
        if (str(after.voice_channel) == "#voice"):
            await client.add_roles(after,discord.utils.get(server.roles, name='in voice'))
            print("Given 'in voice' role to %s \n" % str(after))
        elif after.voice_channel == None:
            await client.remove_roles(after,discord.utils.get(server.roles, name='in voice'))
            print("Taken 'in voice' role from %s \n" % str(after))
        else:
            pass
    except:
        print("Error K800")

loop = asyncio.get_event_loop()

## init client ##
try:
    loop.run_until_complete(client.login(config.token))
    loop.run_until_complete(client.connect())
except Exception:
    loop.run_until_complete(client.close())
finally:
    loop.close()
