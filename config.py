import json

token = ""
modteam = []
filterdelete = []
filterwarn = []
warnchannel = ""
deletechannel = ""
outputchannel = ""
welcomechannel = ""
dicechannel = ""
testchannel = ""
authorID = ""
showcase = ""

data = {}

def data_import():
    with open("config.json") as json_data:
        d = json.load(json_data)
        token = d["token"]
        modteam = d["modteam"]
        warnchannel = d["WarnChannel"]
        outputchannel = d["OutputChannel"]
        welcomechannel = d["WelcomeChannel"]
        dicechannel = d["DiceChannel"]
        testchannel = d["TestChannel"]
        authorID = d["AuthorID"]
        showcase = d["ShowcaseChannel"]
    with open("dict.json") as json_data:
        d = json.load(json_data)
        filterdelete = d["delete"]
        filterwarn = d["warn"]
    return token, modteam, filterdelete, filterwarn, warnchannel, outputchannel, welcomechannel, dicechannel, testchannel, authorID, showcase

def data_assemble(delete,warn):
    data = {"delete" : delete,"warn" : warn}
    return data

def data_dump(data, path):
    with open(path,"w") as json_data:
        d = json.dump(data,json_data)

def dict_dump(delete,warn):
    data = data_assemble(delete,warn)
    data_dump(data,"dict.json")

def refresh_dict(delete,warn):
    dict_dump(delete,warn)
    with open("dict.json") as json_data:
        d = json.load(json_data)
        filterdelete = d["delete"]
        filterwarn = d["warn"]
    json_data.close()
    return filterdelete,filterwarn