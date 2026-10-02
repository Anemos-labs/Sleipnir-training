"""timesheet (rust): an hours ledger extended with filters, caps, rounding, CSV, overtime, tags, locks and undo."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # timesheet

    Hour tracking for a small consultancy: people log minutes against projects on numbered days, and the office turns
    that into reports. Rust 2021, no dependencies; `cargo test` runs the tests.

    ## Layout

    * `src/entry.rs`: `Entry`.
    * `src/ledger.rs`: `Ledger`, `LedgerError`.
    * `src/report.rs`: text output.
    * `tests/`: integration tests.

    ## Basics

    A day is a number from 1 to 366 (day of the year). An `Entry` has `id: u32`, `day: u32`, `project: String`,
    `minutes: u32` and `note: String`.

    * `Ledger::new()`.
    * `ledger.log(day, project, minutes, note) -> Result<u32, LedgerError>` adds an entry and returns its id; ids
      are 1, 2, 3, ... in the order of the successful calls. `LedgerError::ZeroMinutes` for 0 minutes (checked first),
      `LedgerError::BadDay(day)` for a day outside 1..=366. A failed call changes nothing.
    * `ledger.remove(id) -> Result<Entry, LedgerError>`; `LedgerError::NotFound(id)` for an unknown id.
    * `ledger.entries() -> &[Entry]` in id order; `ledger.total_minutes() -> u32`.
    * `LedgerError` implements `Display` and `Error`.
    * `report::text(&ledger) -> String`: one line per entry ordered by (day, id), `{day:>3} {project:<10} {h}:{mm:02} {note}`
      with trailing whitespace trimmed, each line ending in a newline.
''')

ENTRY = '''\
/// One logged block of time.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub id: u32,
    pub day: u32,
    pub project: String,
    pub minutes: u32,
    pub note: String,
    @@slot entry_fields
}
'''

LIB = '''\
//! Hour tracking for a small consultancy.
pub mod entry;
pub mod ledger;
pub mod report;

pub use entry::Entry;
pub use ledger::{Ledger, LedgerError};
@@slot reexports
'''

LEDGER = '''\
use std::fmt;

use crate::entry::Entry;
@@uniq imports

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LedgerError {
    ZeroMinutes,
    BadDay(u32),
    NotFound(u32),
    @@slot error_variants
}

impl fmt::Display for LedgerError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LedgerError::ZeroMinutes => write!(f, "an entry needs at least one minute"),
            LedgerError::BadDay(d) => write!(f, "day {} is outside 1..=366", d),
            LedgerError::NotFound(id) => write!(f, "no entry with id {}", id),
            @@slot error_display
        }
    }
}

impl std::error::Error for LedgerError {}

@@blocks types

/// The list of entries.
#[derive(Debug, Clone)]
pub struct Ledger {
    entries: Vec<Entry>,
    next_id: u32,
    @@slot ledger_fields
}

impl Ledger {
    pub fn new() -> Ledger {
        Ledger {
            entries: Vec::new(),
            next_id: 1,
            @@slot ledger_init
        }
    }

    pub fn log(&mut self, day: u32, project: &str, minutes: u32, note: &str) -> Result<u32, LedgerError> {
        if minutes == 0 {
            return Err(LedgerError::ZeroMinutes);
        }
        if !(1..=366).contains(&day) {
            return Err(LedgerError::BadDay(day));
        }
        @@slot log_checks
        @@slot log_pre
        let id = self.next_id;
        self.next_id += 1;
        self.entries.push(Entry {
            id,
            day,
            project: project.to_string(),
            minutes,
            note: note.to_string(),
            @@slot entry_init
        });
        @@slot log_post
        Ok(id)
    }

    pub fn remove(&mut self, id: u32) -> Result<Entry, LedgerError> {
        let pos = self.entries.iter().position(|e| e.id == id).ok_or(LedgerError::NotFound(id))?;
        @@slot remove_checks
        @@slot remove_pre
        let removed = self.entries.remove(pos);
        @@slot remove_post
        Ok(removed)
    }

    pub fn entries(&self) -> &[Entry] {
        &self.entries
    }

    pub fn total_minutes(&self) -> u32 {
        self.entries.iter().map(|e| e.minutes).sum()
    }

    @@blocks methods
}
'''

REPORT = '''\
use crate::ledger::Ledger;
@@uniq imports

/// One line per entry ordered by (day, id).
pub fn text(ledger: &Ledger) -> String {
    let mut rows: Vec<_> = ledger.entries().iter().collect();
    rows.sort_by_key(|e| (e.day, e.id));
    let mut out = String::new();
    for e in rows {
        let line = format!("{:>3} {:<10} {}:{:02} {}", e.day, e.project, e.minutes / 60, e.minutes % 60, e.note);
        out.push_str(line.trim_end());
        out.push('\\n');
    }
    out
}

@@blocks functions
'''

TEST_HELPERS = '''\
use timesheet::*;
@@uniq imports

fn ledger() -> Ledger {
    let mut l = Ledger::new();
    l.log(1, "atlas", 90, "kickoff").unwrap();
    l.log(1, "Birch", 45, "").unwrap();
    l.log(3, "atlas", 125, "wiring, phase 1").unwrap();
    l.log(8, "cedar", 30, "call").unwrap();
    l.log(9, "atlas", 600, "migration").unwrap();
    l
}

fn ids(l: &Ledger) -> Vec<u32> {
    l.entries().iter().map(|e| e.id).collect()
}
'''

VISIBLE = TEST_HELPERS + '''
#[test]
fn log_assigns_ids_and_validates() {
    let mut l = Ledger::new();
    assert_eq!(l.log(1, "a", 10, ""), Ok(1));
    assert_eq!(l.log(0, "a", 10, ""), Err(LedgerError::BadDay(0)));
    assert_eq!(l.log(367, "a", 10, ""), Err(LedgerError::BadDay(367)));
    assert_eq!(l.log(5, "a", 0, ""), Err(LedgerError::ZeroMinutes));
    assert_eq!(l.log(366, "b", 5, "end"), Ok(2));
    assert_eq!(l.entries().len(), 2);
}

#[test]
fn remove_and_total() {
    let mut l = ledger();
    assert_eq!(l.total_minutes(), 890);
    let gone = l.remove(2).unwrap();
    assert_eq!((gone.project.as_str(), gone.minutes), ("Birch", 45));
    assert_eq!(l.remove(2), Err(LedgerError::NotFound(2)));
    assert_eq!(ids(&l), vec![1, 3, 4, 5]);
}

#[test]
fn text_report() {
    let l = ledger();
    let text = report::text(&l);
    let lines: Vec<&str> = text.lines().collect();
    assert_eq!(lines[0], "  1 atlas      1:30 kickoff");
    assert_eq!(lines[1], "  1 Birch      0:45");
    assert_eq!(lines[4], "  9 atlas      10:00 migration");
}
@@blocks tests
'''

HIDDEN = TEST_HELPERS + '''
#[test]
fn base_rules_hold() {
    let mut l = ledger();
    assert_eq!(l.log(2, "x", 0, ""), Err(LedgerError::ZeroMinutes));
    assert_eq!(l.log(0, "x", 0, ""), Err(LedgerError::ZeroMinutes));
    assert_eq!(l.log(400, "x", 5, ""), Err(LedgerError::BadDay(400)));
    assert_eq!(ids(&l), vec![1, 2, 3, 4, 5]);
    assert_eq!(l.log(2, "x", 5, "n"), Ok(6));
    l.remove(3).unwrap();
    assert_eq!(l.log(2, "y", 5, "n"), Ok(7));
    assert_eq!(LedgerError::NotFound(4).to_string(), "no entry with id 4");
    assert_eq!(LedgerError::BadDay(9).to_string(), "day 9 is outside 1..=366");
    let t = report::text(&l);
    assert!(t.ends_with("migration\\n"));
    assert_eq!(report::text(&Ledger::new()), "");
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    cap = rng.choice([720, 900, 960])
    cap_h = cap // 60
    step = rng.choice([10, 15, 30])
    S = []

    S.append(Slice(
        id="project-filter", title="Entries by project", d=1,
        pitch=("Invoicing needs everything booked on one project.",
               "Project managers keep asking for the entries of just their project."),
        reqs=("`Ledger::for_project(&self, name: &str) -> Vec<&Entry>` returns the entries of that project in id order. The project name is compared case-insensitively and exactly (`atl` does not match `atlas`).",
              "An unknown project gives an empty vector."),
        code={
            "src/ledger.rs::methods": '''
                /// Entries of one project (case-insensitive exact match), in id order.
                pub fn for_project(&self, name: &str) -> Vec<&Entry> {
                    let want = name.to_lowercase();
                    self.entries.iter().filter(|e| e.project.to_lowercase() == want).collect()
                }
            ''',
        },
        readme=dd('''
            ## Entries by project

            `ledger.for_project(name)` returns the entries whose project equals `name` ignoring case, in id order.
        '''),
        vtests='''
            #[test]
            fn for_project_basic() {
                assert_eq!(ledger().for_project("atlas").len(), 3);
            }
        ''',
        tests='''
            #[test]
            fn for_project_is_case_insensitive_exact() {
                let l = ledger();
                let found: Vec<u32> = l.for_project("ATLAS").iter().map(|e| e.id).collect();
                assert_eq!(found, vec![1, 3, 5]);
                assert!(l.for_project("atl").is_empty());
                assert!(l.for_project("").is_empty());
                assert_eq!(l.for_project("birch").len(), 1);
                assert!(Ledger::new().for_project("x").is_empty());
            }
        ''',
    ))

    S.append(Slice(
        id="day-cap", title="Daily cap", d=2,
        pitch=("Somebody logged 31 hours on a single day last month and nobody noticed until invoicing.",
               "The office wants impossible days rejected when they are entered."),
        reqs=(f"One day may hold at most {cap} minutes ({cap_h} hours) in total. `log` fails with the new error `LedgerError::DayFull {{ day: u32, total: u32 }}` when the entry would push the day's total above {cap}; `total` is the total the day would have reached. Exactly {cap} is fine.",
              "The check comes after the existing ones (`ZeroMinutes`, `BadDay`) and a failed call changes nothing. `Display` for the new error reads `day D would reach T minutes`."),
        code={
            "src/ledger.rs::error_variants": "DayFull { day: u32, total: u32 },",
            "src/ledger.rs::error_display": 'LedgerError::DayFull { day, total } => write!(f, "day {} would reach {} minutes", day, total),',
            "src/ledger.rs::log_checks": f'''
                let total = self.entries.iter().filter(|e| e.day == day).map(|e| e.minutes).sum::<u32>() + minutes;
                if total > {cap} {{
                    return Err(LedgerError::DayFull {{ day, total }});
                }}
            ''',
        },
        readme=fmt(dd('''
            ## Daily cap

            A day holds at most __CAP__ minutes. `log` returns `LedgerError::DayFull { day, total }` (total = what the day would
            have reached) beyond that; exactly the cap is accepted.
        '''), CAP=cap),
        vtests='''
            #[test]
            fn day_cap_exists() {
                let mut l = Ledger::new();
                assert!(l.log(1, "a", 30, "").is_ok());
            }
        ''',
        tests=fmt('''
            #[test]
            fn a_day_cannot_exceed_the_cap() {
                let mut l = Ledger::new();
                l.log(5, "a", __CAP__ - 60, "").unwrap();
                assert_eq!(l.log(5, "b", 61, ""), Err(LedgerError::DayFull { day: 5, total: __CAP__ + 1 }));
                assert_eq!(l.entries().len(), 1);
                assert_eq!(l.log(5, "b", 60, ""), Ok(2));
                assert_eq!(l.log(5, "c", 1, ""), Err(LedgerError::DayFull { day: 5, total: __CAP__ + 1 }));
                assert_eq!(l.log(6, "c", __CAP__, ""), Ok(3));
                assert_eq!(l.total_minutes(), 2 * __CAP__);
            }

            #[test]
            fn cap_check_order_and_display() {
                let mut l = Ledger::new();
                assert_eq!(l.log(1, "a", 0, ""), Err(LedgerError::ZeroMinutes));
                assert_eq!(l.log(500, "a", __CAP__ + 100, ""), Err(LedgerError::BadDay(500)));
                assert_eq!(l.log(7, "a", __CAP__ + 100, "").unwrap_err().to_string(), format!("day 7 would reach {} minutes", __CAP__ + 100));
                assert_eq!(l.log(7, "a", 5, ""), Ok(1));
            }
        ''', CAP=cap),
    ))

    S.append(Slice(
        id="rounding", title="Billing rounding", d=3,
        pitch=("Clients are billed in quarter-hours, but the ledger only knows exact minutes.",
               "Invoices must use rounded time while the ledger keeps exact minutes."),
        reqs=("New public enum `Rounding { None, Nearest(u32), Up(u32), Down(u32) }` (derives `Debug, Clone, Copy, PartialEq, Eq`), re-exported at the crate root. The default is `Rounding::None`.",
              "`ledger.set_rounding(r) -> Result<(), LedgerError>`. A step of `Nearest`, `Up` or `Down` must be between 1 and 240 inclusive, otherwise `Err(LedgerError::BadStep(step))` and the old setting stays.",
              "`ledger.billable_minutes(&entry) -> u32` rounds one entry's minutes to a multiple of the step: `Nearest` to the closest multiple with halves rounding up (`(m + step / 2) / step * step`), `Up` to the next multiple at or above `m`, `Down` to the multiple at or below `m` (the result may be 0). `None` returns `m`. `ledger.billable_total() -> u32` sums `billable_minutes` over all entries (each rounded separately).",
              "Stored minutes are never changed; `Display` of `BadStep` reads `rounding step N is outside 1..=240`."),
        code={
            "src/lib.rs::reexports": "pub use ledger::Rounding;",
            "src/ledger.rs::error_variants": "BadStep(u32),",
            "src/ledger.rs::error_display": 'LedgerError::BadStep(s) => write!(f, "rounding step {} is outside 1..=240", s),',
            "src/ledger.rs::types": '''
                /// How billable time is derived from the logged minutes.
                #[derive(Debug, Clone, Copy, PartialEq, Eq)]
                pub enum Rounding {
                    None,
                    Nearest(u32),
                    Up(u32),
                    Down(u32),
                }
            ''',
            "src/ledger.rs::ledger_fields": "rounding: Rounding,",
            "src/ledger.rs::ledger_init": "rounding: Rounding::None,",
            "src/ledger.rs::methods": '''
                pub fn set_rounding(&mut self, r: Rounding) -> Result<(), LedgerError> {
                    match r {
                        Rounding::Nearest(s) | Rounding::Up(s) | Rounding::Down(s) if !(1..=240).contains(&s) => {
                            return Err(LedgerError::BadStep(s));
                        }
                        _ => {}
                    }
                    self.rounding = r;
                    Ok(())
                }

                pub fn billable_minutes(&self, e: &Entry) -> u32 {
                    let m = e.minutes;
                    match self.rounding {
                        Rounding::None => m,
                        Rounding::Nearest(s) => (m + s / 2) / s * s,
                        Rounding::Up(s) => (m + s - 1) / s * s,
                        Rounding::Down(s) => m / s * s,
                    }
                }

                pub fn billable_total(&self) -> u32 {
                    self.entries.iter().map(|e| self.billable_minutes(e)).sum()
                }
            ''',
        },
        readme=dd('''
            ## Billing rounding

            `Rounding::{None, Nearest(step), Up(step), Down(step)}` with `ledger.set_rounding(r)` (step 1..=240 else
            `LedgerError::BadStep`). `billable_minutes(&entry)` rounds one entry (`Nearest`: halves up); `billable_total()` sums them.
            Logged minutes are untouched.
        '''),
        vtests='''
            #[test]
            fn rounding_default_is_exact() {
                let l = ledger();
                assert_eq!(l.billable_total(), l.total_minutes());
            }
        ''',
        tests=fmt('''
            fn billable(l: &Ledger) -> Vec<u32> {
                l.entries().iter().map(|e| l.billable_minutes(e)).collect()
            }

            fn short_ledger() -> Ledger {
                let mut l = Ledger::new();
                for (i, m) in [7u32, 8, 15, 22, 23, 37].iter().enumerate() {
                    l.log(1 + i as u32, "p", *m, "").unwrap();
                }
                l
            }

            #[test]
            fn rounding_modes() {
                let mut l = short_ledger();
                assert_eq!(billable(&l), vec![7, 8, 15, 22, 23, 37]);
                l.set_rounding(Rounding::Nearest(15)).unwrap();
                assert_eq!(billable(&l), vec![0, 15, 15, 15, 30, 30]);
                l.set_rounding(Rounding::Up(15)).unwrap();
                assert_eq!(billable(&l), vec![15, 15, 15, 30, 30, 45]);
                l.set_rounding(Rounding::Down(15)).unwrap();
                assert_eq!(billable(&l), vec![0, 0, 15, 15, 15, 30]);
                l.set_rounding(Rounding::Nearest(10)).unwrap();
                assert_eq!(billable(&l), vec![10, 10, 20, 20, 20, 40]);
                assert_eq!(l.billable_total(), 120);
                l.set_rounding(Rounding::None).unwrap();
                assert_eq!(l.billable_total(), l.total_minutes());
                assert_eq!(l.total_minutes(), 112);
            }

            #[test]
            fn rounding_step_limits() {
                let mut l = short_ledger();
                l.set_rounding(Rounding::Up(__STEP__)).unwrap();
                assert_eq!(l.set_rounding(Rounding::Nearest(0)), Err(LedgerError::BadStep(0)));
                assert_eq!(l.set_rounding(Rounding::Down(241)), Err(LedgerError::BadStep(241)));
                assert_eq!(l.set_rounding(Rounding::Up(1)), Ok(()));
                assert_eq!(l.set_rounding(Rounding::Up(240)), Ok(()));
                l.set_rounding(Rounding::Up(__STEP__)).unwrap();
                assert_eq!(l.set_rounding(Rounding::Up(0)), Err(LedgerError::BadStep(0)));
                assert_eq!(billable(&l)[0], (7 + __STEP__ - 1) / __STEP__ * __STEP__);
                assert_eq!(LedgerError::BadStep(300).to_string(), "rounding step 300 is outside 1..=240");
                assert_eq!(l.entries()[0].minutes, 7);
            }

            #[test]
            fn rounding_each_entry_separately() {
                let mut l = Ledger::new();
                l.log(1, "p", 20, "").unwrap();
                l.log(1, "p", 20, "").unwrap();
                l.set_rounding(Rounding::Down(30)).unwrap();
                assert_eq!(l.billable_total(), 0);
                l.set_rounding(Rounding::Up(30)).unwrap();
                assert_eq!(l.billable_total(), 60);
            }
        ''', STEP=step),
    ))

    S.append(Slice(
        id="csv-export", title="CSV export", d=2,
        pitch=("Payroll imports the ledger into a spreadsheet every Friday.",
               "The accountants want the entries as a CSV file."),
        reqs=("`report::csv(&ledger) -> String`: a header line `id,day,project,minutes,note`, then one line per entry in id order, every line ending in `\\n`. An empty ledger gives just the header line.",
              "A text field (`project`, `note`) is wrapped in double quotes, with inner quotes doubled, when it contains a comma, a double quote or a newline; otherwise it is written as is."),
        code={
            "src/report.rs::functions": '''
                fn field(s: &str) -> String {
                    if s.contains(',') || s.contains('"') || s.contains('\\n') {
                        format!("\\"{}\\"", s.replace('"', "\\"\\""))
                    } else {
                        s.to_string()
                    }
                }

                /// The entries as CSV.
                pub fn csv(ledger: &Ledger) -> String {
                    let mut header = vec!["id", "day", "project", "minutes", "note"];
                    @@slot csv_header
                    let mut out = header.join(",") + "\\n";
                    for e in ledger.entries() {
                        let mut cells = vec![e.id.to_string(), e.day.to_string(), field(&e.project), e.minutes.to_string(), field(&e.note)];
                        @@slot csv_cells
                        out.push_str(&cells.join(","));
                        out.push('\\n');
                    }
                    out
                }
            ''',
        },
        readme=dd('''
            ## CSV export

            `report::csv(&ledger)`: header `id,day,project,minutes,note`, one line per entry in id order; text fields containing
            a comma, quote or newline are quoted with doubled quotes.
        '''),
        vtests='''
            #[test]
            fn csv_header_line() {
                assert!(report::csv(&Ledger::new()).starts_with("id,day,project,minutes,note"));
            }
        ''',
        tests='''
            #[test]
            fn csv_lines() {
                let l = ledger();
                let out = report::csv(&l);
                let lines: Vec<&str> = out.lines().collect();
                assert_eq!(lines.len(), 6);
                assert!(lines[0].starts_with("id,day,project,minutes,note"));
                assert!(lines[1].starts_with("1,1,atlas,90,kickoff"));
                assert!(lines[2].starts_with("2,1,Birch,45,"));
                assert!(lines[3].starts_with("3,3,atlas,125,\\"wiring, phase 1\\""));
                assert!(lines[5].starts_with("5,9,atlas,600,migration"));
                assert!(out.ends_with('\\n'));
                let empty = report::csv(&Ledger::new());
                assert_eq!(empty.lines().count(), 1);
                assert!(empty.starts_with("id,day,project,minutes,note"));
            }

            #[test]
            fn csv_quotes() {
                let mut l = Ledger::new();
                l.log(1, "a\\"b", 5, "x\\ny").unwrap();
                l.log(2, "plain", 6, "").unwrap();
                let out = report::csv(&l);
                assert!(out.contains("\\n1,1,\\"a\\"\\"b\\",5,\\"x\\ny\\""));
                assert!(out.contains("\\n2,2,plain,6,"));
            }
        ''',
        cross={
            "rounding": {
                "reqs": ("With rounding available the CSV gets one more column, `billable`, right after `note`: header `billable`, value `ledger.billable_minutes(entry)`.",),
                "code": {
                    "src/report.rs::csv_header": 'header.push("billable");',
                    "src/report.rs::csv_cells": "cells.push(ledger.billable_minutes(e).to_string());",
                },
                "tests": '''
                    #[test]
                    fn csv_has_billable_column() {
                        let mut l = ledger();
                        l.set_rounding(Rounding::Up(60)).unwrap();
                        let out = report::csv(&l);
                        let lines: Vec<&str> = out.lines().collect();
                        assert!(lines[0].starts_with("id,day,project,minutes,note,billable"));
                        assert!(lines[1].starts_with("1,1,atlas,90,kickoff,120"));
                        assert!(lines[2].starts_with("2,1,Birch,45,,60"));
                        assert!(lines[3].starts_with("3,3,atlas,125,\\"wiring, phase 1\\",180"));
                    }
                '''},
            "tags": {
                "reqs": ("With tags available the CSV gets one more column, `tags`, after `note` (and after `billable` when that column exists): header `tags`, value the entry's tags joined with `;` (empty for none).",),
                "code": {
                    "src/report.rs::csv_header": 'header.push("tags");',
                    "src/report.rs::csv_cells": 'cells.push(e.tags.join(";"));',
                },
                "tests": '''
                    #[test]
                    fn csv_has_tags_column() {
                        let mut l = Ledger::new();
                        l.log_tagged(1, "a", 5, "n", &["X", "y"]).unwrap();
                        l.log(2, "a", 5, "n").unwrap();
                        let out = report::csv(&l);
                        let lines: Vec<&str> = out.lines().collect();
                        assert!(lines[0].ends_with(",tags"));
                        assert!(lines[1].ends_with(",x;y"));
                        assert!(lines[2].ends_with(','));
                    }
                '''},
        },
    ))


    S.append(Slice(
        id="overtime", title="Weekly totals and overtime", d=2,
        pitch=("Payroll needs weekly totals and the overtime above the contract hours.",
               "We have to see which weeks went over the agreed hours."),
        reqs=("Weeks are numbered from 1: the week of a day is `(day - 1) / 7 + 1` (days 1 to 7 are week 1, 8 to 14 week 2, ...).",
              "`ledger.weekly_minutes() -> Vec<(u32, u32)>` returns `(week, minutes)` pairs ordered by week, only for weeks that have entries.",
              "`ledger.overtime(threshold: u32) -> Vec<(u32, u32)>` returns `(week, minutes - threshold)` for each week whose total is strictly greater than `threshold`, ordered by week."),
        code={
            "src/ledger.rs::imports": "use std::collections::BTreeMap;",
            "src/ledger.rs::methods": '''
                pub fn weekly_minutes(&self) -> Vec<(u32, u32)> {
                    let mut weeks: BTreeMap<u32, u32> = BTreeMap::new();
                    for e in &self.entries {
                        *weeks.entry((e.day - 1) / 7 + 1).or_insert(0) += e.minutes;
                    }
                    weeks.into_iter().collect()
                }

                pub fn overtime(&self, threshold: u32) -> Vec<(u32, u32)> {
                    self.weekly_minutes()
                        .into_iter()
                        .filter(|&(_, m)| m > threshold)
                        .map(|(w, m)| (w, m - threshold))
                        .collect()
                }
            ''',
        },
        readme=dd('''
            ## Weekly totals and overtime

            Week of a day: `(day - 1) / 7 + 1`. `weekly_minutes()` lists `(week, minutes)` for weeks with entries;
            `overtime(threshold)` lists `(week, minutes - threshold)` for weeks strictly above the threshold.
        '''),
        vtests='''
            #[test]
            fn weekly_minutes_basic() {
                assert_eq!(ledger().weekly_minutes()[0], (1, 260));
            }
        ''',
        tests='''
            #[test]
            fn weekly_totals_and_overtime() {
                let l = ledger();
                assert_eq!(l.weekly_minutes(), vec![(1, 260), (2, 630)]);
                assert_eq!(l.overtime(300), vec![(2, 330)]);
                assert_eq!(l.overtime(260), vec![(2, 370)]);
                assert_eq!(l.overtime(0), vec![(1, 260), (2, 630)]);
                assert!(l.overtime(630).is_empty());
                assert!(Ledger::new().weekly_minutes().is_empty());
            }

            #[test]
            fn week_boundaries() {
                let mut l = Ledger::new();
                l.log(7, "a", 10, "").unwrap();
                l.log(8, "a", 20, "").unwrap();
                l.log(366, "a", 40, "").unwrap();
                l.log(15, "a", 5, "").unwrap();
                assert_eq!(l.weekly_minutes(), vec![(1, 10), (2, 20), (3, 5), (53, 40)]);
            }
        ''',
    ))

    S.append(Slice(
        id="tags", title="Entry tags", d=3,
        pitch=("People want to mark entries as `billable`, `internal`, `travel` and so on.",
               "We need to slice time by labels that cut across projects."),
        reqs=("`Entry` gets a public field `tags: Vec<String>`; entries made with `log` have no tags.",
              "`ledger.log_tagged(day, project, minutes, note, tags: &[&str]) -> Result<u32, LedgerError>` is `log` plus tags, with exactly the same checks and ids. The stored tags are trimmed and lower-cased; empty tags are dropped and duplicates removed, keeping the first occurrence's position.",
              "`ledger.with_tag(tag: &str) -> Vec<&Entry>` returns the entries that have the tag (tag trimmed and lower-cased before comparing), in id order."),
        code={
            "src/entry.rs::entry_fields": "pub tags: Vec<String>,",
            "src/ledger.rs::entry_init": "tags: Vec::new(),",
            "src/ledger.rs::methods": '''
                pub fn log_tagged(&mut self, day: u32, project: &str, minutes: u32, note: &str, tags: &[&str]) -> Result<u32, LedgerError> {
                    let id = self.log(day, project, minutes, note)?;
                    let mut clean: Vec<String> = Vec::new();
                    for t in tags {
                        let t = t.trim().to_lowercase();
                        if !t.is_empty() && !clean.contains(&t) {
                            clean.push(t);
                        }
                    }
                    if let Some(e) = self.entries.last_mut() {
                        e.tags = clean;
                    }
                    Ok(id)
                }

                pub fn with_tag(&self, tag: &str) -> Vec<&Entry> {
                    let want = tag.trim().to_lowercase();
                    self.entries.iter().filter(|e| e.tags.contains(&want)).collect()
                }
            ''',
        },
        readme=dd('''
            ## Tags

            `Entry::tags` (empty for `log`), `log_tagged(day, project, minutes, note, &[tags])` (trimmed, lower-cased, deduplicated,
            empties dropped) and `with_tag(tag)` (case-insensitive, id order).
        '''),
        vtests='''
            #[test]
            fn tags_default_empty() {
                assert!(ledger().entries()[0].tags.is_empty());
            }
        ''',
        tests='''
            #[test]
            fn tags_are_normalised() {
                let mut l = ledger();
                let id = l.log_tagged(10, "atlas", 15, "x", &[" Urgent ", "billing", "urgent", "", "  "]).unwrap();
                assert_eq!(id, 6);
                assert_eq!(l.entries()[5].tags, vec!["urgent".to_string(), "billing".to_string()]);
                assert!(l.entries()[0].tags.is_empty());
                let again = l.log_tagged(11, "b", 5, "", &["Billing"]).unwrap();
                assert_eq!(again, 7);
            }

            #[test]
            fn with_tag_finds_entries() {
                let mut l = Ledger::new();
                l.log_tagged(1, "a", 5, "", &["x", "y"]).unwrap();
                l.log(2, "a", 5, "").unwrap();
                l.log_tagged(3, "a", 5, "", &["Y"]).unwrap();
                let found: Vec<u32> = l.with_tag(" y ").iter().map(|e| e.id).collect();
                assert_eq!(found, vec![1, 3]);
                assert_eq!(l.with_tag("X").len(), 1);
                assert!(l.with_tag("z").is_empty());
                assert!(l.with_tag("").is_empty());
            }

            #[test]
            fn log_tagged_validates_like_log() {
                let mut l = Ledger::new();
                assert_eq!(l.log_tagged(1, "a", 0, "", &["x"]), Err(LedgerError::ZeroMinutes));
                assert_eq!(l.log_tagged(0, "a", 5, "", &["x"]), Err(LedgerError::BadDay(0)));
                assert!(l.entries().is_empty());
                assert_eq!(l.log(1, "a", 5, ""), Ok(1));
            }
        ''',
    ))

    S.append(Slice(
        id="lock", title="Closing periods", d=3,
        pitch=("Once payroll has run, nobody may change the days it covered.",
               "After month-end close the old days must become read-only."),
        reqs=("`ledger.lock_through(day) -> Result<(), LedgerError>` locks every day up to and including `day` (`BadDay(day)` outside 1..=366). A lock never moves backwards: locking an earlier day than the current lock does nothing (and is not an error). `ledger.locked_through() -> u32` is the last locked day, 0 when nothing is locked.",
              "`log` for a locked day fails with the new error `LedgerError::Locked(day)`; this check comes right after the `ZeroMinutes` and `BadDay` checks and before any other validation. `remove` of an entry whose day is locked fails with `Locked(day)` too. Failed calls change nothing. `Display` reads `day D is locked`."),
        code={
            "src/ledger.rs::error_variants": "Locked(u32),",
            "src/ledger.rs::error_display": 'LedgerError::Locked(d) => write!(f, "day {} is locked", d),',
            "src/ledger.rs::ledger_fields": "locked: u32,",
            "src/ledger.rs::ledger_init": "locked: 0,",
            "src/ledger.rs::log_checks": '''
                if day <= self.locked {
                    return Err(LedgerError::Locked(day));
                }
            ''',
            "src/ledger.rs::remove_checks": '''
                let day = self.entries[pos].day;
                if day <= self.locked {
                    return Err(LedgerError::Locked(day));
                }
            ''',
            "src/ledger.rs::methods": '''
                pub fn lock_through(&mut self, day: u32) -> Result<(), LedgerError> {
                    if !(1..=366).contains(&day) {
                        return Err(LedgerError::BadDay(day));
                    }
                    if day > self.locked {
                        self.locked = day;
                    }
                    Ok(())
                }

                pub fn locked_through(&self) -> u32 {
                    self.locked
                }
            ''',
        },
        readme=dd('''
            ## Closing periods

            `lock_through(day)` makes days up to `day` read-only (never moves backwards); `locked_through()` reports it. `log`
            and `remove` on a locked day fail with `LedgerError::Locked(day)`.
        '''),
        vtests='''
            #[test]
            fn lock_basic() {
                let mut l = ledger();
                l.lock_through(2).unwrap();
                assert_eq!(l.locked_through(), 2);
            }
        ''',
        tests='''
            #[test]
            fn locked_days_are_read_only() {
                let mut l = ledger();
                assert_eq!(l.locked_through(), 0);
                l.lock_through(3).unwrap();
                assert_eq!(l.log(3, "x", 5, ""), Err(LedgerError::Locked(3)));
                assert_eq!(l.log(1, "x", 5, ""), Err(LedgerError::Locked(1)));
                assert_eq!(l.remove(1), Err(LedgerError::Locked(1)));
                assert_eq!(l.remove(3), Err(LedgerError::Locked(3)));
                assert_eq!(l.entries().len(), 5);
                assert_eq!(l.log(4, "x", 5, ""), Ok(6));
                assert_eq!(l.remove(4).unwrap().day, 8);
                assert_eq!(l.remove(77), Err(LedgerError::NotFound(77)));
            }

            #[test]
            fn lock_moves_forward_only() {
                let mut l = Ledger::new();
                l.lock_through(10).unwrap();
                l.lock_through(4).unwrap();
                assert_eq!(l.locked_through(), 10);
                l.lock_through(10).unwrap();
                l.lock_through(30).unwrap();
                assert_eq!(l.locked_through(), 30);
                assert_eq!(l.lock_through(0), Err(LedgerError::BadDay(0)));
                assert_eq!(l.lock_through(367), Err(LedgerError::BadDay(367)));
                assert_eq!(l.locked_through(), 30);
            }

            #[test]
            fn lock_check_order_and_display() {
                let mut l = Ledger::new();
                l.lock_through(5).unwrap();
                assert_eq!(l.log(2, "a", 0, ""), Err(LedgerError::ZeroMinutes));
                assert_eq!(l.log(400, "a", 5, ""), Err(LedgerError::BadDay(400)));
                assert_eq!(l.log(2, "a", 5, "").unwrap_err().to_string(), "day 2 is locked");
            }
        ''',
    ))

    S.append(Slice(
        id="undo", title="Undo and redo", d=4,
        pitch=("A mistyped entry or a wrong delete should not need manual repair in the data file.",
               "People fat-finger the ledger all the time; they want an undo button."),
        reqs=("`ledger.undo() -> Result<(), LedgerError>` reverts the most recent successful `log` or `remove`: the entries and the id counter go back to exactly what they were before that call (so the next `log` hands out the id again). `ledger.redo()` re-applies the most recently undone change. `ledger.can_undo()` and `ledger.can_redo()` tell whether they would succeed.",
              "Only successful calls of `log` and `remove` count as changes (failed ones leave the history alone). A new change clears everything that could be redone. Undo and redo are not changes themselves. Settings that are not entries (for example a rounding step) are not part of the history.",
              "With nothing to undo, `undo` returns the new error `LedgerError::NothingToUndo`; with nothing to redo, `redo` returns `LedgerError::NothingToRedo`. `Display` reads `nothing to undo` / `nothing to redo`.",
              "Several steps can be undone in a row, back to the empty ledger, and redone again."),
        code={
            "src/ledger.rs::error_variants": "NothingToUndo,\nNothingToRedo,",
            "src/ledger.rs::error_display": 'LedgerError::NothingToUndo => write!(f, "nothing to undo"),\nLedgerError::NothingToRedo => write!(f, "nothing to redo"),',
            "src/ledger.rs::types": "type Snapshot = (Vec<Entry>, u32);",
            "src/ledger.rs::ledger_fields": "undo_stack: Vec<Snapshot>,\nredo_stack: Vec<Snapshot>,",
            "src/ledger.rs::ledger_init": "undo_stack: Vec::new(),\nredo_stack: Vec::new(),",
            "src/ledger.rs::log_pre": "self.checkpoint();",
            "src/ledger.rs::remove_pre": "self.checkpoint();",
            "src/ledger.rs::methods": '''
                fn checkpoint(&mut self) {
                    self.undo_stack.push((self.entries.clone(), self.next_id));
                    self.redo_stack.clear();
                }

                pub fn can_undo(&self) -> bool {
                    !self.undo_stack.is_empty()
                }

                pub fn can_redo(&self) -> bool {
                    !self.redo_stack.is_empty()
                }

                pub fn undo(&mut self) -> Result<(), LedgerError> {
                    let (entries, next_id) = match self.undo_stack.last() {
                        Some(s) => s.clone(),
                        None => return Err(LedgerError::NothingToUndo),
                    };
                    @@slot undo_check
                    self.undo_stack.pop();
                    let now = (std::mem::replace(&mut self.entries, entries), std::mem::replace(&mut self.next_id, next_id));
                    self.redo_stack.push(now);
                    Ok(())
                }

                pub fn redo(&mut self) -> Result<(), LedgerError> {
                    let (entries, next_id) = match self.redo_stack.last() {
                        Some(s) => s.clone(),
                        None => return Err(LedgerError::NothingToRedo),
                    };
                    @@slot redo_check
                    self.redo_stack.pop();
                    let now = (std::mem::replace(&mut self.entries, entries), std::mem::replace(&mut self.next_id, next_id));
                    self.undo_stack.push(now);
                    Ok(())
                }
            ''',
        },
        readme=dd('''
            ## Undo and redo

            `undo()` reverts the last successful `log`/`remove` (entries and id counter), `redo()` re-applies it; `can_undo()` /
            `can_redo()`. New changes clear the redo history; failed calls are not recorded. Errors: `NothingToUndo`,
            `NothingToRedo`.
        '''),
        vtests='''
            #[test]
            fn undo_basic() {
                let mut l = ledger();
                assert!(l.can_undo());
                l.undo().unwrap();
                assert_eq!(l.entries().len(), 4);
            }
        ''',
        tests='''
            #[test]
            fn undo_and_redo_log() {
                let mut l = Ledger::new();
                assert!(!l.can_undo() && !l.can_redo());
                assert_eq!(l.undo(), Err(LedgerError::NothingToUndo));
                l.log(1, "a", 10, "").unwrap();
                l.log(2, "b", 20, "").unwrap();
                assert!(l.can_undo() && !l.can_redo());
                l.undo().unwrap();
                assert_eq!(ids(&l), vec![1]);
                assert!(l.can_redo());
                l.redo().unwrap();
                assert_eq!(ids(&l), vec![1, 2]);
                assert_eq!(l.redo(), Err(LedgerError::NothingToRedo));
                l.undo().unwrap();
                assert_eq!(l.log(3, "c", 30, ""), Ok(2));
                assert!(!l.can_redo());
                assert_eq!(l.redo(), Err(LedgerError::NothingToRedo));
                assert_eq!(l.entries()[1].project, "c");
            }

            #[test]
            fn undo_remove_restores_position_and_ids() {
                let mut l = ledger();
                l.remove(2).unwrap();
                l.remove(4).unwrap();
                assert_eq!(ids(&l), vec![1, 3, 5]);
                l.undo().unwrap();
                assert_eq!(ids(&l), vec![1, 3, 4, 5]);
                l.undo().unwrap();
                assert_eq!(ids(&l), vec![1, 2, 3, 4, 5]);
                assert_eq!(l.entries()[1].project, "Birch");
                assert_eq!(l.log(2, "z", 5, ""), Ok(6));
                l.undo().unwrap();
                assert_eq!(l.log(2, "z", 5, ""), Ok(6));
            }

            #[test]
            fn undo_all_the_way_and_back() {
                let mut l = ledger();
                for _ in 0..5 {
                    l.undo().unwrap();
                }
                assert!(l.entries().is_empty());
                assert!(!l.can_undo());
                assert_eq!(l.undo(), Err(LedgerError::NothingToUndo));
                for _ in 0..5 {
                    l.redo().unwrap();
                }
                assert_eq!(ids(&l), vec![1, 2, 3, 4, 5]);
                assert_eq!(l.total_minutes(), 890);
                assert_eq!(LedgerError::NothingToUndo.to_string(), "nothing to undo");
                assert_eq!(LedgerError::NothingToRedo.to_string(), "nothing to redo");
            }

            #[test]
            fn failed_calls_are_not_history() {
                let mut l = Ledger::new();
                l.log(1, "a", 10, "").unwrap();
                assert!(l.log(0, "b", 10, "").is_err());
                assert!(l.log(2, "b", 0, "").is_err());
                assert!(l.remove(99).is_err());
                l.undo().unwrap();
                assert!(l.entries().is_empty());
                assert!(!l.can_undo());
                assert!(l.can_redo());
                assert!(l.remove(1).is_err());
                assert!(l.can_redo());
            }
        ''',
        cross={
            "lock": {
                "reqs": ("`undo` and `redo` fail with `LedgerError::Locked(day)` when they would add or remove an entry on a locked day (the earliest such day is reported); nothing changes and the history stays as it was.",),
                "code": {
                    "src/ledger.rs::undo_check": '''
                        if let Some(day) = self.touches_locked(&entries) {
                            return Err(LedgerError::Locked(day));
                        }
                    ''',
                    "src/ledger.rs::redo_check": '''
                        if let Some(day) = self.touches_locked(&entries) {
                            return Err(LedgerError::Locked(day));
                        }
                    ''',
                    "src/ledger.rs::methods": '''
                        fn touches_locked(&self, other: &[Entry]) -> Option<u32> {
                            let mut days: Vec<u32> = Vec::new();
                            for e in &self.entries {
                                if !other.iter().any(|o| o.id == e.id) {
                                    days.push(e.day);
                                }
                            }
                            for o in other {
                                if !self.entries.iter().any(|e| e.id == o.id) {
                                    days.push(o.day);
                                }
                            }
                            days.into_iter().filter(|d| *d <= self.locked).min()
                        }
                    ''',
                },
                "tests": '''
                    #[test]
                    fn undo_and_redo_respect_locks() {
                        let mut l = Ledger::new();
                        l.log(1, "a", 10, "").unwrap();
                        l.log(5, "b", 10, "").unwrap();
                        l.lock_through(5).unwrap();
                        assert_eq!(l.undo(), Err(LedgerError::Locked(5)));
                        assert_eq!(l.entries().len(), 2);
                        assert!(l.can_undo());
                        let mut m = Ledger::new();
                        m.log(2, "a", 10, "").unwrap();
                        m.log(9, "b", 10, "").unwrap();
                        m.lock_through(3).unwrap();
                        m.undo().unwrap();
                        assert_eq!(m.entries().len(), 1);
                        m.lock_through(9).unwrap();
                        assert_eq!(m.redo(), Err(LedgerError::Locked(9)));
                        assert!(m.can_redo());
                        assert_eq!(m.entries().len(), 1);
                    }
                '''},
        },
    ))

    order = ["project-filter", "lock", "day-cap", "rounding", "csv-export", "overtime", "tags", "undo"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="timesheet", lang="rust", title="the hour-tracking library", role="the office manager", key="TIME",
    base={
        "README.md": README + "\n@@blocks features\n",
        "Cargo.toml": langs.cargo_toml("timesheet"),
        "src/lib.rs": LIB,
        "src/entry.rs": ENTRY,
        "src/ledger.rs": LEDGER,
        "src/report.rs": REPORT,
        ".gitignore": langs.GITIGNORE["rust"],
    },
    visible={"tests/basic.rs": VISIBLE},
    hidden={"tests/features.rs": HIDDEN},
)

register_app("feature-rs-timesheet", APP, make_slices, n=16, summary="hours ledger: filters, caps, rounding, CSV, overtime, tags, locks, undo")
