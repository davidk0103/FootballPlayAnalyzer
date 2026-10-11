"""The standardized play schema that uploaded CSV columns are mapped onto.

Each field lists the CSV header names we recognize when suggesting a mapping. The
suggestion is only a starting point: the user confirms every mapping, and nothing is
inferred from columns they did not map.
"""

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    TEXT = "text"
    TEAM = "team"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    PLAY_TYPE = "play_type"
    SEASON_TYPE = "season_type"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: Kind
    description: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None


PLAY_TYPES = (
    "pass",
    "run",
    "punt",
    "field_goal",
    "kickoff",
    "extra_point",
    "qb_kneel",
    "qb_spike",
    "no_play",
)
PLAY_TYPE_SYNONYMS = {
    "rush": "run",
    "running": "run",
    "passing": "pass",
    "fg": "field_goal",
    "field goal": "field_goal",
    "pat": "extra_point",
    "xp": "extra_point",
    "extra point": "extra_point",
    "kneel": "qb_kneel",
    "spike": "qb_spike",
    "penalty": "no_play",
    "no play": "no_play",
    "ko": "kickoff",
}
SEASON_TYPES = {
    "reg": "REG",
    "regular": "REG",
    "post": "POST",
    "postseason": "POST",
    "playoffs": "POST",
    "pre": "PRE",
    "preseason": "PRE",
}

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "game_key",
        "Game ID",
        Kind.TEXT,
        "Identifies the game; plays with the same value belong to one game.",
        required=True,
        aliases=("game_id", "game", "gameid", "game_key", "old_game_id"),
        max_length=60,
    ),
    FieldSpec(
        "offense",
        "Offense",
        Kind.TEAM,
        "Team with the ball (abbreviation, 1-5 letters or digits).",
        required=True,
        aliases=("posteam", "offense", "off", "offense_team", "possession_team"),
    ),
    FieldSpec(
        "defense",
        "Defense",
        Kind.TEAM,
        "Team on defense (abbreviation).",
        required=True,
        aliases=("defteam", "defense", "def", "defense_team"),
    ),
    FieldSpec(
        "play_type",
        "Play type",
        Kind.PLAY_TYPE,
        "pass, run, punt, field_goal, "
        "kickoff, extra_point, qb_kneel, qb_spike, or no_play. Sacks are passes; "
        "scrambles are runs.",
        required=True,
        aliases=("play_type", "playtype", "type", "play"),
    ),
    FieldSpec(
        "season",
        "Season",
        Kind.INTEGER,
        "Season year.",
        aliases=("season", "year"),
        minimum=1900,
        maximum=2100,
    ),
    FieldSpec(
        "season_type",
        "Season type",
        Kind.SEASON_TYPE,
        "REG, POST, or PRE.",
        aliases=("season_type", "seasontype"),
    ),
    FieldSpec(
        "week", "Week", Kind.INTEGER, "Week number.", aliases=("week", "wk"), minimum=0, maximum=30
    ),
    FieldSpec(
        "qtr",
        "Quarter",
        Kind.INTEGER,
        "Quarter (5 = overtime).",
        aliases=("qtr", "quarter", "period"),
        minimum=1,
        maximum=6,
    ),
    FieldSpec(
        "down",
        "Down",
        Kind.INTEGER,
        "Down (1-4); blank for kickoffs and tries.",
        aliases=("down", "dn"),
        minimum=1,
        maximum=4,
    ),
    FieldSpec(
        "yards_to_go",
        "Yards to go",
        Kind.INTEGER,
        "Distance to a first down.",
        aliases=("ydstogo", "yards_to_go", "distance", "dist", "togo"),
        minimum=0,
        maximum=100,
    ),
    FieldSpec(
        "yard_line_100",
        "Yards from end zone",
        Kind.INTEGER,
        "Distance from the opponent's end zone (1-99).",
        aliases=("yardline_100", "yard_line_100", "yards_to_endzone"),
        minimum=0,
        maximum=100,
    ),
    FieldSpec(
        "score_differential",
        "Score differential",
        Kind.INTEGER,
        "Offense score minus defense score before the play.",
        aliases=("score_differential", "score_diff", "margin"),
        minimum=-200,
        maximum=200,
    ),
    FieldSpec(
        "yards_gained",
        "Yards gained",
        Kind.INTEGER,
        "Net yards on the play.",
        aliases=("yards_gained", "yards", "gain", "gn_ls", "gnls"),
        minimum=-110,
        maximum=110,
    ),
    FieldSpec(
        "epa",
        "EPA",
        Kind.NUMBER,
        "Expected points added, if your data has it. Never estimated.",
        aliases=("epa",),
        minimum=-20,
        maximum=20,
    ),
    FieldSpec(
        "success",
        "Success",
        Kind.BOOLEAN,
        "Successful play (if omitted and EPA is mapped, success = EPA > 0).",
        aliases=("success",),
    ),
    FieldSpec(
        "complete_pass",
        "Complete pass",
        Kind.BOOLEAN,
        "Pass was completed.",
        aliases=("complete_pass", "completion", "complete"),
    ),
    FieldSpec("sack", "Sack", Kind.BOOLEAN, "Quarterback was sacked.", aliases=("sack",)),
    FieldSpec(
        "touchdown",
        "Touchdown",
        Kind.BOOLEAN,
        "Play resulted in a touchdown.",
        aliases=("touchdown", "td"),
    ),
    FieldSpec(
        "interception",
        "Interception",
        Kind.BOOLEAN,
        "Pass was intercepted.",
        aliases=("interception", "int"),
    ),
    FieldSpec(
        "fumble_lost",
        "Fumble lost",
        Kind.BOOLEAN,
        "Offense lost a fumble.",
        aliases=("fumble_lost", "fumble"),
    ),
    FieldSpec(
        "first_down",
        "First down",
        Kind.BOOLEAN,
        "Play earned a first down (including by penalty).",
        aliases=("first_down", "firstdown", "first_dn"),
    ),
    FieldSpec(
        "first_down_penalty",
        "First down by penalty",
        Kind.BOOLEAN,
        "First down awarded by a defensive penalty.",
        aliases=("first_down_penalty",),
    ),
    FieldSpec(
        "penalty", "Penalty", Kind.BOOLEAN, "A penalty was called.", aliases=("penalty", "flag")
    ),
    FieldSpec(
        "third_down_converted",
        "Third down converted",
        Kind.BOOLEAN,
        "Offense "
        "converted on third down (if omitted and First down is mapped, third-down "
        "plays use First down).",
        aliases=("third_down_converted",),
    ),
    FieldSpec(
        "two_point_attempt",
        "Two-point attempt",
        Kind.BOOLEAN,
        "Play was a two-point try (excluded from scrimmage metrics).",
        aliases=("two_point_attempt", "two_point", "2pt"),
    ),
)
FIELDS_BY_NAME = {f.name: f for f in FIELDS}
REQUIRED_FIELDS = tuple(f.name for f in FIELDS if f.required)
