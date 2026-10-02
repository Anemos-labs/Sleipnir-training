"""Tap-in/tap-out fares (rust): zone spans, peak surcharge, transfer discount, daily cap that grows, penalty fares."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # tapfare

    Fare calculation for the harbour tram's contactless cards. A day's card taps go in, priced journeys come out. Money is in cents.

    ## Input
    ```rust
    pub enum Kind { In, Out }
    pub struct Tap { pub day: u32, pub minute: u32, pub zone: u8, pub kind: Kind }
    ```
    `day` counts days from a Monday (`day % 7`: 0 Monday ... 4 Friday, 5 Saturday, 6 Sunday), `minute` is the minute of the day (0..=1439), `zone` is 1..=6.
    `price(taps: &[Tap]) -> Result<Summary, FareError>` processes the taps in order. A tap that is invalid gives the error for the **first** such tap
    in the slice (its index inside the variant): `BadZone(i)` (zone outside 1..=6), `BadTime(i)` (minute above 1439), `OutOfOrder(i)` (its
    `(day, minute)` is earlier than the previous tap's; equal is fine). For one tap the checks run in that order.

    ## Pairing taps
    * An `In` followed by an `Out` **on the same day** is a journey. The `Out` may be at any zone; the tap-in zone and time define the fare.
    * An `In` followed by another `In` leaves the first one incomplete: it is charged a *penalty* when the second arrives.
    * An `Out` with no open `In`, or on a different day than the open `In`, is an orphan: the open `In` (if any) is charged a penalty first, then
      the orphan `Out` is charged a penalty too.
    * An `In` still open after the last tap is charged a penalty at the end.
    A penalty is `480` cents, `base = 480`, `to = None`, flags all false except `penalty`; `from` and `minute` are those of the tap it is charged for.

    ## Pricing a journey
    1. `span = |zone_out - zone_in| + 1` and `base = [180, 260, 330, 390, 440, 480][span - 1]`.
    2. **Peak**: if the day is Monday to Friday and the tap-in minute is in `[390, 570)` or `[960, 1140)` the fare is `base * 1.2` rounded to the
       nearest multiple of 5, halves up: `((base * 12 + 25) / 50) * 5` (integer division). Otherwise the fare is `base`.
    3. **Transfer**: if the previous *journey* (penalties do not count) is on the same day, ended at the zone where this one starts, and this tap-in is at
       most 45 minutes after that journey's tap-out (45 included), the fare is halved and rounded to the nearest multiple of 5, halves up:
       `((fare + 5) / 10) * 5`. This is applied to the fare of step 2.
    4. **Daily cap**: per day, the cap depends on the longest span of any journey of that day so far, this one included:
       `[450, 650, 800, 950, 1050, 1140][max_span - 1]`. The amount charged is `min(fare, cap - already charged for journeys that day)` (never below 0), and
       `capped` is set when that is less than the fare. Penalties neither count towards the cap nor are limited by it.

    ## Output
    ```rust
    pub struct Item { pub day: u32, pub minute: u32, pub from: u8, pub to: Option<u8>, pub base: u32, pub charged: u32,
                      pub peak: bool, pub transfer: bool, pub capped: bool, pub penalty: bool }
    pub struct Summary { pub items: Vec<Item>, pub day_totals: Vec<(u32, u32)> }
    ```
    One `Item` per journey or penalty, in the order they are charged (a journey when its `Out` arrives, a penalty when it is detected as described).
    For a journey `minute` and `from` describe the tap-in. `day_totals` lists `(day, everything charged that day including penalties)` for every day
    that has at least one item, ascending by day (a penalty counts for the day of the tap it is charged for).
''')

SRC = dd('''
    //! Fare calculation for tap-in / tap-out cards.
    use std::collections::BTreeMap;

    const BASE: [u32; 6] = [180, 260, 330, 390, 440, 480];
    const CAP: [u32; 6] = [450, 650, 800, 950, 1050, 1140];
    const PENALTY: u32 = 480;
    const PEAK: [(u32, u32); 2] = [(390, 570), (960, 1140)];
    const TRANSFER_MINUTES: u32 = 45;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Kind {
        In,
        Out,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Tap {
        pub day: u32,
        pub minute: u32,
        pub zone: u8,
        pub kind: Kind,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum FareError {
        BadZone(usize),
        BadTime(usize),
        OutOfOrder(usize),
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Item {
        pub day: u32,
        pub minute: u32,
        pub from: u8,
        pub to: Option<u8>,
        pub base: u32,
        pub charged: u32,
        pub peak: bool,
        pub transfer: bool,
        pub capped: bool,
        pub penalty: bool,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Summary {
        pub items: Vec<Item>,
        pub day_totals: Vec<(u32, u32)>,
    }

    #[derive(Default)]
    struct DayTally {
        longest: usize,
        fares: u32,
        total: u32,
    }

    struct Previous {
        day: u32,
        minute: u32,
        zone: u8,
    }

    fn is_peak(day: u32, minute: u32) -> bool {
        day % 7 < 5 && PEAK.iter().any(|&(from, to)| minute >= from && minute < to)
    }

    fn penalty_item(tap: &Tap) -> Item {
        Item {
            day: tap.day,
            minute: tap.minute,
            from: tap.zone,
            to: None,
            base: PENALTY,
            charged: PENALTY,
            peak: false,
            transfer: false,
            capped: false,
            penalty: true,
        }
    }

    pub fn price(taps: &[Tap]) -> Result<Summary, FareError> {
        let mut items = Vec::new();
        let mut tallies: BTreeMap<u32, DayTally> = BTreeMap::new();
        let mut open: Option<Tap> = None;
        let mut previous: Option<Previous> = None;
        let mut last: Option<(u32, u32)> = None;
        for (i, tap) in taps.iter().enumerate() {
            if tap.zone < 1 || tap.zone > 6 {
                return Err(FareError::BadZone(i));
            }
            if tap.minute > 1439 {
                return Err(FareError::BadTime(i));
            }
            if last.map_or(false, |l| (tap.day, tap.minute) < l) {
                return Err(FareError::OutOfOrder(i));
            }
            last = Some((tap.day, tap.minute));
            let mut penalties: Vec<Tap> = Vec::new();
            match tap.kind {
                Kind::In => {
                    penalties.extend(open.replace(*tap));
                }
                Kind::Out => match open.take() {
                    Some(inp) if inp.day == tap.day => {
                        let span = (tap.zone as i32 - inp.zone as i32).unsigned_abs() as usize + 1;
                        let base = BASE[span - 1];
                        let peak = is_peak(inp.day, inp.minute);
                        let mut fare = if peak { (base * 12 + 25) / 50 * 5 } else { base };
                        let transfer = previous.as_ref().map_or(false, |p| {
                            p.day == inp.day && p.zone == inp.zone && inp.minute - p.minute <= TRANSFER_MINUTES
                        });
                        if transfer {
                            fare = (fare + 5) / 10 * 5;
                        }
                        let tally = tallies.entry(inp.day).or_default();
                        tally.longest = tally.longest.max(span);
                        let room = CAP[tally.longest - 1].saturating_sub(tally.fares);
                        let charged = fare.min(room);
                        tally.fares += charged;
                        tally.total += charged;
                        items.push(Item {
                            day: inp.day,
                            minute: inp.minute,
                            from: inp.zone,
                            to: Some(tap.zone),
                            base,
                            charged,
                            peak,
                            transfer,
                            capped: charged < fare,
                            penalty: false,
                        });
                        previous = Some(Previous { day: tap.day, minute: tap.minute, zone: tap.zone });
                    }
                    other => {
                        penalties.extend(other);
                        penalties.push(*tap);
                    }
                },
            }
            for p in &penalties {
                tallies.entry(p.day).or_default().total += PENALTY;
                items.push(penalty_item(p));
            }
        }
        if let Some(p) = open {
            tallies.entry(p.day).or_default().total += PENALTY;
            items.push(penalty_item(&p));
        }
        Ok(Summary { items, day_totals: tallies.into_iter().map(|(d, t)| (d, t.total)).collect() })
    }
''')

VISIBLE = dd('''
    use tapfare::*;

    fn tap(day: u32, minute: u32, zone: u8, kind: Kind) -> Tap {
        Tap { day, minute, zone, kind }
    }

    #[test]
    fn one_zone_off_peak() {
        let s = price(&[tap(5, 600, 1, Kind::In), tap(5, 615, 1, Kind::Out)]).unwrap();
        assert_eq!(s.items.len(), 1);
        assert_eq!(s.items[0].charged, 180);
        assert_eq!(s.day_totals, vec![(5, 180)]);
    }

    #[test]
    fn empty_input() {
        let s = price(&[]).unwrap();
        assert!(s.items.is_empty() && s.day_totals.is_empty());
    }
''')

HIDDEN = dd('''
    use tapfare::*;
    use Kind::{In as I, Out as O};

    fn tap(day: u32, minute: u32, zone: u8, kind: Kind) -> Tap {
        Tap { day, minute, zone, kind }
    }

    fn brief(items: &[Item]) -> Vec<String> {
        items
            .iter()
            .map(|it| {
                format!(
                    "{}@{} {}>{} {}/{}{}{}{}{}",
                    it.day,
                    it.minute,
                    it.from,
                    it.to.map_or("-".to_string(), |z| z.to_string()),
                    it.base,
                    it.charged,
                    if it.peak { " P" } else { "" },
                    if it.transfer { " T" } else { "" },
                    if it.capped { " C" } else { "" },
                    if it.penalty { " !" } else { "" },
                )
            })
            .collect()
    }

    fn run(taps: &[Tap]) -> (Vec<String>, Vec<(u32, u32)>) {
        let s = price(taps).unwrap();
        (brief(&s.items), s.day_totals)
    }

    #[test]
    fn peak_and_transfer_on_a_monday() {
        let (items, totals) = run(&[tap(0, 480, 1, I), tap(0, 500, 3, O), tap(0, 520, 3, I), tap(0, 540, 3, O)]);
        assert_eq!(items, ["0@480 1>3 330/395 P", "0@520 3>3 180/110 P T"]);
        assert_eq!(totals, [(0, 505)]);
    }

    #[test]
    fn weekends_have_no_peak() {
        let (items, totals) = run(&[tap(5, 480, 1, I), tap(5, 500, 1, O), tap(6, 480, 1, I), tap(6, 500, 2, O)]);
        assert_eq!(items, ["5@480 1>1 180/180", "6@480 1>2 260/260"]);
        assert_eq!(totals, [(5, 180), (6, 260)]);
    }

    #[test]
    fn weekday_numbering() {
        let mut taps = Vec::new();
        for d in [4, 5, 6, 7, 11, 12, 13, 14] {
            taps.push(tap(d, 480, 1, I));
            taps.push(tap(d, 490, 1, O));
        }
        let (items, _) = run(&taps);
        assert_eq!(
            items,
            [
                "4@480 1>1 180/215 P", "5@480 1>1 180/180", "6@480 1>1 180/180", "7@480 1>1 180/215 P", "11@480 1>1 180/215 P",
                "12@480 1>1 180/180", "13@480 1>1 180/180", "14@480 1>1 180/215 P"
            ]
        );
    }

    #[test]
    fn peak_window_edges() {
        let mut taps = Vec::new();
        for (d, m) in [(0, 389), (1, 390), (2, 569), (3, 570), (4, 959), (7, 960), (8, 1139), (9, 1140)] {
            taps.push(tap(d, m, 1, I));
            taps.push(tap(d, m + 1, 1, O));
        }
        let (items, _) = run(&taps);
        assert_eq!(
            items,
            [
                "0@389 1>1 180/180", "1@390 1>1 180/215 P", "2@569 1>1 180/215 P", "3@570 1>1 180/180", "4@959 1>1 180/180",
                "7@960 1>1 180/215 P", "8@1139 1>1 180/215 P", "9@1140 1>1 180/180"
            ]
        );
    }

    #[test]
    fn peak_is_decided_by_the_tap_in() {
        // in at 09:29 (peak), out after the window: still a peak fare; in at 09:30, out earlier is impossible
        let (items, _) = run(&[tap(0, 569, 1, I), tap(0, 700, 1, O), tap(1, 380, 1, I), tap(1, 420, 1, O)]);
        assert_eq!(items, ["0@569 1>1 180/215 P", "1@380 1>1 180/180"]);
    }

    #[test]
    fn peak_fares_per_span() {
        let want = [215, 310, 395, 470, 530, 575];
        for (i, w) in want.iter().enumerate() {
            let span = i as u8 + 1;
            let s = price(&[tap(0, 420, 1, I), tap(0, 425, span, O)]).unwrap();
            assert_eq!(s.items[0].charged, *w, "span {span}");
            assert_eq!(s.items[0].base, [180, 260, 330, 390, 440, 480][i]);
        }
    }

    #[test]
    fn off_peak_fares_per_span_both_directions() {
        let (items, _) = run(&[tap(5, 100, 6, I), tap(5, 110, 1, O), tap(5, 300, 4, I), tap(5, 310, 2, O)]);
        assert_eq!(items, ["5@100 6>1 480/480", "5@300 4>2 330/330"]);
        let (items, totals) = run(&[
            tap(6, 100, 1, I), tap(6, 105, 1, O), tap(6, 200, 1, I), tap(6, 205, 2, O), tap(6, 300, 1, I), tap(6, 305, 3, O),
        ]);
        assert_eq!(items, ["6@100 1>1 180/180", "6@200 1>2 260/260", "6@300 1>3 330/330"]);
        assert_eq!(totals, [(6, 770)]);
    }

    #[test]
    fn transfer_window_is_inclusive() {
        let (items, _) = run(&[
            tap(5, 700, 1, I), tap(5, 720, 2, O), tap(5, 765, 2, I), tap(5, 780, 3, O), tap(5, 827, 3, I), tap(5, 840, 3, O),
        ]);
        // 45 minutes after the first tap-out (720 -> 765): transfer; 47 minutes after the second (780 -> 827): none
        assert_eq!(items, ["5@700 1>2 260/260", "5@765 2>3 260/130 T", "5@827 3>3 180/180"]);
        let (items, _) = run(&[tap(5, 700, 1, I), tap(5, 720, 2, O), tap(5, 766, 2, I), tap(5, 770, 2, O)]);
        assert_eq!(items[1], "5@766 2>2 180/180");
        let (items, _) = run(&[tap(5, 700, 1, I), tap(5, 720, 2, O), tap(5, 720, 2, I), tap(5, 721, 2, O)]);
        assert_eq!(items[1], "5@720 2>2 180/90 T");
    }

    #[test]
    fn transfer_needs_the_same_zone_and_day() {
        let (items, _) = run(&[tap(5, 700, 1, I), tap(5, 720, 2, O), tap(5, 730, 3, I), tap(5, 740, 3, O)]);
        assert_eq!(items[1], "5@730 3>3 180/180");
        // after midnight no transfer, even a minute later
        let (items, _) = run(&[tap(5, 1430, 1, I), tap(5, 1439, 1, O), tap(6, 0, 1, I), tap(6, 5, 1, O)]);
        assert_eq!(items, ["5@1430 1>1 180/180", "6@0 1>1 180/180"]);
    }

    #[test]
    fn transfers_chain() {
        let (items, totals) = run(&[
            tap(1, 1000, 2, I), tap(1, 1010, 2, O), tap(1, 1055, 2, I), tap(1, 1060, 2, O), tap(1, 1105, 2, I), tap(1, 1110, 2, O),
            tap(1, 1120, 1, I), tap(1, 1130, 1, O),
        ]);
        assert_eq!(items, ["1@1000 2>2 180/215 P", "1@1055 2>2 180/110 P T", "1@1105 2>2 180/110 P T", "1@1120 1>1 180/15 P C"]);
        assert_eq!(totals, [(1, 450)]);
    }

    #[test]
    fn transfer_rounding() {
        let mut off = Vec::new();
        let mut peak = Vec::new();
        for span in 1..=6u8 {
            for (day, sink) in [(5u32, &mut off), (0u32, &mut peak)] {
                let s = price(&[tap(day, 420, 1, I), tap(day, 425, 1, O), tap(day, 430, 1, I), tap(day, 435, span, O)]).unwrap();
                sink.push(s.items[1].charged);
                assert!(s.items[1].transfer);
            }
        }
        assert_eq!(off, [90, 130, 165, 195, 220, 240]);
        assert_eq!(peak, [110, 155, 200, 235, 265, 290]);
    }

    #[test]
    fn same_minute_taps_are_allowed() {
        let (items, totals) = run(&[tap(0, 600, 1, I), tap(0, 600, 1, O), tap(0, 600, 1, I), tap(0, 600, 1, O)]);
        assert_eq!(items, ["0@600 1>1 180/180", "0@600 1>1 180/90 T"]);
        assert_eq!(totals, [(0, 270)]);
    }

    #[test]
    fn cap_with_transfers() {
        let mut taps = Vec::new();
        for i in 0..6 {
            taps.push(tap(5, 100 + i * 60, 1, I));
            taps.push(tap(5, 130 + i * 60, 1, O));
        }
        let (items, totals) = run(&taps);
        assert_eq!(
            items,
            ["5@100 1>1 180/180", "5@160 1>1 180/90 T", "5@220 1>1 180/90 T", "5@280 1>1 180/90 T", "5@340 1>1 180/0 T C", "5@400 1>1 180/0 T C"]
        );
        assert_eq!(totals, [(5, 450)]);
    }

    #[test]
    fn cap_grows_with_the_longest_span() {
        let (items, totals) = run(&[
            tap(5, 100, 1, I), tap(5, 110, 1, O), tap(5, 200, 1, I), tap(5, 210, 1, O), tap(5, 300, 1, I), tap(5, 330, 4, O),
            tap(5, 400, 1, I), tap(5, 420, 6, O), tap(5, 500, 1, I), tap(5, 510, 2, O),
        ]);
        assert_eq!(items, ["5@100 1>1 180/180", "5@200 1>1 180/180", "5@300 1>4 390/390", "5@400 1>6 480/390 C", "5@500 1>2 260/0 C"]);
        assert_eq!(totals, [(5, 1140)]);
    }

    #[test]
    fn spans_against_the_cap() {
        let mut taps = Vec::new();
        for i in 0..6u8 {
            taps.push(tap(5, 100 + 10 * i as u32, 1, I));
            taps.push(tap(5, 105 + 10 * i as u32, 1 + i, O));
        }
        let (items, totals) = run(&taps);
        assert_eq!(
            items,
            ["5@100 1>1 180/180", "5@110 1>2 260/130 T", "5@120 1>3 330/330", "5@130 1>4 390/310 C", "5@140 1>5 440/100 C", "5@150 1>6 480/90 C"]
        );
        assert_eq!(totals, [(5, 1140)]);
    }

    #[test]
    fn the_cap_is_per_day() {
        let (items, totals) = run(&[
            tap(5, 100, 1, I), tap(5, 110, 1, O), tap(5, 200, 1, I), tap(5, 210, 1, O), tap(5, 300, 1, I), tap(5, 310, 1, O),
            tap(6, 100, 1, I), tap(6, 110, 1, O),
        ]);
        assert_eq!(items, ["5@100 1>1 180/180", "5@200 1>1 180/180", "5@300 1>1 180/90 C", "6@100 1>1 180/180"]);
        assert_eq!(totals, [(5, 450), (6, 180)]);
    }

    #[test]
    fn penalties() {
        let (items, totals) = run(&[tap(5, 100, 1, I), tap(5, 110, 2, I), tap(5, 120, 2, O), tap(5, 130, 3, O), tap(5, 200, 1, I)]);
        assert_eq!(items, ["5@100 1>- 480/480 !", "5@110 2>2 180/180", "5@130 3>- 480/480 !", "5@200 1>- 480/480 !"]);
        assert_eq!(totals, [(5, 1620)]);
        let (items, _) = run(&[tap(0, 100, 2, O)]);
        assert_eq!(items, ["0@100 2>- 480/480 !"]);
        let (items, _) = run(&[tap(0, 100, 2, I)]);
        assert_eq!(items, ["0@100 2>- 480/480 !"]);
    }

    #[test]
    fn penalties_are_not_capped_and_do_not_count_towards_the_cap() {
        let (items, totals) = run(&[
            tap(5, 100, 1, I), tap(5, 110, 1, O), tap(5, 120, 1, I), tap(5, 130, 1, O), tap(5, 140, 1, I), tap(5, 150, 1, O),
            tap(5, 160, 1, I), tap(5, 170, 1, I), tap(5, 180, 1, O),
        ]);
        assert_eq!(items, ["5@100 1>1 180/180", "5@120 1>1 180/90 T", "5@140 1>1 180/90 T", "5@160 1>- 480/480 !", "5@170 1>1 180/90 T"]);
        assert_eq!(totals, [(5, 930)]);
    }

    #[test]
    fn journeys_across_midnight_are_penalised() {
        let (items, totals) = run(&[tap(2, 1400, 1, I), tap(2, 1430, 1, O), tap(3, 5, 1, I), tap(3, 15, 1, O)]);
        assert_eq!(items, ["2@1400 1>1 180/180", "3@5 1>1 180/180"]);
        assert_eq!(totals, [(2, 180), (3, 180)]);
        let (items, totals) = run(&[tap(2, 1400, 3, I), tap(3, 30, 1, O)]);
        assert_eq!(items, ["2@1400 3>- 480/480 !", "3@30 1>- 480/480 !"]);
        assert_eq!(totals, [(2, 480), (3, 480)]);
    }

    #[test]
    fn a_penalty_does_not_break_the_transfer_chain() {
        let (items, _) = run(&[tap(5, 100, 1, I), tap(5, 110, 2, O), tap(5, 120, 2, O), tap(5, 130, 2, I), tap(5, 135, 2, O)]);
        assert_eq!(items, ["5@100 1>2 260/260", "5@120 2>- 480/480 !", "5@130 2>2 180/90 T"]);
    }

    #[test]
    fn validation() {
        assert_eq!(price(&[tap(0, 100, 0, I)]), Err(FareError::BadZone(0)));
        assert_eq!(price(&[tap(0, 100, 1, I), tap(0, 110, 7, O)]), Err(FareError::BadZone(1)));
        assert_eq!(price(&[tap(0, 1440, 1, I)]), Err(FareError::BadTime(0)));
        assert_eq!(price(&[tap(0, 1439, 1, I), tap(0, 1439, 1, O)]).map(|s| s.items.len()), Ok(1));
        assert_eq!(price(&[tap(1, 100, 1, I), tap(0, 200, 1, O)]), Err(FareError::OutOfOrder(1)));
        assert_eq!(price(&[tap(1, 100, 1, I), tap(1, 99, 1, O)]), Err(FareError::OutOfOrder(1)));
        assert_eq!(price(&[tap(0, 100, 1, I), tap(0, 110, 1, O), tap(0, 105, 1, I)]), Err(FareError::OutOfOrder(2)));
        assert_eq!(price(&[tap(0, 1440, 9, I), tap(0, 100, 1, I)]), Err(FareError::BadZone(0)));
        assert_eq!(price(&[tap(0, 1440, 3, I), tap(0, 100, 1, I)]), Err(FareError::BadTime(0)));
        assert_eq!(price(&[tap(5, 1000, 3, I), tap(0, 100, 9, O)]), Err(FareError::BadZone(1)));
        assert_eq!(price(&[tap(5, 1000, 3, I), tap(0, 100, 3, O)]), Err(FareError::OutOfOrder(1)));
    }

    #[test]
    fn empty_input() {
        let s = price(&[]).unwrap();
        assert!(s.items.is_empty());
        assert!(s.day_totals.is_empty());
    }
''')

LIB = Lib(
    name="tapfare", lang="rust", title="the tapfare crate",
    blurb="The harbour tram prices contactless card taps with tapfare: zone spans, peak surcharge, transfers, a daily cap and penalty fares.",
    files={"Cargo.toml": cargo("tapfare"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["fares", "transit", "pricing"],
)

register_libs([LIB], n=8)
