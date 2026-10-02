"""Rust libraries for the testing families: fuel log, rail fares."""
from __future__ import annotations

from fx import dd, langs

from ._engine import TLib

def where_rs(crate: str) -> str:
    return (f"Put your tests in `tests/` as integration tests (for example `tests/{crate}_tests.rs`, using the crate `{crate}` by its name); only the standard library "
            "and `cargo test --offline` are available. Do not rely on private items.")

# ---------------------------------------------------------------------------------------------------------------------
# fuel log
# ---------------------------------------------------------------------------------------------------------------------

FUEL_README = dd('''
    # vanlog

    Fuel log helpers for a small van fleet. A log line is `YYYY-MM-DD ODOMETER_KM LITRES FLAG`, for example `2025-03-02 120450 41.5 full`.

    ## `parse_line(line: &str) -> Result<Fill, ParseError>`
    Exactly four whitespace separated fields, otherwise `ParseError::Fields`.
    * the date is a real calendar date (leap years count; years 2000..=2099) or `ParseError::Date`;
    * the odometer is an unsigned integer of kilometres, or `ParseError::Odometer`;
    * the litres are a decimal number with at most one digit after the point (`40`, `40.0`, `41.5`), above 0 and at most 200.0, or `ParseError::Litres`;
    * the flag is `full` or `part` in any capitalisation, or `ParseError::Flag`.
    The checks run in the order date, odometer, litres, flag; the first failing check decides the error.
    A `Fill` has the public fields `year: u16, month: u8, day: u8, odo: u32, litres_x10: u32` (litres in tenths) and `full: bool`.

    ## `consumption(fills: &[Fill]) -> Result<Vec<Segment>, ConsumptionError>`
    The fills are in time order. A *segment* runs from one full fill to the next full fill: its litres are those of every fill **after** the first full one up to and
    including the second full one (part fills in between count, the first full fill does not), its distance is the odometer difference.
    `Segment { from_odo, to_odo, km, litres_x10, l100_x10 }` where `l100_x10` is the consumption in litres per 100 km times 10, i.e. `litres_x10 * 100 / km`
    rounded half up to an integer. Fills before the first full fill and after the last full fill belong to no segment. If an odometer reading is lower than
    the one before it (anywhere in the list) the result is `Err(ConsumptionError::OdometerWentBack { index })` with the index in `fills` of the offending fill; equal
    readings are allowed, but a segment with 0 km is `Err(ConsumptionError::ZeroDistance { index })` with the index of its closing full fill.

    ## `worst_segment(segments: &[Segment]) -> Option<&Segment>`
    The segment with the highest `l100_x10`; on a tie the earlier one. `None` for an empty slice.

    ## `total_litres_x10(fills: &[Fill]) -> u32`
    All litres of the list, in tenths.
''')

