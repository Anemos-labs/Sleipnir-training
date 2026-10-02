"""A layered rust crate that plans hikes (waypoint parsing, pace rules, climb measurement, plan and summary).
Defects sit in different modules than the symptom the report names; two incident tickets combine causes."""
from fx import dd, langs, family
from generators.fix._hand_kit import Base, Bug, panic_excerpt, tasks_from

README = dd('''
    # trailplan

    A small Rust library that turns a list of waypoints into a hiking plan: legs between named stops with distance, climb
    and walking time, a one-line summary and arrival times. Modules: `geo`, `parse`, `pace`, `profile`, `plan`.

    ## Input (`parse::parse_waypoints`)

    One waypoint per line: `name; x; y; elevation`, all separated by semicolons. `x` and `y` are metres on a local grid,
    the elevation is in metres and may have decimals and be negative. A name of `-` is an unnamed *trackpoint* that only
    shapes the route; anything else is a named *stop*. Blank lines, lines starting with `#` and a UTF-8 byte order mark at
    the start of the text are ignored. Windows line endings are fine.

    Errors (`ParseError`): `Line { line, msg }` for a malformed line (`line` is the 1-based physical line number, comments
    and blank lines count); `TooFew` when there are fewer than two stops; `Unanchored` when the first or last waypoint is
    a trackpoint; `DuplicateStop(name)` when two stops have the same name ignoring case (the name as written in the later one).

    ## Walking time (`pace::leg_minutes(distance_m, ascent_m)`)

    12 minutes per km plus 10 minutes per 100 m of ascent. A leg whose ascent is steeper than 15% of its length
    (`ascent / distance > 0.15`, strictly) takes one and a half times the ascent time. The sum is rounded *up* to whole
    minutes, and a leg of *more than* 90 minutes gets a 10 minute break added on top.

    ## Climb (`profile::climb(elevations) -> (ascent, descent)`)

    GPS elevations are noisy, so a change only counts once it is 3 m or more away from the last *counted* elevation (the
    first elevation is the starting reference). When it counts, the whole difference is added to ascent or descent and
    that elevation becomes the new reference. Descent is reported as a positive number.

    ## Plan (`plan::build`, `Plan`)

    * A leg runs from one stop to the next; the trackpoints in between only add distance (horizontal, summed over
      consecutive points) and are part of the elevation series given to `climb` (stop elevation first and last).
    * `Plan::total_minutes()` is the sum of the legs' minutes; the other totals are sums over the legs too.
    * `Plan::summary()`: `"{n} leg(s), {km} km, +{ascent} m / -{descent} m, {h}h{mm}"`: `leg` for exactly one leg, `legs`
      otherwise. The kilometres are the *exact* total distance rounded once to one decimal, halves rounded up (12.25 km
      is `12.3`). Ascent and descent are rounded to whole metres, the duration is `{h}h{mm:02}`.
    * `Plan::arrivals("HH:MM")`: the stop names with the clock time of arrival, starting at the given time (24 hour
      clock, two digits each). After midnight the time wraps and gets a suffix: `00:10+1d`. A bad start time is an `Err`.
''')

GEO = dd('''
    /// A point on the local grid: metres east, metres north, elevation in metres.
    #[derive(Debug, Clone, PartialEq)]
    pub struct Point {
        pub x: f64,
        pub y: f64,
        pub elev: f64,
    }

    /// Horizontal distance in metres.
    pub fn dist(a: &Point, b: &Point) -> f64 {
        ((b.x - a.x).powi(2) + (b.y - a.y).powi(2)).sqrt()
    }
''')

