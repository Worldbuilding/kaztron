# coding=utf8

import asyncio
import discord
from discord.ext import commands
import random
import config
import wordfilter

## In the loving memory of Venntron ##

client = commands.Bot(command_prefix='.', description='This an automated bot for r/worldbuilding discord server', pm_help= True)
Client = discord.Client()
version = "v1.1.2"
Changelog = "```" \
            "Changelog: \n" \
            "-Reworked filtering, now has basic regex features. ( Thanks Laogeobunny! ) \n" \
            "-Added regex functions and known bugs to the instruction manual. \n" \
            "```"
Info = "**INSTRUCTION MANUAL**\n" \
       "<https://tinyurl.com/KazTron>"

##init##
config.token, config.modteam, config.filterdelete, config.filterwarn, config.warnchannel, config.deletechannel, config.warnalternative, config.welcomechannel, config.dicechannel, config.testchannel, config.authorID = config.data_import()

filterdelete = config.filterdelete
filterwarn = config.filterwarn
warnCHID = config.warnchannel
deleteChannel = discord.Object(id=config.deletechannel)




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
    try:
        ismod = False
        for role in rolelist:
            if discord.utils.get(message.server.roles, name=role) in message.author.roles:
                ismod = True
                return ismod
                break
            else:
                pass
        return ismod
    except:
        print("Error K200")

## changes the bot warn channel between #mods and #bot_output ##
@client.command(pass_context = True, description="Mod only command, handles bot output")
async def switch(ctx):
    global warnCHID
    ch = warnCHID
    if checkmod(config.modteam,ctx.message)==True:
        if ch == "221333052629057536":
            warnCHID = "281955353632178186"
            await client.say("Changed the auto-warning output directory to #bot_output")
        else:
            warnCHID = "221333052629057536"
            await client.say("Changed the auto-warning output directory to #mods")

@client.event
async def on_message(message):
    if checkmod(config.modteam,message) == False:
        message_string = str(message.content)
        if wordfilter.filter_func(filterdelete,message_string) == True:
            await client.delete_message(message)
            await client.send_message(deleteChannel,"Deleted message by " + str(message.author) + " in " + str(message.channel) +"for containing auto-delete filtered word. Message content: " + " ' " + message_string + " ' ")
        elif wordfilter.filter_func(filterwarn,message_string) == True:
            await client.send_message(discord.Object(id=warnCHID),"Message caught by auto-warn filter, from user " + str(message.author) + " in " + str(message.channel) +". Message content: " + " ' " + message_string + " ' ")
        else:
            pass
    await client.process_commands(message)

@client.command(pass_context = True, description= "Admin only command, adds/removes strings to/from filter list. Commands are ad, rd, aw, rw and l, you can contact me anytime to make sense of the commands.")
async def filter(ctx):
    if checkmod(config.modteam,ctx.message) == True:
        try:
            commandraw = str(ctx.message.content)
            command = commandraw[8:]
            if command.startswith("ad "):
                filterdelete.append(command[3:])
                config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete, filterwarn)
                await client.say("Added '" + str(command[3:]) + "' to the auto-delete list.")
            elif command.startswith("rd "):
                for item in filterdelete:
                    if command[3:] == item:
                        filterdelete.remove(item)
                        config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete,filterwarn)
                        await client.say("Removed '" + str(item) + "' from the auto-delete list.")
            elif command.startswith("aw "):
                filterwarn.append(command[3:])
                config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete, filterwarn)
                await client.say("Added '" + str(command[3:]) + "' to the auto-warn list.")
            elif command.startswith("rw "):
                for item in filterwarn:
                    if command[3:] == item:
                        filterwarn.remove(item)
                        config.filterdelete, config.filterwarn = config.refresh_dict(filterdelete,filterwarn)
                        await client.say("Removed '" + str(item) + "' from the auto-warn list.")
            elif command == "l":
                tosay ="Currently the auto-delete filter has these strings: " + "```" + str(filterdelete) + "```" \
                        "Currently the auto-warn filter has these strings: " + "```" + str(filterwarn) + "```"
                await client.say(tosay)
            else:
                await client.say("Recognised modifiers for the filter command are (ad, rd, aw, rw, l).")
        except:
            print("Error KA00")

## check if the bot is online & responding to commands##

@client.command(pass_context = True, description= "Tests the bot, admin/mod only command.")
async def test(ctx):
    ver = version
    if checkmod(config.modteam,ctx.message) == True:
            await client.say("KazTron " + ver + " is operational.")
            await client.say(Changelog)
            await client.say(Info)
    else:
        pass

## rolls a XdY dice in allowed channels ##
@client.command(pass_context = True, description= "Rolls X amount of Y sided dice on allowed channels.")
async def rolls(ctx, dice : str):
    try:
        if ctx.message.channel == client.get_channel(id=config.dicechannel) or ctx.message.channel == client.get_channel(id=config.testchannel):
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
        if ctx.message.channel == client.get_channel(id=config.dicechannel) or ctx.message.channel == client.get_channel(id=config.testchannel):
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

## Welcomes a newly joined member on #Worldbuilding ##
@client.event
async def on_member_join(member):
    try:
        WelcomeChannel = config.welcomechannel
        channel = discord.Object(id=WelcomeChannel)
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}!'
        print("Welcomed %s \n" % str(member))
        await client.send_message(channel, fmt.format(member, server))
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
