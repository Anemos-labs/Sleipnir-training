"""SQL index tasks on the greenhouse database: range scans, IS NULL searches, covering indexes, latest-row lookups and OR branches (judged with EXPLAIN QUERY PLAN)."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_greenhouse import DOMAIN

S = K.IndexSpec

Q_DAY = {"name": "one zone, one day", "sql": "SELECT taken_at, moisture_pct FROM readings WHERE zone_id = 2 AND taken_at >= '2039-06-15' AND taken_at < '2039-06-16' ORDER BY taken_at", "no_scan": ["readings"], "no_sort": True, "covering": True}
Q_OPEN = {"name": "valves still open", "sql": "SELECT event_id FROM events WHERE closed_at IS NULL", "no_scan": ["events"]}
Q_LEAK = {"name": "open leak alerts", "sql": "SELECT alert_id FROM alerts WHERE kind = 'leak' AND cleared_at IS NULL", "no_scan": ["alerts"], "covering": True}
Q_LAST = {"name": "latest opening of a valve", "sql": "SELECT opened_at FROM events WHERE valve_id = 3 ORDER BY opened_at DESC LIMIT 1", "no_scan": ["events"], "no_sort": True}
Q_HOT = {"name": "hot readings", "sql": "SELECT COUNT(*) FROM readings WHERE temp_c > 33", "no_scan": ["readings"], "covering": True}

SPECS = [
    S("index-zone-day", 2,
      "The zone chart asks for one zone's readings of one day in time order (query below). Create **one** index so that the plan is a search, needs no sort, and is answered from the index alone (`COVERING INDEX`). Write `indexes.sql`.",
      [Q_DAY], ref="CREATE INDEX ix_readings_zone_time ON readings (zone_id, taken_at, moisture_pct);", max_indexes=1,
      wrong=("CREATE INDEX ix_readings_zone ON readings (zone_id);", "CREATE INDEX ix_readings_time ON readings (taken_at, moisture_pct);")),
    S("index-open-events", 2,
      "`SELECT event_id FROM events WHERE closed_at IS NULL` scans the whole events table although only a handful of valves are open at any time. Add one index so that the plan becomes a search. Write `indexes.sql`.",
      [Q_OPEN], ref="CREATE INDEX ix_events_open ON events (closed_at);", max_indexes=1,
      wrong=("CREATE INDEX ix_events_valve ON events (valve_id);", "CREATE INDEX ix_events_trigger ON events (trigger);")),
    S("index-leak-alerts", 3,
      "The alert board shows the open leak alerts (query below). Create one index that answers it from the index alone, without scanning `alerts`. Write `indexes.sql`.",
      [Q_LEAK], ref="CREATE INDEX ix_alerts_kind_open ON alerts (kind, cleared_at);", max_indexes=1,
      wrong=("CREATE INDEX ix_alerts_zone ON alerts (zone_id);", "CREATE INDEX ix_alerts_raised ON alerts (raised_at);")),
    S("index-latest-opening", 3,
      "`SELECT opened_at FROM events WHERE valve_id = 3 ORDER BY opened_at DESC LIMIT 1` should neither scan `events` nor sort. Create the index. Write `indexes.sql`.",
      [Q_LAST], ref="CREATE INDEX ix_events_valve_time ON events (valve_id, opened_at);", max_indexes=1,
      wrong=("CREATE INDEX ix_events_valve ON events (valve_id);", "CREATE INDEX ix_events_time ON events (opened_at);")),
    S("index-manual-waterings", 4,
      "The query below lists the manual waterings since 2039-06-18 with the valve label. The plan scans `events`. Add one index so that `events` is searched (the join to `valves` is by primary key already). Write `indexes.sql`.",
      [{"name": "manual waterings", "sql": "SELECT valves.label, events.opened_at FROM events JOIN valves ON valves.valve_id = events.valve_id WHERE events.trigger = 'manual' AND events.opened_at >= '2039-06-18'", "no_scan": ["events"]}],
      ref="CREATE INDEX ix_events_trigger_time ON events (trigger, opened_at);", max_indexes=1,
      wrong=("CREATE INDEX ix_events_valve ON events (valve_id);", "CREATE INDEX ix_events_closed ON events (closed_at);")),
    S("index-hot-count", 3,
      "`SELECT COUNT(*) FROM readings WHERE temp_c > 33` reads the whole table. Create one index so that SQLite counts from the index (a covering range search on the temperature). Write `indexes.sql`.",
      [Q_HOT], ref="CREATE INDEX ix_readings_temp ON readings (temp_c);", max_indexes=1,
      wrong=("CREATE INDEX ix_readings_zone_time ON readings (zone_id, taken_at);", "CREATE INDEX ix_readings_moisture ON readings (moisture_pct);")),
    S("index-dashboard-five", 4,
      "Five queries run on every dashboard refresh (listed below). Make them all fast: no table scans, no sort for the time-ordered ones, and covering indexes where marked. You may add at most 5 indexes. Write `indexes.sql`.",
      [Q_DAY, Q_OPEN, Q_LEAK, Q_LAST, Q_HOT], ref="""CREATE INDEX ix_readings_zone_time ON readings (zone_id, taken_at, moisture_pct);
CREATE INDEX ix_events_open ON events (closed_at);
CREATE INDEX ix_alerts_kind_open ON alerts (kind, cleared_at);
CREATE INDEX ix_events_valve_time ON events (valve_id, opened_at);
CREATE INDEX ix_readings_temp ON readings (temp_c);""", max_indexes=5,
      wrong=("""CREATE INDEX a ON readings (zone_id, taken_at, moisture_pct);
CREATE INDEX b ON events (closed_at);
CREATE INDEX c ON alerts (kind, cleared_at);
CREATE INDEX d ON events (valve_id, opened_at);""", """CREATE INDEX a ON readings (zone_id);
CREATE INDEX b ON events (valve_id);
CREATE INDEX c ON alerts (zone_id);
CREATE INDEX d ON readings (temp_c);
CREATE INDEX e ON events (trigger);""")),
    S("index-either-or-readings", 5,
      "The overview screen shows the readings of zone 1 **or** from 2039-06-19 on: `SELECT reading_id FROM readings WHERE zone_id = 1 OR taken_at >= '2039-06-19'`. One index cannot serve both sides of the OR; add the (at most two) indexes that let SQLite search both branches. Write `indexes.sql`.",
      [{"name": "zone or recent", "sql": "SELECT reading_id FROM readings WHERE zone_id = 1 OR taken_at >= '2039-06-19'", "no_scan": ["readings"]}],
      ref="CREATE INDEX ix_readings_zone ON readings (zone_id);\nCREATE INDEX ix_readings_time ON readings (taken_at);", max_indexes=2,
      wrong=("CREATE INDEX ix_readings_zone ON readings (zone_id);", "CREATE INDEX ix_readings_time ON readings (taken_at);")),
]


@family("data-greenhouse-indexes", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="choose indexes for a greenhouse dashboard: covering range searches, IS NULL lookups, latest-row lookups, join filters and OR branches")
def greenhouse_indexes(rng, n):
    return K.index_tasks(DOMAIN, SPECS, rng, n)