PARSE = dd('''
    use crate::geo::Point;

    #[derive(Debug, Clone, PartialEq)]
    pub struct Waypoint {
        pub name: Option<String>,
        pub point: Point,
    }

    #[derive(Debug, Clone, PartialEq)]
    pub enum ParseError {
        Line { line: usize, msg: String },
        TooFew,
        Unanchored,
        DuplicateStop(String),
    }

    pub fn parse_waypoints(text: &str) -> Result<Vec<Waypoint>, ParseError> {
        let text = text.strip_prefix('\\u{feff}').unwrap_or(text);
        let mut out: Vec<Waypoint> = Vec::new();
        for (i, raw) in text.lines().enumerate() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let fields: Vec<&str> = line.split(';').map(|s| s.trim()).collect();
            let err = |msg: String| ParseError::Line { line: i + 1, msg };
            if fields.len() != 4 {
                return Err(err(format!("want 4 fields, got {}", fields.len())));
            }
            if fields[0].is_empty() {
                return Err(err("empty name".to_string()));
            }
            let num = |s: &str, what: &str| -> Result<f64, ParseError> {
                s.parse::<f64>()
                    .ok()
                    .filter(|v| v.is_finite())
                    .ok_or_else(|| err(format!("bad {} {:?}", what, s)))
            };
            let x = num(fields[1], "x")?;
            let y = num(fields[2], "y")?;
            let elev = num(fields[3], "elevation")?;
            let name = if fields[0] == "-" { None } else { Some(fields[0].to_string()) };
            out.push(Waypoint { name, point: Point { x, y, elev } });
        }
        let stops: Vec<&String> = out.iter().filter_map(|w| w.name.as_ref()).collect();
        if stops.len() < 2 {
            return Err(ParseError::TooFew);
        }
        if out.first().map_or(true, |w| w.name.is_none()) || out.last().map_or(true, |w| w.name.is_none()) {
            return Err(ParseError::Unanchored);
        }
        let mut seen: Vec<String> = Vec::new();
        for name in stops {
            let key = name.to_lowercase();
            if seen.contains(&key) {
                return Err(ParseError::DuplicateStop(name.clone()));
            }
            seen.push(key);
        }
        Ok(out)
    }
''')

PACE = dd('''
    /// Walking time of one leg in minutes (distance and ascent in metres).
    pub fn leg_minutes(distance_m: f64, ascent_m: f64) -> u32 {
        let mut climb = ascent_m / 10.0;
        if distance_m > 0.0 && ascent_m / distance_m > 0.15 {
            climb *= 1.5;
        }
        let minutes = (distance_m * 12.0 / 1000.0 + climb).ceil() as u32;
        if minutes > 90 {
            minutes + 10
        } else {
            minutes
        }
    }
''')

PROFILE = dd('''
    /// Changes smaller than this (metres) are treated as GPS noise.
    pub const DEAD_BAND_M: f64 = 3.0;

    /// Total ascent and descent (both positive) along a series of elevations.
    pub fn climb(elevations: &[f64]) -> (f64, f64) {
        let mut up = 0.0;
        let mut down = 0.0;
        let Some(&first) = elevations.first() else {
            return (0.0, 0.0);
        };
        let mut reference = first;
        for &e in &elevations[1..] {
            let d = e - reference;
            if d >= DEAD_BAND_M {
                up += d;
                reference = e;
            } else if d <= -DEAD_BAND_M {
                down -= d;
                reference = e;
            }
        }
        (up, down)
    }
''')

