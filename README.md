# PMSFnestScript
Script to analyze scanned Data from Scanner Projects (like RDM or MAD) in combination with Data from OSM (Open Street Map)

## USAGE
Edit and rename the `default.ini.example` to `default.ini`

If you want to use your own config, start it with the config argument:

`python analyze_nests.py -c myconfig.ini`<br />

You only need to add attributes to your custom config that needs to be changed.<br />
It will use the default attributes from `default.ini` if an attribute is missing in your config.<br />

**If you have different scan areas/cities** you can edit the `default.ini` and use the example city configs(*`00_city_1.ini`, ...*) in the `custom_configs` folder.<br />
**After this just start the bash script:**<br />
`./nest_them_all.sh`<br />
The script will use each config in the `custom_configs` folder, one after the other.<br />
*(If you use the given numeration in the filenames `00_city_foo.ini`, `01_city_bar.ini`, it will keep the sequence of the files.)*


## Config File Explanation

### \[Nest Config]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `TIMESPAN_SINCE_CHANGE`      | Timespan which should be used to analyze      | `Integer`       | `16`       |
| `MIN_POKEMON_NEST_COUNT`      | Minimum amount a poke must be spawned in nest area       | `Integer`       | `10`       |
| `MIN_SPAWNPOINT_NEST_COUNT`      | Minimum amount a spawnpoint must be in nest area       | `Integer`       | `10`       |
| `DELETE_OLD_NESTS`      | Delete old Nests in DB       | `Boolean`       | `True`       |
| `EVENT_POKEMON`      | Filter out event pokemon from nest analyze       | `List`       | `[]`       |
| `POKESTOP_POKEMON`      | Use also Pokemon from pokestops (ONLY USE THIS WITH RDM!)       | `Boolean`       | `True`       |
| `ANALYZE_MULTIPOLYGONS`      | Analyze only Multipolygons<br /> \[only needed if not all Nests are scanned]<br /> (Use an extra config for each park, to not get limited by API!)       | `Boolean`       | `False`       |



### \[Area]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `NAME`      | Name of the Area, this will be used for OSM filename`| `String`| `My_Area`       |
| `POINT1_LAT`      | **Point 1** - LATITUDE of **LOWER LEFT POINT** of the Reactangle Area       | `Double`       | `0.236535`       |
| `POINT1_LON`      | **Point 1** - LONGITUDE of **LOWER LEFT POINT** of the Reactangle Area       | `Double`       | `0.932723`       |
| `POINT2_LAT`      | **Point 2** - LATITUDE of **UPPER RIGHT POINT** of the Reactangle Area       | `Double`       | `0.236535`       |
| `POINT2_LON`      | **Point 2** - LONGITUDE of **UPPER RIGHT POINT** of the Reactangle Area       | `Double`       | `0.932723`       |


### [DB Read]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `HOST`      | Adresse of your Database      | `String`       | `127.0.0.1`       |
| `NAME`      | Name of the Database       | `String`       | `rdmdb`       |
| `USER`      | Username for Database       | `String`       | `rdmuser`       |
| `PASSWORD`      | Password of Username for Database       | `String`       | `my_password`       |
| `PORT`      | Port of the Database       | `Integer`       | `3307`       |
| `CHARSET`      | Charset of the Database       | `String`       | `utf8mb4`       |
| `TABLE_POKEMON`      | Name of the Pokemon Table       | `String`       | `pokemon`       |
| `TABLE_POKEMON_SPAWNID`      | Name of the Spawn id Column in pokemon table       | `String`       | `spawn_id`       |
| `TABLE_POKEMON_TIMESTAMP`      | Name of the Timestamp Column in pokemon table       | `String`       | `first_seen_timestamp`       |
| `TABLE_POKESTOP`      | Name of the Pokestop Table       | `String`       | `pokestop`       |
| `TABLE_SPAWNPOINT`      | Name of the Spawnpoint Table       | `String`       | `spawnpoint`       |
| `TABLE_SPAWNPOINT_ID`      | Name of the Spawnpoint id Column in spawnpoint table       | `String`       | `id`       |
| `TABLE_SPAWNPOINT_LAT`      | Name of the Spawnpoint Latitude Column in spawnpoint table       | `String`       | `lat`       |
| `TABLE_SPAWNPOINT_LON`      | Name of the Spawnpoint Longitude Column in spawnpoint table       | `String`       | `lon`       |
| `USE_UNIX_TIMESTAMP`      | Use Unix Timestamp in SQL Queries<br /> (only needed with MAD)       | `Boolean`       | `False`       |


