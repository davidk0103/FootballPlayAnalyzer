"""The 32 franchises as abbreviated in current nflverse data (see docs/data.md)."""

from typing import NamedTuple


class TeamInfo(NamedTuple):
    abbreviation: str
    name: str
    conference: str
    division: str


TEAMS: tuple[TeamInfo, ...] = (
    TeamInfo("BUF", "Buffalo Bills", "AFC", "East"),
    TeamInfo("MIA", "Miami Dolphins", "AFC", "East"),
    TeamInfo("NE", "New England Patriots", "AFC", "East"),
    TeamInfo("NYJ", "New York Jets", "AFC", "East"),
    TeamInfo("BAL", "Baltimore Ravens", "AFC", "North"),
    TeamInfo("CIN", "Cincinnati Bengals", "AFC", "North"),
    TeamInfo("CLE", "Cleveland Browns", "AFC", "North"),
    TeamInfo("PIT", "Pittsburgh Steelers", "AFC", "North"),
    TeamInfo("HOU", "Houston Texans", "AFC", "South"),
    TeamInfo("IND", "Indianapolis Colts", "AFC", "South"),
    TeamInfo("JAX", "Jacksonville Jaguars", "AFC", "South"),
    TeamInfo("TEN", "Tennessee Titans", "AFC", "South"),
    TeamInfo("DEN", "Denver Broncos", "AFC", "West"),
    TeamInfo("KC", "Kansas City Chiefs", "AFC", "West"),
    TeamInfo("LAC", "Los Angeles Chargers", "AFC", "West"),
    TeamInfo("LV", "Las Vegas Raiders", "AFC", "West"),
    TeamInfo("DAL", "Dallas Cowboys", "NFC", "East"),
    TeamInfo("NYG", "New York Giants", "NFC", "East"),
    TeamInfo("PHI", "Philadelphia Eagles", "NFC", "East"),
    TeamInfo("WAS", "Washington Commanders", "NFC", "East"),
    TeamInfo("CHI", "Chicago Bears", "NFC", "North"),
    TeamInfo("DET", "Detroit Lions", "NFC", "North"),
    TeamInfo("GB", "Green Bay Packers", "NFC", "North"),
    TeamInfo("MIN", "Minnesota Vikings", "NFC", "North"),
    TeamInfo("ATL", "Atlanta Falcons", "NFC", "South"),
    TeamInfo("CAR", "Carolina Panthers", "NFC", "South"),
    TeamInfo("NO", "New Orleans Saints", "NFC", "South"),
    TeamInfo("TB", "Tampa Bay Buccaneers", "NFC", "South"),
    TeamInfo("ARI", "Arizona Cardinals", "NFC", "West"),
    TeamInfo("LA", "Los Angeles Rams", "NFC", "West"),
    TeamInfo("SEA", "Seattle Seahawks", "NFC", "West"),
    TeamInfo("SF", "San Francisco 49ers", "NFC", "West"),
)

TEAM_ABBREVIATIONS = frozenset(t.abbreviation for t in TEAMS)

# Abbreviations nflverse uses for seasons before a relocation, mapped to the franchise's
# current abbreviation so every season attaches to the same 32 teams.
FRANCHISE_ALIASES: dict[str, str] = {
    "OAK": "LV",  # Oakland Raiders, through 2019
    "SD": "LAC",  # San Diego Chargers, through 2016
    "STL": "LA",  # St. Louis Rams, through 2015
}