PLAN = dd('''
    use crate::geo::{dist, Point};
    use crate::pace::leg_minutes;
    use crate::parse::Waypoint;
    use crate::profile::climb;

    #[derive(Debug, Clone, PartialEq)]
    pub struct Leg {
        pub from: String,
        pub to: String,
        pub distance_m: f64,
        pub ascent_m: f64,
        pub descent_m: f64,
        pub minutes: u32,
    }

    #[derive(Debug, Clone, PartialEq)]
    pub struct Plan {
        pub legs: Vec<Leg>,
    }

    /// Build the plan: one leg from each stop to the next.
    pub fn build(points: &[Waypoint]) -> Plan {
        let mut legs = Vec::new();
        let mut from: Option<&Waypoint> = None;
        let mut run_m = 0.0;
        let mut elevs: Vec<f64> = Vec::new();
        let mut prev: Option<&Point> = None;
        for w in points {
            if let Some(p) = prev {
                run_m += dist(p, &w.point);
            }
            prev = Some(&w.point);
            elevs.push(w.point.elev);
            if let Some(name) = &w.name {
                if let Some(f) = from {
                    let (up, down) = climb(&elevs);
                    legs.push(Leg {
                        from: f.name.clone().unwrap_or_default(),
                        to: name.clone(),
                        distance_m: run_m,
                        ascent_m: up,
                        descent_m: down,
                        minutes: leg_minutes(run_m, up),
                    });
                }
                from = Some(w);
                run_m = 0.0;
                elevs.clear();
                elevs.push(w.point.elev);
            }
        }
        Plan { legs }
    }

    /// Kilometres with one decimal, halves rounded up.
    pub fn fmt_km(metres: f64) -> String {
        let tenths = (metres / 100.0).round() as i64;
        format!("{}.{}", tenths / 10, tenths % 10)
    }

    pub fn fmt_duration(minutes: u32) -> String {
        format!("{}h{:02}", minutes / 60, minutes % 60)
    }

    fn clock(t: u32) -> String {
        let (day, hm) = (t / 1440, t % 1440);
        let s = format!("{:02}:{:02}", hm / 60, hm % 60);
        if day > 0 {
            format!("{}+{}d", s, day)
        } else {
            s
        }
    }

    fn parse_hhmm(s: &str) -> Result<u32, String> {
        let bad = || format!("bad time {:?}", s);
        if !s.is_ascii() || s.len() != 5 || s.as_bytes()[2] != b':' {
            return Err(bad());
        }
        let h: u32 = s[0..2].parse().map_err(|_| bad())?;
        let m: u32 = s[3..5].parse().map_err(|_| bad())?;
        if h > 23 || m > 59 {
            return Err(bad());
        }
        Ok(h * 60 + m)
    }

    impl Plan {
        pub fn total_distance_m(&self) -> f64 {
            self.legs.iter().map(|l| l.distance_m).sum()
        }

        pub fn total_ascent_m(&self) -> f64 {
            self.legs.iter().map(|l| l.ascent_m).sum()
        }

        pub fn total_descent_m(&self) -> f64 {
            self.legs.iter().map(|l| l.descent_m).sum()
        }

        pub fn total_minutes(&self) -> u32 {
            self.legs.iter().map(|l| l.minutes).sum()
        }

        pub fn summary(&self) -> String {
            let n = self.legs.len();
            format!(
                "{} {}, {} km, +{} m / -{} m, {}",
                n,
                if n == 1 { "leg" } else { "legs" },
                fmt_km(self.total_distance_m()),
                self.total_ascent_m().round() as i64,
                self.total_descent_m().round() as i64,
                fmt_duration(self.total_minutes())
            )
        }

        /// Stop names with their arrival times, starting at `start` ("HH:MM").
        pub fn arrivals(&self, start: &str) -> Result<Vec<(String, String)>, String> {
            let mut t = parse_hhmm(start)?;
            let mut out = Vec::new();
            let first = match self.legs.first() {
                Some(l) => l.from.clone(),
                None => return Ok(out),
            };
            out.push((first, clock(t)));
            for leg in &self.legs {
                t += leg.minutes;
                out.push((leg.to.clone(), clock(t)));
            }
            Ok(out)
        }
    }
''')

LIB = dd('''
    pub mod geo;
    pub mod pace;
    pub mod parse;
    pub mod plan;
    pub mod profile;
''')

VISIBLE = {
    "tests/visible.rs": dd('''
        use trailplan::pace::leg_minutes;
        use trailplan::parse::parse_waypoints;
        use trailplan::plan::build;

        #[test]
        fn parses_three_stops() {
            let pts = parse_waypoints("A; 0; 0; 100\\nB; 1000; 0; 100\\nC; 2000; 0; 100\\n").unwrap();
            assert_eq!(pts.len(), 3);
            assert_eq!(pts[1].name.as_deref(), Some("B"));
        }

        #[test]
        fn flat_walking_time() {
            assert_eq!(leg_minutes(5000.0, 0.0), 60);
            assert_eq!(leg_minutes(0.0, 0.0), 0);
        }

        #[test]
        fn summary_of_two_flat_legs() {
            let pts = parse_waypoints("A; 0; 0; 100\\nB; 1000; 0; 100\\nC; 2000; 0; 100\\n").unwrap();
            let plan = build(&pts);
            assert_eq!(plan.summary(), "2 legs, 2.0 km, +0 m / -0 m, 0h24");
        }
    '''),
}

