element = {
    "ddtags": {
        "official_name": "name"
    }
}
default_name = "unbekannt"


tags = element.get("tags", {})
name = tags.get("name", tags.get("official_name", default_name))

print(name)