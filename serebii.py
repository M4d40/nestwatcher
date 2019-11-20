# -*- coding: utf-8 -*-
""" Module to scrap events from serebii.

Example usage:
serebii = SerebiiPokemonGo()
last_events = serebii.get_last_x_events(5)
active_events = serebii.get_active_events()
"""

from datetime import datetime
import re
from dateutil.parser import parse  # python-dateutil

import requests
from bs4 import BeautifulSoup


class SerebiiDateUtils(object):
    """ Helper class for serebii dates. """
    def __init__(self, time_):
        self.year = 0
        self.month = 13
        self.start, self.end = time_.split("-")

    def _analyze_event_end(self):
        """ Analyze end of event. """
        if len(self.end.split()) == 3:
            self.end = parse(self.end)
            self.year = self.end.year
            self.month = self.end.month
        elif len(self.end.split()) == 2:
            day, year = self.end.split()
            end_str = "{} {} {}".format(
                day,
                self.month,
                year,
            )
            self.year = year
            self.end = parse(end_str)

    def _analyze_event_start(self):
        """ Analyze start of event. """
        if len(self.start.split()) == 3:
            self.start = parse(self.start)
            self.year = self.start.year
            self.month = self.start.month
            self._analyze_event_end()
        elif len(self.start.split()) == 2:
            start_ = parse(self.start)
            self.month = start_.month
            self._analyze_event_end()
            self.start = parse(self.start + " " + str(self.year))

    def analyze_dates(self):
        """ Analyze start and end of event. """
        self._analyze_event_start()
        return (self.start, self.end)

    def is_active(self):
        """ Return true/false if event is active. """
        now = datetime.utcnow()
        return (self.start <= now) & (self.end >= now)

class SerebiiEvent(object):
    """ Class for seribii events. """
    def __init__(self, name_, uri, start, end, active, pokemon):
        self.name = name_
        self.uri = uri
        self.start = start
        self.end = end
        self.active = active
        self.pokemon = pokemon

    def __repr__(self):
        return """
        Event Name: {name_},
        Event URI: {uri}
        Event Start: {start}
        Event End: {end}
        Event is active: {active}
        Event Pokemon: {pokemon}
        """.format(
            name_=self.name,
            uri=self.uri,
            start=self.start,
            end=self.end,
            active=self.active,
            pokemon=self.pokemon
        )

class SerebiiPokemonGo(object):
    """ Class for PokemonGo Events from serebii. """
    EVENTS_URL = "https://www.serebii.net/pokemongo/events.shtml"

    def get_last_x_events(self, amount=None):
        """ Get the last x amount of events as list. """
        events = list()
        events_req = requests.get(self.EVENTS_URL)
        events_soup = BeautifulSoup(events_req.content, 'html.parser')
        event_table = events_soup.find("table", class_="dextab")
        for event in event_table.find_all("tr")[1:amount+1]:
            e_name, e_time = event.find_all("td", class_="fooinfo")
            event_name = e_name.text

            # Parse event start and end
            if e_time.text.count("-") != 1:
                print("No valid Event-Time - or no real Event, so we don't use event_pokes")
            s_utils = SerebiiDateUtils(e_time.text)
            event_start, event_end = s_utils.analyze_dates()
            event_active = s_utils.is_active()

            event_href = event.find("a", href=True, text=True)
            event_link = "https://www.serebii.net/pokemongo/" + event_href["href"]
            event_req = requests.get(event_link)
            event_soup = BeautifulSoup(event_req.content, 'html.parser')
            rest = re.split(r'<p><font size="(\d)+"><b><u>Specific Pokémon</u></b></font></p>',
                            str(event_soup))
            event_poke_list = list()
            if len(rest) >= 3:
                soup = BeautifulSoup(rest[2], 'html.parser')
                soup_table = soup.find("table", class_="dextab")

                for event_pokes in soup_table.find_all("tr"):
                    for line in event_pokes.find_all("td", class_="cen"):
                        if line.text.strip():
                            event_poke_list.append(int(line.text.strip().replace("#", "")))
            events.append(SerebiiEvent(
                event_name,
                event_link,
                event_start,
                event_end,
                event_active,
                event_poke_list,
            ))
        return events

    def get_last_event(self):
        """ Return last event. """
        return self.get_last_x_events(1)[0]

    def get_active_events(self):
        """ Return a list of active events. """
        last_events = self.get_last_x_events(10)
        active_events = set(event for event in last_events if event.active)
        return active_events