HIDDEN = {
    "tests/hidden.rs": dd('''
        use trailplan::pace::leg_minutes;
        use trailplan::parse::{parse_waypoints, ParseError};
        use trailplan::plan::{build, fmt_km, Plan};
        use trailplan::profile::climb;

        fn plan_of(text: &str) -> Plan {
            build(&parse_waypoints(text).expect("trail must parse"))
        }

        // ---- parse -------------------------------------------------------------------------------------------

        #[test]
        fn decimals_and_negative_elevations_are_kept() {
            let pts = parse_waypoints("A; 0; 0; 1203.5\\n-; 3; 4; -12.25\\nB; 6; 8; 0\\n").unwrap();
            assert_eq!(pts[0].point.elev, 1203.5);
            assert_eq!(pts[1].point.elev, -12.25);
            assert_eq!(pts[1].name, None);
            assert_eq!(pts[2].point.x, 6.0);
        }

        #[test]
        fn comments_blank_lines_crlf_and_bom_are_ignored() {
            let text = "\\u{feff}# route\\r\\n\\r\\nA; 0; 0; 5\\r\\n  # note\\r\\nB; 10; 0; 5\\r\\n";
            let pts = parse_waypoints(text).unwrap();
            assert_eq!(pts.len(), 2);
            assert_eq!(pts[0].name.as_deref(), Some("A"));
        }

        #[test]
        fn errors_name_the_physical_line() {
            let e = parse_waypoints("# header\\n\\nA; 0; 0; 5\\nB; 10; zero; 5\\n").unwrap_err();
            match e {
                ParseError::Line { line, msg } => {
                    assert_eq!(line, 4);
                    assert!(msg.contains("y"), "{}", msg);
                }
                other => panic!("{:?}", other),
            }
            let e = parse_waypoints("A; 0; 0\\nB; 1; 1; 1").unwrap_err();
            assert!(matches!(e, ParseError::Line { line: 1, .. }), "{:?}", e);
            let e = parse_waypoints("A; 0; 0; 5\\n; 1; 1; 1\\nB; 2; 2; 2").unwrap_err();
            assert!(matches!(e, ParseError::Line { line: 2, .. }), "{:?}", e);
            let e = parse_waypoints("A; 0; 0; inf\\nB; 1; 1; 1").unwrap_err();
            assert!(matches!(e, ParseError::Line { line: 1, .. }), "{:?}", e);
        }

        #[test]
        fn structure_errors() {
            assert_eq!(parse_waypoints("").unwrap_err(), ParseError::TooFew);
            assert_eq!(parse_waypoints("A; 0; 0; 1\\n").unwrap_err(), ParseError::TooFew);
            assert_eq!(parse_waypoints("-; 0; 0; 1\\nA; 1; 1; 1\\nB; 2; 2; 2\\n").unwrap_err(), ParseError::Unanchored);
            assert_eq!(parse_waypoints("A; 0; 0; 1\\nB; 1; 1; 1\\n-; 2; 2; 2\\n").unwrap_err(), ParseError::Unanchored);
        }

        #[test]
        fn duplicate_stops_ignore_case() {
            let e = parse_waypoints("Hut; 0; 0; 1\\nCol; 5; 5; 9\\nhut; 9; 9; 1\\n").unwrap_err();
            assert_eq!(e, ParseError::DuplicateStop("hut".to_string()));
            assert!(parse_waypoints("Hut; 0; 0; 1\\n-; 1; 1; 1\\n-; 2; 2; 2\\nCol; 5; 5; 9\\n").is_ok());
        }

        // ---- pace ----------------------------------------------------------------------------------------------

        #[test]
        fn minutes_are_rounded_up() {
            assert_eq!(leg_minutes(5030.0, 0.0), 61);
            assert_eq!(leg_minutes(1.0, 0.0), 1);
            assert_eq!(leg_minutes(5000.0, 0.0), 60);
            assert_eq!(leg_minutes(5000.0, 100.0), 70);
            assert_eq!(leg_minutes(1000.0, 5.0), 13);
        }

        #[test]
        fn long_legs_get_a_break_only_above_ninety() {
            assert_eq!(leg_minutes(7500.0, 0.0), 90);
            assert_eq!(leg_minutes(7517.0, 0.0), 101);
            assert_eq!(leg_minutes(7600.0, 0.0), 102);
            assert_eq!(leg_minutes(20000.0, 0.0), 250);
        }

        #[test]
        fn steepness_is_a_grade_not_metres_per_km() {
            assert_eq!(leg_minutes(1000.0, 100.0), 22);
            assert_eq!(leg_minutes(1000.0, 200.0), 42);
            assert_eq!(leg_minutes(2000.0, 300.0), 54);
            assert_eq!(leg_minutes(2000.0, 310.0), 24 + 47);
            assert_eq!(leg_minutes(0.0, 50.0), 5);
        }

        // ---- profile ---------------------------------------------------------------------------------------------

        #[test]
        fn climb_ignores_noise() {
            assert_eq!(climb(&[]), (0.0, 0.0));
            assert_eq!(climb(&[100.0]), (0.0, 0.0));
            assert_eq!(climb(&[100.0, 101.0, 100.5, 102.0, 101.0, 99.5]), (0.0, 0.0));
        }

        #[test]
        fn a_slow_climb_counts_from_the_reference() {
            let slope: Vec<f64> = (0..=9).map(|i| i as f64).collect();
            assert_eq!(climb(&slope), (9.0, 0.0));
            let long: Vec<f64> = (0..100).map(|i| 500.0 + i as f64).collect();
            assert_eq!(climb(&long), (99.0, 0.0));
        }

        #[test]
        fn three_metres_count_and_descents_move_the_reference() {
            assert_eq!(climb(&[0.0, 3.0]), (3.0, 0.0));
            assert_eq!(climb(&[3.0, 0.0]), (0.0, 3.0));
            let down: Vec<f64> = (0..=10).map(|i| 10.0 - i as f64).collect();
            assert_eq!(climb(&down), (0.0, 9.0));
            assert_eq!(climb(&[0.0, 5.0, 2.0, 8.0]), (11.0, 3.0));
            assert_eq!(climb(&[0.0, 2.5, 5.5, 2.0]), (5.5, 3.5));
        }

        // ---- plan ------------------------------------------------------------------------------------------------

        const TRAIL: &str = "A; 0; 0; 100\\n-; 300; 400; 110\\nB; 600; 800; 90\\n-; 600; 1400; 120\\nC; 1200; 1400; 120\\n";

        #[test]
        fn legs_run_between_stops() {
            let plan = plan_of(TRAIL);
            assert_eq!(plan.legs.len(), 2);
            let (l1, l2) = (&plan.legs[0], &plan.legs[1]);
            assert_eq!((l1.from.as_str(), l1.to.as_str()), ("A", "B"));
            assert_eq!((l2.from.as_str(), l2.to.as_str()), ("B", "C"));
            assert_eq!(l1.distance_m, 1000.0);
            assert_eq!(l2.distance_m, 1200.0);
            assert_eq!((l1.ascent_m, l1.descent_m), (10.0, 20.0));
            assert_eq!((l2.ascent_m, l2.descent_m), (30.0, 0.0));
            assert_eq!((l1.minutes, l2.minutes), (13, 18));
        }

        #[test]
        fn totals_and_summary() {
            let plan = plan_of(TRAIL);
            assert_eq!(plan.total_distance_m(), 2200.0);
            assert_eq!(plan.total_ascent_m(), 40.0);
            assert_eq!(plan.total_descent_m(), 20.0);
            assert_eq!(plan.total_minutes(), 31);
            assert_eq!(plan.summary(), "2 legs, 2.2 km, +40 m / -20 m, 0h31");
        }

        #[test]
        fn one_leg_is_singular() {
            let plan = plan_of("A; 0; 0; 0\\nB; 3000; 4000; 0\\n");
            assert_eq!(plan.summary(), "1 leg, 5.0 km, +0 m / -0 m, 1h00");
        }

        #[test]
        fn kilometres_are_rounded_once_with_halves_up() {
            let plan = plan_of("A; 0; 0; 0\\nB; 340; 0; 0\\nC; 680; 0; 0\\nD; 1020; 0; 0\\n");
            assert!(plan.summary().starts_with("3 legs, 1.0 km,"), "{}", plan.summary());
            assert_eq!(fmt_km(12250.0), "12.3");
            assert_eq!(fmt_km(12249.0), "12.2");
            assert_eq!(fmt_km(250.0), "0.3");
            assert_eq!(fmt_km(750.0), "0.8");
            assert_eq!(fmt_km(0.0), "0.0");
            assert_eq!(fmt_km(99950.0), "100.0");
            let plan = plan_of("A; 0; 0; 0\\nB; 12250; 0; 0\\n");
            assert_eq!(plan.summary(), "1 leg, 12.3 km, +0 m / -0 m, 2h37");
        }

        #[test]
        fn total_minutes_add_up_the_legs() {
            let plan = plan_of("A; 0; 0; 0\\nB; 5030; 0; 0\\nC; 10060; 0; 0\\n");
            assert_eq!(plan.legs[0].minutes, 61);
            assert_eq!(plan.total_minutes(), 122);
            assert!(plan.summary().ends_with("2h02"), "{}", plan.summary());
        }

        #[test]
        fn a_gentle_long_climb_is_measured() {
            let mut text = String::from("A; 0; 0; 500\\n");
            for i in 1..100 {
                text.push_str(&format!("-; {}; 0; {}\\n", i * 10, 500 + i));
            }
            text.push_str("B; 1000; 0; 599\\n");
            let plan = plan_of(&text);
            assert_eq!(plan.legs.len(), 1);
            assert_eq!(plan.legs[0].ascent_m, 99.0);
            assert_eq!(plan.legs[0].minutes, 22);
        }

        #[test]
        fn arrivals_wrap_past_midnight() {
            let plan = plan_of("A; 0; 0; 0\\nB; 3300; 0; 0\\nC; 7400; 0; 0\\nD; 14900; 0; 0\\n");
            let mins: Vec<u32> = plan.legs.iter().map(|l| l.minutes).collect();
            assert_eq!(mins, vec![40, 50, 90]);
            let a = plan.arrivals("22:30").unwrap();
            let got: Vec<(&str, &str)> = a.iter().map(|(n, t)| (n.as_str(), t.as_str())).collect();
            assert_eq!(got, vec![("A", "22:30"), ("B", "23:10"), ("C", "00:00+1d"), ("D", "01:30+1d")]);
            let b = plan.arrivals("07:05").unwrap();
            assert_eq!(b[3], ("D".to_string(), "10:05".to_string()));
        }

        #[test]
        fn arrivals_after_two_days() {
            let plan = plan_of("A; 0; 0; 0\\nB; 120000; 0; 0\\n");
            assert_eq!(plan.legs[0].minutes, 1450);
            let a = plan.arrivals("23:59").unwrap();
            assert_eq!(a[1].1, "00:09+2d");
        }

        #[test]
        fn bad_start_times_are_errors() {
            let plan = plan_of("A; 0; 0; 0\\nB; 1000; 0; 0\\n");
            for bad in ["7:05", "24:00", "12:60", "ab:cd", "12-30", "", "12:300", "\\u{e9}1:00"] {
                assert!(plan.arrivals(bad).is_err(), "{:?} should be refused", bad);
            }
            assert!(plan.arrivals("00:00").is_ok());
            assert!(plan.arrivals("23:59").is_ok());
        }
    '''),
}