FUEL_SRC = dd('''
    //! Fuel log helpers for a small van fleet.

    #[derive(Debug, Clone, PartialEq)]
    pub struct Fill {
        pub year: u16,
        pub month: u8,
        pub day: u8,
        pub odo: u32,
        pub litres_x10: u32,
        pub full: bool,
    }

    #[derive(Debug, Clone, PartialEq)]
    pub struct Segment {
        pub from_odo: u32,
        pub to_odo: u32,
        pub km: u32,
        pub litres_x10: u32,
        pub l100_x10: u32,
    }

    #[derive(Debug, PartialEq)]
    pub enum ParseError {
        Fields,
        Date,
        Odometer,
        Litres,
        Flag,
    }

    #[derive(Debug, PartialEq)]
    pub enum ConsumptionError {
        OdometerWentBack { index: usize },
        ZeroDistance { index: usize },
    }

    fn is_leap(y: u16) -> bool {
        (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
    }

    fn days_in(y: u16, m: u8) -> u8 {
        match m {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            _ => {
                if is_leap(y) {
                    29
                } else {
                    28
                }
            }
        }
    }

    fn parse_date(s: &str) -> Option<(u16, u8, u8)> {
        let parts: Vec<&str> = s.split('-').collect();
        if parts.len() != 3 || parts[0].len() != 4 || parts[1].len() != 2 || parts[2].len() != 2 {
            return None;
        }
        let y: u16 = parts[0].parse().ok()?;
        let m: u8 = parts[1].parse().ok()?;
        let d: u8 = parts[2].parse().ok()?;
        if !(2000..=2099).contains(&y) || !(1..=12).contains(&m) || d < 1 || d > days_in(y, m) {
            return None;
        }
        Some((y, m, d))
    }

    fn parse_litres(s: &str) -> Option<u32> {
        let (whole, frac) = match s.split_once('.') {
            Some((w, f)) => (w, f),
            None => (s, "0"),
        };
        if whole.is_empty() || frac.len() != 1 || !whole.chars().all(|c| c.is_ascii_digit()) || !frac.chars().all(|c| c.is_ascii_digit()) {
            return None;
        }
        let tenths = whole.parse::<u32>().ok()? * 10 + frac.parse::<u32>().ok()?;
        if tenths == 0 || tenths > 2000 {
            return None;
        }
        Some(tenths)
    }

    /// Parses one log line.
    pub fn parse_line(line: &str) -> Result<Fill, ParseError> {
        let f: Vec<&str> = line.split_whitespace().collect();
        if f.len() != 4 {
            return Err(ParseError::Fields);
        }
        let (year, month, day) = parse_date(f[0]).ok_or(ParseError::Date)?;
        let odo: u32 = f[1].parse().map_err(|_| ParseError::Odometer)?;
        let litres_x10 = parse_litres(f[2]).ok_or(ParseError::Litres)?;
        let full = match f[3].to_ascii_lowercase().as_str() {
            "full" => true,
            "part" => false,
            _ => return Err(ParseError::Flag),
        };
        Ok(Fill { year, month, day, odo, litres_x10, full })
    }

    /// Consumption figures between consecutive full fills.
    pub fn consumption(fills: &[Fill]) -> Result<Vec<Segment>, ConsumptionError> {
        for i in 1..fills.len() {
            if fills[i].odo < fills[i - 1].odo {
                return Err(ConsumptionError::OdometerWentBack { index: i });
            }
        }
        let mut out = Vec::new();
        let mut last_full: Option<usize> = None;
        let mut litres = 0u32;
        for (i, f) in fills.iter().enumerate() {
            if let Some(start) = last_full {
                litres += f.litres_x10;
                if f.full {
                    let km = f.odo - fills[start].odo;
                    if km == 0 {
                        return Err(ConsumptionError::ZeroDistance { index: i });
                    }
                    let l100 = (litres as u64 * 100 * 2 + km as u64) / (2 * km as u64);
                    out.push(Segment { from_odo: fills[start].odo, to_odo: f.odo, km, litres_x10: litres, l100_x10: l100 as u32 });
                    last_full = Some(i);
                    litres = 0;
                }
            } else if f.full {
                last_full = Some(i);
            }
        }
        Ok(out)
    }

    /// The thirstiest segment (the first one on a tie).
    pub fn worst_segment(segments: &[Segment]) -> Option<&Segment> {
        let mut best: Option<&Segment> = None;
        for s in segments {
            if best.map_or(true, |b| s.l100_x10 > b.l100_x10) {
                best = Some(s);
            }
        }
        best
    }

    /// All litres in tenths.
    pub fn total_litres_x10(fills: &[Fill]) -> u32 {
        fills.iter().map(|f| f.litres_x10).sum()
    }
''')

