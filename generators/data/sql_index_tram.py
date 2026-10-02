"""SQL index tasks on the tram operator's database: choose indexes so that the workload's query plans stop scanning and sorting (judged with EXPLAIN QUERY PLAN)."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_tramdepot import DOMAIN

S = K.IndexSpec

Q_STOP = {"name": "skipped at one stop", "sql": "SELECT run_id, seq FROM stop_events WHERE stop_id = 3 AND actual_time IS NULL", "no_scan": ["stop_events"]}
Q_DAY = {"name": "a day's runs of one line", "sql": "SELECT run_id, direction, scheduled_start FROM runs WHERE service_date = '2032-03-10' AND line_id = 2 ORDER BY scheduled_start", "no_scan": ["runs"], "no_sort": True}
Q_FAULT = {"name": "open faults of a tram", "sql": "SELECT fault_id FROM faults WHERE tram_id = 4 AND fixed_on IS NULL", "no_scan": ["faults"], "covering": True}
Q_RECENT = {"name": "latest runs of a tram", "sql": "SELECT run_id, service_date FROM runs WHERE tram_id = 3 ORDER BY service_date DESC, run_id DESC LIMIT 5", "no_scan": ["runs"], "no_sort": True}

SPECS = [
    S("index-skips-by-stop", 2,
      "The planner scans the whole `stop_events` table for the query below (`EXPLAIN QUERY PLAN` shows `SCAN stop_events`). Write `indexes.sql` with one `CREATE INDEX` statement so that it becomes a search.",
      [Q_STOP], ref="CREATE INDEX ix_events_stop ON stop_events (stop_id, actual_time);", max_indexes=1,
      wrong=("CREATE INDEX ix_events_sched ON stop_events (sched_time);", "CREATE INDEX ix_events_board ON stop_events (boarded);")),
    S("index-day-of-line", 3,
      "The timetable page runs the query below hundreds of times a minute. It scans `runs` and then sorts. Add one index so that the plan is a search that also returns the rows already in `scheduled_start` order (no `USE TEMP B-TREE FOR ORDER BY`). Write `indexes.sql`.",
      [Q_DAY], ref="CREATE INDEX ix_runs_day_line ON runs (service_date, line_id, scheduled_start);", max_indexes=1,
      wrong=("CREATE INDEX ix_runs_day ON runs (service_date);", "CREATE INDEX ix_runs_line ON runs (line_id);")),
    S("index-open-faults-covering", 3,
      "The workshop dashboard asks for the ids of the open faults of one tram. Make the query answerable from an index alone (the plan must say `COVERING INDEX`) without scanning `faults`. One index at most. Write `indexes.sql`.",
      [Q_FAULT], ref="CREATE INDEX ix_faults_open ON faults (tram_id, fixed_on);", max_indexes=1,
      wrong=("CREATE INDEX ix_faults_tram ON faults (tram_id);", "CREATE INDEX ix_faults_fixed ON faults (fixed_on);")),
    S("index-latest-runs", 3,
      "`SELECT ... WHERE tram_id = 3 ORDER BY service_date DESC, run_id DESC LIMIT 5` should neither scan `runs` nor sort. Create the one index that makes this possible. Write `indexes.sql`.",
      [Q_RECENT], ref="CREATE INDEX ix_runs_tram_date ON runs (tram_id, service_date, run_id);", max_indexes=1,
      wrong=("CREATE INDEX ix_runs_tram ON runs (tram_id);", "CREATE INDEX ix_runs_tram_run ON runs (tram_id, run_id);")),
    S("index-workload-of-four", 4,
      "Four queries make up the daily load (listed below). Together they must run without scanning the big tables, the timetable query without a sort and the fault query from a covering index. You may add at most 4 indexes (writes get slower with every one). Write `indexes.sql`.",
      [Q_STOP, Q_DAY, Q_FAULT, Q_RECENT], ref="""CREATE INDEX ix_events_stop ON stop_events (stop_id, actual_time);
CREATE INDEX ix_runs_day_line ON runs (service_date, line_id, scheduled_start);
CREATE INDEX ix_faults_open ON faults (tram_id, fixed_on);
CREATE INDEX ix_runs_tram_date ON runs (tram_id, service_date, run_id);""", max_indexes=4,
      wrong=("""CREATE INDEX a ON stop_events (stop_id, actual_time);
CREATE INDEX b ON runs (service_date, line_id, scheduled_start);
CREATE INDEX c ON faults (tram_id, fixed_on);""", """CREATE INDEX a ON stop_events (stop_id);
CREATE INDEX b ON runs (service_date);
CREATE INDEX c ON faults (tram_id);
CREATE INDEX d ON runs (tram_id);
CREATE INDEX e ON runs (line_id);""")),
    S("index-join-by-category", 4,
      "The query below lists, for the doors faults, the tram and its fleet number. It scans `faults`. Add the index (one is enough) that turns the scan into a search; the lookup of `trams` is by primary key already. Write `indexes.sql`.",
      [{"name": "doors faults per tram", "sql": "SELECT trams.fleet_no, faults.reported_on FROM faults JOIN trams ON trams.tram_id = faults.tram_id WHERE faults.category = 'doors' AND faults.severity >= 2", "no_scan": ["faults"]}],
      ref="CREATE INDEX ix_faults_cat_sev ON faults (category, severity);", max_indexes=1,
      wrong=("CREATE INDEX ix_faults_rep ON faults (reported_on);", "CREATE INDEX ix_faults_tram ON faults (tram_id);")),
    S("index-either-or", 5,
      "The depot screen shows runs that either use tram 1 or belong to line 2: `SELECT run_id FROM runs WHERE tram_id = 1 OR line_id = 2`. A single index cannot serve both sides of the OR, so the plan scans `runs`. "
      "Create the indexes (at most two) that let SQLite answer both branches by index search. Write `indexes.sql`.",
      [{"name": "tram or line", "sql": "SELECT run_id FROM runs WHERE tram_id = 1 OR line_id = 2", "no_scan": ["runs"]}],
      ref="CREATE INDEX ix_runs_tram ON runs (tram_id);\nCREATE INDEX ix_runs_line ON runs (line_id);", max_indexes=2,
      wrong=("CREATE INDEX ix_runs_tram ON runs (tram_id);", "CREATE INDEX ix_runs_both ON runs (tram_id, line_id);")),
    S("index-serious-open", 4,
      "Only a handful of faults are both open and serious, yet `SELECT fault_id, tram_id FROM faults WHERE fixed_on IS NULL AND severity >= 4` scans the table. Write `indexes.sql` with one index that makes it a search "
      "(a partial index with a `WHERE` clause would be the smallest answer, but any single index that does the job is accepted).",
      [{"name": "serious open faults", "sql": "SELECT fault_id, tram_id FROM faults WHERE fixed_on IS NULL AND severity >= 4", "no_scan": ["faults"]}],
      ref="CREATE INDEX ix_faults_serious_open ON faults (severity) WHERE fixed_on IS NULL;", max_indexes=1,
      wrong=("CREATE INDEX ix_faults_cat ON faults (category);", "CREATE INDEX ix_faults_reported ON faults (reported_on);")),
]


@family("data-tram-indexes", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="choose indexes for a tram operator's workload so that EXPLAIN QUERY PLAN stops scanning and sorting: composite order, covering, OR branches, partial indexes")
def tram_indexes(rng, n):
    return K.index_tasks(DOMAIN, SPECS, rng, n)
