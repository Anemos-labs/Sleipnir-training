"""Job-graph planning (rust): ordering, waves, slack, critical path and list scheduling on k workers."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # jobdag

    Planning for a build farm: jobs have a cost (in seconds) and a list of jobs that must finish first. A `Plan` answers *in what order*, *how
    long at least*, *what can slip*, and *who runs what* on a pool of workers.

    ```rust
    pub enum PlanError { Duplicate(String), SelfDep(String), UnknownDep(String, String), Cycle(Vec<String>), ZeroWorkers }
    pub struct Timing { pub name: String, pub start: u32, pub finish: u32, pub slack: u32 }
    pub struct Slot { pub job: String, pub worker: usize, pub start: u32, pub end: u32 }
    pub struct Schedule { pub slots: Vec<Slot>, pub makespan: u32, pub workers: usize }
    ```

    ## Building a plan
    `Plan::new()`, then `add(&mut self, name: &str, cost: u32, deps: &[&str]) -> Result<(), PlanError>`. `Duplicate(name)` if a job of that name
    exists already (checked first), `SelfDep(name)` if `name` is among its own deps. Repeating a dependency in `deps` counts once. A dep may name a
    job that is added later; names are only resolved when the plan is analysed.

    Every analysis below first checks the plan: the first job in insertion order that has an unknown dependency (its deps taken in the order
    given) is reported as `UnknownDep(job, dep)`; then, if the jobs cannot all be ordered, `Cycle(names)` lists every job that could not be
    placed, which includes jobs that merely depend on a cycle, sorted by name.

    ## Analyses
    * `order(&self) -> Result<Vec<String>, PlanError>`: a valid execution order built greedily: repeatedly take, among the jobs whose deps are all
      placed already, the one with the smallest name.
    * `waves(&self) -> Result<Vec<Vec<String>>, PlanError>`: the depth of a job is 0 without deps, otherwise 1 + the largest depth among its deps;
      wave `k` holds the jobs of depth `k`, sorted by name. An empty plan has no waves.
    * `timing(&self) -> Result<Vec<Timing>, PlanError>`: one entry per job, in `order()` order, for an unlimited number of workers. `start` is the
      largest `finish` among its deps (0 without deps) and `finish = start + cost`. The plan's length is the largest finish (0 when empty). The
      latest finish of a job is the plan's length if nothing depends on it, otherwise the smallest *latest start* (latest finish minus cost)
      among the jobs that depend on it; `slack` is its latest finish minus its finish.
    * `critical_path(&self) -> Result<(u32, Vec<String>), PlanError>`: the plan's length and one longest chain, first job first. The chain ends at
      the job whose `finish` equals the plan's length (smallest name if several). From a job it continues to the dep whose `finish` equals the
      job's `start` (smallest name if several), and stops at a job that has no deps. An empty plan gives `(0, vec![])`.
    * `schedule(&self, workers: usize) -> Result<Schedule, PlanError>`: list scheduling on `workers` identical workers numbered from 0.
      `ZeroWorkers` if `workers == 0` (checked before the plan). The *priority* of a job is its cost plus the largest priority among the jobs that
      depend on it. The clock starts at 0. At each instant, as long as some worker is free (its last job ended at or before now) and some job is
      ready (not started, all deps ended at or before now), the ready job with the highest priority (smallest name on ties) starts on the
      lowest-numbered free worker; zero-cost jobs therefore end at once and may release more jobs at the same instant. When nothing more can start the
      clock jumps to the earliest end that lies after now. `slots` are listed in the order jobs were started, `makespan` is the latest end (0 if empty).
    * `Schedule::utilisation_permille(&self) -> u64`: total busy time of all slots * 1000 / (makespan * workers), rounded down; 0 when the makespan is 0.
''')

SRC = dd('''
    //! Build-farm job planning.

    use std::collections::HashMap;

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub enum PlanError {
        Duplicate(String),
        SelfDep(String),
        UnknownDep(String, String),
        Cycle(Vec<String>),
        ZeroWorkers,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Timing {
        pub name: String,
        pub start: u32,
        pub finish: u32,
        pub slack: u32,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Slot {
        pub job: String,
        pub worker: usize,
        pub start: u32,
        pub end: u32,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Schedule {
        pub slots: Vec<Slot>,
        pub makespan: u32,
        pub workers: usize,
    }

    impl Schedule {
        pub fn utilisation_permille(&self) -> u64 {
            if self.makespan == 0 {
                return 0;
            }
            let busy: u64 = self.slots.iter().map(|s| (s.end - s.start) as u64).sum();
            busy * 1000 / (self.makespan as u64 * self.workers as u64)
        }
    }

    #[derive(Debug, Clone)]
    struct Job {
        name: String,
        cost: u32,
        deps: Vec<String>,
    }

    struct Times {
        order: Vec<usize>,
        deps: Vec<Vec<usize>>,
        start: Vec<u32>,
        finish: Vec<u32>,
        slack: Vec<u32>,
        length: u32,
    }

    #[derive(Debug, Clone, Default)]
    pub struct Plan {
        jobs: Vec<Job>,
    }

    impl Plan {
        pub fn new() -> Plan {
            Plan { jobs: Vec::new() }
        }

        pub fn add(&mut self, name: &str, cost: u32, deps: &[&str]) -> Result<(), PlanError> {
            if self.jobs.iter().any(|j| j.name == name) {
                return Err(PlanError::Duplicate(name.to_string()));
            }
            if deps.contains(&name) {
                return Err(PlanError::SelfDep(name.to_string()));
            }
            let mut list: Vec<String> = Vec::new();
            for d in deps {
                if !list.iter().any(|x| x == d) {
                    list.push(d.to_string());
                }
            }
            self.jobs.push(Job { name: name.to_string(), cost, deps: list });
            Ok(())
        }

        fn graph(&self) -> Result<Vec<Vec<usize>>, PlanError> {
            let index: HashMap<&str, usize> = self.jobs.iter().enumerate().map(|(i, j)| (j.name.as_str(), i)).collect();
            let mut deps = Vec::new();
            for j in &self.jobs {
                let mut v = Vec::new();
                for d in &j.deps {
                    match index.get(d.as_str()) {
                        Some(&i) => v.push(i),
                        None => return Err(PlanError::UnknownDep(j.name.clone(), d.clone())),
                    }
                }
                deps.push(v);
            }
            Ok(deps)
        }

        fn topo(&self, deps: &[Vec<usize>]) -> Result<Vec<usize>, PlanError> {
            let n = self.jobs.len();
            let mut done = vec![false; n];
            let mut order = Vec::new();
            loop {
                let mut best: Option<usize> = None;
                for i in 0..n {
                    if done[i] || !deps[i].iter().all(|&d| done[d]) {
                        continue;
                    }
                    if best.map_or(true, |b| self.jobs[i].name < self.jobs[b].name) {
                        best = Some(i);
                    }
                }
                match best {
                    Some(i) => {
                        done[i] = true;
                        order.push(i);
                    }
                    None => break,
                }
            }
            if order.len() < n {
                let mut left: Vec<String> = (0..n).filter(|&i| !done[i]).map(|i| self.jobs[i].name.clone()).collect();
                left.sort();
                return Err(PlanError::Cycle(left));
            }
            Ok(order)
        }

        fn times(&self) -> Result<Times, PlanError> {
            let deps = self.graph()?;
            let order = self.topo(&deps)?;
            let n = self.jobs.len();
            let mut start = vec![0u32; n];
            let mut finish = vec![0u32; n];
            for &i in &order {
                start[i] = deps[i].iter().map(|&d| finish[d]).max().unwrap_or(0);
                finish[i] = start[i] + self.jobs[i].cost;
            }
            let length = finish.iter().copied().max().unwrap_or(0);
            let mut latest = vec![length; n];
            for &i in order.iter().rev() {
                let latest_start = latest[i] - self.jobs[i].cost;
                for &d in &deps[i] {
                    latest[d] = latest[d].min(latest_start);
                }
            }
            let slack = (0..n).map(|i| latest[i] - finish[i]).collect();
            Ok(Times { order, deps, start, finish, slack, length })
        }

        pub fn order(&self) -> Result<Vec<String>, PlanError> {
            let deps = self.graph()?;
            let order = self.topo(&deps)?;
            Ok(order.into_iter().map(|i| self.jobs[i].name.clone()).collect())
        }

        pub fn waves(&self) -> Result<Vec<Vec<String>>, PlanError> {
            let deps = self.graph()?;
            let order = self.topo(&deps)?;
            let mut depth = vec![0usize; self.jobs.len()];
            for &i in &order {
                depth[i] = deps[i].iter().map(|&d| depth[d] + 1).max().unwrap_or(0);
            }
            let mut waves: Vec<Vec<String>> = Vec::new();
            for i in 0..self.jobs.len() {
                while waves.len() <= depth[i] {
                    waves.push(Vec::new());
                }
                waves[depth[i]].push(self.jobs[i].name.clone());
            }
            for w in waves.iter_mut() {
                w.sort();
            }
            Ok(waves)
        }

        pub fn timing(&self) -> Result<Vec<Timing>, PlanError> {
            let t = self.times()?;
            Ok(t.order
                .iter()
                .map(|&i| Timing { name: self.jobs[i].name.clone(), start: t.start[i], finish: t.finish[i], slack: t.slack[i] })
                .collect())
        }

        pub fn critical_path(&self) -> Result<(u32, Vec<String>), PlanError> {
            let t = self.times()?;
            if self.jobs.is_empty() {
                return Ok((0, Vec::new()));
            }
            let by_name = |a: &usize, b: &usize| self.jobs[*a].name.cmp(&self.jobs[*b].name);
            let mut cur = (0..self.jobs.len()).filter(|&i| t.finish[i] == t.length).min_by(by_name).unwrap();
            let mut path = vec![cur];
            while let Some(d) = t.deps[cur].iter().copied().filter(|&d| t.finish[d] == t.start[cur]).min_by(by_name) {
                path.push(d);
                cur = d;
            }
            path.reverse();
            Ok((t.length, path.into_iter().map(|i| self.jobs[i].name.clone()).collect()))
        }

        pub fn schedule(&self, workers: usize) -> Result<Schedule, PlanError> {
            if workers == 0 {
                return Err(PlanError::ZeroWorkers);
            }
            let deps = self.graph()?;
            let order = self.topo(&deps)?;
            let n = self.jobs.len();
            let mut priority = vec![0u32; n];
            for &i in order.iter().rev() {
                let mut tail = 0;
                for j in 0..n {
                    if deps[j].contains(&i) {
                        tail = tail.max(priority[j]);
                    }
                }
                priority[i] = self.jobs[i].cost + tail;
            }
            let mut end_of: Vec<Option<u32>> = vec![None; n];
            let mut busy_until = vec![0u32; workers];
            let mut slots: Vec<Slot> = Vec::new();
            let mut now = 0u32;
            while slots.len() < n {
                loop {
                    let free = match (0..workers).find(|&w| busy_until[w] <= now) {
                        Some(w) => w,
                        None => break,
                    };
                    let mut pick: Option<usize> = None;
                    for i in 0..n {
                        if end_of[i].is_some() || !deps[i].iter().all(|&d| matches!(end_of[d], Some(e) if e <= now)) {
                            continue;
                        }
                        let better = match pick {
                            None => true,
                            Some(b) => priority[i] > priority[b] || (priority[i] == priority[b] && self.jobs[i].name < self.jobs[b].name),
                        };
                        if better {
                            pick = Some(i);
                        }
                    }
                    let i = match pick {
                        Some(i) => i,
                        None => break,
                    };
                    let end = now + self.jobs[i].cost;
                    end_of[i] = Some(end);
                    busy_until[free] = end;
                    slots.push(Slot { job: self.jobs[i].name.clone(), worker: free, start: now, end });
                }
                if slots.len() == n {
                    break;
                }
                now = busy_until.iter().copied().filter(|&b| b > now).min().expect("a job is still running");
            }
            let makespan = slots.iter().map(|s| s.end).max().unwrap_or(0);
            Ok(Schedule { slots, makespan, workers })
        }
    }
''')

VISIBLE = dd('''
    use jobdag::*;

    fn plan(spec: &str) -> Plan {
        let mut p = Plan::new();
        for tok in spec.split_whitespace() {
            let (head, deps) = match tok.split_once('<') {
                Some((h, d)) => (h, d.split(',').collect::<Vec<_>>()),
                None => (tok, Vec::new()),
            };
            let (name, cost) = head.split_once(':').unwrap();
            p.add(name, cost.parse().unwrap(), &deps).unwrap();
        }
        p
    }

    #[test]
    fn order_respects_dependencies() {
        let p = plan("link:2<compile,assets compile:5 assets:1");
        assert_eq!(p.order().unwrap(), vec!["assets", "compile", "link"]);
    }

    #[test]
    fn duplicate_and_self_dependency() {
        let mut p = Plan::new();
        p.add("a", 1, &[]).unwrap();
        assert_eq!(p.add("a", 2, &[]), Err(PlanError::Duplicate("a".to_string())));
        assert_eq!(p.add("b", 2, &["b"]), Err(PlanError::SelfDep("b".to_string())));
    }

    #[test]
    fn critical_path_of_a_diamond() {
        let p = plan("a:3 b:2<a c:4<a d:1<b,c");
        assert_eq!(p.critical_path().unwrap(), (8, vec!["a".to_string(), "c".to_string(), "d".to_string()]));
    }

    #[test]
    fn zero_workers_is_an_error() {
        let p = plan("a:1");
        assert_eq!(p.schedule(0), Err(PlanError::ZeroWorkers));
    }
''')

HIDDEN = dd('''
    use jobdag::*;

    fn plan(spec: &str) -> Plan {
        let mut p = Plan::new();
        for tok in spec.split_whitespace() {
            let (head, deps) = match tok.split_once('<') {
                Some((h, d)) => (h, d.split(',').collect::<Vec<_>>()),
                None => (tok, Vec::new()),
            };
            let (name, cost) = head.split_once(':').unwrap();
            p.add(name, cost.parse().unwrap(), &deps).unwrap();
        }
        p
    }

    fn timing_str(p: &Plan) -> String {
        p.timing().unwrap().iter().map(|t| format!("{}:{}:{}:{}", t.name, t.start, t.finish, t.slack)).collect::<Vec<_>>().join(" ")
    }

    fn waves_str(p: &Plan) -> String {
        p.waves().unwrap().iter().map(|w| w.join(",")).collect::<Vec<_>>().join(" | ")
    }

    fn crit_str(p: &Plan) -> String {
        let (len, path) = p.critical_path().unwrap();
        format!("{} {}", len, path.join(" "))
    }

    fn sched_str(s: &Schedule) -> String {
        s.slots.iter().map(|x| format!("{}@{}:{}-{}", x.job, x.worker, x.start, x.end)).collect::<Vec<_>>().join(" ")
    }

    #[test]
    fn add_errors() {
        let mut p = Plan::new();
        p.add("a", 1, &[]).unwrap();
        assert_eq!(p.add("a", 5, &["x"]), Err(PlanError::Duplicate("a".to_string())));
        assert_eq!(p.add("a", 5, &["a"]), Err(PlanError::Duplicate("a".to_string())));
        assert_eq!(p.add("b", 5, &["x", "b"]), Err(PlanError::SelfDep("b".to_string())));
        // failed adds leave nothing behind
        assert_eq!(p.order().unwrap(), vec!["a"]);
        p.add("b", 2, &["a"]).unwrap();
        assert_eq!(p.order().unwrap(), vec!["a", "b"]);
    }

    #[test]
    fn order_ties_by_name_not_insertion() {
        let p = plan("d:1<b,c a:1 c:1<a b:1<a");
        assert_eq!(p.order().unwrap().join(" "), "a b c d");
    }

    #[test]
    fn order_independent_jobs() {
        let p = plan("z:1 y:1 x:1");
        assert_eq!(p.order().unwrap().join(" "), "x y z");
    }

    #[test]
    fn order_takes_smallest_ready_job() {
        let p = plan("a:1<z z:1 b:1");
        assert_eq!(p.order().unwrap().join(" "), "b z a");
    }

    #[test]
    fn order_with_shared_dependencies() {
        let p = plan("m:1<k,l k:1 l:1<k n:1");
        assert_eq!(p.order().unwrap().join(" "), "k l m n");
    }

    #[test]
    fn order_repeated_dependency_counts_once() {
        let p = plan("b:1<a,a,a a:1");
        assert_eq!(p.order().unwrap().join(" "), "a b");
    }

    #[test]
    fn order_interleaves_chains() {
        let p = plan("c:1<b b:1<a a:1 d:1 aa:1<d");
        assert_eq!(p.order().unwrap().join(" "), "a b c d aa");
    }

    #[test]
    fn order_long_chain_reversed() {
        let p = plan("x1:1<x2 x2:1<x3 x3:1 x0:1<x1");
        assert_eq!(p.order().unwrap().join(" "), "x3 x2 x1 x0");
    }

    #[test]
    fn forward_references_are_resolved_late() {
        let mut p = Plan::new();
        p.add("top", 2, &["mid"]).unwrap();
        p.add("mid", 2, &["base"]).unwrap();
        assert!(p.order().is_err());
        p.add("base", 1, &[]).unwrap();
        assert_eq!(p.order().unwrap(), vec!["base", "mid", "top"]);
    }

    #[test]
    fn unknown_dependency_reporting() {
        let mut p = Plan::new();
        p.add("b", 1, &["a", "q"]).unwrap();
        p.add("c", 1, &["zz"]).unwrap();
        // first job in insertion order, first unknown dep in the order given
        assert_eq!(p.order(), Err(PlanError::UnknownDep("b".to_string(), "a".to_string())));
        p.add("a", 1, &[]).unwrap();
        assert_eq!(p.order(), Err(PlanError::UnknownDep("b".to_string(), "q".to_string())));
        assert_eq!(p.waves(), Err(PlanError::UnknownDep("b".to_string(), "q".to_string())));
        assert_eq!(p.timing(), Err(PlanError::UnknownDep("b".to_string(), "q".to_string())));
        assert_eq!(p.critical_path(), Err(PlanError::UnknownDep("b".to_string(), "q".to_string())));
        assert_eq!(p.schedule(2), Err(PlanError::UnknownDep("b".to_string(), "q".to_string())));
        // an unknown dependency is reported before a cycle
        let mut p = Plan::new();
        p.add("x", 1, &["y"]).unwrap();
        p.add("y", 1, &["x"]).unwrap();
        p.add("w", 1, &["nope"]).unwrap();
        assert_eq!(p.order(), Err(PlanError::UnknownDep("w".to_string(), "nope".to_string())));
    }

    fn cyc(names: &[&str]) -> PlanError {
        PlanError::Cycle(names.iter().map(|s| s.to_string()).collect())
    }

    #[test]
    fn cycles_list_everything_unplaced() {
        let p = plan("a:1<c b:1<a c:1<b x:1 y:1<a z:1<y");
        let err = cyc(&["a", "b", "c", "y", "z"]);
        assert_eq!(p.order().unwrap_err(), err);
        assert_eq!(p.waves().unwrap_err(), err);
        assert_eq!(p.timing().unwrap_err(), err);
        assert_eq!(p.critical_path().unwrap_err(), err);
        assert_eq!(p.schedule(3).unwrap_err(), err);
        // two independent cycles
        let p = plan("q:1<r r:1<q m:1<n n:1<m ok:1");
        assert_eq!(p.order().unwrap_err(), cyc(&["m", "n", "q", "r"]));
        // a job that depends on a cycle member is part of the report, one that a cycle member depends on is not
        let p = plan("a:1<b b:1<a root:1 c:1<root,a");
        assert_eq!(p.order().unwrap_err(), cyc(&["a", "b", "c"]));
    }

    #[test]
    fn waves_of_a_diamond() {
        let p = plan("a:1 b:1<a c:1<a d:1<b,c");
        assert_eq!(waves_str(&p), "a | b,c | d");
    }

    #[test]
    fn waves_use_the_longest_chain() {
        let p = plan("a:1 b:1 c:1<a d:1<c e:1<d,b f:1");
        assert_eq!(waves_str(&p), "a,b,f | c | d | e");
    }

    #[test]
    fn waves_sorted_within_each_level() {
        let p = plan("z:1 y:1<z x:1<y,a a:1 w:1<z,y");
        assert_eq!(waves_str(&p), "a,z | y | w,x");
    }

    #[test]
    fn waves_of_a_reversed_chain() {
        let p = plan("c:1<b b:1<a a:1");
        assert_eq!(waves_str(&p), "a | b | c");
    }

    #[test]
    fn waves_single_level() {
        let p = plan("q:1 p:1");
        assert_eq!(waves_str(&p), "p,q");
    }

    #[test]
    fn timing_of_a_diamond() {
        let p = plan("a:3 b:2<a c:4<a d:1<b,c");
        assert_eq!(timing_str(&p), "a:0:3:0 b:3:5:2 c:3:7:0 d:7:8:0");
    }

    #[test]
    fn timing_with_several_branches() {
        let p = plan("a:2 b:3 c:1<a,b d:4<c e:2<c f:1");
        assert_eq!(timing_str(&p), "a:0:2:1 b:0:3:0 c:3:4:0 d:4:8:0 e:4:6:2 f:0:1:7");
    }

    #[test]
    fn timing_with_zero_cost_jobs() {
        let p = plan("a:0 b:0<a c:5<b d:0<c e:2");
        assert_eq!(timing_str(&p), "a:0:0:0 b:0:0:0 c:0:5:0 d:5:5:0 e:0:2:3");
    }

    #[test]
    fn timing_slack_uses_the_tightest_dependent() {
        let p = plan("a:1 b:2<a c:5<a d:1<b e:1<c");
        assert_eq!(timing_str(&p), "a:0:1:0 b:1:3:3 c:1:6:0 d:3:4:3 e:6:7:0");
    }

    #[test]
    fn timing_of_parallel_roots() {
        let p = plan("x:4 y:4 z:1<x,y");
        assert_eq!(timing_str(&p), "x:0:4:0 y:0:4:0 z:4:5:0");
    }

    #[test]
    fn timing_of_a_single_job() {
        let p = plan("solo:7");
        assert_eq!(timing_str(&p), "solo:0:7:0");
    }

    #[test]
    fn timing_with_unequal_branches() {
        let p = plan("p:6 q:2 r:3<q s:1<p,r t:2<r");
        assert_eq!(timing_str(&p), "p:0:6:0 q:0:2:0 r:2:5:0 s:6:7:0 t:5:7:0");
    }

    #[test]
    fn critical_path_of_a_diamond() {
        let p = plan("a:3 b:2<a c:4<a d:1<b,c");
        assert_eq!(crit_str(&p), "8 a c d");
    }

    #[test]
    fn critical_path_tie_between_branches() {
        let p = plan("a:2 b:2 c:3<a d:3<b e:1<c,d");
        assert_eq!(crit_str(&p), "6 a c e");
    }

    #[test]
    fn critical_path_tie_between_ends() {
        let p = plan("p:5 q:5 r:2");
        assert_eq!(crit_str(&p), "5 p");
    }

    #[test]
    fn critical_path_with_zero_cost_tail() {
        let p = plan("a:4 b:0<a c:0<b d:3 e:1<d");
        assert_eq!(crit_str(&p), "4 a");
    }

    #[test]
    fn critical_path_ignores_short_dependency() {
        let p = plan("a:1 b:10 c:1<a,b");
        assert_eq!(crit_str(&p), "11 b c");
    }

    #[test]
    fn critical_path_follows_exact_finish() {
        let p = plan("a:5 b:3 c:2<a,b");
        assert_eq!(crit_str(&p), "7 a c");
    }

    #[test]
    fn critical_path_of_a_long_chain() {
        let p = plan("k:2<j j:3<i i:4 h:9");
        assert_eq!(crit_str(&p), "9 h");
    }

    #[test]
    fn critical_path_all_free() {
        let p = plan("a:0 b:0<a");
        assert_eq!(crit_str(&p), "0 a");
    }

    #[test]
    fn schedule_diamond() {
        let p = plan("a:3 b:2<a c:4<a d:1<b,c");
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-3 c@0:3-7 b@0:7-9 d@0:9-10");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (10, 1, 1000));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-3 c@0:3-7 b@1:3-5 d@0:7-8");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (8, 2, 625));
        let s = p.schedule(3).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-3 c@0:3-7 b@1:3-5 d@0:7-8");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (8, 3, 416));
        let s = p.schedule(8).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-3 c@0:3-7 b@1:3-5 d@0:7-8");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (8, 8, 156));
    }

    #[test]
    fn schedule_priorities() {
        let p = plan("a:5 b:3 c:4 d:2 e:6");
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "e@0:0-6 a@1:0-5 c@1:5-9 b@0:6-9 d@0:9-11");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (11, 2, 909));
        let s = p.schedule(3).unwrap();
        assert_eq!(sched_str(&s), "e@0:0-6 a@1:0-5 c@2:0-4 b@2:4-7 d@1:5-7");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (7, 3, 952));
    }

    #[test]
    fn schedule_equal_priorities_use_names() {
        let p = plan("d:2 b:2 c:2 a:2");
        let s = p.schedule(3).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-2 b@1:0-2 c@2:0-2 d@0:2-4");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (4, 3, 666));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-2 b@1:0-2 c@0:2-4 d@1:2-4");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (4, 2, 1000));
    }

    #[test]
    fn schedule_zero_cost_jobs() {
        let p = plan("a:0 b:0<a c:3<b d:2 z:0");
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-0 b@0:0-0 c@0:0-3 d@0:3-5 z@0:5-5");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (5, 1, 1000));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-0 b@0:0-0 c@0:0-3 d@1:0-2 z@1:2-2");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (3, 2, 833));
    }

    #[test]
    fn schedule_prefers_the_long_tail() {
        let p = plan("a:1 b:1 c:1<a e:10<b");
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "b@0:0-1 e@0:1-11 a@0:11-12 c@0:12-13");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (13, 1, 1000));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "b@0:0-1 a@1:0-1 e@0:1-11 c@1:1-2");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (11, 2, 590));
    }

    #[test]
    fn schedule_more_workers_than_jobs() {
        let p = plan("a:1 b:2");
        let s = p.schedule(5).unwrap();
        assert_eq!(sched_str(&s), "b@0:0-2 a@1:0-1");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (2, 5, 300));
    }

    #[test]
    fn schedule_fan_out_and_in() {
        let p = plan("src:2 w1:3<src w2:3<src w3:3<src w4:3<src sink:1<w1,w2,w3,w4");
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "src@0:0-2 w1@0:2-5 w2@0:5-8 w3@0:8-11 w4@0:11-14 sink@0:14-15");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (15, 1, 1000));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "src@0:0-2 w1@0:2-5 w2@1:2-5 w3@0:5-8 w4@1:5-8 sink@0:8-9");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (9, 2, 833));
        let s = p.schedule(3).unwrap();
        assert_eq!(sched_str(&s), "src@0:0-2 w1@0:2-5 w2@1:2-5 w3@2:2-5 w4@0:5-8 sink@0:8-9");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (9, 3, 555));
        let s = p.schedule(4).unwrap();
        assert_eq!(sched_str(&s), "src@0:0-2 w1@0:2-5 w2@1:2-5 w3@2:2-5 w4@3:2-5 sink@0:5-6");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (6, 4, 625));
    }

    #[test]
    fn schedule_waits_for_all_dependencies() {
        let p = plan("a:2 b:5 c:1<a,b d:1<a");
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "b@0:0-5 a@1:0-2 d@1:2-3 c@0:5-6");
        assert_eq!((s.makespan, s.workers, s.utilisation_permille()), (6, 2, 750));
    }

    #[test]
    fn schedule_priority_counts_every_dependent() {
        // "b" is the first job added and depends on a job added after it
        let p = plan("b:5<a a:1 c:3");
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-1 b@0:1-6 c@0:6-9");
        assert_eq!((s.makespan, s.utilisation_permille()), (9, 1000));
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "a@0:0-1 c@1:0-3 b@0:1-6");
        assert_eq!((s.makespan, s.utilisation_permille()), (6, 750));
    }

    #[test]
    fn empty_plan() {
        let p = Plan::new();
        assert!(p.order().unwrap().is_empty());
        assert!(p.waves().unwrap().is_empty());
        assert!(p.timing().unwrap().is_empty());
        assert_eq!(p.critical_path().unwrap(), (0, vec![]));
        let s = p.schedule(3).unwrap();
        assert!(s.slots.is_empty());
        assert_eq!(s.makespan, 0);
        assert_eq!(s.workers, 3);
        assert_eq!(s.utilisation_permille(), 0);
    }

    #[test]
    fn zero_workers_come_first() {
        assert_eq!(Plan::new().schedule(0), Err(PlanError::ZeroWorkers));
        let p = plan("a:1<b b:1<a");
        assert_eq!(p.schedule(0), Err(PlanError::ZeroWorkers));
        let mut p = Plan::new();
        p.add("a", 1, &["ghost"]).unwrap();
        assert_eq!(p.schedule(0), Err(PlanError::ZeroWorkers));
    }

    const BIG: &str = "j15:0<j01,j09,j11 j09:3<j00,j06,j08 j06:3<j00,j03 j20:5<j09,j15,j16 j01:2 j19:1<j07 j23:2<j10 j24:1<j01,j13 j14:1<j03,j05,j10 j18:3<j09,j11 j00:5 j21:1<j09,j19 j32:5<j29 j03:0 j16:9<j06,j07,j10 j33:8<j07 j02:6 j27:1<j26 j07:6<j04 j30:4<j14,j21,j26 j11:9<j02,j06 j35:6<j15 j22:6<j16 j34:4<j13 j29:4<j23 j13:12<j01,j02,j10 j26:8<j15,j18,j25 j04:5<j00 j08:3<j01 j17:12<j10,j14 j12:4<j09 j28:1<j15,j22 j10:2<j08 j05:1<j00,j01,j04 j31:5<j21,j28 j25:5<j10,j18,j22";



    #[test]
    fn big_plan_order_and_waves() {
        let p = plan(BIG);

        assert_eq!(p.order().unwrap().join(" "), "j00 j01 j02 j03 j04 j05 j06 j07 j08 j09 j10 j11 j12 j13 j14 j15 j16 j17 j18 j19 j20 j21 j22 j23 j24 j25 j26 j27 j28 j29 j30 j31 j32 j33 j34 j35");

        assert_eq!(waves_str(&p), "j00,j01,j02,j03 | j04,j06,j08 | j05,j07,j09,j10,j11 | j12,j13,j14,j15,j16,j18,j19,j23,j33 | j17,j20,j21,j22,j24,j29,j34,j35 | j25,j28,j32 | j26,j31 | j27,j30");
    }

    #[test]
    fn big_plan_timing() {
        let p = plan(BIG);
        assert_eq!(timing_str(&p), "j00:0:5:0 j01:0:2:9 j02:0:6:13 j03:0:0:13 j04:5:10:0 j05:10:11:24 j06:5:8:8 j07:10:16:0 j08:2:5:9 j09:8:11:17 j10:5:7:9 j11:8:17:11 j12:11:15:33 j13:7:19:25 j14:11:12:24 j15:17:17:19 j16:16:25:0 j17:12:24:24 j18:17:20:11 j19:16:17:25 j20:25:30:18 j21:17:18:25 j22:25:31:0 j23:7:9:30 j24:19:20:28 j25:31:36:0 j26:36:44:0 j27:44:45:3 j28:31:32:11 j29:9:13:30 j30:44:48:0 j31:32:37:11 j32:13:18:30 j33:16:24:24 j34:19:23:25 j35:17:23:25");
        assert_eq!(crit_str(&p), "48 j00 j04 j07 j16 j22 j25 j26 j30");
    }

    #[test]
    fn big_plan_on_1_workers() {
        let p = plan(BIG);
        let s = p.schedule(1).unwrap();
        assert_eq!(sched_str(&s), "j00@0:0-5 j04@0:5-10 j01@0:10-12 j07@0:12-18 j08@0:18-21 j02@0:21-27 j03@0:27-27 j06@0:27-30 j10@0:30-32 j16@0:32-41 j11@0:41-50 j09@0:50-53 j22@0:53-59 j18@0:59-62 j25@0:62-67 j13@0:67-79 j05@0:79-80 j14@0:80-81 j15@0:81-81 j17@0:81-93 j26@0:93-101 j23@0:101-103 j29@0:103-107 j33@0:107-115 j19@0:115-116 j21@0:116-117 j28@0:117-118 j35@0:118-124 j20@0:124-129 j31@0:129-134 j32@0:134-139 j12@0:139-143 j30@0:143-147 j34@0:147-151 j24@0:151-152 j27@0:152-153");
        assert_eq!((s.makespan, s.utilisation_permille()), (153, 1000));
    }

    #[test]
    fn big_plan_on_2_workers() {
        let p = plan(BIG);
        let s = p.schedule(2).unwrap();
        assert_eq!(sched_str(&s), "j00@0:0-5 j01@1:0-2 j08@1:2-5 j04@0:5-10 j02@1:5-11 j07@0:10-16 j03@1:11-11 j06@1:11-14 j10@1:14-16 j16@0:16-25 j11@1:16-25 j09@0:25-28 j22@1:25-31 j18@0:28-31 j25@0:31-36 j13@1:31-43 j05@0:36-37 j14@0:37-38 j15@0:38-38 j17@0:38-50 j26@1:43-51 j23@0:50-52 j33@1:51-59 j29@0:52-56 j19@0:56-57 j21@0:57-58 j28@0:58-59 j35@0:59-65 j20@1:59-64 j31@1:64-69 j32@0:65-70 j12@1:69-73 j30@0:70-74 j34@1:73-77 j24@0:74-75 j27@0:75-76");
        assert_eq!((s.makespan, s.utilisation_permille()), (77, 993));
    }

    #[test]
    fn big_plan_on_3_workers() {
        let p = plan(BIG);
        let s = p.schedule(3).unwrap();
        assert_eq!(sched_str(&s), "j00@0:0-5 j01@1:0-2 j02@2:0-6 j08@1:2-5 j04@0:5-10 j03@1:5-5 j06@1:5-8 j10@2:6-8 j11@1:8-17 j09@2:8-11 j07@0:10-16 j13@2:11-23 j16@0:16-25 j18@1:17-20 j05@1:20-21 j14@1:21-22 j15@1:22-22 j17@1:22-34 j23@2:23-25 j22@0:25-31 j29@2:25-29 j33@2:29-37 j25@0:31-36 j19@1:34-35 j21@1:35-36 j26@0:36-44 j28@1:36-37 j35@1:37-43 j20@2:37-42 j31@2:42-47 j32@1:43-48 j12@0:44-48 j30@2:47-51 j34@0:48-52 j24@1:48-49 j27@1:49-50");
        assert_eq!((s.makespan, s.utilisation_permille()), (52, 980));
    }

    #[test]
    fn big_plan_on_5_workers() {
        let p = plan(BIG);
        let s = p.schedule(5).unwrap();
        assert_eq!(sched_str(&s), "j00@0:0-5 j01@1:0-2 j02@2:0-6 j03@3:0-0 j08@1:2-5 j04@0:5-10 j06@1:5-8 j10@3:5-7 j13@2:7-19 j23@3:7-9 j11@1:8-17 j09@4:8-11 j29@3:9-13 j07@0:10-16 j05@4:11-12 j14@4:12-13 j17@3:13-25 j32@4:13-18 j16@0:16-25 j18@1:17-20 j15@4:18-18 j33@4:18-26 j19@2:19-20 j21@1:20-21 j35@2:20-26 j12@1:21-25 j22@0:25-31 j20@1:25-30 j34@3:25-29 j24@2:26-27 j25@0:31-36 j28@1:31-32 j31@1:32-37 j26@0:36-44 j30@0:44-48 j27@1:44-45");
        assert_eq!((s.makespan, s.utilisation_permille()), (48, 637));
    }
''')

LIB = Lib(
    name="jobdag", lang="rust", title="the jobdag crate",
    blurb="The build farm plans its jobs with jobdag: execution order, slack, the critical path and a list schedule on a pool of workers.",
    files={"Cargo.toml": cargo("jobdag"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["scheduling", "graphs", "build"],
)

register_libs([LIB], n=8)