FUEL_TEST = dd('''
    use vanlog::fuel::*;

    fn fill(odo: u32, litres_x10: u32, full: bool) -> Fill {
        Fill { year: 2025, month: 3, day: 1, odo, litres_x10, full }
    }

    #[test]
    fn parses_a_good_line() {
        let f = parse_line("2025-03-02 120450 41.5 full").unwrap();
        assert_eq!(f, Fill { year: 2025, month: 3, day: 2, odo: 120450, litres_x10: 415, full: true });
        let g = parse_line("  2000-02-29   0   40   PART ").unwrap();
        assert_eq!(g, Fill { year: 2000, month: 2, day: 29, odo: 0, litres_x10: 400, full: false });
        assert_eq!(parse_line("2099-12-31 7 0.1 Full").unwrap().litres_x10, 1);
        assert_eq!(parse_line("2025-01-01 7 200.0 full").unwrap().litres_x10, 2000);
        assert_eq!(parse_line("2025-01-01 7 40.0 full").unwrap().litres_x10, 400);
        assert_eq!(parse_line("2025-01-01 4294967295 5 part").unwrap().odo, 4294967295);
    }

    #[test]
    fn field_count_is_checked_first() {
        for l in ["", "2025-03-02 1 2.0", "2025-03-02 1 2.0 full extra", "x y"] {
            assert_eq!(parse_line(l), Err(ParseError::Fields), "{l:?}");
        }
        assert_eq!(parse_line("nonsense 1 2.0 full"), Err(ParseError::Date));
    }

    #[test]
    fn dates_are_real_dates() {
        for l in ["2025-02-29 1 2.0 full", "2025-13-01 1 2.0 full", "2025-00-10 1 2.0 full", "2025-04-31 1 2.0 full", "2025-01-00 1 2.0 full", "2025-01-32 1 2.0 full",
                  "1999-12-31 1 2.0 full", "2100-01-01 1 2.0 full", "2025-3-02 1 2.0 full", "25-03-02 1 2.0 full", "2025/03/02 1 2.0 full", "2100-02-29 1 2.0 full", "2025-06-31 1 2.0 full"] {
            assert_eq!(parse_line(l), Err(ParseError::Date), "{l:?}");
        }
        for l in ["2024-02-29 1 2.0 full", "2000-02-29 1 2.0 full", "2025-01-31 1 2.0 full", "2025-04-30 1 2.0 full", "2025-12-31 1 2.0 full", "2000-01-01 1 2.0 full", "2099-12-31 1 2.0 full"] {
            assert!(parse_line(l).is_ok(), "{l:?}");
        }
    }

    #[test]
    fn odometer_litres_and_flag_errors() {
        assert_eq!(parse_line("2025-01-01 -5 2.0 full"), Err(ParseError::Odometer));
        assert_eq!(parse_line("2025-01-01 12.5 2.0 full"), Err(ParseError::Odometer));
        assert_eq!(parse_line("2025-01-01 abc 2.0 full"), Err(ParseError::Odometer));
        assert_eq!(parse_line("2025-01-01 4294967296 2.0 full"), Err(ParseError::Odometer));
        for l in ["2025-01-01 5 0 full", "2025-01-01 5 0.0 full", "2025-01-01 5 200.1 full", "2025-01-01 5 201 full", "2025-01-01 5 41.55 full", "2025-01-01 5 .5 full", "2025-01-01 5 -3.0 full",
                  "2025-01-01 5 1e1 full", "2025-01-01 5 4. full", "2025-01-01 5 abc full", "2025-01-01 5 1,5 full", "2025-01-01 5 +3.0 full"] {
            assert_eq!(parse_line(l), Err(ParseError::Litres), "{l:?}");
        }
        for l in ["2025-01-01 5 2.0 half", "2025-01-01 5 2.0 f", "2025-01-01 5 2.0 fulll", "2025-01-01 5 2.0 1"] {
            assert_eq!(parse_line(l), Err(ParseError::Flag), "{l:?}");
        }
    }

    #[test]
    fn first_failing_check_wins() {
        assert_eq!(parse_line("2025-02-30 abc 0 maybe"), Err(ParseError::Date));
        assert_eq!(parse_line("2025-02-20 abc 0 maybe"), Err(ParseError::Odometer));
        assert_eq!(parse_line("2025-02-20 10 0 maybe"), Err(ParseError::Litres));
    }

    #[test]
    fn simple_segment() {
        let fills = [fill(1000, 400, true), fill(1500, 300, true)];
        let s = consumption(&fills).unwrap();
        assert_eq!(s, vec![Segment { from_odo: 1000, to_odo: 1500, km: 500, litres_x10: 300, l100_x10: 60 }]);
    }

    #[test]
    fn part_fills_count_and_the_first_full_does_not() {
        let fills = [fill(100, 500, false), fill(1000, 400, true), fill(1200, 100, false), fill(1400, 150, false), fill(1500, 250, true), fill(1700, 90, false)];
        let s = consumption(&fills).unwrap();
        assert_eq!(s.len(), 1);
        assert_eq!(s[0].litres_x10, 500);
        assert_eq!(s[0].km, 500);
        assert_eq!((s[0].from_odo, s[0].to_odo), (1000, 1500));
        assert_eq!(s[0].l100_x10, 100);
    }

    #[test]
    fn several_segments_and_rounding() {
        let fills = [fill(0, 10, true), fill(300, 187, true), fill(900, 450, true), fill(901, 5, true)];
        let s = consumption(&fills).unwrap();
        assert_eq!(s.iter().map(|x| x.l100_x10).collect::<Vec<_>>(), vec![62, 75, 500]);
        assert_eq!(s.iter().map(|x| x.km).collect::<Vec<_>>(), vec![300, 600, 1]);
        // 187*100/300 = 62.33 -> 62 ; exact half: 5 litres over 8 km -> 62.5 -> 63
        let h = consumption(&[fill(0, 1, true), fill(8, 5, true)]).unwrap();
        assert_eq!(h[0].l100_x10, 63);
        let g = consumption(&[fill(0, 1, true), fill(3, 1, true)]).unwrap();
        assert_eq!(g[0].l100_x10, 33);
    }

    #[test]
    fn no_segments_without_two_full_fills() {
        assert_eq!(consumption(&[]).unwrap(), vec![]);
        assert_eq!(consumption(&[fill(10, 10, true)]).unwrap(), vec![]);
        assert_eq!(consumption(&[fill(10, 10, false), fill(20, 10, false)]).unwrap(), vec![]);
        assert_eq!(consumption(&[fill(10, 10, false), fill(20, 10, true), fill(30, 5, false)]).unwrap(), vec![]);
    }

    #[test]
    fn odometer_errors() {
        let back = [fill(100, 10, true), fill(90, 10, true)];
        assert_eq!(consumption(&back), Err(ConsumptionError::OdometerWentBack { index: 1 }));
        let back2 = [fill(100, 10, false), fill(200, 10, true), fill(300, 10, false), fill(250, 10, true)];
        assert_eq!(consumption(&back2), Err(ConsumptionError::OdometerWentBack { index: 3 }));
        let before_first = [fill(500, 10, false), fill(400, 10, false), fill(600, 10, true)];
        assert_eq!(consumption(&before_first), Err(ConsumptionError::OdometerWentBack { index: 1 }));
        let zero = [fill(100, 10, true), fill(100, 10, true)];
        assert_eq!(consumption(&zero), Err(ConsumptionError::ZeroDistance { index: 1 }));
        let zero2 = [fill(100, 10, true), fill(100, 10, false), fill(100, 10, true)];
        assert_eq!(consumption(&zero2), Err(ConsumptionError::ZeroDistance { index: 2 }));
        let ok_equal = [fill(100, 10, false), fill(100, 10, false), fill(100, 10, true), fill(150, 10, true)];
        assert_eq!(consumption(&ok_equal).unwrap().len(), 1);
    }

    #[test]
    fn worst_segment_picks_the_highest_first_on_ties() {
        let mk = |l: u32, odo: u32| Segment { from_odo: odo, to_odo: odo + 100, km: 100, litres_x10: l, l100_x10: l };
        assert_eq!(worst_segment(&[]), None);
        let a = [mk(50, 0), mk(80, 100), mk(80, 200), mk(60, 300)];
        assert_eq!(worst_segment(&a).unwrap().from_odo, 100);
        let b = [mk(70, 0)];
        assert_eq!(worst_segment(&b).unwrap().l100_x10, 70);
        let c = [mk(10, 0), mk(20, 100), mk(30, 200)];
        assert_eq!(worst_segment(&c).unwrap().l100_x10, 30);
    }

    #[test]
    fn totals() {
        assert_eq!(total_litres_x10(&[]), 0);
        assert_eq!(total_litres_x10(&[fill(1, 415, true), fill(2, 400, false), fill(3, 1, true)]), 816);
    }
''')

