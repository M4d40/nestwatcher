from configparser import ConfigParser

class Config:
    def __init__(self, config_path="config/config.ini"):
        config_file = ConfigParser()
        config_file.read(config_path)

        self.hours_since_change = 3
        self.auto_time = config_file.getboolean("Config", "auto_time", fallback=True)
        self.use_events = config_file.getboolean("Config", "events", fallback=True)
        self.less_queries = config_file.getboolean("Config", "less_queries", fallback=False)
        self.pokestop_pokemon = config_file.getboolean("Config", "pokestop_pokemon")
        self.in_meganest = config_file.getboolean("Config", "i_scan_berlin", fallback=False)
        self.workers = 5

        self.scanner = config_file.get("Scanner DB", "scanner")
        self.db_name = config_file.get("Scanner DB", "name")
        self.db_user = config_file.get("Scanner DB", "user")
        self.db_password = config_file.get("Scanner DB", "password")
        self.db_host = config_file.get("Scanner DB", "host")
        self.db_port = config_file.getint("Scanner DB", "port")
        self.custom_pokemon = config_file.get("Scanner DB", "custom_pokemon_table", fallback="pokemon")

        self.nest_db_name = config_file.get("Nest DB", "name")
        self.nest_db_user = config_file.get("Nest DB", "user")
        self.nest_db_password = config_file.get("Nest DB", "password")
        self.nest_db_host = config_file.get("Nest DB", "host")
        self.nest_db_port = config_file.getint("Nest DB", "port")

        self.default_park_name = config_file.get("Geojson", "default_park_name")
        self.json_path = config_file.get("Geojson", "path")
        self.json_stroke = config_file.get("Geojson", "stroke")
        self.json_stroke_width = config_file.getint("Geojson", "stroke_width")
        self.json_stroke_opacity = config_file.getfloat("Geojson", "stroke_opacity")
        self.json_fill = config_file.get("Geojson", "fill")
        self.json_fill_opacity = config_file.getfloat("Geojson", "fill_opacity")

        self.discord_token = config_file.get("Discord", "token")
        self.language = config_file.get("Discord", "language")
        self.static_url = config_file.get("Discord", "tileserver_url")
        self.icon_repo = config_file.get("Discord", "icon_repo")