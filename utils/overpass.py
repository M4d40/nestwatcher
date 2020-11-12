import requests

def get_osm_data(bbox, date):
    data = """
    [out:json]
    [date:"{date}"]
    [timeout:100000000000000]
    [bbox:{bbox}];
    (
        way[leisure=park];
        way[landuse=recreation_ground];
        way[leisure=recreation_ground];
        way[leisure=pitch];
        way[leisure=garden];
        way[leisure=golf_course];
        way[leisure=playground];
        way[landuse=meadow];
        way[landuse=grass];
        way[landuse=greenfield];
        way[natural=scrub];
        way[natural=heath];
        way[natural=grassland];
        way[landuse=farmyard];
        way[landuse=vineyard];
        way[landuse=farmland];
        way[landuse=orchard];
        way[natural=plateau];
        way[natural=moor];
        
        rel[leisure=park];
        rel[landuse=recreation_ground];
        rel[leisure=recreation_ground];
        rel[leisure=pitch];
        rel[leisure=garden];
        rel[leisure=golf_course];
        rel[leisure=playground];
        rel[landuse=meadow];
        rel[landuse=grass];
        rel[landuse=greenfield];
        rel[natural=scrub];
        rel[natural=heath];
        rel[natural=grassland];
        rel[landuse=farmyard];
        rel[landuse=vineyard];
        rel[landuse=farmland];
        rel[landuse=orchard];
        rel[natural=plateau];
        rel[natural=moor];
    );
    out body;
    >;
    out skel qt;

    """

    data = data.format(bbox=bbox, date=date)

    r = requests.post("http://overpass-api.de/api/interpreter", data=data)
    try:
        return r.json()
    except:
        {"remark": r.content}