FUEL_STUB = dd('''
    use vanlog::fuel::*;

    #[test]
    fn smoke() {
        assert!(parse_line("2025-01-01 5 2.0 full").is_ok());
    }
''')


def fuel(rng) -> TLib:
    files = {"README.md": FUEL_README, "Cargo.toml": langs.cargo_toml("vanlog"), "src/lib.rs": "pub mod fuel;\n", "src/fuel.rs": FUEL_SRC}
    wrong = [
        ("tests/fuel_gold.rs", 'assert_eq!(parse_line("2025-02-30 abc 0 maybe"), Err(ParseError::Date));', 'assert_eq!(parse_line("2025-02-30 abc 0 maybe"), Err(ParseError::Odometer));'),
        ("tests/fuel_gold.rs", "assert_eq!(h[0].l100_x10, 63);", "assert_eq!(h[0].l100_x10, 62);"),
        ("tests/fuel_gold.rs", "assert_eq!(s[0].litres_x10, 500);", "assert_eq!(s[0].litres_x10, 900);"),
        ("tests/fuel_gold.rs", "assert_eq!(total_litres_x10(&[fill(1, 415, true), fill(2, 400, false), fill(3, 1, true)]), 816);", "assert_eq!(total_litres_x10(&[fill(1, 415, true), fill(2, 400, false), fill(3, 1, true)]), 815);"),
    ]
    return TLib(
        name="rs-vanlog", lang="rust", title="the van fleet fuel-log library", blurb="The fleet manager's tool parses fuel logs and reports consumption per tank.",
        files=files, stub={"tests/smoke.rs": FUEL_STUB}, gold={"tests/fuel_gold.rs": FUEL_TEST}, mutate=["src/fuel.rs"], cmd="cargo test --offline --quiet",
        where=where_rs("vanlog"), difficulty=4, wrong_edits=wrong, timeout=90, focus="the order of the parse checks, calendar edge cases, which fills belong to a segment, rounding, and the error indexes",
    )


