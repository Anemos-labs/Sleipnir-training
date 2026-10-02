"""Weighted fair queue (rust): self-clocked virtual finish tags, a strict-priority class, per-flow limits."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # fairq

    The egress scheduler of a software switch: several flows share one link and each gets a share proportional to its weight.
    Packets are only *described* here (id and size); the crate decides the order in which they leave. Integer arithmetic only.

    ## Flows
    `FairQueue::new()`. `add_flow(&mut self, id: u32, weight: u32, class: Class, max_packets: usize) -> Result<(), QueueError>` registers a
    flow. `Class` is `High` or `Normal`. Errors, in this order: `BadWeight` (weight 0), `BadLimit` (`max_packets` 0), `Duplicate` (id already
    registered).

    ## Enqueueing
    `enqueue(&mut self, flow: u32, packet: u64, size: u32) -> Result<(), QueueError>`. Errors in this order: `UnknownFlow`, `ZeroSize`
    (`size == 0`), `Full` (the flow already holds `max_packets` packets).

    Every accepted packet gets a *virtual finish tag*. Each class has its own virtual clock `vtime` (starting at 0) and each flow remembers
    the finish tag of its latest packet (starting at 0):

    `start = max(vtime[class of the flow], flow's last finish)`, `finish = start + size * 1000 / weight` (integer division, truncating, computed
    per packet), and the flow's last finish becomes `finish`.

    Packets are also numbered 1, 2, 3, ... in the order they are accepted (across all flows); this number breaks ties.

    ## Dequeueing
    `dequeue(&mut self) -> Option<Served>` with `Served { flow: u32, packet: u64, size: u32, finish: u64 }`:

    1. if any `High` flow has packets, only `High` flows compete, otherwise only `Normal` flows (strict priority);
    2. among the competing flows' *oldest* packets, the one with the smallest `(finish, acceptance number)` leaves;
    3. the clock of that class is set to the `finish` of the packet that left (it may move backwards of other tags, never mind: this is
       self-clocking) and the flow's served-byte counter grows by the packet's size.

    `None` when nothing is queued. Within one flow packets always leave in the order they arrived.

    ## Inspection
    * `backlog(&self, flow: u32) -> Option<(usize, u64)>`: packets and bytes queued (`None` for an unknown flow).
    * `served_bytes(&self, flow: u32) -> Option<u64>`: total bytes of its packets that have left.
    * `virtual_time(&self, class: Class) -> u64`.
    * `len(&self) -> usize` and `is_empty(&self) -> bool`: total queued packets.
    * `remove_flow(&mut self, flow: u32) -> Result<(), QueueError>`: `UnknownFlow`, or `NotEmpty` if packets are still queued; otherwise the flow
      and its history disappear.
''')

SRC = dd('''
    //! A self-clocked weighted fair queue with a strict-priority class.
    use std::collections::{BTreeMap, VecDeque};

    const SCALE: u64 = 1000;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Class {
        High,
        Normal,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum QueueError {
        BadWeight,
        BadLimit,
        Duplicate,
        UnknownFlow,
        ZeroSize,
        Full,
        NotEmpty,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Served {
        pub flow: u32,
        pub packet: u64,
        pub size: u32,
        pub finish: u64,
    }

    #[derive(Debug)]
    struct Packet {
        id: u64,
        size: u32,
        finish: u64,
        number: u64,
    }

    #[derive(Debug)]
    struct Flow {
        weight: u32,
        class: Class,
        limit: usize,
        last_finish: u64,
        queue: VecDeque<Packet>,
        queued_bytes: u64,
        served_bytes: u64,
    }

    #[derive(Debug, Default)]
    pub struct FairQueue {
        flows: BTreeMap<u32, Flow>,
        vtime_high: u64,
        vtime_normal: u64,
        accepted: u64,
    }

    impl FairQueue {
        pub fn new() -> FairQueue {
            FairQueue::default()
        }

        pub fn add_flow(&mut self, id: u32, weight: u32, class: Class, max_packets: usize) -> Result<(), QueueError> {
            if weight == 0 {
                return Err(QueueError::BadWeight);
            }
            if max_packets == 0 {
                return Err(QueueError::BadLimit);
            }
            if self.flows.contains_key(&id) {
                return Err(QueueError::Duplicate);
            }
            let flow = Flow {
                weight,
                class,
                limit: max_packets,
                last_finish: 0,
                queue: VecDeque::new(),
                queued_bytes: 0,
                served_bytes: 0,
            };
            self.flows.insert(id, flow);
            Ok(())
        }

        fn clock(&self, class: Class) -> u64 {
            match class {
                Class::High => self.vtime_high,
                Class::Normal => self.vtime_normal,
            }
        }

        pub fn enqueue(&mut self, flow: u32, packet: u64, size: u32) -> Result<(), QueueError> {
            let class = self.flows.get(&flow).ok_or(QueueError::UnknownFlow)?.class;
            if size == 0 {
                return Err(QueueError::ZeroSize);
            }
            let clock = self.clock(class);
            let f = self.flows.get_mut(&flow).unwrap();
            if f.queue.len() >= f.limit {
                return Err(QueueError::Full);
            }
            let start = clock.max(f.last_finish);
            let finish = start + size as u64 * SCALE / f.weight as u64;
            f.last_finish = finish;
            self.accepted += 1;
            f.queue.push_back(Packet { id: packet, size, finish, number: self.accepted });
            f.queued_bytes += size as u64;
            Ok(())
        }

        pub fn dequeue(&mut self) -> Option<Served> {
            let high = self.flows.values().any(|f| f.class == Class::High && !f.queue.is_empty());
            let class = if high { Class::High } else { Class::Normal };
            let mut best: Option<(u32, u64, u64)> = None;
            for (&id, f) in &self.flows {
                if f.class != class {
                    continue;
                }
                if let Some(head) = f.queue.front() {
                    if best.map_or(true, |(_, finish, number)| (head.finish, head.number) < (finish, number)) {
                        best = Some((id, head.finish, head.number));
                    }
                }
            }
            let (id, _, _) = best?;
            let f = self.flows.get_mut(&id).unwrap();
            let p = f.queue.pop_front().unwrap();
            f.queued_bytes -= p.size as u64;
            f.served_bytes += p.size as u64;
            match class {
                Class::High => self.vtime_high = p.finish,
                Class::Normal => self.vtime_normal = p.finish,
            }
            Some(Served { flow: id, packet: p.id, size: p.size, finish: p.finish })
        }

        pub fn backlog(&self, flow: u32) -> Option<(usize, u64)> {
            self.flows.get(&flow).map(|f| (f.queue.len(), f.queued_bytes))
        }

        pub fn served_bytes(&self, flow: u32) -> Option<u64> {
            self.flows.get(&flow).map(|f| f.served_bytes)
        }

        pub fn virtual_time(&self, class: Class) -> u64 {
            self.clock(class)
        }

        pub fn len(&self) -> usize {
            self.flows.values().map(|f| f.queue.len()).sum()
        }

        pub fn is_empty(&self) -> bool {
            self.len() == 0
        }

        pub fn remove_flow(&mut self, flow: u32) -> Result<(), QueueError> {
            let f = self.flows.get(&flow).ok_or(QueueError::UnknownFlow)?;
            if !f.queue.is_empty() {
                return Err(QueueError::NotEmpty);
            }
            self.flows.remove(&flow);
            Ok(())
        }
    }
''')

VISIBLE = dd('''
    use fairq::*;

    #[test]
    fn single_flow_is_fifo() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 8).unwrap();
        q.enqueue(1, 10, 100).unwrap();
        q.enqueue(1, 11, 100).unwrap();
        assert_eq!(q.dequeue().map(|s| s.packet), Some(10));
        assert_eq!(q.dequeue().map(|s| s.packet), Some(11));
        assert_eq!(q.dequeue(), None);
    }

    #[test]
    fn zero_weight_is_rejected() {
        let mut q = FairQueue::new();
        assert_eq!(q.add_flow(1, 0, Class::Normal, 8), Err(QueueError::BadWeight));
    }
''')

HIDDEN = dd('''
    use fairq::*;

    fn order(q: &mut FairQueue, n: usize) -> Vec<(u32, u64)> {
        let mut out = Vec::new();
        for _ in 0..n {
            match q.dequeue() {
                Some(s) => out.push((s.flow, s.packet)),
                None => break,
            }
        }
        out
    }

    #[test]
    fn add_flow_errors() {
        let mut q = FairQueue::new();
        assert_eq!(q.add_flow(1, 0, Class::Normal, 5), Err(QueueError::BadWeight));
        assert_eq!(q.add_flow(1, 1, Class::Normal, 0), Err(QueueError::BadLimit));
        assert_eq!(q.add_flow(1, 0, Class::Normal, 0), Err(QueueError::BadWeight));
        assert_eq!(q.add_flow(1, 1, Class::Normal, 1), Ok(()));
        assert_eq!(q.add_flow(1, 1, Class::High, 1), Err(QueueError::Duplicate));
        assert_eq!(q.add_flow(1, 0, Class::High, 1), Err(QueueError::BadWeight));
        assert_eq!(q.add_flow(2, 5, Class::High, 1), Ok(()));
    }

    #[test]
    fn enqueue_errors_and_limits() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 2).unwrap();
        assert_eq!(q.enqueue(9, 1, 10), Err(QueueError::UnknownFlow));
        assert_eq!(q.enqueue(9, 1, 0), Err(QueueError::UnknownFlow));
        assert_eq!(q.enqueue(1, 1, 0), Err(QueueError::ZeroSize));
        assert_eq!(q.enqueue(1, 1, 10), Ok(()));
        assert_eq!(q.enqueue(1, 2, 10), Ok(()));
        assert_eq!(q.enqueue(1, 3, 10), Err(QueueError::Full));
        assert_eq!(q.enqueue(1, 3, 0), Err(QueueError::ZeroSize));
        assert_eq!(q.len(), 2);
        // a rejected packet must not disturb the tags of later ones
        assert_eq!(q.dequeue().map(|s| s.packet), Some(1));
        assert_eq!(q.enqueue(1, 4, 10), Ok(()));
        let a = q.dequeue().unwrap();
        let b = q.dequeue().unwrap();
        assert_eq!((a.packet, a.finish), (2, 20_000));
        assert_eq!((b.packet, b.finish), (4, 30_000));
    }

    #[test]
    fn equal_weights_alternate_with_priority_flow() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 100).unwrap();
        q.add_flow(2, 2, Class::Normal, 100).unwrap();
        q.add_flow(3, 1, Class::High, 100).unwrap();
        for p in 1..=4 {
            q.enqueue(1, p, 1000).unwrap();
        }
        for p in 11..=14 {
            q.enqueue(2, p, 1000).unwrap();
        }
        assert_eq!(
            order(&mut q, 8),
            vec![(2, 11), (1, 1), (2, 12), (2, 13), (1, 2), (2, 14), (1, 3), (1, 4)]
        );
        assert!(q.is_empty());
    }

    #[test]
    fn three_to_one_share() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 100).unwrap();
        q.add_flow(2, 3, Class::Normal, 100).unwrap();
        for p in 1..=6 {
            q.enqueue(1, p, 500).unwrap();
        }
        for p in 21..=26 {
            q.enqueue(2, p, 500).unwrap();
        }
        let got: Vec<(u32, u64)> = order(&mut q, 12);
        let want = vec![(2, 21), (2, 22), (2, 23), (1, 1), (2, 24), (2, 25), (2, 26), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6)];
        assert_eq!(got, want);
    }

    #[test]
    fn finish_tags_truncate_per_packet() {
        let mut q = FairQueue::new();
        q.add_flow(1, 3, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 10).unwrap();
        q.enqueue(1, 2, 10).unwrap();
        let a = q.dequeue().unwrap();
        let b = q.dequeue().unwrap();
        assert_eq!((a.finish, b.finish), (3333, 6666));
        let mut q = FairQueue::new();
        q.add_flow(1, 7, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 1).unwrap();
        q.enqueue(1, 2, 1).unwrap();
        q.enqueue(1, 3, 1).unwrap();
        let tags: Vec<u64> = (0..3).map(|_| q.dequeue().unwrap().finish).collect();
        assert_eq!(tags, [142, 284, 426]);
    }

    #[test]
    fn served_record_fields() {
        let mut q = FairQueue::new();
        q.add_flow(4, 2, Class::Normal, 10).unwrap();
        q.enqueue(4, 77, 1500).unwrap();
        assert_eq!(q.dequeue(), Some(Served { flow: 4, packet: 77, size: 1500, finish: 750_000 }));
        assert_eq!(q.dequeue(), None);
        assert_eq!(q.virtual_time(Class::Normal), 750_000);
        assert_eq!(q.virtual_time(Class::High), 0);
    }

    #[test]
    fn high_class_is_strict() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(9, 1, Class::High, 10).unwrap();
        q.enqueue(1, 1, 100).unwrap();
        q.enqueue(1, 2, 100).unwrap();
        q.enqueue(9, 50, 100).unwrap();
        assert_eq!(q.dequeue().map(|s| (s.flow, s.packet)), Some((9, 50)));
        q.enqueue(9, 51, 100).unwrap();
        assert_eq!(order(&mut q, 5), vec![(9, 51), (1, 1), (1, 2)]);
    }

    #[test]
    fn clocks_are_per_class() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::High, 10).unwrap();
        q.enqueue(1, 1, 1000).unwrap();
        q.enqueue(2, 2, 100).unwrap();
        assert_eq!(q.dequeue().unwrap().flow, 2);
        assert_eq!(q.virtual_time(Class::High), 100_000);
        assert_eq!(q.virtual_time(Class::Normal), 0);
        assert_eq!(q.dequeue().unwrap().flow, 1);
        assert_eq!(q.virtual_time(Class::Normal), 1_000_000);
        assert_eq!(q.virtual_time(Class::High), 100_000);
    }

    #[test]
    fn a_new_flow_starts_at_the_current_clock() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 1000).unwrap();
        q.enqueue(1, 2, 1000).unwrap();
        q.enqueue(1, 3, 1000).unwrap();
        assert_eq!(q.dequeue().unwrap().packet, 1);
        assert_eq!(q.dequeue().unwrap().packet, 2);
        assert_eq!(q.virtual_time(Class::Normal), 2_000_000);
        // flow 2 has been idle: its first packet is tagged from the clock, not from 0
        q.enqueue(2, 10, 1000).unwrap();
        // flow 1's third packet has finish 3_000_000 as well and was accepted first
        assert_eq!(order(&mut q, 5), vec![(1, 3), (2, 10)]);
    }

    #[test]
    fn a_busy_flow_continues_from_its_own_last_finish() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 1000).unwrap();
        q.enqueue(1, 2, 1000).unwrap();
        assert_eq!(q.dequeue().unwrap().finish, 1_000_000);
        // the clock is 1_000_000 but the flow's last finish (2_000_000) is later
        q.enqueue(1, 3, 1000).unwrap();
        let tags: Vec<u64> = (0..2).map(|_| q.dequeue().unwrap().finish).collect();
        assert_eq!(tags, [2_000_000, 3_000_000]);
    }

    #[test]
    fn ties_go_to_the_earlier_packet() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::Normal, 10).unwrap();
        q.enqueue(2, 20, 1000).unwrap();
        q.enqueue(1, 10, 1000).unwrap();
        assert_eq!(order(&mut q, 2), vec![(2, 20), (1, 10)]);
        // the other way round, so the flow id does not decide
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::Normal, 10).unwrap();
        q.enqueue(1, 10, 1000).unwrap();
        q.enqueue(2, 20, 1000).unwrap();
        assert_eq!(order(&mut q, 2), vec![(1, 10), (2, 20)]);
    }

    #[test]
    fn small_packets_of_a_light_flow_can_pass_a_big_one() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 9000).unwrap();
        q.enqueue(2, 2, 100).unwrap();
        q.enqueue(2, 3, 100).unwrap();
        q.enqueue(2, 4, 100).unwrap();
        assert_eq!(order(&mut q, 4), vec![(2, 2), (2, 3), (2, 4), (1, 1)]);
    }

    #[test]
    fn backlog_and_served_bytes() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.add_flow(2, 1, Class::High, 10).unwrap();
        assert_eq!(q.backlog(1), Some((0, 0)));
        q.enqueue(1, 1, 100).unwrap();
        q.enqueue(1, 2, 250).unwrap();
        q.enqueue(2, 3, 40).unwrap();
        assert_eq!(q.backlog(1), Some((2, 350)));
        assert_eq!(q.backlog(2), Some((1, 40)));
        assert_eq!(q.backlog(3), None);
        assert_eq!(q.len(), 3);
        q.dequeue();
        q.dequeue();
        assert_eq!(q.backlog(1), Some((1, 250)));
        assert_eq!(q.served_bytes(1), Some(100));
        assert_eq!(q.served_bytes(2), Some(40));
        assert_eq!(q.served_bytes(5), None);
        q.dequeue();
        assert_eq!(q.served_bytes(1), Some(350));
        assert!(q.is_empty());
        assert_eq!(q.dequeue(), None);
    }

    #[test]
    fn remove_flow_rules() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 10).unwrap();
        q.enqueue(1, 1, 100).unwrap();
        assert_eq!(q.remove_flow(1), Err(QueueError::NotEmpty));
        assert_eq!(q.remove_flow(2), Err(QueueError::UnknownFlow));
        q.dequeue();
        assert_eq!(q.remove_flow(1), Ok(()));
        assert_eq!(q.backlog(1), None);
        assert_eq!(q.remove_flow(1), Err(QueueError::UnknownFlow));
        // the id can be registered again with a clean history
        q.add_flow(1, 4, Class::Normal, 10).unwrap();
        q.enqueue(1, 9, 400).unwrap();
        // the clock (100_000, left by the first packet) is the start of the re-registered flow: 100_000 + 400 * 1000 / 4
        let s = q.dequeue().unwrap();
        assert_eq!(s.finish, 200_000);
    }

    #[test]
    fn weights_give_proportional_service_over_time() {
        let mut q = FairQueue::new();
        q.add_flow(1, 1, Class::Normal, 1000).unwrap();
        q.add_flow(2, 2, Class::Normal, 1000).unwrap();
        q.add_flow(3, 5, Class::Normal, 1000).unwrap();
        for p in 0..300 {
            q.enqueue(1, p, 100).unwrap();
            q.enqueue(2, 1000 + p, 100).unwrap();
            q.enqueue(3, 2000 + p, 100).unwrap();
        }
        // serve while all three flows are backlogged
        for _ in 0..160 {
            q.dequeue();
        }
        let a = q.served_bytes(1).unwrap();
        let b = q.served_bytes(2).unwrap();
        let c = q.served_bytes(3).unwrap();
        assert_eq!(a + b + c, 16_000);
        assert_eq!((a, b, c), (2000, 4000, 10000));
    }
''')

LIB = Lib(
    name="fairq", lang="rust", title="the fairq crate",
    blurb="The software switch orders its egress traffic with fairq, a weighted fair queue with a strict-priority class and per-flow limits.",
    files={"Cargo.toml": cargo("fairq"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["scheduling", "queueing", "fairness"],
)

register_libs([LIB], n=8)