REPORTED_TIES = {
    "tests/reported.rs": dd('''
        use trailplan::parse::parse_waypoints;
        use trailplan::plan::build;

        #[test]
        fn leaflet_rounds_halves_up() {
            let plan = build(&parse_waypoints("A; 0; 0; 0\\nB; 12250; 0; 0\\n").unwrap());
            assert!(plan.summary().contains(" 12.3 km"), "summary was {:?}", plan.summary());
        }
    '''),
}

REPORTED_CLOCK = {
    "tests/reported.rs": dd('''
        use trailplan::parse::parse_waypoints;
        use trailplan::plan::build;

        #[test]
        fn night_hike_wraps_at_midnight() {
            let plan = build(&parse_waypoints("A; 0; 0; 0\\nB; 5000; 0; 0\\nC; 10000; 0; 0\\n").unwrap());
            let a = plan.arrivals("23:00").unwrap();
            assert_eq!(a[2].1, "01:00+1d", "arrivals were {:?}", a);
        }
    '''),
}


def _prompts() -> dict:
    p = {}
    p["elev"] = (
        "Imported tracks have lost the decimals of their elevations: a pass that the GPS file gives as 1203.5 m is "
        "kept as 1203 m, and the ascent of gently rolling routes (where neighbouring trackpoints differ by fractions of a metre) drifts."
    )
    p["dup"] = (
        "A route with the stops `Col du Lac` and later `col du lac` is accepted and the plan then has two different stops that "
        "look the same on the printout. The README says what happens to stop names that differ only in case."
    )
    p["bom"] = (
        "Routes exported by a Windows GPS tool cannot be imported: `Err(Line { line: 1, msg: \"want 4 fields, got 1\" })`, although the file "
        "looks fine in an editor (line 1 is a `# route` comment). A hex dump shows `EF BB BF` at the start. The same route saved by another tool works."
    )
    p["round"] = (
        "Mountain rescue complained that the timetable has no slack: a flat 5.03 km leg is planned at 60 minutes, but the rule is that "
        "walking times are rounded *up* to whole minutes (61)."
    )
    p["ninety"] = (
        "A leg that is planned at exactly 90 minutes gets the 10 minute break added; the README says only legs of more than 90 minutes do."
    )
    p["steep-km"] = (
        "Ordinary short climbs are planned far too slowly: a 1 km leg with 100 m of ascent (10%) takes 27 minutes instead of 22, as if "
        "it were steep. The truly steep legs come out right."
    )
    p["slow-climb"] = (
        "The plan for the Seealp route says `+0 m` ascent although the profile climbs steadily from 500 m to 599 m over a hundred "
        "trackpoints (1 m per point). Noisy tracks are handled fine; it is the slow, steady climbs that vanish."
    )
    p["band-edge"] = (
        "A climb of exactly 3 m, which is the threshold, is ignored. The README says a change of 3 m or more counts."
    )
    p["desc-ref"] = (
        "Descent totals explode on long steady descents: a track that drops from 10 m to 0 m in 1 m steps reports 52 m of descent "
        "(ascent on the way up is fine)."
    )
    p["track-legs"] = (
        "The leg table has a row for every trackpoint: our two-stop route shows four legs, some of them named `-` or with an empty start."
    )
    p["rounded-legs"] = (
        "The summary says 0.9 km for a route made of three 340 m legs; the real length is 1.02 km, so it should read 1.0. It looks as "
        "if each leg is rounded before they are added up."
    )
    p["ties"] = lambda c: (
        "Our printed leaflets say 12.3 km but the summary of the same route says 12.2 (and 0.25 km turns into 0.2). The README rounds halves up. "
        "A reduced test in CI:\n\n```\n" + panic_excerpt(c.visible_out(60)) + "\n```\n"
    )
    p["clock"] = lambda c: (
        "The night-hike timetable shows arrival times such as `24:00` and `25:30` after midnight. A reduced test from CI:\n\n```\n"
        + panic_excerpt(c.visible_out(60)) + "\n```\n"
    )
    p["total-recomputed"] = (
        "The route sheet's header duration does not match its own leg table: the legs say 61 + 61 minutes (2h02) but the header says 2h11."
    )
    p["leg-table"] = (
        "Two complaints about the route sheet of the Seealp tour: (1) the leg table has a row for every trackpoint, some named `-`; "
        "(2) the header says 0.9 km for a trail of three 340 m legs (it should say 1.0): rounded numbers seem to be added up. Please fix both."
    )
    p["night-hike"] = (
        "Night-hike timetable review. (1) Arrival times after midnight read 24:xx or 25:xx instead of wrapping with the `+1d` suffix. "
        "(2) Some legs are planned a minute short because walking times are rounded to the nearest minute instead of up. (3) A leg of exactly 90 "
        "minutes gets the break that is meant only for longer legs. Please fix all three."
    )
    p["feasibility"] = (
        "Seealp feasibility review against the README. Findings: (a) a long steady climb (1 m per trackpoint) shows `+0 m` of ascent; (b) "
        "ordinary short climbs (100 m over 1 km) are timed as if they were steep; (c) the header duration does not equal the sum of the "
        "leg table. Please bring the library in line with the specification."
    )
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "Cargo.toml": langs.cargo_toml("trailplan"), "src/lib.rs": LIB, "src/geo.rs": GEO,
        "src/parse.rs": PARSE, "src/pace.rs": PACE, "src/profile.rs": PROFILE, "src/plan.rs": PLAN,
    }
    pa, pc, pr, pl = "src/parse.rs", "src/pace.rs", "src/profile.rs", "src/plan.rs"
    elev = ('        let elev = num(fields[3], "elevation")?;\n', '        let elev = num(fields[3], "elevation")?.trunc();\n')
    dup = ("        let key = name.to_lowercase();\n", "        let key = name.clone();\n")
    bom = ("    let text = text.strip_prefix('\\u{feff}').unwrap_or(text);\n", "")
    rnd = ("    let minutes = (distance_m * 12.0 / 1000.0 + climb).ceil() as u32;\n", "    let minutes = (distance_m * 12.0 / 1000.0 + climb).round() as u32;\n")
    ninety = ("    if minutes > 90 {\n", "    if minutes >= 90 {\n")
    steep = ("    if distance_m > 0.0 && ascent_m / distance_m > 0.15 {\n", "    if distance_m > 0.0 && ascent_m / (distance_m / 1000.0) > 0.15 {\n")
    per_step = ("    let mut reference = first;\n    for &e in &elevations[1..] {\n        let d = e - reference;\n        if d >= DEAD_BAND_M {\n            up += d;\n            reference = e;\n        } else if d <= -DEAD_BAND_M {\n            down -= d;\n            reference = e;\n        }\n    }\n",
                "    let mut previous = first;\n    for &e in &elevations[1..] {\n        let d = e - previous;\n        previous = e;\n        if d >= DEAD_BAND_M {\n            up += d;\n        } else if d <= -DEAD_BAND_M {\n            down -= d;\n        }\n    }\n")
    band_edge = ("        if d >= DEAD_BAND_M {\n", "        if d > DEAD_BAND_M {\n"), ("        } else if d <= -DEAD_BAND_M {\n", "        } else if d < -DEAD_BAND_M {\n")
    desc_ref = ("            down -= d;\n            reference = e;\n", "            down -= d;\n")
    track_legs = ("        if let Some(name) = &w.name {\n", "        {\n            let name = w.name.clone().unwrap_or_else(|| \"-\".to_string());\n")
    rounded_legs = [
        ("fmt_km(self.total_distance_m()),", "fmt_km_sum(&self.legs),"),
        ("pub fn fmt_duration(minutes: u32) -> String {\n", "fn fmt_km_sum(legs: &[Leg]) -> String {\n    let tenths: i64 = legs.iter().map(|l| (l.distance_m / 100.0).round() as i64).sum();\n    format!(\"{}.{}\", tenths / 10, tenths % 10)\n}\n\npub fn fmt_duration(minutes: u32) -> String {\n"),
    ]
    ties = ("    let tenths = (metres / 100.0).round() as i64;\n    format!(\"{}.{}\", tenths / 10, tenths % 10)\n", "    format!(\"{:.1}\", metres / 1000.0)\n")
    clock = ("    let (day, hm) = (t / 1440, t % 1440);\n    let s = format!(\"{:02}:{:02}\", hm / 60, hm % 60);\n    if day > 0 {\n        format!(\"{}+{}d\", s, day)\n    } else {\n        s\n    }\n",
             "    format!(\"{:02}:{:02}\", t / 60, t % 60)\n")
    total = ("        self.legs.iter().map(|l| l.minutes).sum()\n", "        leg_minutes(self.total_distance_m(), self.total_ascent_m())\n")
    bugs = [
        Bug("elevations-lose-their-decimals", 2, {pa: [elev]}, P["elev"]),
        Bug("duplicate-stops-are-case-sensitive", 2, {pa: [dup]}, P["dup"]),
        Bug("byte-order-mark-breaks-line-one", 2, {pa: [bom]}, P["bom"]),
        Bug("walking-time-rounded-to-nearest", 2, {pc: [rnd]}, P["round"]),
        Bug("break-from-exactly-ninety-minutes", 2, {pc: [ninety]}, P["ninety"]),
        Bug("steepness-uses-metres-per-kilometre", 4, {pc: [steep]}, P["steep-km"]),
        Bug("dead-band-measured-per-step", 4, {pr: [per_step]}, P["slow-climb"]),
        Bug("dead-band-edge-is-exclusive", 2, {pr: list(band_edge)}, P["band-edge"]),
        Bug("descent-never-moves-the-reference", 4, {pr: [desc_ref]}, P["desc-ref"]),
        Bug("trackpoints-end-legs", 3, {pl: [track_legs]}, P["track-legs"]),
        Bug("kilometres-from-rounded-legs", 3, {pl: rounded_legs}, P["rounded-legs"]),
        Bug("kilometre-ties-go-to-even", 3, {pl: [ties]}, P["ties"], reported=REPORTED_TIES),
        Bug("arrivals-do-not-wrap-at-midnight", 3, {pl: [clock]}, P["clock"], reported=REPORTED_CLOCK),
        Bug("total-minutes-recomputed-from-totals", 3, {pl: [total]}, P["total-recomputed"]),
        Bug("leg-table-and-header-distance", 4, {pl: [track_legs] + rounded_legs}, P["leg-table"]),
        Bug("night-hike-timetable", 4, {pc: [rnd, ninety], pl: [clock]}, P["night-hike"]),
        Bug("feasibility-review", 5, {pr: [per_step], pc: [steep], pl: [total]}, P["feasibility"]),
    ]
    return Base("trailplan", "rust", good, VISIBLE, HIDDEN, bugs)


@family("fix-hand-trail-plan", category="fix", lang="rust", kind="fix", n=17,
        summary="a layered rust crate that plans hikes (parse, pace rules, climb dead band, plan summary) with cross-module defects and review tickets")
def gen(rng, n):
    return tasks_from([_base()])