# ---------------------------------------------------------------------------------------------------------------------
# rail fares
# ---------------------------------------------------------------------------------------------------------------------

RAIL_README = dd('''
    # railfare

    Fare rules of the Dunmore Valley Railway. Money is in pence (`u32`), times are minutes since midnight (`u16`, 0..=1439).

    ## `fare(base: u32, depart: u16, age: u8, card: Card) -> Result<u32, FareError>`
    The price of one single ticket.
    * `depart` above 1439 is `FareError::BadTime`; otherwise any `age` is allowed (0..=255).
    * Ages 0..=4 travel free: the result is `0`, whatever the time and card.
    * Ages 5..=15 pay 50% of the base fare. Everybody else pays 100%.
    * A `Card::Senior` (age 60 or over only; for a younger passenger the card is ignored) takes one third off: 66.67%, i.e. `base * 2 / 3`, rounded *down* to a whole penny, applied
      before everything below. A child never gets the card discount on top of the child discount: the child rate wins.
    * Peak departures (06:30 up to and including 09:29, and 16:00 up to and including 18:59) add 20% to the fare so far, rounded *down*. All other times are off-peak and unchanged.
    * The fare is then raised to the minimum fare of 150p if it is below it (but a free ticket stays free), and finally rounded **up** to the next multiple of 5p.

    ## `day_pass(base_fares: &[u32]) -> u32`
    The price of a day pass that replaces several single tickets: the sum of the three highest base fares (all of them if there are fewer than three), capped at 2500p;
    an empty list costs 0.

    ## `describe_band(depart: u16) -> &'static str`
    `"peak"` or `"off-peak"` for the departure time, with the peak hours above (`depart` above 1439 counts as `"off-peak"`).
''')

RAIL_SRC = dd('''
    //! Fare rules of the Dunmore Valley Railway.

    #[derive(Debug, Clone, Copy, PartialEq)]
    pub enum Card {
        None,
        Senior,
    }

    #[derive(Debug, PartialEq)]
    pub enum FareError {
        BadTime,
    }

    const MIN_FARE: u32 = 150;
    const DAY_CAP: u32 = 2500;

    fn is_peak(depart: u16) -> bool {
        (390..=569).contains(&depart) || (960..=1139).contains(&depart)
    }

    /// "peak" or "off-peak".
    pub fn describe_band(depart: u16) -> &'static str {
        if is_peak(depart) {
            "peak"
        } else {
            "off-peak"
        }
    }

    /// Price of a single ticket in pence.
    pub fn fare(base: u32, depart: u16, age: u8, card: Card) -> Result<u32, FareError> {
        if depart > 1439 {
            return Err(FareError::BadTime);
        }
        if age <= 4 {
            return Ok(0);
        }
        let mut f = base;
        if age <= 15 {
            f = base / 2;
        } else if card == Card::Senior && age >= 60 {
            f = base * 2 / 3;
        }
        if is_peak(depart) {
            f = f + f / 5;
        }
        if f < MIN_FARE {
            f = MIN_FARE;
        }
        Ok((f + 4) / 5 * 5)
    }

    /// Day pass price.
    pub fn day_pass(base_fares: &[u32]) -> u32 {
        let mut v = base_fares.to_vec();
        v.sort_unstable_by(|a, b| b.cmp(a));
        let sum: u32 = v.iter().take(3).sum();
        sum.min(DAY_CAP)
    }
''')

