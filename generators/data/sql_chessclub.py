"""SQL tasks on an invented chess club's tournament records (UNION ALL player views, standings with tie-breaks, pairings, streaks, rating-based reports)."""
from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE players (
      player_id  INTEGER PRIMARY KEY,
      name       TEXT NOT NULL UNIQUE,
      joined_on  TEXT NOT NULL,
      rating     INTEGER NOT NULL            -- rating at the start of the tournament
    );
    CREATE TABLE games (
      game_id    INTEGER PRIMARY KEY,
      round      INTEGER NOT NULL,
      white_id   INTEGER NOT NULL REFERENCES players(player_id),
      black_id   INTEGER NOT NULL REFERENCES players(player_id),
      result     TEXT NOT NULL CHECK (result IN ('1-0', '0-1', '1/2-1/2')),
      played_on  TEXT NOT NULL,
      moves      INTEGER NOT NULL,
      CHECK (white_id <> black_id)
    );
    CREATE TABLE byes (
      player_id  INTEGER NOT NULL REFERENCES players(player_id),
      round      INTEGER NOT NULL,
      PRIMARY KEY (player_id, round)
    );
''')

DOC = dd('''
    The Oldtown Chess Club plays a Swiss-style tournament and keeps the records.

    * `1-0` is a win for White, `0-1` a win for Black, `1/2-1/2` a draw. A win scores 1 point, a draw 0.5, a loss 0.
    * A **bye** (a player sits a round out) scores 1 point but is not a game: byes do not count as games played, wins, or opponents.
    * Every player should play at most once per round (the records may contain mistakes).
    * The **Buchholz** tie-break of a player is the sum of the total scores (points including byes) of all opponents he or she actually played.
    * Ratings are the rating at the start of the tournament.
