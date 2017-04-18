import json

token = ""
modteam = []
filterdelete = []
filterwarn = []
warnchannel = ""
deletechannel = ""
warnalternative = ""
welcomechannel = ""
dicechannel = ""
testchannel = ""
authorID = ""

data = {}

def data_import():
    with open("config.json") as json_data:
        d = json.load(json_data)
        token = d["token"]
        modteam = d["modteam"]
        warnchannel = d["WarnChannel"]
        deletechannel = d["DeleteChannel"]
        warnalternative = d["WarnAlternative"]
        welcomechannel = d["WelcomeChannel"]
        dicechannel = d["DiceChannel"]
        testchannel = d["TestChannel"]
        authorID = d["AuthorID"]
    with open("dict.json") as json_data:
        d = json.load(json_data)
        filterdelete = d["delete"]
        filterwarn = d["warn"]
    return token, modteam, filterdelete, filterwarn, warnchannel, deletechannel, warnalternative, welcomechannel, dicechannel, testchannel, authorID

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
    token, modteam, filterdelete, filterwarn = data_import()
    return filterdelete,filterwarn