RAIL_TEST = dd('''
    use railfare::*;

    const OFF: u16 = 600; // 10:00, off-peak
    const PEAK: u16 = 480; // 08:00, peak

    fn f(base: u32, t: u16, age: u8, card: Card) -> u32 {
        fare(base, t, age, card).unwrap()
    }

    #[test]
    fn adults_pay_the_base_fare_rounded_up_to_five() {
        assert_eq!(f(1000, OFF, 30, Card::None), 1000);
        assert_eq!(f(1001, OFF, 30, Card::None), 1005);
        assert_eq!(f(1004, OFF, 30, Card::None), 1005);
        assert_eq!(f(1005, OFF, 30, Card::None), 1005);
        assert_eq!(f(1006, OFF, 30, Card::None), 1010);
        assert_eq!(f(16, OFF, 16, Card::None), 150);
        assert_eq!(f(15, OFF, 59, Card::None), 150);
    }

    #[test]
    fn minimum_fare_and_free_tickets() {
        assert_eq!(f(100, OFF, 30, Card::None), 150);
        assert_eq!(f(149, OFF, 30, Card::None), 150);
        assert_eq!(f(150, OFF, 30, Card::None), 150);
        assert_eq!(f(151, OFF, 30, Card::None), 155);
        assert_eq!(f(0, OFF, 30, Card::None), 150);
        assert_eq!(f(5000, OFF, 0, Card::None), 0);
        assert_eq!(f(5000, PEAK, 4, Card::Senior), 0);
        assert_eq!(f(5000, OFF, 5, Card::None), 2500);
    }

    #[test]
    fn child_rate() {
        assert_eq!(f(1000, OFF, 5, Card::None), 500);
        assert_eq!(f(1000, OFF, 15, Card::None), 500);
        assert_eq!(f(1000, OFF, 16, Card::None), 1000);
        assert_eq!(f(1001, OFF, 10, Card::None), 500);
        assert_eq!(f(1003, OFF, 10, Card::None), 505);
        assert_eq!(f(200, OFF, 10, Card::None), 150);
        assert_eq!(f(1000, OFF, 12, Card::Senior), 500);
    }

    #[test]
    fn senior_card() {
        assert_eq!(f(1200, OFF, 60, Card::Senior), 800);
        assert_eq!(f(1000, OFF, 60, Card::Senior), 670);
        assert_eq!(f(1001, OFF, 70, Card::Senior), 670);
        assert_eq!(f(1002, OFF, 70, Card::Senior), 670);
        assert_eq!(f(1000, OFF, 59, Card::Senior), 1000);
        assert_eq!(f(1000, OFF, 60, Card::None), 1000);
        assert_eq!(f(1000, OFF, 255, Card::Senior), 670);
        assert_eq!(f(300, OFF, 80, Card::Senior), 200);
        assert_eq!(f(200, OFF, 80, Card::Senior), 150);
    }

    #[test]
    fn peak_surcharge() {
        assert_eq!(f(1000, PEAK, 30, Card::None), 1200);
        assert_eq!(f(1004, PEAK, 30, Card::None), 1205);
        assert_eq!(f(1003, PEAK, 30, Card::None), 1205);
        assert_eq!(f(1000, PEAK, 10, Card::None), 600);
        assert_eq!(f(1000, PEAK, 60, Card::Senior), 800);
        assert_eq!(f(1001, PEAK, 60, Card::Senior), 800);
        assert_eq!(f(100, PEAK, 30, Card::None), 150);
        assert_eq!(f(120, PEAK, 30, Card::None), 150);
        assert_eq!(f(130, PEAK, 30, Card::None), 160);
        assert_eq!(f(135, PEAK, 30, Card::None), 165);
    }

    #[test]
    fn peak_boundaries() {
        for (t, band) in [(389, "off-peak"), (390, "peak"), (569, "peak"), (570, "off-peak"), (959, "off-peak"), (960, "peak"), (1139, "peak"), (1140, "off-peak"), (0, "off-peak"), (1439, "off-peak"), (1440, "off-peak"), (60000, "off-peak")] {
            assert_eq!(describe_band(t), band, "{t}");
        }
        assert_eq!(f(1000, 389, 30, Card::None), 1000);
        assert_eq!(f(1000, 390, 30, Card::None), 1200);
        assert_eq!(f(1000, 569, 30, Card::None), 1200);
        assert_eq!(f(1000, 570, 30, Card::None), 1000);
        assert_eq!(f(1000, 959, 30, Card::None), 1000);
        assert_eq!(f(1000, 960, 30, Card::None), 1200);
        assert_eq!(f(1000, 1139, 30, Card::None), 1200);
        assert_eq!(f(1000, 1140, 30, Card::None), 1000);
    }

    #[test]
    fn bad_times() {
        assert_eq!(fare(1000, 1440, 30, Card::None), Err(FareError::BadTime));
        assert_eq!(fare(1000, 1440, 2, Card::None), Err(FareError::BadTime));
        assert_eq!(fare(1000, u16::MAX, 30, Card::Senior), Err(FareError::BadTime));
        assert_eq!(fare(1000, 1439, 30, Card::None), Ok(1000));
        assert_eq!(fare(1000, 0, 30, Card::None), Ok(1000));
    }

    #[test]
    fn day_pass_rules() {
        assert_eq!(day_pass(&[]), 0);
        assert_eq!(day_pass(&[400]), 400);
        assert_eq!(day_pass(&[400, 900]), 1300);
        assert_eq!(day_pass(&[400, 900, 700]), 2000);
        assert_eq!(day_pass(&[100, 400, 900, 700, 300]), 2000);
        assert_eq!(day_pass(&[900, 900, 900]), 2500);
        assert_eq!(day_pass(&[1000, 1000, 500, 4000]), 2500);
        assert_eq!(day_pass(&[1000, 1000, 500]), 2500);
        assert_eq!(day_pass(&[1000, 1000, 499]), 2499);
        assert_eq!(day_pass(&[3000]), 2500);
    }
''')

