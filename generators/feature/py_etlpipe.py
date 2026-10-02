"""etlpipe (python): a record pipeline extended with cleanup stages, error routing, metrics, specs and batching."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # etlpipe

    A tiny record-processing pipeline (Python 3, standard library only): records are dictionaries, a `Pipeline` pushes them
    through stages in order. Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `etlpipe/pipeline.py`: `Pipeline`, `StageError`.
    * `etlpipe/stages.py`: ready-made stage functions.
    * `etlpipe/spec.py`: the operation registry used to build pipelines from plain data.

    ## Basics

    * `Pipeline(name="pipeline")`. `pipeline.map(fn, name=None)` adds a stage that replaces each record by `fn(record)`;
      `pipeline.filter(fn, name=None)` keeps the records for which `fn(record)` is true. Both return the pipeline, so calls
      chain. A stage without a name is called `map1`, `filter2`, ... (its kind and its 1-based position). `pipeline.names()`
      lists the stage names in order.
    * `pipeline.run(records, **options)` returns a list with the records that came out of the last stage. Each stage
      processes the output of the previous one, record by record, in the original order. If a stage function raises, `run`
      raises `StageError` with `.stage` (the stage name), `.record` (the record it was processing) and `.cause` (the original
      exception); the message is `stage 'NAME' failed: CAUSE`. There are no options yet; unknown options raise `TypeError`.
    * `stages.rename(mapping)` returns a function that renames fields (`{"old": "new"}`; fields not in the mapping are
      untouched, missing ones ignored; the renamed field keeps its position). `stages.select(fields)` keeps only the listed
      fields, in that order (missing ones are skipped). `stages.cast(field, kind)` converts `record[field]` with kind `int`,
      `float` or `str` (`ValueError` for a value that does not convert, `KeyError` for a missing field). They return new
      dictionaries and never modify their input.
    * `spec.OPS` maps operation names to builders `build(pipeline, **args)` that add stages; `rename`, `select` and `cast`
      are registered under their own names.
''')

PIPELINE = '''\
"""The pipeline."""
from dataclasses import dataclass
@@uniq imports


class StageError(Exception):
    """A stage function raised while processing a record."""

    def __init__(self, stage, record, cause):
        super().__init__(f"stage '{stage}' failed: {cause}")
        self.stage = stage
        self.record = record
        self.cause = cause

@@blocks classes

@dataclass
class Stage:
    kind: str
    fn: object
    name: str
    @@slot stage_fields


class Pipeline:
    def __init__(self, name="pipeline"):
        self.name = name
        self._stages = []
        @@slot init

    def _add(self, kind, fn, name, **extra):
        stage = Stage(kind, fn, name or f"{kind}{len(self._stages) + 1}", **extra)
        self._stages.append(stage)
        return self

    def map(self, fn, name=None):
        return self._add("map", fn, name)

    def filter(self, fn, name=None):
        return self._add("filter", fn, name)

    def names(self):
        return [s.name for s in self._stages]

    def _begin(self, opts):
        @@slot run_begin
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))

    def _apply(self, stage, records):
        @@slot apply_special
        out = []
        for rec in records:
            try:
                if stage.kind == "map":
                    out.append(stage.fn(rec))
                elif stage.kind == "filter":
                    if stage.fn(rec):
                        out.append(rec)
            except Exception as e:
                @@default on_error
                raise StageError(stage.name, rec, e) from e
                @@end
        return out

    def _process(self, records):
        current = records
        for i, stage in enumerate(self._stages):
            @@slot stage_begin
            current = self._apply(stage, current)
            @@slot stage_end
        return current

    def run(self, records, **opts):
        self._begin(opts)
        return self._process(list(records))

    @@blocks methods
'''

STAGES = '''\
"""Ready-made stage functions."""
@@uniq imports


def rename(mapping):
    def apply(rec):
        return {mapping.get(k, k): v for k, v in rec.items()}

    return apply


def select(fields):
    fields = list(fields)

    def apply(rec):
        return {f: rec[f] for f in fields if f in rec}

    return apply


def cast(field, kind):
    convert = {"int": int, "float": float, "str": str}[kind]

    def apply(rec):
        out = dict(rec)
        out[field] = convert(rec[field])
        return out

    return apply

@@blocks functions
'''

SPEC = '''\
"""Building pipelines from plain data."""
from . import stages
@@uniq imports

OPS = {
    "rename": lambda p, mapping: p.map(stages.rename(mapping)),
    "select": lambda p, fields: p.map(stages.select(fields)),
    "cast": lambda p, field, kind: p.map(stages.cast(field, kind)),
}
@@slot ops

@@blocks functions
'''

INIT = '''\
"""A tiny record pipeline."""
from . import spec, stages
from .pipeline import Pipeline, StageError
@@uniq exports
'''

HELPERS = '''\
import unittest
@@uniq imports

from etlpipe import Pipeline, StageError, spec, stages

ROWS = [
    {"id": 1, "name": "Ana", "qty": "3", "city": "Oslo"},
    {"id": 2, "name": "", "qty": "5", "city": "Bergen"},
    {"id": 2, "name": "Bo", "qty": "x", "city": "Bergen"},
    {"id": 3, "name": "Cy", "qty": "7", "city": None},
    {"id": 4, "name": "Di", "qty": "2", "city": "Oslo"},
]


def rows():
    return [dict(r) for r in ROWS]


def ids(records):
    return [r["id"] for r in records]

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_map_and_filter(self):
        p = Pipeline().map(stages.rename({"name": "customer"})).filter(lambda r: r["qty"] != "x")
        out = p.run(rows())
        self.assertEqual(ids(out), [1, 2, 3, 4])
        self.assertEqual(list(out[0]), ["id", "customer", "qty", "city"])
        self.assertEqual(p.names(), ["map1", "filter2"])

    def test_stage_error(self):
        p = Pipeline().map(stages.cast("qty", "int"), name="to-int")
        with self.assertRaises(StageError) as cm:
            p.run(rows())
        e = cm.exception
        self.assertEqual((e.stage, e.record["id"]), ("to-int", 2))
        self.assertIsInstance(e.cause, ValueError)

    def test_select(self):
        out = Pipeline().map(stages.select(["city", "id"])).run(rows())
        self.assertEqual(out[0], {"city": "Oslo", "id": 1})
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_behaviour(self):
        src = rows()
        p = Pipeline("demo").map(stages.rename({"name": "customer", "nope": "x"})).map(stages.cast("qty", "float"), name="num").filter(lambda r: r["qty"] > 2.5)
        out = p.run(src[:2] + src[3:])
        self.assertEqual([(r["id"], r["qty"]) for r in out], [(1, 3.0), (2, 5.0), (3, 7.0)])
        self.assertEqual(src, rows())
        self.assertEqual(p.names(), ["map1", "num", "filter3"])
        self.assertEqual(p.run([]), [])
        with self.assertRaises(TypeError):
            p.run(src, colour="red")
        self.assertEqual(stages.select(["zz", "id"])({"id": 1}), {"id": 1})
        self.assertEqual(stages.cast("id", "str")({"id": 7})["id"], "7")
        with self.assertRaises(KeyError):
            stages.cast("zz", "int")({"id": 1})
        self.assertTrue({"rename", "select", "cast"} <= set(spec.OPS))

    def test_stage_errors_carry_context(self):
        def boom(rec):
            if rec["id"] == 3:
                raise RuntimeError("bad city")
            return rec

        p = Pipeline().map(boom, name="check")
        with self.assertRaises(StageError) as cm:
            p.run(rows())
        self.assertEqual(str(cm.exception), "stage 'check' failed: bad city")
        self.assertEqual((cm.exception.stage, cm.exception.record["name"], str(cm.exception.cause)), ("check", "Cy", "bad city"))
        later = Pipeline().filter(lambda r: r["id"] != 1).map(boom, name="check")
        with self.assertRaises(StageError):
            later.run(rows())
    @@blocks tests
'''


def make_slices(rng: random.Random):
    batch_note = rng.choice(["Each batch is a list, even an empty one.", "Batches that end up empty are still yielded as empty lists."])
    S = []

    S.append(Slice(
        id="drop-empty", title="Drop empty records", d=1,
        pitch=("Half of the incoming rows have blank names and break the report.",
               "Exports contain rows with missing values; we want a one-line way to filter them out."),
        reqs=("`stages.drop_empty(fields=None)` returns a predicate for `Pipeline.filter`: a record is kept when every field in `fields` has a real value. `None`, the empty string and strings that contain only whitespace count as empty, and so does a field that is missing from the record. With `fields=None` every field of the record is checked.",
              "Example: `pipeline.filter(stages.drop_empty([\"name\"]))`."),
        code={
            "etlpipe/stages.py::functions": '''
                def drop_empty(fields=None):
                    def empty(v):
                        return v is None or (isinstance(v, str) and not v.strip())

                    def keep(rec):
                        names = list(rec) if fields is None else list(fields)
                        return not any(f not in rec or empty(rec[f]) for f in names)

                    return keep
            ''',
        },
        readme="## Drop empty records\n\n`stages.drop_empty(fields=None)` is a predicate for `filter` that rejects records whose listed fields (all fields by default) are missing, `None`, empty or whitespace-only.\n",
        vtests='''
            def test_drop_empty_basic(self):
                out = Pipeline().filter(stages.drop_empty(["name"])).run(rows())
                self.assertEqual(ids(out), [1, 2, 3, 4])
        ''',
        tests='''
            def test_drop_empty_fields(self):
                out = Pipeline().filter(stages.drop_empty(["name"])).run(rows())
                self.assertEqual(ids(out), [1, 2, 3, 4])
                self.assertEqual([r["name"] for r in out], ["Ana", "Bo", "Cy", "Di"])
                self.assertEqual(ids(Pipeline().filter(stages.drop_empty(["name", "city"])).run(rows())), [1, 2, 4])
                self.assertEqual(ids(Pipeline().filter(stages.drop_empty()).run(rows())), [1, 2, 4])

            def test_drop_empty_edge_values(self):
                keep = stages.drop_empty(["a"])
                self.assertFalse(keep({"a": "  \\t"}))
                self.assertFalse(keep({"a": None}))
                self.assertFalse(keep({}))
                self.assertTrue(keep({"a": 0}))
                self.assertTrue(keep({"a": False}))
                self.assertTrue(keep({"a": "x", "b": None}))
                self.assertTrue(stages.drop_empty([])({"a": None}))
                self.assertTrue(stages.drop_empty()({}))
        ''',
    ))

    S.append(Slice(
        id="sort", title="Sort stage", d=1,
        pitch=("Reports need the output ordered; sorting after `run` loses the stage names in the metrics and the error context.",
               "People keep sorting the result by hand after the pipeline has run."),
        reqs=("`pipeline.sort(key, reverse=False, name=None)` adds a stage that sorts the records it receives: `key` is a field name or a function of the record. The sort is stable and `reverse=True` keeps equal records in their original order. A default name is `sort` plus the position (`sort3`).",
              "A record without the key field makes `run` raise `KeyError` (it is not wrapped in `StageError`)."),
        code={
            "etlpipe/pipeline.py::apply_special": '''
                if stage.kind == "sort":
                    key, reverse = stage.fn
                    keyfn = (lambda r: r[key]) if isinstance(key, str) else key
                    return sorted(records, key=keyfn, reverse=reverse)
            ''',
            "etlpipe/pipeline.py::methods": '''
                def sort(self, key, reverse=False, name=None):
                    return self._add("sort", (key, reverse), name)
            ''',
        },
        readme="## Sort stage\n\n`pipeline.sort(key, reverse=False, name=None)` sorts the records at that point (stable; `key` is a field name or a function). A record missing the key field raises `KeyError`.\n",
        vtests='''
            def test_sort_basic(self):
                out = Pipeline().sort("qty").run(rows())
                self.assertEqual([r["qty"] for r in out], ["2", "3", "5", "7", "x"])
        ''',
        tests='''
            def test_sort_stage(self):
                p = Pipeline().filter(lambda r: r["qty"] != "x").sort("qty")
                self.assertEqual(ids(p.run(rows())), [4, 1, 2, 3])
                self.assertEqual(p.names(), ["filter1", "sort2"])
                self.assertEqual(ids(Pipeline().sort("id", reverse=True).run(rows())), [4, 3, 2, 2, 1])
                self.assertEqual([r["name"] for r in Pipeline().sort("id", reverse=True).run(rows())], ["Di", "Cy", "", "Bo", "Ana"])
                self.assertEqual([r["name"] for r in Pipeline().sort(lambda r: -r["id"]).run(rows())][:3], ["Di", "Cy", ""])
                self.assertEqual(Pipeline().sort("id", name="order").names(), ["order"])

            def test_sort_is_stable(self):
                out = Pipeline().sort("city").run([r for r in rows() if r["city"]])
                self.assertEqual(ids(out), [2, 2, 1, 4])

            def test_sort_missing_key(self):
                with self.assertRaises(KeyError):
                    Pipeline().sort("nope").run(rows())
        ''',
    ))

    S.append(Slice(
        id="dedupe", title="Deduplicate stage", d=2,
        pitch=("The upstream export repeats rows whenever a batch is retried.",
               "We keep getting the same customer twice and have to remove the repeats downstream."),
        reqs=("`pipeline.dedupe(key, name=None)` adds a filter stage that keeps only the first record for each key value; `key` is a field name or a list of field names (the key value is the tuple of those fields' values). A default name is `dedupe` plus the position (`dedupe3`).",
              "The memory of the stage is cleared at the start of every `run`, so running the same pipeline twice gives the same result. A record that lacks a key field makes the stage fail like any other failing stage (`StageError` with the `KeyError` as cause)."),
        code={
            "etlpipe/pipeline.py::stage_fields": "reset: object = None",
            "etlpipe/pipeline.py::run_begin": '''
                for stage in self._stages:
                    if stage.reset is not None:
                        stage.reset()
            ''',
            "etlpipe/pipeline.py::methods": '''
                def dedupe(self, key, name=None):
                    fields = [key] if isinstance(key, str) else list(key)
                    seen = set()

                    def first_time(rec):
                        k = tuple(rec[f] for f in fields)
                        if k in seen:
                            return False
                        seen.add(k)
                        return True

                    return self._add("filter", first_time, name or f"dedupe{len(self._stages) + 1}", reset=seen.clear)
            ''',
        },
        readme="## Deduplicate stage\n\n`pipeline.dedupe(key, name=None)` keeps the first record per key (a field name or a list of names); its memory is cleared at the start of each `run`.\n",
        vtests='''
            def test_dedupe_basic(self):
                self.assertEqual(ids(Pipeline().dedupe("id").run(rows())), [1, 2, 3, 4])
        ''',
        tests='''
            def test_dedupe_keeps_first(self):
                p = Pipeline().dedupe("id")
                out = p.run(rows())
                self.assertEqual(ids(out), [1, 2, 3, 4])
                self.assertEqual([r["name"] for r in out], ["Ana", "", "Cy", "Di"])
                self.assertEqual(ids(p.run(rows())), [1, 2, 3, 4])
                self.assertEqual(p.names(), ["dedupe1"])
                self.assertEqual(ids(Pipeline().dedupe("city").run(rows())), [1, 2, 3])
                self.assertEqual(len(Pipeline().dedupe(["city", "qty"], name="pair").run(rows())), 5)
                self.assertEqual(ids(Pipeline().dedupe(["id", "city"]).run(rows())), [1, 2, 3, 4])

            def test_dedupe_position_and_errors(self):
                p = Pipeline().filter(lambda r: True).dedupe("id")
                self.assertEqual(p.names(), ["filter1", "dedupe2"])
                with self.assertRaises(StageError) as cm:
                    Pipeline().dedupe("nope", name="dd").run(rows())
                self.assertEqual(cm.exception.stage, "dd")
                self.assertIsInstance(cm.exception.cause, KeyError)
        ''',
    ))

    S.append(Slice(
        id="require", title="Required fields", d=2,
        pitch=("Rows without a customer id silently flow through and fail three steps later.",
               "We want records with missing mandatory fields to be flagged at the stage where they enter."),
        reqs=("`stages.require(fields)` returns a function for `Pipeline.map` that returns the record unchanged when every listed field is present and not `None`, and otherwise raises `ValueError(\"missing field: NAME\")` for the first listed field that is missing (an empty string is a valid value).",
              "Inside a pipeline such a failure is reported like any stage failure: `StageError` with the `ValueError` as cause."),
        code={
            "etlpipe/stages.py::functions": '''
                def require(fields):
                    fields = list(fields)

                    def apply(rec):
                        for f in fields:
                            if rec.get(f) is None:
                                raise ValueError(f"missing field: {f}")
                        return rec

                    return apply
            ''',
        },
        readme="## Required fields\n\n`stages.require(fields)` is a map function that passes records through and raises `ValueError(\"missing field: NAME\")` when a listed field is missing or `None`.\n",
        vtests='''
            def test_require_basic(self):
                self.assertEqual(stages.require(["id"])({"id": 1}), {"id": 1})
        ''',
        tests='''
            def test_require_function(self):
                need = stages.require(["id", "city"])
                rec = {"id": 1, "city": "Oslo", "x": 2}
                self.assertIs(need(rec), rec)
                self.assertEqual(need({"id": 1, "city": ""}), {"id": 1, "city": ""})
                with self.assertRaisesRegex(ValueError, "^missing field: city$"):
                    need({"id": 1, "city": None})
                with self.assertRaisesRegex(ValueError, "^missing field: id$"):
                    need({"city": "x"})
                with self.assertRaisesRegex(ValueError, "^missing field: id$"):
                    need({})
                self.assertEqual(stages.require([])({}), {})

            def test_require_in_a_pipeline(self):
                p = Pipeline().map(stages.require(["city"]), name="need-city")
                with self.assertRaises(StageError) as cm:
                    p.run(rows())
                self.assertEqual((cm.exception.stage, cm.exception.record["id"]), ("need-city", 3))
                self.assertEqual(str(cm.exception.cause), "missing field: city")
                self.assertEqual(ids(p.run([r for r in rows() if r["city"]])), [1, 2, 2, 4])
        ''',
    ))

    S.append(Slice(
        id="dead-letter", title="Error handling modes", d=3,
        pitch=("One bad row aborts a ten-minute run and nobody can see which rows were bad.",
               "We want to finish the run and get a list of the rows that failed."),
        reqs=("`run(records, on_error=\"raise\")` gets an `on_error` option: `\"raise\"` (the default, today's behaviour), `\"skip\"` or `\"collect\"`; any other value is a `ValueError` raised before any record is processed.",
              "In `skip` and `collect` mode a record whose stage function raises is dropped (the stage's input record, unchanged) and processing continues with the next record. With `collect` it is also appended to `pipeline.rejected` as a tuple `(stage_name, record, message)` with `message = str(exception)`.",
              "`pipeline.rejected` is `[]` for a new pipeline and is reset at the start of every run; in `raise` and `skip` mode it stays empty."),
        code={
            "etlpipe/pipeline.py::init": "self.rejected = []",
            "etlpipe/pipeline.py::run_begin": '''
                self._on_error = opts.pop("on_error", "raise")
                if self._on_error not in ("raise", "skip", "collect"):
                    raise ValueError(f"unknown on_error mode: {self._on_error!r}")
                self.rejected = []
            ''',
            "etlpipe/pipeline.py::on_error": '''
                if self._on_error == "raise":
                    raise StageError(stage.name, rec, e) from e
                if self._on_error == "collect":
                    self.rejected.append((stage.name, rec, str(e)))
            ''',
        },
        readme="## Error handling modes\n\n`run(records, on_error=\"raise\" | \"skip\" | \"collect\")`: failing records are dropped in the last two modes, and `collect` lists them in `pipeline.rejected` as `(stage_name, record, message)`; `rejected` is reset on every run.\n",
        vtests='''
            def test_on_error_skip(self):
                p = Pipeline().map(stages.cast("qty", "int"))
                self.assertEqual(ids(p.run(rows(), on_error="skip")), [1, 2, 3, 4])
        ''',
        tests='''
            def test_collect_and_skip(self):
                p = Pipeline().map(stages.cast("qty", "int"), name="to-int").filter(lambda r: r["qty"] > 2, name="big")
                self.assertEqual(p.rejected, [])
                out = p.run(rows(), on_error="collect")
                self.assertEqual(ids(out), [1, 2, 3])
                self.assertEqual(len(p.rejected), 1)
                stage, rec, message = p.rejected[0]
                self.assertEqual((stage, rec), ("to-int", ROWS[2]))
                self.assertIsInstance(message, str)
                self.assertIn("x", message)
                self.assertEqual(ids(p.run(rows(), on_error="skip")), [1, 2, 3])
                self.assertEqual(p.rejected, [])
                p.run(rows(), on_error="collect")
                p.run([ROWS[0]], on_error="collect")
                self.assertEqual(p.rejected, [])

            def test_raise_is_the_default(self):
                p = Pipeline().map(stages.cast("qty", "int"), name="to-int")
                for kwargs in ({}, {"on_error": "raise"}):
                    with self.assertRaises(StageError):
                        p.run(rows(), **kwargs)
                    self.assertEqual(p.rejected, [])

            def test_errors_in_any_stage_and_bad_mode(self):
                def picky(rec):
                    if rec["id"] == 3:
                        raise RuntimeError("no id 3")
                    return rec["id"] != 4

                p = Pipeline().filter(picky, name="picky")
                self.assertEqual(ids(p.run(rows(), on_error="collect")), [1, 2, 2])
                self.assertEqual([(s, r["id"], m) for s, r, m in p.rejected], [("picky", 3, "no id 3")])
                with self.assertRaises(ValueError):
                    p.run(rows(), on_error="explode")
                with self.assertRaises(ValueError):
                    p.run(rows(), on_error=None)
                with self.assertRaises(TypeError):
                    p.run(rows(), colour="red")
        ''',
    ))

    S.append(Slice(
        id="metrics", title="Run metrics", d=3,
        pitch=("When the output looks short nobody can tell which stage ate the records.",
               "Operations wants counts per stage after each run."),
        reqs=("After a run, `pipeline.metrics` is a list with one dict per stage, in stage order: `{\"stage\": name, \"in\": n, \"out\": m}` where `n` is the number of records that entered the stage and `m` the number that left it. It is `[]` for a pipeline that has not run and is replaced at the start of every run.",
              "The counts describe the whole run, so they are complete after a successful `run`."),
        code={
            "etlpipe/pipeline.py::init": "self.metrics = []",
            "etlpipe/pipeline.py::run_begin": 'self.metrics = [{"stage": s.name, "in": 0, "out": 0} for s in self._stages]',
            "etlpipe/pipeline.py::stage_begin": "n_in = len(current)",
            "etlpipe/pipeline.py::stage_end": '''
                self.metrics[i]["in"] += n_in
                self.metrics[i]["out"] += len(current)
            ''',
        },
        readme="## Run metrics\n\nAfter a run `pipeline.metrics` lists `{\"stage\", \"in\", \"out\"}` for each stage in order; it is replaced by every run.\n",
        vtests='''
            def test_metrics_basic(self):
                p = Pipeline().filter(lambda r: r["qty"] != "x", name="no-x")
                p.run(rows())
                self.assertEqual((p.metrics[0]["in"], p.metrics[0]["out"]), (5, 4))
        ''',
        tests='''
            def core(self, metrics):
                return [{k: m[k] for k in ("stage", "in", "out")} for m in metrics]

            def test_metrics_counts(self):
                p = Pipeline().filter(lambda r: r["qty"] != "x", name="no-x").map(stages.cast("qty", "int"), name="int").filter(lambda r: r["qty"] > 2, name="big")
                self.assertEqual(p.metrics, [])
                p.run(rows())
                self.assertEqual(self.core(p.metrics), [
                    {"stage": "no-x", "in": 5, "out": 4},
                    {"stage": "int", "in": 4, "out": 4},
                    {"stage": "big", "in": 4, "out": 3},
                ])
                p.run(rows()[:2])
                self.assertEqual(self.core(p.metrics), [
                    {"stage": "no-x", "in": 2, "out": 2},
                    {"stage": "int", "in": 2, "out": 2},
                    {"stage": "big", "in": 2, "out": 2},
                ])
                p.run([])
                self.assertEqual([(m["in"], m["out"]) for m in p.metrics], [(0, 0)] * 3)
                self.assertEqual(Pipeline().metrics, [])
                empty = Pipeline()
                empty.run(rows())
                self.assertEqual(empty.metrics, [])
        ''',
        cross={
            "dead-letter": {
                "reqs": ("With the error modes every metrics entry also has `\"errors\"`: how many records that stage rejected in the run (0 when none; in `raise` mode the run stops at the first failure, so counts are only guaranteed for `skip` and `collect`). A rejected record counts in `in` but not in `out`.",),
                "code": {
                    "etlpipe/pipeline.py::run_begin": '''
                        for entry in self.metrics:
                            entry["errors"] = 0
                    ''',
                    "etlpipe/pipeline.py::stage_begin": "err0 = len(self.rejected)",
                    "etlpipe/pipeline.py::stage_end": 'self.metrics[i]["errors"] += len(self.rejected) - err0',
                },
                "tests": '''
                    def test_metrics_count_rejected_records(self):
                        p = Pipeline().map(stages.cast("qty", "int"), name="to-int").filter(lambda r: r["qty"] > 2, name="big")
                        p.run(rows(), on_error="collect")
                        self.assertEqual(p.metrics, [
                            {"stage": "to-int", "in": 5, "out": 4, "errors": 1},
                            {"stage": "big", "in": 4, "out": 3, "errors": 0},
                        ])
                '''},
        },
    ))

    S.append(Slice(
        id="from-spec", title="Pipelines from data", d=3,
        pitch=("Pipelines are defined in a YAML-ish settings file and the loader code is copy-pasted in three services.",
               "Operators want to describe a pipeline as plain data instead of Python."),
        reqs=("`spec.register_op(name, build)` adds a builder to `spec.OPS` (`ValueError` if the name is taken); `build(pipeline, **args)` adds stages to the pipeline it receives.",
              "`Pipeline.from_spec(items, name=\"pipeline\")` builds a pipeline from a list of dicts. Each item has an `\"op\"` key naming an entry of `spec.OPS`; all its other keys are passed as keyword arguments to the builder, and the items are applied in order. An item that is not a dict or has no `\"op\"`, or an unknown op, is a `ValueError` (message `unknown op: NAME` for the latter). Bad arguments are the builder's `TypeError`.",
              "The built-in ops are `rename` (`mapping`), `select` (`fields`) and `cast` (`field`, `kind`), each adding one `map` stage with the matching function from `stages`."),
        code={
            "etlpipe/spec.py::functions": '''
                def register_op(name, build):
                    if name in OPS:
                        raise ValueError(f"op already registered: {name}")
                    OPS[name] = build
            ''',
            "etlpipe/pipeline.py::methods": '''
                @classmethod
                def from_spec(cls, items, name="pipeline"):
                    from . import spec

                    pipeline = cls(name)
                    for item in items:
                        if not isinstance(item, dict) or "op" not in item:
                            raise ValueError("each item must be a dict with an 'op' key")
                        args = dict(item)
                        op = args.pop("op")
                        if op not in spec.OPS:
                            raise ValueError(f"unknown op: {op}")
                        spec.OPS[op](pipeline, **args)
                    return pipeline
            ''',
        },
        readme="## Pipelines from data\n\n`Pipeline.from_spec([{\"op\": \"rename\", \"mapping\": {...}}, ...])` builds a pipeline from `spec.OPS`; `spec.register_op(name, build)` adds your own ops.\n",
        vtests='''
            def test_from_spec_basic(self):
                p = Pipeline.from_spec([{"op": "select", "fields": ["id"]}])
                self.assertEqual(p.run(rows())[0], {"id": 1})
        ''',
        tests='''
            def test_from_spec_builtin_ops(self):
                p = Pipeline.from_spec([
                    {"op": "rename", "mapping": {"name": "customer"}},
                    {"op": "cast", "field": "id", "kind": "str"},
                    {"op": "select", "fields": ["id", "customer"]},
                ], name="spec")
                self.assertEqual(p.name, "spec")
                self.assertEqual(p.names(), ["map1", "map2", "map3"])
                self.assertEqual(p.run(rows())[:2], [{"id": "1", "customer": "Ana"}, {"id": "2", "customer": ""}])
                self.assertEqual(Pipeline.from_spec([]).run(rows()), rows())

            def test_from_spec_errors(self):
                for bad in ([{"op": "teleport"}], ["rename"], [{}], [{"mapping": {}}], [None]):
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        Pipeline.from_spec(bad)
                with self.assertRaisesRegex(ValueError, "unknown op: teleport"):
                    Pipeline.from_spec([{"op": "teleport"}])
                with self.assertRaises(TypeError):
                    Pipeline.from_spec([{"op": "select"}])
                with self.assertRaises(TypeError):
                    Pipeline.from_spec([{"op": "select", "fields": [], "extra": 1}])

            def test_register_op(self):
                def upper(p, field):
                    return p.map(lambda r: {**r, field: r[field].upper()}, name="upper-" + field)

                spec.register_op("upper-test", upper)
                self.addCleanup(spec.OPS.pop, "upper-test", None)
                self.assertIs(spec.OPS["upper-test"], upper)
                p = Pipeline.from_spec([{"op": "upper-test", "field": "city"}])
                self.assertEqual(p.names(), ["upper-city"])
                self.assertEqual(p.run([{"city": "oslo"}]), [{"city": "OSLO"}])
                with self.assertRaises(ValueError):
                    spec.register_op("upper-test", upper)
                with self.assertRaises(ValueError):
                    spec.register_op("rename", upper)
        ''',
        cross={
            "drop-empty": {
                "reqs": ("`drop_empty` is available as a spec op with the optional argument `fields` (it adds a `filter` stage).",),
                "code": {"etlpipe/spec.py::ops": 'OPS["drop_empty"] = lambda p, fields=None: p.filter(stages.drop_empty(fields))'},
                "tests": '''
                    def test_spec_op_drop_empty(self):
                        p = Pipeline.from_spec([{"op": "drop_empty", "fields": ["name"]}])
                        self.assertEqual(ids(p.run(rows())), [1, 2, 3, 4])
                        self.assertEqual(ids(Pipeline.from_spec([{"op": "drop_empty"}]).run(rows())), [1, 2, 4])
                '''},
            "sort": {
                "reqs": ("`sort` is available as a spec op with `key` (a field name) and optional `reverse`.",),
                "code": {"etlpipe/spec.py::ops": 'OPS["sort"] = lambda p, key, reverse=False: p.sort(key, reverse)'},
                "tests": '''
                    def test_spec_op_sort(self):
                        p = Pipeline.from_spec([{"op": "sort", "key": "id", "reverse": True}])
                        self.assertEqual(ids(p.run(rows())), [4, 3, 2, 2, 1])
                '''},
            "dedupe": {
                "reqs": ("`dedupe` is available as a spec op with `key` (a field name or a list of names).",),
                "code": {"etlpipe/spec.py::ops": 'OPS["dedupe"] = lambda p, key: p.dedupe(key)'},
                "tests": '''
                    def test_spec_op_dedupe(self):
                        p = Pipeline.from_spec([{"op": "dedupe", "key": ["id"]}])
                        self.assertEqual(ids(p.run(rows())), [1, 2, 3, 4])
                '''},
            "require": {
                "reqs": ("`require` is available as a spec op with `fields`.",),
                "code": {"etlpipe/spec.py::ops": 'OPS["require"] = lambda p, fields: p.map(stages.require(fields))'},
                "tests": '''
                    def test_spec_op_require(self):
                        p = Pipeline.from_spec([{"op": "require", "fields": ["city"]}])
                        with self.assertRaises(StageError):
                            p.run(rows())
                '''},
        },
    ))

    S.append(Slice(
        id="batches", title="Batched runs", d=4,
        pitch=("The nightly file has millions of rows and holding the whole result in memory is not an option.",
               "Large inputs have to be processed in chunks and handed on chunk by chunk."),
        reqs=("`pipeline.run_batches(records, size, **options)` returns a generator that reads `records` (any iterable, consumed lazily) in consecutive chunks of `size` records (the last may be smaller) and yields, for each chunk, the list of records that came out of the pipeline for that chunk. " + batch_note + " An empty input yields nothing.",
              "`size` must be a positive integer (`ValueError` otherwise, raised by the call itself, not by the first iteration). The options are those of `run`; invalid options also raise at the call.",
              "Everything that is state of a *run* belongs to the whole `run_batches` call, not to one chunk: it starts once when the call is made and carries on across chunks."),
        code={
            "etlpipe/pipeline.py::methods": '''
                def run_batches(self, records, size, **opts):
                    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
                        raise ValueError("size must be a positive integer")
                    self._begin(opts)
                    return self._batches(records, size)

                def _batches(self, records, size):
                    chunk = []
                    for rec in records:
                        chunk.append(rec)
                        if len(chunk) == size:
                            yield self._process(chunk)
                            chunk = []
                    if chunk:
                        yield self._process(chunk)
            ''',
        },
        readme="## Batched runs\n\n`pipeline.run_batches(records, size, **options)` yields one output list per chunk of `size` input records; run state (stage memory, metrics, rejected records) spans the whole call.\n",
        vtests='''
            def test_batches_basic(self):
                batches = list(Pipeline().filter(lambda r: r["qty"] != "x").run_batches(rows(), 2))
                self.assertEqual([ids(b) for b in batches], [[1, 2], [3], [4]])
        ''',
        tests='''
            def test_batches_chunking(self):
                p = Pipeline().filter(lambda r: r["qty"] != "x")
                self.assertEqual([ids(b) for b in p.run_batches(rows(), 2)], [[1, 2], [3], [4]])
                self.assertEqual([ids(b) for b in p.run_batches(iter(rows()), 5)], [[1, 2, 3, 4]])
                self.assertEqual([ids(b) for b in p.run_batches(rows(), 100)], [[1, 2, 3, 4]])
                self.assertEqual(list(p.run_batches([], 3)), [])
                city = Pipeline().filter(lambda r: r["city"] == "Oslo")
                self.assertEqual([ids(b) for b in city.run_batches(rows(), 2)], [[1], [], [4]])

            def test_batches_validate_eagerly(self):
                p = Pipeline()
                for bad in (0, -1, 1.5, "2", None, True):
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        p.run_batches(rows(), bad)
                with self.assertRaises(TypeError):
                    p.run_batches(rows(), 2, colour="red")

            def test_batches_are_lazy(self):
                pulled = []

                def source():
                    for r in rows():
                        pulled.append(r["id"])
                        yield r

                it = Pipeline().run_batches(source(), 2)
                self.assertEqual(pulled, [])
                self.assertEqual(ids(next(it)), [1, 2])
                self.assertEqual(pulled, [1, 2])
        ''',
        cross={
            "dedupe": {
                "reqs": ("A `dedupe` stage remembers across the chunks of one `run_batches` call and forgets when the next call (or `run`) starts.",),
                "tests": '''
                    def test_dedupe_spans_batches(self):
                        p = Pipeline().dedupe("id")
                        self.assertEqual([ids(b) for b in p.run_batches(rows(), 2)], [[1, 2], [3], [4]])
                        self.assertEqual([ids(b) for b in p.run_batches(rows(), 2)], [[1, 2], [3], [4]])
                        self.assertEqual(ids(p.run(rows())), [1, 2, 3, 4])
                '''},
            "sort": {
                "reqs": ("A `sort` stage sorts each chunk on its own.",),
                "tests": '''
                    def test_sort_is_per_batch(self):
                        p = Pipeline().sort("id", reverse=True)
                        self.assertEqual([ids(b) for b in p.run_batches(rows(), 3)], [[2, 2, 1], [4, 3]])
                '''},
            "metrics": {
                "reqs": ("`pipeline.metrics` counts the whole call (all chunks together), starting from zero when the call is made.",),
                "tests": '''
                    def test_metrics_span_batches(self):
                        p = Pipeline().filter(lambda r: r["qty"] != "x", name="no-x").map(stages.cast("qty", "int"), name="int")
                        list(p.run_batches(rows(), 2))
                        self.assertEqual([(m["stage"], m["in"], m["out"]) for m in p.metrics], [("no-x", 5, 4), ("int", 4, 4)])
                        list(p.run_batches(rows()[:1], 2))
                        self.assertEqual([(m["in"], m["out"]) for m in p.metrics], [(1, 1), (1, 1)])
                '''},
            "dead-letter": {
                "reqs": ("With `on_error=\"collect\"` the rejected records of all chunks accumulate in `pipeline.rejected`; it is reset when the call is made.",),
                "tests": '''
                    def test_rejected_spans_batches(self):
                        p = Pipeline().map(stages.cast("qty", "int"), name="to-int")
                        out = list(p.run_batches(rows() + rows(), 4, on_error="collect"))
                        self.assertEqual([len(b) for b in out], [3, 3, 2])
                        self.assertEqual([r["id"] for _, r, _ in p.rejected], [2, 2])
                        list(p.run_batches([], 4, on_error="collect"))
                        self.assertEqual(p.rejected, [])
                '''},
        },
    ))

    return S


APP = App(
    name="etlpipe", lang="python", title="the record pipeline library", role="a data engineer", key="ETL",
    base={
        "README.md": README + "\n@@blocks features\n",
        "etlpipe/__init__.py": INIT,
        "etlpipe/pipeline.py": PIPELINE,
        "etlpipe/stages.py": STAGES,
        "etlpipe/spec.py": SPEC,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-etlpipe", APP, make_slices, n=16, summary="record pipeline: cleanup stages, error modes, metrics, specs, batching")
