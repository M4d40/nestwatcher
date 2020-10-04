from configparser import ConfigParser

class Config:
    def __init__(self, config_path):
        config_file = ConfigParser()
        config_file.read(config_path)

        self.hours_since_change = config_file.getint("Config", "hours_since_change")
        self.pokestop_pokemon = config_file.getboolean("Config", "pokestop_pokemon")

        self.scanner = config_file.get("Scanner DB", "scanner")
        self.db_name = config_file.get("Scanner DB", "name")
        self.db_user = config_file.get("Scanner DB", "user")
        self.db_password = config_file.get("Scanner DB", "password")
        self.db_host = config_file.get("Scanner DB", "host")
        self.db_port = config_file.getint("Scanner DB", "port")

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