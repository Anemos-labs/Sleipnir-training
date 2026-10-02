"""Expert SQL index tasks on the greenhouse database: expression indexes (a plain index cannot serve a computed predicate), range predicates on expressions and ordered partial lookups (judged with EXPLAIN QUERY PLAN)."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_greenhouse import DOMAIN

S = K.IndexSpec

Q_DAY_MAX = {"name": "hot readings of a day", "sql": "SELECT reading_id FROM readings WHERE substr(taken_at, 1, 10) = '2039-06-15' AND temp_c > 33", "no_scan": ["readings"]}
Q_DAY_ZONE = {"name": "readings of one zone on one day", "sql": "SELECT COUNT(*) FROM readings WHERE zone_id = 2 AND substr(taken_at, 1, 10) = '2039-06-15'", "no_scan": ["readings"]}
Q_EARLY = {"name": "waterings before seven", "sql": "SELECT event_id, valve_id FROM events WHERE CAST(substr(opened_at, 12, 2) AS INTEGER) < 7", "no_scan": ["events"]}
Q_OPEN_ORDER = {"name": "open valves by opening time", "sql": "SELECT valve_id, opened_at FROM events WHERE closed_at IS NULL ORDER BY opened_at", "no_scan": ["events"], "no_sort": True, "covering": True}

SPECS = [
    S("index-day-expression", 5,
      "The daily report filters on the **date part** of the timestamp: `substr(taken_at, 1, 10) = '2039-06-15'`, once together with a temperature condition and once together with a zone (both queries below). An ordinary index on `taken_at` does not help because the predicate is a computed value. "
      "Create **one** index so that both queries are searches (no scan of `readings`). Write `indexes.sql`.",
      [Q_DAY_MAX, Q_DAY_ZONE], ref="CREATE INDEX ix_readings_day_zone ON readings (substr(taken_at, 1, 10), zone_id);", max_indexes=1,
      wrong=("CREATE INDEX ix_readings_time ON readings (taken_at, zone_id);", "CREATE INDEX ix_readings_zone_time ON readings (zone_id, taken_at);")),
    S("index-early-waterings", 5,
      "`SELECT event_id, valve_id FROM events WHERE CAST(substr(opened_at, 12, 2) AS INTEGER) < 7` finds the waterings that started before seven in the morning, but SQLite reads the whole table. Add one index so that the plan becomes a search. Write `indexes.sql`.",
      [Q_EARLY], ref="CREATE INDEX ix_events_hour ON events (CAST(substr(opened_at, 12, 2) AS INTEGER));", max_indexes=1,
      wrong=("CREATE INDEX ix_events_opened ON events (opened_at);", "CREATE INDEX ix_events_hour_text ON events (substr(opened_at, 12, 2));")),
    S("index-open-ordered", 4,
      "The valve board lists the valves that are open right now, oldest opening first (query below). Create one index so that the plan is a search of `events` (a scan does not count, not even a scan of an index), needs no sort, and is answered from the index alone. Write `indexes.sql`.",
      [Q_OPEN_ORDER], ref="CREATE INDEX ix_events_open_by_time ON events (closed_at, opened_at, valve_id);", max_indexes=1,
      wrong=("CREATE INDEX ix_events_opened ON events (opened_at);", "CREATE INDEX ix_events_closed ON events (closed_at);", "CREATE INDEX ix_events_open_part ON events (opened_at, valve_id) WHERE closed_at IS NULL;")),
]


@family("data-expert-indexes", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="expert index design on the greenhouse database: expression indexes for computed predicates, a range over a computed hour, an ordered lookup of open rows")
def expert_indexes(rng, n):
    return K.index_tasks(DOMAIN, SPECS, rng, n)
