test = {
    "server1": {
        "mon1": "emote1",
        "mon2": "emote2"
    },
    "server2": {
        "mon3": "emote3",
        "mon4": "emote4"
    }
}
emote_refs = {}
for server, data in test.items():
    print(server)
    for mid, eid in data.items():
        emote_refs[mid] = eid
print(emote_refs)