''')

NAMES = ["Aldous Fenn", "Brigid Oake", "Casimir Dray", "Dalia Wren", "Eamon Thorne", "Fiora Vale", "Gideon Marsh", "Hester Lowe", "Ivo Kestrel", "Juno Beck", "Kasper Rowe", "Lysa Crane", "Mordecai Pike", "Nell Ashby", "Orson Hale", "Petra Quill"]


def gen(rng, big):
    n = 14 if big else 7
    players = [(i + 1, NAMES[i], f"20{rng.randint(10, 36)}-{rng.randint(1, 12):02d}-01", rng.randint(1100, 2150)) for i in range(n)]
    for i, r in enumerate((1400, 1600, 1800)):  # ratings exactly on the band limits
        players[i] = players[i][:3] + (r,)
    rating = {p[0]: p[3] for p in players}
    games, byes, gid = [], [], 0
    rounds = 8 if big else 5
    for r in range(1, rounds + 1):
        ids = [p[0] for p in players]
        rng.shuffle(ids)
        if len(ids) % 2:
            byes.append((ids.pop(), r))
        for k in range(0, len(ids), 2):
            a, b = ids[k], ids[k + 1]
            gid += 1
            diff = rating[a] - rating[b]
            pw = 1 / (1 + 10 ** (-diff / 400))
            u = rng.random()
            res = "1-0" if u < pw * 0.75 else ("0-1" if u > 1 - (1 - pw) * 0.75 else "1/2-1/2")
            games.append((gid, r, a, b, res, f"2036-{9 + (r - 1) // 4:02d}-{(r - 1) % 4 * 7 + rng.randint(1, 6):02d}", rng.randint(18, 90)))
    # plant: a repeated pairing and (in the big club) a player listed twice in one round, and two upsets
    if big:
        a, b = games[0][2], games[0][3]
        gid += 1
        games.append((gid, rounds, b, a, "1/2-1/2", "2036-10-27", 40))
        gid += 1
        games.append((gid, 3, games[1][2], games[2][3], "0-1", "2036-09-20", 31))
    strong = max(players, key=lambda p: p[3])[0]
    weak = min(players, key=lambda p: p[3])[0]
    gid += 1
    games.append((gid, 1, weak, strong, "1-0", "2036-09-02", 55))
    return {"players": players, "games": games, "byes": byes}


DOMAIN = K.Domain("chessclub", "Oldtown Chess Club: Swiss tournament", SCHEMA, DOC, gen)
S = K.Spec

PERGAME = """WITH g AS (
  SELECT white_id AS pid, black_id AS opp, round, 'W' AS colour, CASE result WHEN '1-0' THEN 1.0 WHEN '1/2-1/2' THEN 0.5 ELSE 0.0 END AS pts FROM games
  UNION ALL SELECT black_id, white_id, round, 'B', CASE result WHEN '0-1' THEN 1.0 WHEN '1/2-1/2' THEN 0.5 ELSE 0.0 END FROM games
)"""
SCORES = f"""{PERGAME}, sc AS (SELECT p.player_id AS pid, COALESCE((SELECT SUM(pts) FROM g WHERE g.pid = p.player_id), 0) + (SELECT COUNT(*) FROM byes b WHERE b.player_id = p.player_id) AS score FROM players p)"""

SPECS = [
    S("rating-bands", 1,
      "Group the players into rating bands: `under 1400`, `1400-1599`, `1600-1799`, `1800+`. For each band that has players: band, number of players and average rating rounded to a whole number. Order by the band's lower limit (under 1400 first).",
      """SELECT CASE WHEN rating < 1400 THEN 'under 1400' WHEN rating < 1600 THEN '1400-1599' WHEN rating < 1800 THEN '1600-1799' ELSE '1800+' END AS band, COUNT(*) AS players, CAST(ROUND(AVG(rating)) AS INTEGER) AS avg_rating
FROM players GROUP BY band ORDER BY MIN(rating);""",
      ["band", "players", "avg_rating"], ordered=True,
      wrong=("""SELECT CASE WHEN rating <= 1400 THEN 'under 1400' WHEN rating <= 1600 THEN '1400-1599' WHEN rating <= 1800 THEN '1600-1799' ELSE '1800+' END AS band, COUNT(*), CAST(ROUND(AVG(rating)) AS INTEGER) FROM players GROUP BY band ORDER BY MIN(rating);""",)),
    S("standings", 3,
      "The standings: for every player points (games plus byes), games played, wins, draws, losses. Order by points descending, then wins descending, then name. Columns: name, points, games, wins, draws, losses.",
      f"""{PERGAME}
SELECT p.name, COALESCE(SUM(g.pts), 0) + (SELECT COUNT(*) FROM byes b WHERE b.player_id = p.player_id) AS points, COUNT(g.pid) AS games,
       COALESCE(SUM(g.pts = 1.0), 0) AS wins, COALESCE(SUM(g.pts = 0.5), 0) AS draws, COALESCE(SUM(g.pts = 0.0), 0) AS losses
FROM players p LEFT JOIN g ON g.pid = p.player_id GROUP BY p.player_id ORDER BY points DESC, wins DESC, p.name;""",
      ["name", "points", "games", "wins", "draws", "losses"], ordered=True,
      wrong=("""SELECT p.name, SUM(CASE WHEN (g.white_id = p.player_id AND g.result = '1-0') OR (g.black_id = p.player_id AND g.result = '0-1') THEN 1 WHEN g.result = '1/2-1/2' THEN 0.5 ELSE 0 END), COUNT(*), 0, 0, 0
FROM players p JOIN games g ON g.white_id = p.player_id OR g.black_id = p.player_id GROUP BY p.player_id ORDER BY 2 DESC, p.name;""",)),
    S("buchholz-ranking", 4,
      "Rank the players by points (including byes) and break ties with the Buchholz score (sum of the opponents' total scores; a player who faced the same opponent twice counts that opponent twice; byes add nothing). "
      "Columns: name, points, buchholz. Order by points descending, buchholz descending, then name.",
      f"""{SCORES}
SELECT p.name, s.score AS points, COALESCE((SELECT SUM(o.score) FROM g JOIN sc o ON o.pid = g.opp WHERE g.pid = p.player_id), 0) AS buchholz
FROM players p JOIN sc s ON s.pid = p.player_id ORDER BY points DESC, buchholz DESC, p.name;""",
      ["name", "points", "buchholz"], ordered=True,
      wrong=(f"""{SCORES}
SELECT p.name, s.score, COALESCE((SELECT SUM(o.score) FROM (SELECT DISTINCT pid, opp FROM g) d JOIN sc o ON o.pid = d.opp WHERE d.pid = p.player_id), 0) AS b FROM players p JOIN sc s ON s.pid = p.player_id ORDER BY s.score DESC, b DESC, p.name;""",)),
    S("colour-imbalance", 3,
      "Colour balance: for every player the number of games as White and as Black and the difference (white minus black). List only players whose difference is 2 or more in either direction. Columns: name, white, black, diff. Order by the absolute difference descending, then name.",
      """SELECT p.name, SUM(g.colour = 'W') AS white, SUM(g.colour = 'B') AS black, SUM(g.colour = 'W') - SUM(g.colour = 'B') AS diff FROM players p JOIN (SELECT white_id AS pid, 'W' AS colour FROM games UNION ALL SELECT black_id, 'B' FROM games) g ON g.pid = p.player_id
GROUP BY p.player_id HAVING ABS(SUM(g.colour = 'W') - SUM(g.colour = 'B')) >= 2 ORDER BY ABS(diff) DESC, p.name;""",
      ["name", "white", "black", "diff"], ordered=True, allow_empty=True),
    S("repeat-pairings", 3,
      "Pairs of players who met more than once (in either colour order): both names, the lower player id first, and the number of games between them. Order by games descending, then the first name.",
      """SELECT a.name AS player_a, b.name AS player_b, COUNT(*) AS games FROM games g JOIN players a ON a.player_id = MIN(g.white_id, g.black_id) JOIN players b ON b.player_id = MAX(g.white_id, g.black_id) GROUP BY a.player_id, b.player_id HAVING COUNT(*) > 1 ORDER BY games DESC, a.name, b.name;""",
      ["player_a", "player_b", "games"], ordered=True, allow_empty=True,
      wrong=("""SELECT a.name, b.name, COUNT(*) FROM games g JOIN players a ON a.player_id = g.white_id JOIN players b ON b.player_id = g.black_id GROUP BY g.white_id, g.black_id HAVING COUNT(*) > 1 ORDER BY 3 DESC, a.name, b.name;""",)),
    S("big-upsets", 3,
      "Upsets: decisive games (not draws) won by a player whose start rating was at least 100 points below the loser's. Columns: round, winner, loser, rating gap. Order by gap descending, then round, then winner.",
      """SELECT g.round, w.name AS winner, l.name AS loser, l.rating - w.rating AS gap FROM games g
JOIN players w ON w.player_id = CASE g.result WHEN '1-0' THEN g.white_id ELSE g.black_id END JOIN players l ON l.player_id = CASE g.result WHEN '1-0' THEN g.black_id ELSE g.white_id END
WHERE g.result <> '1/2-1/2' AND l.rating - w.rating >= 100 ORDER BY gap DESC, g.round, w.name;""",
      ["round", "winner", "loser", "gap"], ordered=True,
      wrong=("""SELECT g.round, w.name, l.name, ABS(l.rating - w.rating) FROM games g JOIN players w ON w.player_id = g.white_id JOIN players l ON l.player_id = g.black_id WHERE g.result = '1-0' AND l.rating - w.rating >= 100 ORDER BY 4 DESC, g.round, w.name;""",)),
    S("unbeaten-runs", 4,
      "Unbeaten streaks: per player, order their games by round (a player has at most one game per round in clean data; if there are two in a round, order by game id) and find the longest run of consecutive games without a loss. "
      "Players with a longest run of 3 or more are listed: name, run length, round of the first game of that run (the earliest run if several tie). Order by run length descending, then name.",
      f"""{PERGAME}
, o AS (SELECT pid, round, pts, ROW_NUMBER() OVER (PARTITION BY pid ORDER BY round, opp) AS rn FROM g),
runs AS (SELECT pid, MIN(round) AS first_round, COUNT(*) AS len FROM (SELECT o.pid, o.round, o.rn, o.rn - ROW_NUMBER() OVER (PARTITION BY o.pid ORDER BY o.rn) AS grp FROM o WHERE o.pts > 0) GROUP BY pid, grp),
b AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY pid ORDER BY len DESC, first_round) AS r FROM runs)
SELECT p.name, b.len AS run, b.first_round FROM b JOIN players p ON p.player_id = b.pid WHERE b.r = 1 AND b.len >= 3 ORDER BY b.len DESC, p.name;""",
      ["name", "run", "first_round"], ordered=True,
      wrong=(f"""{PERGAME}
SELECT p.name, COUNT(*), MIN(g.round) FROM g JOIN players p ON p.player_id = g.pid WHERE g.pts > 0 GROUP BY g.pid HAVING COUNT(*) >= 3 ORDER BY 2 DESC, p.name;""",)),
    S("unplayed-pairs", 4,
      "Who has not met yet? List every pair of different players that never played each other (neither as White nor as Black), the lower id first: both names. Order by the first player's name, then the second's. ",
      """SELECT a.name AS player_a, b.name AS player_b FROM players a JOIN players b ON b.player_id > a.player_id
WHERE NOT EXISTS (SELECT 1 FROM games g WHERE (g.white_id = a.player_id AND g.black_id = b.player_id) OR (g.white_id = b.player_id AND g.black_id = a.player_id)) ORDER BY a.name, b.name;""",
      ["player_a", "player_b"], ordered=True,
      wrong=("""SELECT a.name, b.name FROM players a JOIN players b ON b.player_id > a.player_id WHERE NOT EXISTS (SELECT 1 FROM games g WHERE g.white_id = a.player_id AND g.black_id = b.player_id) ORDER BY a.name, b.name;""",)),
    S("double-booked-rounds", 3,
      "Mistakes in the records: players who appear in more than one game of the same round. Columns: name, round, number of games. Order by round, then name.",
      f"""{PERGAME}
SELECT p.name, g.round, COUNT(*) AS games FROM g JOIN players p ON p.player_id = g.pid GROUP BY g.pid, g.round HAVING COUNT(*) > 1 ORDER BY g.round, p.name;""",
      ["name", "round", "games"], ordered=True, allow_empty=True,
      wrong=("""SELECT p.name, g.round, COUNT(*) FROM games g JOIN players p ON p.player_id = g.white_id GROUP BY g.white_id, g.round HAVING COUNT(*) > 1 ORDER BY g.round, p.name;""",)),
    S("length-by-result", 2,
      "How long do the games last? For each result (`1-0`, `0-1`, `1/2-1/2`): number of games, average number of moves with 1 decimal, and the longest game. Order by result.",
      "SELECT result, COUNT(*) AS games, ROUND(AVG(moves), 1) AS avg_moves, MAX(moves) AS longest FROM games GROUP BY result ORDER BY result;", ["result", "games", "avg_moves", "longest"], ordered=True),
    S("performance-estimate", 4,
      "A rough performance rating for players with at least 3 games: the average start rating of the opponents plus 400 times (wins minus losses) divided by the number of games, rounded to a whole number. "
      "(Draws count as neither a win nor a loss; byes are not games.) Columns: name, games, performance. Order by performance descending, then name.",
      f"""{PERGAME}
SELECT p.name, COUNT(*) AS games, CAST(ROUND(AVG(o.rating) + 400.0 * (SUM(g.pts = 1.0) - SUM(g.pts = 0.0)) / COUNT(*)) AS INTEGER) AS performance
FROM g JOIN players p ON p.player_id = g.pid JOIN players o ON o.player_id = g.opp GROUP BY g.pid HAVING COUNT(*) >= 3 ORDER BY performance DESC, p.name;""",
      ["name", "games", "performance"], ordered=True,
      wrong=(f"""{PERGAME}
SELECT p.name, COUNT(*), CAST(ROUND(AVG(o.rating) + 400.0 * (SUM(g.pts = 1.0) - SUM(g.pts < 1.0)) / COUNT(*)) AS INTEGER) AS perf FROM g JOIN players p ON p.player_id = g.pid JOIN players o ON o.player_id = g.opp GROUP BY g.pid HAVING COUNT(*) >= 3 ORDER BY perf DESC, p.name;""",)),
    S("second-half-surge", 4,
      "Late bloomers: split the tournament at the middle round (rounds up to half of the highest round number, rounded down, are the first half; the others the second half). "
      "Compare each player's points from games in the two halves (byes ignored here). List players whose second-half points exceed their first-half points by at least 1.5: name, first half, second half. Order by the difference descending, then name.",
      f"""{PERGAME}
, h AS (SELECT MAX(round) / 2 AS mid FROM games), s AS (SELECT g.pid, SUM(CASE WHEN g.round <= h.mid THEN g.pts ELSE 0 END) AS a, SUM(CASE WHEN g.round > h.mid THEN g.pts ELSE 0 END) AS b FROM g, h GROUP BY g.pid)
SELECT p.name, s.a AS first_half, s.b AS second_half FROM s JOIN players p ON p.player_id = s.pid WHERE s.b - s.a >= 1.5 ORDER BY s.b - s.a DESC, p.name;""",
      ["name", "first_half", "second_half"], ordered=True, allow_empty=True,
      wrong=(f"""{PERGAME}
, s AS (SELECT g.pid, SUM(CASE WHEN g.round <= 3 THEN g.pts ELSE 0 END) AS a, SUM(CASE WHEN g.round > 3 THEN g.pts ELSE 0 END) AS b FROM g GROUP BY g.pid)
SELECT p.name, s.a, s.b FROM s JOIN players p ON p.player_id = s.pid WHERE s.b - s.a >= 1.5 ORDER BY s.b - s.a DESC, p.name;""",)),
    S("fix-standings-points", 3,
      "The points column of the standings in `query.sql` ignores draws and Black's wins. Fix it: for every player (also those without games), name and points from games only (win 1, draw 0.5, loss 0; byes do not count here). "
      "Order by points descending, then name.",
      ref=f"""{PERGAME}
SELECT p.name, COALESCE(SUM(g.pts), 0) AS points FROM players p LEFT JOIN g ON g.pid = p.player_id GROUP BY p.player_id ORDER BY points DESC, p.name;""",
      cols=["name", "points"], ordered=True, show=False,
      buggy="""SELECT p.name, COUNT(g.game_id) AS points FROM players p LEFT JOIN games g ON g.white_id = p.player_id AND g.result = '1-0' GROUP BY p.player_id ORDER BY points DESC, p.name;"""),
]


@family("data-chess-club", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on a Swiss chess tournament: standings and Buchholz tie-breaks over a UNION ALL player view, pairings, colour balance, unbeaten runs, rating-based reports")
def chess_club(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
