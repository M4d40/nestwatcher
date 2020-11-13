import pymysql

from datetime import datetime, timedelta 

class Queries():
    def get_connection(self):
        return pymysql.connect(
            host=self.config.db_host,
            user=self.config.db_user,
            password=self.config.db_password,
            database=self.config.db_name,
            port=self.config.db_port,
            autocommit=True
        )

    def get_nest_connection(self):
        return pymysql.connect(
            host=self.config.nest_db_host,
            user=self.config.nest_db_user,
            password=self.config.nest_db_password,
            database=self.config.nest_db_name,
            port=self.config.nest_db_port,
            autocommit=True
        )

    def __init__(self, config):
        self.config = config
        self.connection = self.get_connection()
        self.cursor = self.connection.cursor()

        self.nest_connection = self.get_nest_connection()
        self.nest_cursor = self.nest_connection.cursor()

        if config.scanner == "rdm":
            pokestop_select = """SELECT id, lat, lon
            FROM pokestop
            WHERE ST_CONTAINS(ST_GEOMFROMTEXT('MULTIPOLYGON(({area}))'), point(lat, lon))"""
            spawnpoint_select = """SELECT id, lat, lon
            FROM spawnpoint
            WHERE ST_CONTAINS(ST_GEOMFROMTEXT('MULTIPOLYGON(({area}))'), point(lat, lon))
            """
            mon_select = """SELECT pokemon_id, COUNT(pokemon_id) AS count
            FROM pokemon
            WHERE (
                (
                    pokestop_id IN ({pokestops})
                    OR
                    spawn_id IN ({spawnpoints})
                )
                AND
                pokemon_id IN {nest_mons}
                AND
                first_seen_timestamp >= {reset_time})
            GROUP BY pokemon_id
            ORDER BY count desc
            LIMIT 1"""
            most_mon = """SELECT pokemon_id, COUNT(pokemon_id) AS count
            FROM pokemon
            WHERE (
                pokemon_id IN {nest_mons}
                AND
                first_seen_timestamp >= {reset_time})
            GROUP BY pokemon_id
            ORDER BY count desc
            LIMIT 1"""
            all_mons = """SELECT pokemon_id, lat, lon
            FROM pokemon
            WHERE (
                pokemon_id IN {nest_mons}
                AND
                ST_CONTAINS(ST_GEOMFROMTEXT('POLYGON({area})'), point(lat, lon))
                AND
                first_seen_timestamp >= {reset_time}
            )
            """

        elif config.scanner == "mad":
            pokestop_select = ""
            spawnpoint_select = """SELECT spawnpoint, latitude, longitude
            FROM trs_spawn
            WHERE ST_CONTAINS(ST_GEOMFROMTEXT('MULTIPOLYGON(({area}))'), point(latitude, longitude))
            """
            mon_select = """SELECT pokemon_id, COUNT(pokemon_id) AS count
            FROM pokemon
            WHERE (
                spawnpoint_id IN ({spawnpoints})
                AND
                pokemon_id IN {nest_mons}
                AND
                UNIX_TIMESTAMP(last_modified) >= {reset_time})
            GROUP BY pokemon_id
            ORDER BY count desc
            LIMIT 1"""
            most_mon = """SELECT pokemon_id, COUNT(pokemon_id) AS count
            FROM pokemon
            WHERE (
                pokemon_id IN {nest_mons}
                AND
                UNIX_TIMESTAMP(last_modified) >= {reset_time})
            GROUP BY pokemon_id
            ORDER BY count desc
            LIMIT 1"""
            all_mons = """SELECT pokemon_id, latitude, longitude
            FROM pokemon
            WHERE (
                pokemon_id IN {nest_mons}
                AND
                ST_CONTAINS(ST_GEOMFROMTEXT('POLYGON({area})'), point(latitude, longitude))
                AND
                UNIX_TIMESTAMP(last_modified) >= {reset_time}
            )
            """

        nest_delete = "DELETE FROM nests"
        nest_insert = """INSERT INTO nests (
            nest_id, name, lat, lon, pokemon_id, pokemon_form, type, pokemon_count, pokemon_avg, updated,
            pokemon_ratio, polygon_type, polygon_path)
        VALUES(
            %(nest_id)s, %(name)s, %(lat)s, %(lon)s,
            %(pokemon_id)s, %(form)s, %(type)s, %(pokemon_count)s, %(pokemon_avg)s, %(current_time)s,
            %(pokemon_ratio)s, %(poly_type)s, %(poly_path)s)
        ON DUPLICATE KEY UPDATE
            pokemon_id = %(pokemon_id)s,
            pokemon_form = %(form)s,
            name = %(name)s,
            lat = %(lat)s,
            lon = %(lon)s,
            type = %(type)s,
            pokemon_count = %(pokemon_count)s,
            pokemon_avg = %(pokemon_avg)s,
            updated = %(current_time)s,
            pokemon_ratio = %(pokemon_ratio)s,
            polygon_type = %(poly_type)s,
            polygon_path = %(poly_path)s
        """

        self.queries = {
            "pokestops": pokestop_select,
            "spawns": spawnpoint_select,
            "mons": mon_select,
            "nest_delete": nest_delete,
            "nest_insert": nest_insert,
            "most_mon": most_mon,
            "all_mons": all_mons
        }

    def stops(self, area):
        self.cursor.execute(self.queries["pokestops"].format(area=area))
        return self.cursor.fetchall()

    def own_execute(self, query, connection, one=False, args=None):
        cursor = connection.cursor()
        if args is None:
            cursor.execute(query)
        else:
            cursor.execute(query, args)
        if one:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
        cursor.close()
        connection.close()
        return result

    def spawns(self, area):
        query = self.queries["spawns"].format(area=area)
        #print(query + "\n\n")
        connection = self.get_connection()
        return self.own_execute(query, connection)
    
    def mons(self, spawns, mons, time, pokestops=None):
        query = self.queries["mons"].format(spawnpoints=spawns, nest_mons=mons, reset_time=time, pokestops=pokestops)
        if not pokestops is None:
            query = query.format(pokestops=pokestops)

        connection = self.get_connection()
        return self.own_execute(query, connection, True)
    
    def all_mons(self, mons, time, fence):
        query = self.queries["all_mons"].format(nest_mons=mons, reset_time=time, area=fence)
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def most_mon(self, mons, time):
        self.cursor.execute(self.queries["most_mon"].format(nest_mons=mons, reset_time=time))
        return self.cursor.fetchone()

    def nest_delete(self):
        self.nest_cursor.execute(self.queries["nest_delete"])

    def nest_insert(self, args):
        query = self.queries["nest_insert"]
        connection = self.get_nest_connection()

        return self.own_execute(query, connection, args=args)

    def close(self):
        self.cursor.close()
        self.connection.close()

        self.nest_cursor.close()
        self.nest_connection.close()