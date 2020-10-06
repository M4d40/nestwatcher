# my branch (wip)

## changes:
- runtime improvements (about 1/4 the runtime for me)
- better area support (no extra multipolygon areas, geofences instead of bboxes, no extra config files)
- discord output now works with a bot which edits an existing nest message. it also has static map support. static maps show nests by showing X amounts of the sprite on its nest. where X = hourly average (only works with flos tileserver)
- less reliability on local files
- cleaning up code, logs and configs
- has PR26 for better marker results
- fixes a bug where multipolygons could have had multiple nests displayed
- area data is sorted by nest_avg so most important nests are on the top

## todo
- limit emoji creation to only needed ones (avoid 50 emoji limit)
- discord tool to name parks / change the marker (?)
- show polygons on static maps
- multiple areas + multiple channels throw errors
- actually read area data (apparently it's not saved)

## quick how to setup:
- cp -r config_example config
- fill out config/config.ini
- config/areas.json is a poracle/stopwatcher/discordopole-like geofence file. every geofence in it will be scanned for nests
- config/settings.json can be used to fine-tune nest requirements (like min avg, min spawnpoints, etc). just follow the default file should be fine
- run nests.py
- you'll probably have to install some modules. i have yet to do a reqirements.txt
- to get static maps, copy nests.json to your tileserver's Templates folder
