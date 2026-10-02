"""Scenarios (reproduction programs) for the rust slot modules of the review bank: ``cargo run --example scenario``."""
from __future__ import annotations

from fx import dd

_PRELUDE = '''
    use std::fmt::Debug;
    use std::panic::{self, AssertUnwindSafe};

    fn install_hook() {
        panic::set_hook(Box::new(|info| {
            let msg = if let Some(s) = info.payload().downcast_ref::<&str>() {
                s.to_string()
            } else if let Some(s) = info.payload().downcast_ref::<String>() {
                s.clone()
            } else {
                "?".to_string()
            };
            let loc = info.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
            println!("  panic at {}: {}", loc, msg);
        }));
    }

    fn show<T: Debug>(label: &str, f: impl FnOnce() -> T) {
        match panic::catch_unwind(AssertUnwindSafe(f)) {
            Ok(v) => println!("{}: {:?}", label, v),
            Err(_) => println!("{}: PANICKED", label),
        }
    }
'''

RINGLOG_SCENARIO = dd(_PRELUDE + '''
    use fieldlog::ringlog::{parse_dump, RingLog};

    fn main() {
        install_hook();
        show("RingLog::new(0)", || RingLog::new(0).tail(1).len());

        let mut log = RingLog::new(3);
        for l in ["boot", "net up", "sensor ok", "gps lock", "temp 21\\u{b0}C"] {
            log.push(l);
        }
        show("tail(2) after the ring wrapped", || log.tail(2));
        show("tail(3)", || log.tail(3));
        show("tail(10)", || log.tail(10));

        let ascii = "x".repeat(100);
        show("length of a stored 100 byte ascii line", || {
            let mut l = RingLog::new(2);
            l.push(&ascii);
            l.tail(1)[0].len()
        });
        let accents = format!("a{}", "\\u{e9}".repeat(50));
        show("length of a stored 101 byte line of accents", || {
            let mut l = RingLog::new(2);
            l.push(&accents);
            l.tail(1)[0].len()
        });

        let dump = log.dump();
        println!("dump: {:02x?}", dump);
        show("parse_dump(dump)", || parse_dump(&dump));
        show("parse_dump(truncated dump)", || parse_dump(&dump[..dump.len() - 3]));
        show("parse_dump(empty)", || parse_dump(&[]));
        show("parse_dump(one byte)", || parse_dump(&[7]));
        show("parse_dump(count 2, one line)", || parse_dump(&[0, 2, 1, b'a']));
        show("parse_dump(invalid utf-8)", || parse_dump(&[0, 1, 2, 0xff, 0xfe]));
        show("parse_dump(count 65535)", || parse_dump(&[0xff, 0xff]).map(|v| v.len()));
        show("parse_dump(count 4097)", || parse_dump(&[0x10, 0x01]).map(|v| v.len()));
    }
''')

QUANTITY_SCENARIO = dd(_PRELUDE + '''
    use pantry::quantity::*;

    fn main() {
        install_hook();
        for s in ["12.5", " 3 ", "0", "nan", "inf", "-1", "abc", "1e3"] {
            show(&format!("parse_number({:?})", s), || parse_number(s));
        }
        for s in ["12.5kg", "3 lb", "250 g", "2KG", "kg", "7", ""] {
            show(&format!("split_quantity({:?})", s), || split_quantity(s));
        }
        for (v, u) in [(1.9, "g"), (1.0, "lb"), (2.5, "oz"), (3.0, "kg"), (1e30, "kg"), (1.0, "stone")] {
            show(&format!("to_grams({}, {:?})", v, u), || to_grams(v, u));
        }
        show("sum_grams 1 kg + 250 g + 2 lb", || sum_grams(&["1 kg", "250 g", "2 lb"]));
        show("sum_grams with a unit but no number", || sum_grams(&["1 kg", "kg"]));
        show("sum_grams with a mixed-case unit", || sum_grams(&["2 KG", "1 Lb"]));
        show("sum_grams past u64", || sum_grams(&["18446744073709551615 g", "1 g"]));
        for g in [0u64, 250, 1000, 2000, 1250, 999_999] {
            show(&format!("format_grams({})", g), || format_grams(g));
        }
    }
''')

RATES_SCENARIO = dd(_PRELUDE + '''
    use parcelhub::rates::*;

    fn quote(carrier: &str, zone: &str, cents: u32) -> Quote {
        Quote { carrier: carrier.to_string(), zone: zone.to_string(), cents }
    }

    fn main() {
        install_hook();
        let bands = vec![Band { max_grams: 500, cents: 395 }, Band { max_grams: 2000, cents: 695 }, Band { max_grams: 10000, cents: 1495 }];
        for g in [0u32, 1, 500, 501, 2000, 10000, 10001] {
            show(&format!("price_for({} g)", g), || price_for(&bands, g));
        }

        let quotes = vec![
            quote("alpha", "north", 700),
            quote("bravo", "south", 650),
            quote("cobalt", "north", 650),
            quote("delta", "south", 900),
            quote("echo", "north", 650),
        ];
        show("cheapest", || cheapest(&quotes).map(|q| q.carrier.clone()));
        show("cheapest of nothing", || cheapest(&[]).map(|q| q.carrier.clone()));

        for (c, p) in [(1000u32, 15u32), (999, 15), (1005, 50), (1000, 150), (1, 100), (250, 0)] {
            show(&format!("discounted({}, {} %)", c, p), || discounted(c, p));
        }

        show("drop_suspended bravo + cobalt", || {
            let mut q = quotes.clone();
            drop_suspended(&mut q, &["bravo", "cobalt"]);
            q.iter().map(|x| x.carrier.clone()).collect::<Vec<_>>()
        });
        show("totals_by_zone", || totals_by_zone(&quotes));
    }
''')

SCENARIOS = {"rs-ringlog": RINGLOG_SCENARIO, "rs-quantities": QUANTITY_SCENARIO, "rs-ratesheet": RATES_SCENARIO}
