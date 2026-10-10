"""nflverse play-by-play columns PlaybookIQ depends on."""

ID_COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "season_type",
    "week",
    "game_date",
    "home_team",
    "away_team",
    "posteam",
    "defteam",
]
SITUATION_COLUMNS = [
    "qtr",
    "game_seconds_remaining",
    "down",
    "ydstogo",
    "yardline_100",
    "score_differential",
]
OUTCOME_COLUMNS = ["play_type", "yards_gained", "epa", "success"]
PLAYER_COLUMNS = ["passer_player_id", "rusher_player_id", "receiver_player_id"]
INDICATOR_COLUMNS = [
    "touchdown",
    "interception",
    "fumble_lost",
    "complete_pass",
    "sack",
    "pass",
    "rush",
    "first_down",
    "penalty",
    "third_down_converted",
    "third_down_failed",
    "fourth_down_converted",
    "first_down_penalty",
    "two_point_attempt",
    "qb_kneel",
    "qb_spike",
    "qb_scramble",
    "aborted_play",
    "play_deleted",
]

REQUIRED_COLUMNS = (
    ID_COLUMNS + SITUATION_COLUMNS + OUTCOME_COLUMNS + PLAYER_COLUMNS + INDICATOR_COLUMNS
)
