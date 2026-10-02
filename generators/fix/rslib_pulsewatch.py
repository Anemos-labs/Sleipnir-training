"""Heartbeat failure detector (rust): sliding interval window, permille suspicion levels, reset after a death."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # pulsewatch

    A heartbeat failure detector for the cluster monitor. Nodes send heartbeats at roughly regular intervals; the detector learns
    each node's rhythm and says how late a node is. Time is a plain `u64` of milliseconds supplied by the caller. All
    arithmetic is integer.

    ## `Config` and `Detector::new`
    ```rust
    pub struct Config { pub window: usize, pub min_samples: usize, pub grace_ms: u64, pub suspect_permille: u64, pub dead_permille: u64 }
    ```
    `Detector::new(cfg) -> Result<Detector, WatchError>` rejects with `WatchError::BadConfig` unless `window >= 2`,
    `1 <= min_samples <= window`, `suspect_permille >= 1000` and `dead_permille > suspect_permille`.

    ## Learning the rhythm
    * `heartbeat(&mut self, id: &str, t: u64) -> Result<(), WatchError>`. The first heartbeat of an unknown id registers it (no
      interval yet). For a known node: `t < last` is `Err(WatchError::OutOfOrder)` (nothing changes); `t == last` is accepted and
      ignored (a duplicate); otherwise the interval `t - last` is appended to the node's window (the newest `window` intervals are
      kept) and `last = t`.
    * **A node that was dead restarts its history.** If, at the moment a heartbeat arrives, the node's level (below) was already at
      least `dead_permille`, its interval window is cleared instead of recording the long gap (and `last = t`). Until
      `min_samples` fresh intervals exist the node is `Unknown` again.
    * `expected(&self, id: &str) -> Option<u64>`: the mean of the window rounded down, or `None` when the node is unknown or has fewer than
      `min_samples` intervals.

    ## Levels and status
    With `expected` known, `effective = expected + grace_ms` and for a time `now` (a `now` earlier than `last` counts as zero elapsed):

    `level = elapsed * 1000 / effective` (integer division, `elapsed = now - last`)

    * `level(&self, id: &str, now: u64) -> Option<u64>`: that number, `None` when `expected` is `None`.
    * `status(&self, id: &str, now: u64) -> Status`: `Unknown` when there is no level; `Dead` when `level >= dead_permille`; `Suspect` when
      `level >= suspect_permille`; otherwise `Alive`.
    * `problems(&self, now: u64) -> Vec<(String, Status)>`: every node that is `Suspect` or `Dead`, ordered by id.
    * `remove(&mut self, id: &str) -> bool` forgets a node (true if it was known); `len(&self) -> usize` is the number of known nodes.
''')

SRC = dd('''
    //! A heartbeat failure detector.
    use std::collections::{BTreeMap, VecDeque};

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Config {
        pub window: usize,
        pub min_samples: usize,
        pub grace_ms: u64,
        pub suspect_permille: u64,
        pub dead_permille: u64,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Status {
        Unknown,
        Alive,
        Suspect,
        Dead,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum WatchError {
        BadConfig,
        OutOfOrder,
    }

    #[derive(Debug)]
    struct Node {
        last: u64,
        intervals: VecDeque<u64>,
    }

    #[derive(Debug)]
    pub struct Detector {
        cfg: Config,
        nodes: BTreeMap<String, Node>,
    }

    impl Detector {
        pub fn new(cfg: Config) -> Result<Detector, WatchError> {
            if cfg.window < 2
                || cfg.min_samples < 1
                || cfg.min_samples > cfg.window
                || cfg.suspect_permille < 1000
                || cfg.dead_permille <= cfg.suspect_permille
            {
                return Err(WatchError::BadConfig);
            }
            Ok(Detector { cfg, nodes: BTreeMap::new() })
        }

        fn expected_of(&self, node: &Node) -> Option<u64> {
            if node.intervals.len() < self.cfg.min_samples {
                return None;
            }
            let sum: u64 = node.intervals.iter().sum();
            Some(sum / node.intervals.len() as u64)
        }

        fn level_of(&self, node: &Node, now: u64) -> Option<u64> {
            let expected = self.expected_of(node)?;
            let effective = expected + self.cfg.grace_ms;
            let elapsed = now.saturating_sub(node.last);
            Some((elapsed as u128 * 1000 / effective as u128) as u64)
        }

        pub fn heartbeat(&mut self, id: &str, t: u64) -> Result<(), WatchError> {
            let Some(node) = self.nodes.get(id) else {
                self.nodes.insert(id.to_string(), Node { last: t, intervals: VecDeque::new() });
                return Ok(());
            };
            if t < node.last {
                return Err(WatchError::OutOfOrder);
            }
            if t == node.last {
                return Ok(());
            }
            let was_dead = matches!(self.level_of(node, t), Some(l) if l >= self.cfg.dead_permille);
            let window = self.cfg.window;
            let node = self.nodes.get_mut(id).unwrap();
            if was_dead {
                node.intervals.clear();
            } else {
                node.intervals.push_back(t - node.last);
                if node.intervals.len() > window {
                    node.intervals.pop_front();
                }
            }
            node.last = t;
            Ok(())
        }

        pub fn expected(&self, id: &str) -> Option<u64> {
            self.nodes.get(id).and_then(|n| self.expected_of(n))
        }

        pub fn level(&self, id: &str, now: u64) -> Option<u64> {
            self.nodes.get(id).and_then(|n| self.level_of(n, now))
        }

        pub fn status(&self, id: &str, now: u64) -> Status {
            match self.level(id, now) {
                None => Status::Unknown,
                Some(l) if l >= self.cfg.dead_permille => Status::Dead,
                Some(l) if l >= self.cfg.suspect_permille => Status::Suspect,
                Some(_) => Status::Alive,
            }
        }

        pub fn problems(&self, now: u64) -> Vec<(String, Status)> {
            let mut out = Vec::new();
            for id in self.nodes.keys() {
                let s = self.status(id, now);
                if s == Status::Suspect || s == Status::Dead {
                    out.push((id.clone(), s));
                }
            }
            out
        }

        pub fn remove(&mut self, id: &str) -> bool {
            self.nodes.remove(id).is_some()
        }

        pub fn len(&self) -> usize {
            self.nodes.len()
        }
    }
''')

VISIBLE = dd('''
    use pulsewatch::*;

    const CFG: Config = Config { window: 5, min_samples: 3, grace_ms: 200, suspect_permille: 1500, dead_permille: 3000 };

    #[test]
    fn steady_node_is_alive() {
        let mut d = Detector::new(CFG).unwrap();
        for t in [0, 1000, 2000, 3000] {
            d.heartbeat("a", t).unwrap();
        }
        assert_eq!(d.expected("a"), Some(1000));
        assert_eq!(d.status("a", 3500), Status::Alive);
    }

    #[test]
    fn unknown_ids_are_unknown() {
        let d = Detector::new(CFG).unwrap();
        assert_eq!(d.status("ghost", 10), Status::Unknown);
    }
''')

HIDDEN = dd('''
    use pulsewatch::*;

    const CFG: Config = Config { window: 5, min_samples: 3, grace_ms: 200, suspect_permille: 1500, dead_permille: 3000 };

    fn steady(d: &mut Detector, id: &str, start: u64, step: u64, beats: u64) {
        for i in 0..beats {
            d.heartbeat(id, start + i * step).unwrap();
        }
    }

    #[test]
    fn config_validation() {
        let bad = [
            Config { window: 1, min_samples: 1, ..CFG },
            Config { window: 0, min_samples: 1, ..CFG },
            Config { window: 1, ..CFG },
            Config { min_samples: 0, ..CFG },
            Config { min_samples: 6, ..CFG },
            Config { suspect_permille: 999, ..CFG },
            Config { dead_permille: 1500, ..CFG },
            Config { dead_permille: 1400, ..CFG },
        ];
        for cfg in bad {
            assert_eq!(Detector::new(cfg).unwrap_err(), WatchError::BadConfig, "{cfg:?}");
        }
        let good = [
            Config { window: 2, min_samples: 2, ..CFG },
            Config { min_samples: 5, ..CFG },
            Config { min_samples: 1, ..CFG },
            Config { suspect_permille: 1000, dead_permille: 1001, ..CFG },
            Config { grace_ms: 0, ..CFG },
        ];
        for cfg in good {
            assert!(Detector::new(cfg).is_ok(), "{cfg:?}");
        }
    }

    #[test]
    fn needs_min_samples_before_judging() {
        let mut d = Detector::new(CFG).unwrap();
        d.heartbeat("a", 0).unwrap();
        assert_eq!(d.status("a", 100_000), Status::Unknown);
        d.heartbeat("a", 1000).unwrap();
        d.heartbeat("a", 2000).unwrap();
        // two intervals, three needed
        assert_eq!(d.expected("a"), None);
        assert_eq!(d.level("a", 50_000), None);
        assert_eq!(d.status("a", 100_000), Status::Unknown);
        d.heartbeat("a", 3000).unwrap();
        assert_eq!(d.expected("a"), Some(1000));
        assert_eq!(d.status("a", 100_000), Status::Dead);
    }

    #[test]
    fn single_sample_configuration() {
        let cfg = Config { window: 2, min_samples: 1, ..CFG };
        let mut d = Detector::new(cfg).unwrap();
        d.heartbeat("n", 10).unwrap();
        assert_eq!(d.status("n", 10), Status::Unknown);
        d.heartbeat("n", 110).unwrap();
        assert_eq!(d.expected("n"), Some(100));
        assert_eq!(d.status("n", 110), Status::Alive);
    }

    #[test]
    fn level_and_status_thresholds() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4); // last = 3000, expected 1000, effective 1200
        assert_eq!(d.level("a", 3000), Some(0));
        assert_eq!(d.level("a", 3600), Some(500));
        assert_eq!(d.level("a", 3000 + 1799), Some(1499));
        assert_eq!(d.status("a", 3000 + 1799), Status::Alive);
        assert_eq!(d.level("a", 3000 + 1800), Some(1500));
        assert_eq!(d.status("a", 3000 + 1800), Status::Suspect);
        assert_eq!(d.status("a", 3000 + 3599), Status::Suspect);
        assert_eq!(d.level("a", 3000 + 3599), Some(2999));
        assert_eq!(d.status("a", 3000 + 3600), Status::Dead);
        assert_eq!(d.status("a", 1_000_000), Status::Dead);
        // a clock that is behind the last heartbeat counts as no time elapsed
        assert_eq!(d.level("a", 2500), Some(0));
        assert_eq!(d.status("a", 0), Status::Alive);
    }

    #[test]
    fn grace_widens_the_expected_interval() {
        let cfg = Config { grace_ms: 0, ..CFG };
        let mut d = Detector::new(cfg).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        assert_eq!(d.level("a", 3000 + 1500), Some(1500));
        assert_eq!(d.status("a", 3000 + 1499), Status::Alive);
        assert_eq!(d.status("a", 3000 + 1500), Status::Suspect);
        assert_eq!(d.status("a", 3000 + 3000), Status::Dead);
        let cfg = Config { grace_ms: 1000, ..CFG };
        let mut d = Detector::new(cfg).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        assert_eq!(d.level("a", 3000 + 1000), Some(500));
        assert_eq!(d.status("a", 3000 + 2999), Status::Alive);
        assert_eq!(d.status("a", 3000 + 3000), Status::Suspect);
    }

    #[test]
    fn tiny_intervals_work_without_grace() {
        let cfg = Config { grace_ms: 0, ..CFG };
        let mut d = Detector::new(cfg).unwrap();
        for t in [0, 1, 2, 3] {
            d.heartbeat("fast", t).unwrap();
        }
        assert_eq!(d.expected("fast"), Some(1));
        assert_eq!(d.level("fast", 3), Some(0));
        assert_eq!(d.level("fast", 4), Some(1000));
    }

    #[test]
    fn window_keeps_only_the_newest_intervals() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4); // 3 intervals of 1000, last 3000
        let mut t = 3000;
        for _ in 0..5 {
            t += 2000;
            d.heartbeat("a", t).unwrap();
        }
        assert_eq!(d.expected("a"), Some(2000));
        // one more: window of 5 slides
        t += 4000;
        d.heartbeat("a", t).unwrap();
        assert_eq!(d.expected("a"), Some((4 * 2000 + 4000) / 5));
        // mean rounds down
        d.heartbeat("a", t + 1).unwrap();
        assert_eq!(d.expected("a"), Some((3 * 2000 + 4000 + 1) / 5));
    }

    #[test]
    fn duplicates_and_out_of_order() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 100, 1000, 4);
        assert_eq!(d.heartbeat("a", 3100), Ok(()));
        assert_eq!(d.expected("a"), Some(1000));
        assert_eq!(d.heartbeat("a", 3099), Err(WatchError::OutOfOrder));
        assert_eq!(d.heartbeat("a", 0), Err(WatchError::OutOfOrder));
        assert_eq!(d.expected("a"), Some(1000));
        assert_eq!(d.level("a", 3100), Some(0));
        // the first heartbeat of an id is accepted at any time, even 0
        assert_eq!(d.heartbeat("b", 0), Ok(()));
        assert_eq!(d.heartbeat("b", 0), Ok(()));
        assert_eq!(d.heartbeat("b", 5), Ok(()));
        assert_eq!(d.heartbeat("b", 4), Err(WatchError::OutOfOrder));
    }

    #[test]
    fn a_dead_node_starts_over() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        assert_eq!(d.status("a", 3000 + 5000), Status::Dead);
        d.heartbeat("a", 8000).unwrap();
        // history was cleared: the 5000 ms gap is not part of the mean, and the node is Unknown again
        assert_eq!(d.expected("a"), None);
        assert_eq!(d.status("a", 8000), Status::Unknown);
        steady(&mut d, "a", 9000, 1000, 3);
        assert_eq!(d.expected("a"), Some(1000));
        assert_eq!(d.status("a", 12_000), Status::Alive);
    }

    #[test]
    fn death_boundary_when_a_heartbeat_arrives() {
        // exactly at the dead level (3000 permille) -> history cleared
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        d.heartbeat("a", 3000 + 3600).unwrap();
        assert_eq!(d.expected("a"), None);
        // one millisecond earlier it is only Suspect: the gap is recorded
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        d.heartbeat("a", 3000 + 3599).unwrap();
        assert_eq!(d.expected("a"), Some((3 * 1000 + 3599) / 4));
        assert_eq!(d.status("a", 3000 + 3599), Status::Alive);
    }

    #[test]
    fn suspect_nodes_keep_their_history() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "a", 0, 1000, 4);
        assert_eq!(d.status("a", 3000 + 2000), Status::Suspect);
        d.heartbeat("a", 5000).unwrap();
        assert_eq!(d.expected("a"), Some((3 * 1000 + 2000) / 4));
        assert_eq!(d.status("a", 5100), Status::Alive);
    }

    #[test]
    fn dead_check_uses_the_state_before_the_heartbeat() {
        // a node with too little history cannot be dead: a late heartbeat is just recorded
        let mut d = Detector::new(CFG).unwrap();
        d.heartbeat("x", 0).unwrap();
        d.heartbeat("x", 1000).unwrap();
        d.heartbeat("x", 100_000).unwrap();
        d.heartbeat("x", 101_000).unwrap();
        assert_eq!(d.expected("x"), Some((1000 + 99_000 + 1000) / 3));
    }

    #[test]
    fn problems_lists_suspect_and_dead_sorted() {
        let mut d = Detector::new(CFG).unwrap();
        steady(&mut d, "zeta", 0, 1000, 4); // last 3000, expected 1000
        steady(&mut d, "alpha", 0, 500, 4); // last 1500, expected 500
        steady(&mut d, "mid", 0, 1000, 4);
        d.heartbeat("mid", 4500).unwrap(); // expected (3000 + 1500) / 4 = 1125
        steady(&mut d, "fresh", 2500, 100, 2); // a single interval: still unknown
        let now = 5000;
        assert_eq!(d.status("alpha", now), Status::Dead); // 3500 / 700 -> 5000 permille
        assert_eq!(d.status("zeta", now), Status::Suspect); // 2000 / 1200 -> 1666 permille
        assert_eq!(d.status("mid", now), Status::Alive);
        assert_eq!(d.status("fresh", now), Status::Unknown);
        assert_eq!(d.problems(now), vec![("alpha".to_string(), Status::Dead), ("zeta".to_string(), Status::Suspect)]);
        assert!(d.problems(1600).is_empty());
    }

    #[test]
    fn remove_and_len() {
        let mut d = Detector::new(CFG).unwrap();
        assert_eq!(d.len(), 0);
        steady(&mut d, "a", 0, 10, 4);
        d.heartbeat("b", 1).unwrap();
        assert_eq!(d.len(), 2);
        assert!(d.remove("a"));
        assert!(!d.remove("a"));
        assert!(!d.remove("never"));
        assert_eq!(d.len(), 1);
        assert_eq!(d.status("a", 99), Status::Unknown);
        // a removed node can register again from scratch, even with an earlier time
        d.heartbeat("a", 0).unwrap();
        assert_eq!(d.expected("a"), None);
    }
''')

LIB = Lib(
    name="pulsewatch", lang="rust", title="the pulsewatch crate",
    blurb="The cluster monitor judges which nodes are late with pulsewatch, a heartbeat failure detector that learns each node's rhythm.",
    files={"Cargo.toml": cargo("pulsewatch"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=2, tags=["monitoring", "failure-detector", "state"],
)

register_libs([LIB], n=8)
