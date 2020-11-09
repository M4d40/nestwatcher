CREATE TABLE `nests` (
  `nest_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `lat` double(18,14) DEFAULT NULL,
  `lon` double(18,14) DEFAULT NULL,
  `pokemon_id` int(11) DEFAULT 0,
  `pokemon_form` smallint(6) DEFAULT NULL,
  `name` varchar(250) DEFAULT NULL,
  `pokemon_count` double DEFAULT 0,
  `pokemon_avg` double DEFAULT 0,
  `pokemon_ratio` double DEFAULT 0,
  `polygon_type` tinyint(1) DEFAULT 0,
  `polygon_path` varchar(20000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `type` tinyint(1) NOT NULL DEFAULT 0,
  `updated` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`nest_id`),
  KEY `CoordsIndex` (`lat`,`lon`),
  KEY `UpdatedIndex` (`updated`)
) ENGINE=InnoDB AUTO_INCREMENT=671440879 DEFAULT CHARSET=utf8;
;