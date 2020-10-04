# my branch (wip)
no rdm support yet!!

## changes:
- runtime improvements (about half the runtime for me)
- better area support (no extra multipolygon areas, geofences instead of bboxes)
- less reliability on local files
- cleaning up code, logs and configs
- has PR26 for better marker results
- fixes a bug where multipolygons could have had multiple nests displayed

i'm also adding a better discord integration. there's also support for a debug log but no way to access it yet

## quick how to setup:
- cp -r config_example config
- fill out config/config.ini
- config/areas.json is a poracle/stopwatcher/discordopole-like geofence file. every geofence in it will be scanned for nests
- config/settings.json can be used to fine-tune nest requirements (like min avg, min spawnpoints, etc). just follow the default file should be fine
- run nests.py
- you'll probably have to install some modules. i have yet to do a reqirements.txt