### [DB Write]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `HOST`      | Adresse of your Database      | `String`       | `127.0.0.1`       |
| `NAME`      | Name of the Database       | `String`       | `rdmdb`       |
| `USER`      | Username for Database       | `String`       | `rdmuser`       |
| `PASSWORD`      | Password of Username for Database       | `String`       | `my_password`       |
| `PORT`      | Port of the Database       | `Integer`       | `3307`       |
| `CHARSET`      | Charset of the Database       | `String`       | `utf8mb4`       |
| `TABLE_NESTS`      | Name of the Nest Table       | `String`       | `nests`       |


### [Geojson]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `SAVE_PATH`      | Filepath on which the geojson file should be saved      | `String`       | `/var/www/nest.json`       |
| `GEOJSON_EXTEND`      | False => Overwrite existend file (if there is one)<br /> True => Extend the geojson file with the new analyzed data<br /> (True is normally used for main city and then on the other cities it is used False, so that the one file have data from all cities)      | `Boolean`       | `False`       |
| `DEFAULT_PARK_NAME`      | Default Name that should be used for unknown park names      | `String`       | `Unknown Parkname`       |
| `STROKE`      | Color of the Nest-Area-Line as Hex      | `String`       | `#352BFF`       |
| `STROKE-WIDTH`      | Width of the Nest-Area-Line      | `Int/Double`       | `2`       |
| `STROKE-OPACITY`      | Opacity of the Nest-Area-Line      | `Int/Double`       | `1`       |
| `FILL`      | Color of the Inner-Nest-Area as Hex      | `String`       | `#0651FF`       |
| `FILL-OPACITY`      | Opacity of the Inner-Nest-Area    | `Int/Double`       | `0.5`       |


### [Discord]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `ENABLE`      | Enable or Disable Discord Webhook      | `Boolean`       | `False`       |
| `WEBHOOK`      | Link of the Webhook that should be used       | `String`       | `https://discordapp.com/api/webhooks/xxxxx/xxxxxx`       |
| `USERNAME`      | Username the Bot uses for sending data       | `String`       | `Nest-Bot`       |
| `LANGUAGE`      | Language for the Pokemon named (`en`, `de`, `fr`, `jp`, `cz` )       | `String`       | `en`       |
| `SORT_BY`      | For which value the list should be sorted by:<br /> `name` -> Park Name<br /> `pokemon_id` -> Pokedex Nr<br /> `pokemon_name` -> Pokemon Name (Language specific)<br /> `pokemon_avg` -> Average Sighting     | `String`       | `name`       |
| `IGNORE_UNNAMED`      | Ignore Parks without Names       | `Boolean`       | `True`       |
| `TITLE`      | Title which will be written before the nest list <br /> Available Blocks: `{park_name}`     | `String`        | `**This is the Nest report for {area_name}**`       |
| `TEXT`      | Text which will be used to send to Discord <br /> Available Blocks: `{park_name}`, `{poke_name}`, `{poke_type}`,`{poke_type_emoji}`,`{poke_avg}`, `{g_maps}`, `{time}`     | `String`        | `**{park_name}**: {poke_name} ({poke_type_emoji}) => {poke_avg} per hour {g_maps} *[checked at {time}]*`       |


### [Other]
| Variable name | Description                    | Type       | Default Value       |
| ------------- | ------------- |  ------------------------------ | ------------- |
| `ENCODING`      | Encoding user in the script      | `String`       | `utf-8`       |
| `VERBOSE`      | Print out additional information       | `Boolean`       | `False`       |
| `OSM_DATE`      | Date which should be used the data from OSM<br />Niantic only update/sync their database 2-3 times a year, so **changing this date can lead to false data**<br />the default value is the current date niantic uses     | `String`       | `2019-02-24T00:00:00Z`       |