RAIL_STUB = dd('''
    use railfare::*;

    #[test]
    fn smoke() {
        assert_eq!(describe_band(600), "off-peak");
    }
''')


def railfare(rng) -> TLib:
    files = {"README.md": RAIL_README, "Cargo.toml": langs.cargo_toml("railfare"), "src/lib.rs": RAIL_SRC}
    wrong = [
        ("tests/rail_gold.rs", "assert_eq!(f(1000, OFF, 60, Card::Senior), 670);", "assert_eq!(f(1000, OFF, 60, Card::Senior), 665);"),
        ("tests/rail_gold.rs", "assert_eq!(f(1000, PEAK, 30, Card::None), 1200);\n    assert_eq!(f(1004", "assert_eq!(f(1000, PEAK, 30, Card::None), 1100);\n    assert_eq!(f(1004"),
        ("tests/rail_gold.rs", "assert_eq!(day_pass(&[400, 900]), 1300);", "assert_eq!(day_pass(&[400, 900]), 1400);"),
        ("tests/rail_gold.rs", "(570, \"off-peak\")", "(570, \"peak\")"),
    ]
    return TLib(
        name="rs-railfare", lang="rust", title="the Dunmore Valley fare rules", blurb="The ticket machines price single tickets and day passes with the `railfare` crate.",
        files={**files}, stub={"tests/smoke.rs": RAIL_STUB}, gold={"tests/rail_gold.rs": RAIL_TEST}, mutate=["src/lib.rs"], cmd="cargo test --offline --quiet",
        where=where_rs("railfare"), difficulty=3, wrong_edits=wrong, timeout=90, focus="the order of the discounts, rounding down vs up, the peak boundaries, the minimum fare and the day-pass cap",
    )
