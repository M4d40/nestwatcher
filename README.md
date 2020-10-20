# Nest Script
A Program to analyze nests in your area, save it to a database and send Discord notifications about them.

## Setup:
### The usual steps
- `cp -r config_example config`
- fill out the config files (details are explained below)
- `pip3 install -r requirements.txt --upgrade`

### Database
The Program requires PMSF's table structure to run. If you already have PMSF running, you can use its manualdb. If not; `mysql your_db_name < nests.sql`.

### Config files
#### config.ini
Most values are self-explanatory. Just note that:
- pokestop_pokemon only works for RDM. Ignore this if you're using MAD.
- The Geojson path should be the full path to PMSF's nest file. If you don't run PMSF, just put `geojson.json` to have it saved in the nest script directory
- Discord token: Leave blank if you don't want Discord notifications
- tileserver_url: Leave blank if you don't have a tileserver 
- max_markers_per_nest: If you scan a big area and static maps look like a mess, you can put 1
- i_scan_berlin: Set to true if you live in a meganest

#### Tileserver
This script is capable of generating static maps for a nice nest overview. To get them working, you must have [flo's tileserver](https://github.com/123FLO321/SwiftTileserverCache/) installed and copy nests.json to its `Templates` folder.

If you encounter errors, the URL length might exceed your server's limit. To fix that, you can try reducing the `max_markers` value in settings.json

#### areas.json
Every area configured here will be scanned for nests. It's the same format e.g. Poracle/Discordopole/stopwatcher use. You can copy from there, if you have those scripts set up. If not, Try creating your fences on [geojson.io](http://geojson.io/) and copy it to the right format.

#### settings.json
Settings can be used to fine-tune each area. Everything here is optional. Values configured in the default setting will be used for all areas. Possible keys:
- **area**: The name of the area
- **min_pokemon**: The total amount of nesting Pokemon that have to be found in the given timespan
- **min_spawnpoints**: The minimum amount of spawnpoints that have to exist in a nest
- **min_average**: Minimum hourly spawn average the Nest must have
- **scan_hors_per_day**: How many hours you scan that area per day
- **max_markers**: The maximum amount of markers to display on the area's static map.
- **discord**: Either a Discord webhook url or a Discord Channel ID

#### discord.json
There's two things in here. The first part is the embed template of the nest messages. You can use an embed generator like [this one](https://leovoel.github.io/embed-visualizer/) to generate it. The second part includes the template for a single nest and other settings to customize the message.
##### DTS for the first part
- `{nest_entry}` - The nest entry you can configure in the second part
- `{areaname}` - The area's name configured in areas.json
- `{staticmap}` - The static map (if you have one)
##### Second part
- **nest_entry**: The nest entry for the first part. Possible DTS:
    - `{park_name}` - The nest's name from OSM
    - `{lat}` - The nest's center lat
    - `{lon}` - The nest's center lon
    - `{mon_id}` - The nesting pokemon's ID
    - `{mon_avg}` - The nests's hourly average of nest spawns
    - `{mon_count}` - Total amount of nest spawns in the given timespan
    - `{mon_name}` - The nesting pokemon's name (in the language from your config)
    - `{mon_emoji}` - The nesting pokemon's icon (as an emote) (not supported for webhooks)
    - `{type_emoji}` - The nesting pokemon's type as an emoji (or multiple emojis)
    - `{shiny}` - Whether or not the nesting pokemon can be shiny (shown as an emoji)
- **sort_by**: The value nests are sorted by. Possible values:
    - `sort_vg`
    - `mon_count`
    - `mon_id`
    - `mon_name`
- **min_avg**: The minimum hourly average a nest needs to be posted
- **ignore_unnamed**: Whether or not to ignore parks with unknown names

TIP: If you want a Map link in your message, you can use markdown yourself, e.g. `[{park_name}](www.map.com?lat={lat}&lon={lon})`

### Data files
#### area_data
For each area you analyze, a csv file will be saved in data/area_data. In it, you can customize Each nest's name and center coordinates. TIP: To easily view the nests, copy the saved ID and put it in this URL: `https://www.openstreetmap.org/way/ID` or `https://www.openstreetmap.org/relation/ID`
#### custom_emotes.json
After you first run the script, a file called `custom_emotes.json` will be created in the data/ folder. You can set your own pokemon type emotes and shiny emote in there.

## Running the script
- Start the script using `python3 nests.py`. Two arguments are supported:
- `-t`/`--hours` to specify the timespan since last nest migration
- `-c`/`--config` if you want to use another config file
