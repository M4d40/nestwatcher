# PMSFnestScript
Script to analyze scanned Data from Scanner Projects (like RDM or MAD) in combination with Data from OSM (Open Street Map)

If you want to use your own config, start it with the config argument:
python analyze_nests.py -c myconfig.ini

You only need to add attributes to your custom config that needs to be changed.
It will use the default attributes from default.ini if an attribute is missing in your config.

Config File Explanation
-----------------------
[Nest Config]
# Timespan in hours since last change
TIMESPAN_SINCE_CHANGE = 16
# Minimum amount a poke must be spawned in nest area
MIN_POKEMON_NEST_COUNT = 10
# Delete old Nests in DB
DELETE_OLD_NESTS = True
# Filter out event pokemon from nest analyze
EVENT_POKEMON = [370]

[Area]
# Lower Left Point of the Reactangle Area
POINT1_LAT = 0.360852
POINT1_LON = 0.925244
# Upper Right Point of the Reactangle Area
POINT2_LAT = 0.446112
POINT2_LON = 0.061136

[Other]
# Gives out all configs, for debugging
VERBOSE = False
