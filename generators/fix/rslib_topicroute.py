"""Pub/sub topic routing (rust): wildcard filters, $-topics, shared groups with round-robin, qos merging."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # topicroute

    The message broker's subscription table: which clients get a message published on a topic. Topics and filters are `/`-separated
    levels; case matters; an empty level is a level (`a//b` has three).

    ## Filters and topics
    * A *topic* (what is published) is non-empty and contains no `+` or `#`.
    * A *filter* (what is subscribed to) is non-empty; each level is either exactly `+` (any single level, including an empty one), exactly
      `#` (everything from here on, allowed only as the **last** level) or text without `+` and `#`.
    * `validate_filter(f) -> Result<(), RouteError>` and `validate_topic(t) -> Result<(), RouteError>` return `Err(BadFilter)` / `Err(BadTopic)`.
    * `matches(filter: &str, topic: &str) -> bool`: false when either is invalid. Otherwise levels are compared pairwise: `+` matches any one
      level, text must be equal, and `#` matches all the remaining levels *including none* (so `a/#` matches `a`). Without `#` both must have
      the same number of levels. **A topic whose first level starts with `$` (system topics like `$SYS/uptime`) is never matched by a filter
      whose first level is `+` or `#`**; a filter that names the `$` level explicitly (`$SYS/#`, `$SYS/+`) works. `matches` does not interpret
      `$share` filters.

    ## `Router`
    `Router::new()`. Subscriptions are `(client, filter, qos)` with `qos` 0, 1 or 2.

    * `subscribe(&mut self, client: &str, filter: &str, qos: u8) -> Result<bool, RouteError>`: `Err(BadQos)` if `qos > 2` (checked first). A filter
      of the form `$share/<group>/<filter>` is a *shared* subscription: `<group>` must be non-empty and contain none of `/`, `+`, `#` (the split is
      at the first `/` after `$share/`), otherwise `Err(BadShare)`; the inner filter must be valid, otherwise `Err(BadFilter)`. Any other filter must
      be valid (`BadFilter`). Subscribing again to the same client + filter text (same group for shared ones) just changes the qos and returns
      `Ok(false)`; a new subscription returns `Ok(true)`.
    * `unsubscribe(&mut self, client: &str, filter: &str) -> bool`: removes that client's subscription written exactly like in `subscribe`
      (including a `$share/...` prefix); true if it existed. `unsubscribe_all(&mut self, client: &str) -> usize`: removes all of the client's
      subscriptions and returns how many.
    * `subscriptions(&self, client: &str) -> Vec<(String, u8)>`: the client's filters (shared ones with their `$share/<group>/` prefix) and qos,
      sorted by the filter string.
    * `route(&mut self, topic: &str) -> Result<Vec<Delivery>, RouteError>`: `Err(BadTopic)` for an invalid topic. Otherwise a `Delivery { client: String,
      qos: u8 }` list **sorted by client name**, one per client:
      * plain subscriptions whose filter matches deliver to their client; a client with several matching subscriptions gets one delivery with the
        *highest* qos among them;
      * for each shared subscription key `(group, inner filter)` whose filter matches the topic, exactly one member gets the message. Members are the
        subscribers of that key ordered by client name; each key has a counter starting at 0, the chosen member is `members[counter % members.len()]`,
        and the counter is incremented by one for every message routed through that key (members joining or leaving do not reset it). The chosen
        member's qos for that key takes part in the "highest qos" merge like a plain match.
''')

SRC = dd('''
    //! A topic subscription router.
    use std::collections::BTreeMap;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum RouteError {
        BadFilter,
        BadTopic,
        BadQos,
        BadShare,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Delivery {
        pub client: String,
        pub qos: u8,
    }

    pub fn validate_filter(filter: &str) -> Result<(), RouteError> {
        if filter.is_empty() {
            return Err(RouteError::BadFilter);
        }
        let levels: Vec<&str> = filter.split('/').collect();
        for (i, level) in levels.iter().enumerate() {
            let ok = match *level {
                "#" => i == levels.len() - 1,
                "+" => true,
                other => !other.contains('+') && !other.contains('#'),
            };
            if !ok {
                return Err(RouteError::BadFilter);
            }
        }
        Ok(())
    }

    pub fn validate_topic(topic: &str) -> Result<(), RouteError> {
        if topic.is_empty() || topic.contains('+') || topic.contains('#') {
            return Err(RouteError::BadTopic);
        }
        Ok(())
    }

    pub fn matches(filter: &str, topic: &str) -> bool {
        if validate_filter(filter).is_err() || validate_topic(topic).is_err() {
            return false;
        }
        if topic.starts_with('$') && (filter.starts_with('+') || filter.starts_with('#')) {
            return false;
        }
        let f: Vec<&str> = filter.split('/').collect();
        let t: Vec<&str> = topic.split('/').collect();
        for (i, level) in f.iter().enumerate() {
            if *level == "#" {
                return true;
            }
            match t.get(i) {
                None => return false,
                Some(actual) if *level == "+" || level == actual => {}
                Some(_) => return false,
            }
        }
        f.len() == t.len()
    }

    #[derive(Debug, Clone)]
    struct Sub {
        client: String,
        group: Option<String>,
        filter: String,
        qos: u8,
    }

    #[derive(Debug, Default)]
    pub struct Router {
        subs: Vec<Sub>,
        counters: BTreeMap<(String, String), u64>,
    }

    fn split_share(filter: &str) -> Result<(Option<String>, String), RouteError> {
        match filter.strip_prefix("$share/") {
            None => {
                validate_filter(filter)?;
                Ok((None, filter.to_string()))
            }
            Some(rest) => {
                let (group, inner) = rest.split_once('/').ok_or(RouteError::BadShare)?;
                if group.is_empty() || group.contains('+') || group.contains('#') {
                    return Err(RouteError::BadShare);
                }
                validate_filter(inner)?;
                Ok((Some(group.to_string()), inner.to_string()))
            }
        }
    }

    impl Router {
        pub fn new() -> Router {
            Router::default()
        }

        pub fn subscribe(&mut self, client: &str, filter: &str, qos: u8) -> Result<bool, RouteError> {
            if qos > 2 {
                return Err(RouteError::BadQos);
            }
            let (group, inner) = split_share(filter)?;
            if let Some(s) = self.subs.iter_mut().find(|s| s.client == client && s.group == group && s.filter == inner) {
                s.qos = qos;
                return Ok(false);
            }
            self.subs.push(Sub { client: client.to_string(), group, filter: inner, qos });
            Ok(true)
        }

        pub fn unsubscribe(&mut self, client: &str, filter: &str) -> bool {
            let Ok((group, inner)) = split_share(filter) else {
                return false;
            };
            let before = self.subs.len();
            self.subs.retain(|s| !(s.client == client && s.group == group && s.filter == inner));
            self.subs.len() != before
        }

        pub fn unsubscribe_all(&mut self, client: &str) -> usize {
            let before = self.subs.len();
            self.subs.retain(|s| s.client != client);
            before - self.subs.len()
        }

        pub fn subscriptions(&self, client: &str) -> Vec<(String, u8)> {
            let mut out: Vec<(String, u8)> = self
                .subs
                .iter()
                .filter(|s| s.client == client)
                .map(|s| match &s.group {
                    Some(g) => (format!("$share/{}/{}", g, s.filter), s.qos),
                    None => (s.filter.clone(), s.qos),
                })
                .collect();
            out.sort();
            out
        }

        pub fn route(&mut self, topic: &str) -> Result<Vec<Delivery>, RouteError> {
            validate_topic(topic)?;
            let mut best: BTreeMap<String, u8> = BTreeMap::new();
            let mut keys: Vec<(String, String)> = Vec::new();
            for s in &self.subs {
                if !matches(&s.filter, topic) {
                    continue;
                }
                match &s.group {
                    None => {
                        let q = best.entry(s.client.clone()).or_insert(s.qos);
                        *q = (*q).max(s.qos);
                    }
                    Some(g) => {
                        let key = (g.clone(), s.filter.clone());
                        if !keys.contains(&key) {
                            keys.push(key);
                        }
                    }
                }
            }
            keys.sort();
            for key in keys {
                let mut members: Vec<&Sub> = self
                    .subs
                    .iter()
                    .filter(|s| s.group.as_deref() == Some(key.0.as_str()) && s.filter == key.1)
                    .collect();
                members.sort_by(|a, b| a.client.cmp(&b.client));
                let counter = self.counters.entry(key.clone()).or_insert(0);
                let chosen = members[(*counter % members.len() as u64) as usize];
                *counter += 1;
                let q = best.entry(chosen.client.clone()).or_insert(chosen.qos);
                *q = (*q).max(chosen.qos);
            }
            Ok(best.into_iter().map(|(client, qos)| Delivery { client, qos }).collect())
        }
    }
''')

VISIBLE = dd('''
    use topicroute::*;

    #[test]
    fn plain_and_wildcards() {
        assert!(matches("sensors/+/temp", "sensors/kitchen/temp"));
        assert!(matches("sensors/#", "sensors/kitchen/temp"));
        assert!(!matches("sensors/+", "sensors/kitchen/temp"));
    }

    #[test]
    fn routes_to_subscribers() {
        let mut r = Router::new();
        r.subscribe("alice", "a/b", 1).unwrap();
        let out = r.route("a/b").unwrap();
        assert_eq!(out, vec![Delivery { client: "alice".into(), qos: 1 }]);
    }
''')

CASES = '''
            ("a/b", "a/b", true), ("a/b", "a/c", false), ("a/b", "a", false),
            ("a", "a/b", false), ("+/b", "a/b", true), ("a/+", "a/b", true),
            ("a/+", "a/b/c", false), ("a/+", "a", false), ("+", "a", true),
            ("+", "a/b", false), ("#", "a", true), ("#", "a/b/c", true),
            ("#", "$SYS/x", false), ("+/x", "$SYS/x", false), ("$SYS/#", "$SYS/x/y", true),
            ("$SYS/+", "$SYS/x", true), ("a/#", "a", true), ("a/#", "a/b", true),
            ("a/#", "a/b/c", true), ("a/#", "b", false), ("a/+/c", "a/b/c", true),
            ("a/+/c", "a//c", true), ("a/+/c", "a/b/d", false), ("+/+", "a/b", true),
            ("+/+", "a", false), ("a//b", "a//b", true), ("a//b", "a/b", false),
            ("/a", "/a", true), ("+/a", "/a", true), ("#", "/a", true),
            ("a/", "a/", true), ("a/+", "a/", true), ("a/#", "a/", true),
            ("a/b/#", "a/b", true), ("a/b/#", "a", false), ("sensors/+/temp", "sensors/kitchen/temp", true),
            ("sensors/+/temp", "sensors/kitchen/humidity", false), ("sensors/#", "sensors", true), ("$a/b", "$a/b", true),
            ("$a/#", "$a/b", true), ("#", "$a", false), ("+", "$a", false),
            ("#", "a$", true), ("x/$y", "x/$y", true), ("+/$y", "x/$y", true),
            ("a/#/b", "a/b", false), ("a+", "a+", false), ("a/b#", "a/b#", false),
            ("", "a", false), ("a", "", false), ("a/+/#", "a/b", true),
            ("a/+/#", "a/b/c/d", true), ("a/+/#", "a", false), ("#/a", "x/a", false),
            ("++", "a", false), ("a/++", "a/b", false), ("A/b", "a/b", false),
            ("a/b", "A/b", false), ("a/b/c/d/e", "a/b/c/d/e", true), ("a/b/c/d/e", "a/b/c/d", false),
            ("+/+/+/+", "a/b/c/d", true), ("+/+/+/+", "a/b/c", false), ("a/#", "a/b+", false),
            ("a", "a+", false),
'''.strip('\n')

HIDDEN = dd('''
    use topicroute::*;

    fn d(client: &str, qos: u8) -> Delivery {
        Delivery { client: client.to_string(), qos }
    }

    #[test]
    fn matching_table() {
        let cases: &[(&str, &str, bool)] = &[
''') + CASES + "\n" + dd('''
        ];
        for &(filter, topic, want) in cases {
            assert_eq!(matches(filter, topic), want, "matches({filter:?}, {topic:?})");
        }
    }

    #[test]
    fn validation() {
        for ok in ["a", "a/b", "+", "#", "a/+/b", "a/#", "+/+", "$SYS/#", "a//b", "/", "/#", "sensors/+/temp"] {
            assert_eq!(validate_filter(ok), Ok(()), "{ok:?}");
        }
        for bad in ["", "a/#/b", "#/a", "a+", "+a", "a#", "a/b#", "++", "a/++", "a/#x", "#a", "a/+b/c"] {
            assert_eq!(validate_filter(bad), Err(RouteError::BadFilter), "{bad:?}");
        }
        for ok in ["a", "a/b", "$SYS/x", "/", "a//b", "a/"] {
            assert_eq!(validate_topic(ok), Ok(()), "{ok:?}");
        }
        for bad in ["", "a/+", "#", "a/b#", "+", "a+b"] {
            assert_eq!(validate_topic(bad), Err(RouteError::BadTopic), "{bad:?}");
        }
    }

    #[test]
    fn subscribe_errors_and_updates() {
        let mut r = Router::new();
        assert_eq!(r.subscribe("c", "a/b", 3), Err(RouteError::BadQos));
        assert_eq!(r.subscribe("c", "a/b", 255), Err(RouteError::BadQos));
        assert_eq!(r.subscribe("c", "a/#/b", 3), Err(RouteError::BadQos)); // qos is checked first
        assert_eq!(r.subscribe("c", "a/#/b", 0), Err(RouteError::BadFilter));
        assert_eq!(r.subscribe("c", "", 0), Err(RouteError::BadFilter));
        assert_eq!(r.subscribe("c", "a/b", 2), Ok(true));
        assert_eq!(r.subscribe("c", "a/b", 0), Ok(false));
        assert_eq!(r.subscribe("c", "a/b", 1), Ok(false));
        assert_eq!(r.subscriptions("c"), vec![("a/b".to_string(), 1)]);
        assert_eq!(r.subscribe("c", "a/+", 0), Ok(true));
        assert_eq!(r.subscribe("other", "a/b", 0), Ok(true));
        assert_eq!(r.subscriptions("c"), vec![("a/+".to_string(), 0), ("a/b".to_string(), 1)]);
        assert_eq!(r.subscriptions("nobody"), vec![]);
    }

    #[test]
    fn share_errors() {
        let mut r = Router::new();
        assert_eq!(r.subscribe("c", "$share/g", 0), Err(RouteError::BadShare));
        assert_eq!(r.subscribe("c", "$share/", 0), Err(RouteError::BadShare));
        assert_eq!(r.subscribe("c", "$share//a/b", 0), Err(RouteError::BadShare));
        assert_eq!(r.subscribe("c", "$share/g+/a", 0), Err(RouteError::BadShare));
        assert_eq!(r.subscribe("c", "$share/#/a", 0), Err(RouteError::BadShare));
        assert_eq!(r.subscribe("c", "$share/g/", 0), Err(RouteError::BadFilter));
        assert_eq!(r.subscribe("c", "$share/g/a/#/b", 0), Err(RouteError::BadFilter));
        assert_eq!(r.subscribe("c", "$share/g/a/b", 0), Ok(true));
        assert_eq!(r.subscribe("c", "$share/g/a/b", 2), Ok(false));
        assert_eq!(r.subscribe("c", "$share/h/a/b", 1), Ok(true));
        assert_eq!(r.subscribe("c", "a/b", 0), Ok(true));
        assert_eq!(
            r.subscriptions("c"),
            vec![("$share/g/a/b".to_string(), 2), ("$share/h/a/b".to_string(), 1), ("a/b".to_string(), 0)]
        );
    }

    #[test]
    fn unsubscribe_variants() {
        let mut r = Router::new();
        r.subscribe("c", "a/b", 0).unwrap();
        r.subscribe("c", "$share/g/a/b", 0).unwrap();
        r.subscribe("c", "x/#", 1).unwrap();
        r.subscribe("d", "a/b", 0).unwrap();
        assert!(!r.unsubscribe("c", "a/c"));
        assert!(!r.unsubscribe("c", "$share/h/a/b"));
        assert!(!r.unsubscribe("e", "a/b"));
        assert!(!r.unsubscribe("c", "a/#/b"));
        assert!(!r.unsubscribe("c", "$share/g"));
        assert!(r.unsubscribe("c", "$share/g/a/b"));
        assert!(!r.unsubscribe("c", "$share/g/a/b"));
        assert_eq!(r.subscriptions("c"), vec![("a/b".to_string(), 0), ("x/#".to_string(), 1)]);
        assert!(r.unsubscribe("c", "a/b"));
        assert_eq!(r.unsubscribe_all("c"), 1);
        assert_eq!(r.unsubscribe_all("c"), 0);
        assert_eq!(r.subscriptions("d").len(), 1);
        assert_eq!(r.unsubscribe_all("d"), 1);
    }

    #[test]
    fn route_merges_qos_per_client_and_sorts() {
        let mut r = Router::new();
        r.subscribe("zed", "sensors/#", 0).unwrap();
        r.subscribe("amy", "sensors/+/temp", 1).unwrap();
        r.subscribe("amy", "sensors/kitchen/temp", 2).unwrap();
        r.subscribe("amy", "sensors/#", 0).unwrap();
        r.subscribe("bob", "sensors/kitchen/humidity", 2).unwrap();
        r.subscribe("cat", "#", 1).unwrap();
        assert_eq!(r.route("sensors/kitchen/temp").unwrap(), vec![d("amy", 2), d("cat", 1), d("zed", 0)]);
        assert_eq!(r.route("sensors/kitchen/humidity").unwrap(), vec![d("amy", 0), d("bob", 2), d("cat", 1), d("zed", 0)]);
        assert_eq!(r.route("other").unwrap(), vec![d("cat", 1)]);
        assert_eq!(r.route("sensors").unwrap(), vec![d("amy", 0), d("cat", 1), d("zed", 0)]);
    }

    #[test]
    fn qos_zero_is_kept() {
        let mut r = Router::new();
        r.subscribe("a", "t", 0).unwrap();
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]);
        r.subscribe("a", "+", 0).unwrap();
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]);
        r.subscribe("a", "#", 2).unwrap();
        assert_eq!(r.route("t").unwrap(), vec![d("a", 2)]);
    }

    #[test]
    fn route_rejects_bad_topics() {
        let mut r = Router::new();
        r.subscribe("a", "#", 0).unwrap();
        for bad in ["", "a/+", "#", "x#"] {
            assert_eq!(r.route(bad), Err(RouteError::BadTopic), "{bad:?}");
        }
        assert_eq!(r.route("a/").unwrap(), vec![d("a", 0)]);
        assert_eq!(r.route("/").unwrap(), vec![d("a", 0)]);
    }

    #[test]
    fn system_topics_are_hidden_from_wildcards() {
        let mut r = Router::new();
        r.subscribe("all", "#", 0).unwrap();
        r.subscribe("plus", "+/uptime", 0).unwrap();
        r.subscribe("sys", "$SYS/#", 1).unwrap();
        r.subscribe("sys2", "$SYS/+", 0).unwrap();
        assert_eq!(r.route("$SYS/uptime").unwrap(), vec![d("sys", 1), d("sys2", 0)]);
        assert_eq!(r.route("$SYS/a/b").unwrap(), vec![d("sys", 1)]);
        assert_eq!(r.route("node/uptime").unwrap(), vec![d("all", 0), d("plus", 0)]);
        // only the first level is special
        assert_eq!(r.route("a/$SYS").unwrap(), vec![d("all", 0)]);
    }

    #[test]
    fn shared_group_round_robin() {
        let mut r = Router::new();
        r.subscribe("w2", "$share/workers/jobs/#", 1).unwrap();
        r.subscribe("w1", "$share/workers/jobs/#", 0).unwrap();
        r.subscribe("w3", "$share/workers/jobs/#", 2).unwrap();
        r.subscribe("audit", "jobs/#", 0).unwrap();
        let mut chosen = Vec::new();
        for _ in 0..7 {
            let out = r.route("jobs/build").unwrap();
            assert_eq!(out.len(), 2);
            assert_eq!(out[0], d("audit", 0));
            chosen.push((out[1].client.clone(), out[1].qos));
        }
        let want: Vec<(String, u8)> = ["w1", "w2", "w3", "w1", "w2", "w3", "w1"]
            .iter()
            .zip([0u8, 1, 2, 0, 1, 2, 0])
            .map(|(c, q)| (c.to_string(), q))
            .collect();
        assert_eq!(chosen, want);
    }

    #[test]
    fn shared_counter_only_advances_on_matching_messages() {
        let mut r = Router::new();
        r.subscribe("a", "$share/g/x/+", 0).unwrap();
        r.subscribe("b", "$share/g/x/+", 0).unwrap();
        assert_eq!(r.route("x/1").unwrap(), vec![d("a", 0)]);
        assert!(r.route("y/1").unwrap().is_empty());
        assert!(r.route("x/1/2").unwrap().is_empty());
        assert_eq!(r.route("x/2").unwrap(), vec![d("b", 0)]);
        assert_eq!(r.route("x/3").unwrap(), vec![d("a", 0)]);
    }

    #[test]
    fn shared_keys_are_independent() {
        let mut r = Router::new();
        r.subscribe("a", "$share/g/t", 0).unwrap();
        r.subscribe("b", "$share/g/t", 0).unwrap();
        r.subscribe("a", "$share/h/t", 0).unwrap();
        r.subscribe("b", "$share/h/t", 0).unwrap();
        r.subscribe("a", "$share/g/u", 0).unwrap();
        r.subscribe("b", "$share/g/u", 0).unwrap();
        // keys (g, t) and (h, t) both advance on "t": each message reaches one member per key, both counters move together
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]);
        assert_eq!(r.route("t").unwrap(), vec![d("b", 0)]);
        // key (g, u) has not moved yet
        assert_eq!(r.route("u").unwrap(), vec![d("a", 0)]);
        assert_eq!(r.route("u").unwrap(), vec![d("b", 0)]);
        assert_eq!(r.route("u").unwrap(), vec![d("a", 0)]);
        // two keys matching one topic can deliver to different members
        let mut r = Router::new();
        r.subscribe("a", "$share/g/#", 0).unwrap();
        r.subscribe("b", "$share/g/#", 0).unwrap();
        r.subscribe("a", "$share/g/t", 1).unwrap();
        r.subscribe("b", "$share/g/t", 1).unwrap();
        assert_eq!(r.route("t").unwrap(), vec![d("a", 1)]);
        assert_eq!(r.route("t").unwrap(), vec![d("b", 1)]);
        assert_eq!(r.route("t").unwrap(), vec![d("a", 1)]);
        assert_eq!(r.route("other").unwrap(), vec![d("b", 0)]);
    }

    #[test]
    fn shared_and_plain_deliveries_merge() {
        let mut r = Router::new();
        r.subscribe("a", "$share/g/t", 2).unwrap();
        r.subscribe("a", "t", 0).unwrap();
        r.subscribe("b", "$share/g/t", 0).unwrap();
        // first message: member a (qos 2) merges with plain qos 0 -> 2
        assert_eq!(r.route("t").unwrap(), vec![d("a", 2)]);
        // second: member b (qos 0); a still gets its plain subscription
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0), d("b", 0)]);
        assert_eq!(r.route("t").unwrap(), vec![d("a", 2)]);
    }

    #[test]
    fn counters_survive_membership_changes() {
        let mut r = Router::new();
        for c in ["a", "b", "c"] {
            r.subscribe(c, "$share/g/t", 0).unwrap();
        }
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]); // counter 0 -> 1
        assert_eq!(r.route("t").unwrap(), vec![d("b", 0)]); // 1 -> 2
        assert!(r.unsubscribe("c", "$share/g/t"));
        // counter is 2, two members left: 2 % 2 = 0 -> a
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]);
        r.subscribe("aa", "$share/g/t", 0).unwrap();
        // members: a, aa, b; counter 3 % 3 = 0 -> a
        assert_eq!(r.route("t").unwrap(), vec![d("a", 0)]);
        assert_eq!(r.route("t").unwrap(), vec![d("aa", 0)]);
        assert_eq!(r.route("t").unwrap(), vec![d("b", 0)]);
    }

    #[test]
    fn empty_router_and_unsubscribed_clients() {
        let mut r = Router::new();
        assert!(r.route("anything").unwrap().is_empty());
        r.subscribe("a", "x", 0).unwrap();
        r.unsubscribe_all("a");
        assert!(r.route("x").unwrap().is_empty());
        // a group whose last member left does not panic
        r.subscribe("m", "$share/g/x", 0).unwrap();
        r.unsubscribe("m", "$share/g/x");
        assert!(r.route("x").unwrap().is_empty());
    }
''')

LIB = Lib(
    name="topicroute", lang="rust", title="the topicroute crate",
    blurb="The message broker routes published messages to subscribers with topicroute: wildcard filters, system topics and round-robin shared subscriptions.",
    files={"Cargo.toml": cargo("topicroute"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["pubsub", "matching", "routing"],
)

register_libs([LIB], n=8)
