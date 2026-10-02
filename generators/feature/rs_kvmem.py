"""kvmem (rust): an in-memory key-value store extended with prefixes, counters, compare-and-set, capacity, expiry, dump/load, watchers, transactions."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # kvmem

    A small in-memory key-value store for a configuration service. Rust 2021, no dependencies; `cargo test` runs the tests.

    ## Layout

    * `src/error.rs`: `StoreError`.
    * `src/store.rs`: `Store`.
    * `tests/`: integration tests.

    ## Basics

    Keys are non-empty strings without whitespace; values are any strings.

    * `Store::new()`.
    * `store.set(key, value) -> Result<(), StoreError>` stores a value (overwriting); `StoreError::BadKey(key)` for a bad key.
    * `store.get(key) -> Option<&str>`; `store.delete(key) -> bool` says whether the key existed.
    * `store.len() -> usize` counts the keys; `store.keys() -> Vec<String>` lists them in byte-wise alphabetical order.
    * `StoreError` implements `Display` and `Error`.
''')

ERROR = '''\
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoreError {
    BadKey(String),
    @@slot variants
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::BadKey(k) => write!(f, "bad key {:?}", k),
            @@slot display
        }
    }
}

impl std::error::Error for StoreError {}
'''

LIB = '''\
//! A small in-memory key-value store.
pub mod error;
pub mod store;

pub use error::StoreError;
pub use store::Store;
@@slot reexports
'''

STORE = '''\
use std::collections::BTreeMap;

use crate::error::StoreError;
@@uniq imports

@@blocks types

#[derive(Debug, Clone)]
struct Entry {
    value: String,
    @@slot entry_fields
}

/// The key-value store.
#[derive(Debug)]
pub struct Store {
    data: BTreeMap<String, Entry>,
    @@slot store_fields
}

impl Store {
    pub fn new() -> Store {
        Store {
            data: BTreeMap::new(),
            @@slot store_init
        }
    }

    fn check_key(key: &str) -> Result<(), StoreError> {
        if key.is_empty() || key.chars().any(|c| c.is_whitespace()) {
            return Err(StoreError::BadKey(key.to_string()));
        }
        Ok(())
    }

    /// The entry of a key that is visible right now.
    fn live(&self, key: &str) -> Option<&Entry> {
        let e = self.data.get(key)?;
        @@slot live_check
        Some(e)
    }

    pub fn set(&mut self, key: &str, value: &str) -> Result<(), StoreError> {
        Self::check_key(key)?;
        @@slot set_checks
        self.data.insert(
            key.to_string(),
            Entry {
                value: value.to_string(),
                @@slot entry_init
            },
        );
        @@slot on_set
        Ok(())
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.live(key).map(|e| e.value.as_str())
    }

    pub fn delete(&mut self, key: &str) -> bool {
        let had = self.live(key).is_some();
        self.data.remove(key);
        @@slot on_delete
        had
    }

    pub fn len(&self) -> usize {
        self.keys().len()
    }

    pub fn keys(&self) -> Vec<String> {
        self.data.keys().filter(|k| self.live(k).is_some()).cloned().collect()
    }

    @@blocks methods
}
'''

TEST_HELPERS = '''\
use kvmem::*;
@@uniq imports

fn store() -> Store {
    let mut s = Store::new();
    s.set("user:ana", "10").unwrap();
    s.set("user:bob", "7").unwrap();
    s.set("cfg:mode", "fast").unwrap();
    s.set("cfg:name", "kv one").unwrap();
    s
}
'''

VISIBLE = TEST_HELPERS + '''
#[test]
fn set_get_delete() {
    let mut s = store();
    assert_eq!(s.get("user:ana"), Some("10"));
    assert_eq!(s.get("nope"), None);
    s.set("user:ana", "11").unwrap();
    assert_eq!(s.get("user:ana"), Some("11"));
    assert!(s.delete("user:ana"));
    assert!(!s.delete("user:ana"));
    assert_eq!(s.len(), 3);
}

#[test]
fn bad_keys_and_order() {
    let mut s = store();
    assert_eq!(s.set("", "x"), Err(StoreError::BadKey(String::new())));
    assert_eq!(s.set("a b", "x"), Err(StoreError::BadKey("a b".to_string())));
    assert_eq!(s.keys(), vec!["cfg:mode", "cfg:name", "user:ana", "user:bob"]);
}
@@blocks tests
'''

HIDDEN = TEST_HELPERS + '''
#[test]
fn base_rules() {
    let mut s = Store::new();
    for bad in ["", " ", "a b", "a\\tb", "a\\nb", " lead", "trail "] {
        assert_eq!(s.set(bad, "x"), Err(StoreError::BadKey(bad.to_string())), "{:?}", bad);
    }
    assert_eq!(s.len(), 0);
    assert!(s.keys().is_empty());
    s.set("Zed", "1").unwrap();
    s.set("alpha", "").unwrap();
    s.set("a=b", "2").unwrap();
    s.set("été", "3").unwrap();
    assert_eq!(s.keys(), vec!["Zed", "a=b", "alpha", "été"]);
    assert_eq!(s.get("alpha"), Some(""));
    assert_eq!(s.get("ALPHA"), None);
    s.set("alpha", "multi word value").unwrap();
    assert_eq!(s.get("alpha"), Some("multi word value"));
    assert_eq!(s.len(), 4);
    assert!(s.delete("Zed"));
    assert!(!s.delete("Zed"));
    assert!(!s.delete("never"));
    assert_eq!(s.len(), 3);
    assert_eq!(StoreError::BadKey("x y".to_string()).to_string(), "bad key \\"x y\\"");
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    ev_set, ev_del = rng.choice([("Set", "Delete"), ("Put", "Remove")])
    S = []

    S.append(Slice(
        id="get-many", title="Reading several keys", d=1,
        pitch=("The dashboard asks for twelve keys at once and makes twelve calls.",
               "Callers want to read several keys in one go."),
        reqs=("`store.get_many(keys: &[&str]) -> Vec<Option<String>>` returns one entry per requested key, in the order requested (duplicates included): `Some(value)` or `None` for a key that is not there. An empty slice gives an empty vector.",),
        code={
            "src/store.rs::methods": '''
                pub fn get_many(&self, keys: &[&str]) -> Vec<Option<String>> {
                    keys.iter().map(|k| self.get(k).map(|v| v.to_string())).collect()
                }
            ''',
        },
        readme="## Reading several keys\n\n`store.get_many(&[\"a\", \"b\"])` returns `Vec<Option<String>>` in the order requested.\n",
        vtests='''
            #[test]
            fn get_many_basic() {
                let s = store();
                assert_eq!(s.get_many(&["user:ana", "nope"]), vec![Some("10".to_string()), None]);
            }
        ''',
        tests='''
            #[test]
            fn get_many_keeps_order_and_duplicates() {
                let s = store();
                let got = s.get_many(&["cfg:name", "zzz", "user:bob", "cfg:name", ""]);
                assert_eq!(got, vec![Some("kv one".to_string()), None, Some("7".to_string()), Some("kv one".to_string()), None]);
                assert!(s.get_many(&[]).is_empty());
            }
        ''',
    ))

    S.append(Slice(
        id="prefix", title="Keys by prefix", d=1,
        pitch=("Everything under `user:` is needed for the admin page, and filtering all keys on the client is wasteful.",
               "Callers want to list the keys that share a prefix."),
        reqs=("`store.keys_with_prefix(prefix: &str) -> Vec<String>` returns the keys that start with the prefix, in the same order as `keys()`. The match is case-sensitive; an empty prefix returns every key.",),
        code={
            "src/store.rs::methods": '''
                pub fn keys_with_prefix(&self, prefix: &str) -> Vec<String> {
                    self.keys().into_iter().filter(|k| k.starts_with(prefix)).collect()
                }
            ''',
        },
        readme="## Keys by prefix\n\n`store.keys_with_prefix(prefix)` lists the keys starting with `prefix` (case-sensitive; empty = all) in `keys()` order.\n",
        vtests='''
            #[test]
            fn prefix_basic() {
                assert_eq!(store().keys_with_prefix("user:"), vec!["user:ana", "user:bob"]);
            }
        ''',
        tests='''
            #[test]
            fn prefix_matching() {
                let s = store();
                assert_eq!(s.keys_with_prefix("cfg:"), vec!["cfg:mode", "cfg:name"]);
                assert_eq!(s.keys_with_prefix("cfg:m"), vec!["cfg:mode"]);
                assert_eq!(s.keys_with_prefix("CFG"), Vec::<String>::new());
                assert_eq!(s.keys_with_prefix(""), s.keys());
                assert_eq!(s.keys_with_prefix("user:ana"), vec!["user:ana"]);
                assert!(s.keys_with_prefix("zzz").is_empty());
            }
        ''',
        cross={
            "ttl": {"tests": '''
                #[test]
                fn prefix_skips_expired_keys() {
                    let mut s = store();
                    s.set_with_ttl("user:tmp", "x", 2).unwrap();
                    assert_eq!(s.keys_with_prefix("user:").len(), 3);
                    s.advance(2);
                    assert_eq!(s.keys_with_prefix("user:"), vec!["user:ana", "user:bob"]);
                }
            '''},
        },
    ))

    S.append(Slice(
        id="cas", title="Compare and set", d=2,
        pitch=("Two workers sometimes update the same setting and the slower one silently wins.",
               "Writers need a way to update a key only if nobody else changed it."),
        reqs=("`store.compare_and_set(key, expected: Option<&str>, new: &str) -> Result<bool, StoreError>`: a bad key is an error (checked first); otherwise, if the current value equals `expected` (`None` meaning the key is absent), the new value is stored exactly like `set` and the result is `Ok(true)`; if not, nothing changes and the result is `Ok(false)`. Errors that `set` can return are returned as they are.",),
        code={
            "src/store.rs::methods": '''
                pub fn compare_and_set(&mut self, key: &str, expected: Option<&str>, new: &str) -> Result<bool, StoreError> {
                    Self::check_key(key)?;
                    if self.get(key) != expected {
                        return Ok(false);
                    }
                    self.set(key, new)?;
                    Ok(true)
                }
            ''',
        },
        readme="## Compare and set\n\n`compare_and_set(key, expected, new)` stores `new` like `set` when the current value equals `expected` (`None` = absent) and returns `Ok(true)`, otherwise `Ok(false)`.\n",
        vtests='''
            #[test]
            fn cas_basic() {
                let mut s = store();
                assert_eq!(s.compare_and_set("user:ana", Some("10"), "11"), Ok(true));
                assert_eq!(s.get("user:ana"), Some("11"));
            }
        ''',
        tests='''
            #[test]
            fn cas_semantics() {
                let mut s = store();
                assert_eq!(s.compare_and_set("user:ana", Some("9"), "11"), Ok(false));
                assert_eq!(s.get("user:ana"), Some("10"));
                assert_eq!(s.compare_and_set("user:ana", None, "11"), Ok(false));
                assert_eq!(s.compare_and_set("user:cy", None, "1"), Ok(true));
                assert_eq!(s.get("user:cy"), Some("1"));
                assert_eq!(s.compare_and_set("user:cy", None, "2"), Ok(false));
                assert_eq!(s.compare_and_set("user:cy", Some("1"), "2"), Ok(true));
                assert_eq!(s.compare_and_set("user:zed", Some("x"), "2"), Ok(false));
                assert_eq!(s.get("user:zed"), None);
                assert_eq!(s.compare_and_set("cfg:mode", Some("fast"), ""), Ok(true));
                assert_eq!(s.get("cfg:mode"), Some(""));
                assert_eq!(s.compare_and_set("cfg:mode", Some(""), "slow"), Ok(true));
            }

            #[test]
            fn cas_bad_key_comes_first() {
                let mut s = store();
                assert_eq!(s.compare_and_set("", Some("zzz"), "x"), Err(StoreError::BadKey(String::new())));
                assert_eq!(s.compare_and_set("a b", None, "x"), Err(StoreError::BadKey("a b".to_string())));
                assert_eq!(s.len(), 4);
            }
        ''',
        cross={
            "ttl": {
                "reqs": ("A successful `compare_and_set` clears any expiry of the key, like `set` does.",),
                "tests": '''
                    #[test]
                    fn cas_clears_expiry() {
                        let mut s = store();
                        s.set_with_ttl("tmp", "a", 2).unwrap();
                        assert_eq!(s.compare_and_set("tmp", Some("a"), "b"), Ok(true));
                        assert_eq!(s.ttl("tmp"), None);
                        s.advance(10);
                        assert_eq!(s.get("tmp"), Some("b"));
                        s.set_with_ttl("t2", "a", 2).unwrap();
                        assert_eq!(s.compare_and_set("t2", Some("zzz"), "b"), Ok(false));
                        assert_eq!(s.ttl("t2"), Some(2));
                        s.advance(2);
                        assert_eq!(s.compare_and_set("t2", None, "fresh"), Ok(true));
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="incr", title="Counters", d=1,
        pitch=("The hit counters are read, incremented and written back by every client, and updates get lost.",
               "Clients need an atomic counter for numeric values."),
        reqs=("`store.incr(key, by: i64) -> Result<i64, StoreError>` adds `by` (which may be negative) to the integer stored under the key and returns the new value, which is stored as a decimal string. A missing key counts as 0. A bad key is `StoreError::BadKey` (checked first); a stored value that is not an integer (`str::parse::<i64>` fails, so an empty string or surrounding spaces do not qualify) is `StoreError::NotANumber(key)`; a result outside `i64` is `StoreError::Overflow(key)`. Failed calls change nothing.",
              "`Display`: `NotANumber` reads `value of KEY is not a number`, `Overflow` reads `counter KEY overflows`."),
        code={
            "src/error.rs::variants": '''
                NotANumber(String),
                Overflow(String),
            ''',
            "src/error.rs::display": '''
                StoreError::NotANumber(k) => write!(f, "value of {} is not a number", k),
                StoreError::Overflow(k) => write!(f, "counter {} overflows", k),
            ''',
            "src/store.rs::methods": '''
                pub fn incr(&mut self, key: &str, by: i64) -> Result<i64, StoreError> {
                    Self::check_key(key)?;
                    let current = match self.get(key) {
                        None => 0,
                        Some(v) => v.parse::<i64>().map_err(|_| StoreError::NotANumber(key.to_string()))?,
                    };
                    let next = current.checked_add(by).ok_or_else(|| StoreError::Overflow(key.to_string()))?;
                    @@slot incr_pre
                    self.set(key, &next.to_string())?;
                    @@slot incr_post
                    Ok(next)
                }
            ''',
        },
        readme="## Counters\n\n`store.incr(key, by)` adds to an integer value (missing = 0) and returns the result; `NotANumber(key)` for other values, `Overflow(key)` beyond `i64`.\n",
        vtests='''
            #[test]
            fn incr_basic() {
                let mut s = store();
                assert_eq!(s.incr("user:ana", 5), Ok(15));
                assert_eq!(s.get("user:ana"), Some("15"));
            }
        ''',
        tests='''
            #[test]
            fn incr_semantics() {
                let mut s = store();
                assert_eq!(s.incr("hits", 1), Ok(1));
                assert_eq!(s.incr("hits", -3), Ok(-2));
                assert_eq!(s.get("hits"), Some("-2"));
                s.set("n", "+5").unwrap();
                assert_eq!(s.incr("n", 1), Ok(6));
                assert_eq!(s.get("n"), Some("6"));
                s.set("max", &i64::MAX.to_string()).unwrap();
                assert_eq!(s.incr("max", -1), Ok(i64::MAX - 1));
                assert_eq!(s.incr("fresh", 0), Ok(0));
                assert_eq!(s.get("fresh"), Some("0"));
            }

            #[test]
            fn incr_errors_change_nothing() {
                let mut s = store();
                assert_eq!(s.incr("cfg:mode", 1), Err(StoreError::NotANumber("cfg:mode".to_string())));
                s.set("blank", "").unwrap();
                s.set("spaced", " 5").unwrap();
                s.set("float", "1.5").unwrap();
                for k in ["blank", "spaced", "float"] {
                    assert_eq!(s.incr(k, 1), Err(StoreError::NotANumber(k.to_string())));
                }
                assert_eq!(s.get("spaced"), Some(" 5"));
                assert_eq!(s.incr("user:bob", i64::MAX), Err(StoreError::Overflow("user:bob".to_string())));
                assert_eq!(s.get("user:bob"), Some("7"));
                s.set("min", &i64::MIN.to_string()).unwrap();
                assert_eq!(s.incr("min", -1), Err(StoreError::Overflow("min".to_string())));
                assert_eq!(s.incr("", 1), Err(StoreError::BadKey(String::new())));
                assert_eq!(StoreError::NotANumber("k".to_string()).to_string(), "value of k is not a number");
                assert_eq!(StoreError::Overflow("k".to_string()).to_string(), "counter k overflows");
                assert_eq!(s.len(), 8);
            }
        ''',
        cross={
            "ttl": {
                "reqs": ("`incr` keeps the expiry of a key that is still alive (the value changes, the deadline does not); a key that has expired counts as missing, so the counter restarts from 0 without an expiry.",),
                "code": {
                    "src/store.rs::incr_pre": "let kept = self.live(key).and_then(|e| e.expires);",
                    "src/store.rs::incr_post": '''
                        if let Some(e) = self.data.get_mut(key) {
                            e.expires = kept;
                        }
                    ''',
                },
                "tests": '''
                    #[test]
                    fn incr_keeps_the_expiry() {
                        let mut s = store();
                        s.set_with_ttl("c", "5", 3).unwrap();
                        s.advance(1);
                        assert_eq!(s.incr("c", 1), Ok(6));
                        assert_eq!(s.ttl("c"), Some(2));
                        s.advance(2);
                        assert_eq!(s.get("c"), None);
                        assert_eq!(s.incr("c", 4), Ok(4));
                        assert_eq!(s.ttl("c"), None);
                        s.advance(100);
                        assert_eq!(s.get("c"), Some("4"));
                    }
                '''},
            "capacity": {"tests": '''
                #[test]
                fn incr_respects_capacity() {
                    let mut s = Store::with_capacity(1).unwrap();
                    assert_eq!(s.incr("a", 1), Ok(1));
                    assert_eq!(s.incr("a", 1), Ok(2));
                    assert_eq!(s.incr("b", 1), Err(StoreError::Full(1)));
                    assert_eq!(s.get("b"), None);
                }
            '''},
        },
    ))

    S.append(Slice(
        id="capacity", title="Capacity limit", d=2,
        pitch=("The config service runs in a small container and one runaway client filled the memory with keys.",
               "The store needs an upper bound on the number of keys."),
        reqs=("`Store::with_capacity(max: usize) -> Result<Store, StoreError>` makes a store that holds at most `max` keys (`StoreError::BadCapacity` when `max` is 0) and `store.capacity() -> Option<usize>` returns the limit (`None` for `Store::new()`).",
              "`set` of a key that is not in the store when it already holds `max` keys fails with `StoreError::Full(max)`; overwriting an existing key always works, and so does setting a new key after a delete. A bad key is still reported first and a failed call changes nothing. `Display`: `store is full (N keys)` and `capacity must be at least 1`."),
        code={
            "src/error.rs::variants": '''
                Full(usize),
                BadCapacity,
            ''',
            "src/error.rs::display": '''
                StoreError::Full(n) => write!(f, "store is full ({} keys)", n),
                StoreError::BadCapacity => write!(f, "capacity must be at least 1"),
            ''',
            "src/store.rs::store_fields": "capacity: Option<usize>,",
            "src/store.rs::store_init": "capacity: None,",
            "src/store.rs::set_checks": '''
                if let Some(max) = self.capacity {
                    if self.live(key).is_none() && self.len() >= max {
                        return Err(StoreError::Full(max));
                    }
                }
            ''',
            "src/store.rs::methods": '''
                pub fn with_capacity(max: usize) -> Result<Store, StoreError> {
                    if max == 0 {
                        return Err(StoreError::BadCapacity);
                    }
                    let mut s = Store::new();
                    s.capacity = Some(max);
                    Ok(s)
                }

                pub fn capacity(&self) -> Option<usize> {
                    self.capacity
                }
            ''',
        },
        readme="## Capacity limit\n\n`Store::with_capacity(max)` (`BadCapacity` for 0) refuses new keys beyond `max` with `StoreError::Full(max)`; overwrites and deletes are always fine. `store.capacity()` returns the limit.\n",
        vtests='''
            #[test]
            fn capacity_basic() {
                let mut s = Store::with_capacity(1).unwrap();
                s.set("a", "1").unwrap();
                assert_eq!(s.set("b", "2"), Err(StoreError::Full(1)));
            }
        ''',
        tests='''
            #[test]
            fn capacity_limits_new_keys_only() {
                let mut s = Store::with_capacity(2).unwrap();
                assert_eq!(s.capacity(), Some(2));
                s.set("a", "1").unwrap();
                s.set("b", "2").unwrap();
                assert_eq!(s.set("c", "3"), Err(StoreError::Full(2)));
                assert_eq!(s.len(), 2);
                s.set("a", "9").unwrap();
                assert_eq!(s.get("a"), Some("9"));
                assert!(s.delete("a"));
                s.set("c", "3").unwrap();
                assert_eq!(s.keys(), vec!["b", "c"]);
                assert_eq!(s.set("d", "4"), Err(StoreError::Full(2)));
                assert_eq!(Store::new().capacity(), None);
            }

            #[test]
            fn capacity_errors() {
                assert_eq!(Store::with_capacity(0).unwrap_err(), StoreError::BadCapacity);
                let mut s = Store::with_capacity(1).unwrap();
                s.set("a", "1").unwrap();
                assert_eq!(s.set("", "x"), Err(StoreError::BadKey(String::new())));
                assert_eq!(StoreError::Full(3).to_string(), "store is full (3 keys)");
                assert_eq!(StoreError::BadCapacity.to_string(), "capacity must be at least 1");
                let mut big = Store::new();
                for i in 0..50 {
                    big.set(&format!("k{}", i), "v").unwrap();
                }
                assert_eq!(big.len(), 50);
            }
        ''',
        cross={
            "ttl": {
                "reqs": ("Expired keys do not count against the capacity.",),
                "tests": '''
                    #[test]
                    fn expired_keys_free_their_slot() {
                        let mut s = Store::with_capacity(2).unwrap();
                        s.set_with_ttl("a", "1", 1).unwrap();
                        s.set("b", "2").unwrap();
                        assert_eq!(s.set("c", "3"), Err(StoreError::Full(2)));
                        s.advance(1);
                        s.set("c", "3").unwrap();
                        assert_eq!(s.keys(), vec!["b", "c"]);
                        assert_eq!(s.set("d", "4"), Err(StoreError::Full(2)));
                    }
                '''},
            "dump": {
                "reqs": ("`load` obeys the capacity as a whole: if applying the text would need more keys than fit, it fails with `StoreError::Full(max)` and the store is unchanged.",),
                "code": {"src/store.rs::load_checks": '''
                    if let Some(max) = self.capacity {
                        let mut fresh = std::collections::BTreeSet::new();
                        for (k, _) in &pairs {
                            if self.live(k).is_none() {
                                fresh.insert(k.clone());
                            }
                        }
                        if self.len() + fresh.len() > max {
                            return Err(StoreError::Full(max));
                        }
                    }
                '''},
                "tests": '''
                    #[test]
                    fn load_obeys_capacity_atomically() {
                        let mut s = Store::with_capacity(2).unwrap();
                        s.set("a", "1").unwrap();
                        assert_eq!(s.load("b=1\\nc=2\\n"), Err(StoreError::Full(2)));
                        assert_eq!(s.get("b"), None);
                        assert_eq!(s.keys(), vec!["a"]);
                        assert_eq!(s.load("a=9\\nb=1\\na=10\\n"), Ok(3));
                        assert_eq!(s.get("a"), Some("10"));
                        assert_eq!(s.len(), 2);
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="ttl", title="Expiring keys", d=3,
        pitch=("Session tokens pile up in the store because nothing ever removes them.",
               "Some keys should disappear on their own after a while."),
        reqs=("The store has a logical clock: `store.now() -> u64` starts at 0 and `store.advance(by: u64)` moves it forward (saturating). `store.set_with_ttl(key, value, ttl: u64) -> Result<(), StoreError>` stores a value that is visible for `ttl` ticks: it is gone as soon as `now()` reaches the time of the call plus `ttl`. A bad key is `StoreError::BadKey` (checked first); `ttl` 0 is `StoreError::BadTtl`; otherwise the errors of `set` apply.",
              "An expired key behaves as if it did not exist: `get`, `len`, `keys` and `delete` (which returns false) ignore it. Plain `set` stores a key without an expiry, replacing any earlier deadline. `store.ttl(key) -> Option<u64>` returns the remaining ticks of a live key that has a deadline and `None` otherwise. `store.persist(key) -> bool` removes the deadline of a live key and says whether there was one.",
              "`Display` of `BadTtl` reads `ttl must be at least 1`."),
        code={
            "src/error.rs::variants": "BadTtl,",
            "src/error.rs::display": 'StoreError::BadTtl => write!(f, "ttl must be at least 1"),',
            "src/store.rs::entry_fields": "expires: Option<u64>,",
            "src/store.rs::entry_init": "expires: None,",
            "src/store.rs::store_fields": "now: u64,",
            "src/store.rs::store_init": "now: 0,",
            "src/store.rs::live_check": '''
                if let Some(t) = e.expires {
                    if self.now >= t {
                        return None;
                    }
                }
            ''',
            "src/store.rs::methods": '''
                pub fn now(&self) -> u64 {
                    self.now
                }

                pub fn advance(&mut self, by: u64) {
                    self.now = self.now.saturating_add(by);
                }

                pub fn set_with_ttl(&mut self, key: &str, value: &str, ttl: u64) -> Result<(), StoreError> {
                    Self::check_key(key)?;
                    if ttl == 0 {
                        return Err(StoreError::BadTtl);
                    }
                    self.set(key, value)?;
                    let deadline = self.now.saturating_add(ttl);
                    if let Some(e) = self.data.get_mut(key) {
                        e.expires = Some(deadline);
                    }
                    Ok(())
                }

                pub fn ttl(&self, key: &str) -> Option<u64> {
                    self.live(key)?.expires.map(|t| t - self.now)
                }

                pub fn persist(&mut self, key: &str) -> bool {
                    let had = self.live(key).and_then(|e| e.expires).is_some();
                    if had {
                        if let Some(e) = self.data.get_mut(key) {
                            e.expires = None;
                        }
                    }
                    had
                }
            ''',
        },
        readme="## Expiring keys\n\nA logical clock (`now()`, `advance(by)`) and `set_with_ttl(key, value, ttl)`: the key is gone once `now()` reaches the call time plus `ttl`. `ttl(key)` gives the remaining ticks, `persist(key)` removes the deadline, plain `set` clears it. Expired keys are invisible to `get`, `len`, `keys` and `delete`.\n",
        vtests='''
            #[test]
            fn ttl_basic() {
                let mut s = store();
                s.set_with_ttl("tmp", "x", 2).unwrap();
                assert_eq!(s.get("tmp"), Some("x"));
                s.advance(2);
                assert_eq!(s.get("tmp"), None);
            }
        ''',
        tests='''
            #[test]
            fn keys_expire_exactly_at_the_deadline() {
                let mut s = store();
                assert_eq!(s.now(), 0);
                s.advance(5);
                s.set_with_ttl("tmp", "x", 3).unwrap();
                assert_eq!((s.now(), s.ttl("tmp")), (5, Some(3)));
                s.advance(2);
                assert_eq!((s.get("tmp"), s.ttl("tmp"), s.len()), (Some("x"), Some(1), 5));
                s.advance(1);
                assert_eq!((s.get("tmp"), s.ttl("tmp"), s.len()), (None, None, 4));
                assert!(!s.keys().contains(&"tmp".to_string()));
                assert!(!s.delete("tmp"));
                assert_eq!(s.ttl("user:ana"), None);
                assert_eq!(s.ttl("missing"), None);
            }

            #[test]
            fn set_and_persist_change_deadlines() {
                let mut s = store();
                s.set_with_ttl("a", "1", 2).unwrap();
                s.set("a", "2").unwrap();
                assert_eq!(s.ttl("a"), None);
                s.set_with_ttl("p", "1", 2).unwrap();
                assert!(s.persist("p"));
                assert!(!s.persist("p"));
                assert!(!s.persist("user:ana"));
                assert!(!s.persist("missing"));
                s.set_with_ttl("gone", "1", 1).unwrap();
                s.advance(1);
                assert!(!s.persist("gone"));
                s.advance(50);
                assert_eq!((s.get("a"), s.get("p"), s.get("gone")), (Some("2"), Some("1"), None));
                s.set_with_ttl("r", "1", 5).unwrap();
                s.advance(4);
                s.set_with_ttl("r", "2", 5).unwrap();
                assert_eq!(s.ttl("r"), Some(5));
                s.set("gone", "again").unwrap();
                assert_eq!((s.get("gone"), s.ttl("gone")), (Some("again"), None));
            }

            #[test]
            fn ttl_errors() {
                let mut s = store();
                assert_eq!(s.set_with_ttl("k", "v", 0), Err(StoreError::BadTtl));
                assert_eq!(s.set_with_ttl("", "v", 0), Err(StoreError::BadKey(String::new())));
                assert_eq!(s.set_with_ttl("a b", "v", 5), Err(StoreError::BadKey("a b".to_string())));
                assert_eq!(s.get("k"), None);
                assert_eq!(StoreError::BadTtl.to_string(), "ttl must be at least 1");
                s.advance(u64::MAX);
                s.advance(1);
                assert_eq!(s.now(), u64::MAX);
            }
        ''',
    ))

    S.append(Slice(
        id="dump", title="Dump and load", d=3,
        pitch=("Restarting the service loses all keys, and operators want to save and restore the store as text.",
               "The store needs a plain-text export and import."),
        reqs=("`store.dump() -> String` has one line `KEY=VALUE` per live key in `keys()` order, each ending in a newline. In keys, a backslash is written `\\\\` and an equals sign `\\=`; in values, a backslash is written `\\\\`, a newline `\\n` and a carriage return `\\r`. Nothing else is escaped (a value may contain `=`).",
              "`store.load(text: &str) -> Result<usize, StoreError>` reads such text and sets every line (later lines win over earlier ones and over existing keys), returning the number of lines applied. The key ends at the first unescaped `=`. A trailing `\\r` before a newline is ignored and empty lines are skipped. A line without `=`, with an empty key or a key with whitespace, or with an escape other than the ones above (`\\=` is only valid in keys, `\\n` and `\\r` only in values) is `StoreError::Parse(line)` with the 1-based number of the line (empty lines count). Loading is all or nothing: after an error the store is unchanged.",
              "`Display` of `Parse` reads `cannot parse line N`."),
        code={
            "src/error.rs::variants": "Parse(usize),",
            "src/error.rs::display": 'StoreError::Parse(n) => write!(f, "cannot parse line {}", n),',
            "src/store.rs::types": '''
                fn escape(s: &str, is_key: bool) -> String {
                    let mut out = String::new();
                    for c in s.chars() {
                        match c {
                            '\\\\' => out.push_str("\\\\\\\\"),
                            '\\n' => out.push_str("\\\\n"),
                            '\\r' => out.push_str("\\\\r"),
                            '=' if is_key => out.push_str("\\\\="),
                            _ => out.push(c),
                        }
                    }
                    out
                }

                fn parse_line(line: &str) -> Option<(String, String)> {
                    let mut key = String::new();
                    let mut value = String::new();
                    let mut in_value = false;
                    let mut chars = line.chars();
                    while let Some(c) = chars.next() {
                        let target = if in_value { &mut value } else { &mut key };
                        match c {
                            '\\\\' => match (chars.next()?, in_value) {
                                ('\\\\', _) => target.push('\\\\'),
                                ('=', false) => target.push('='),
                                ('n', true) => target.push('\\n'),
                                ('r', true) => target.push('\\r'),
                                _ => return None,
                            },
                            '=' if !in_value => in_value = true,
                            _ => target.push(c),
                        }
                    }
                    if !in_value || key.is_empty() || key.chars().any(|c| c.is_whitespace()) {
                        return None;
                    }
                    Some((key, value))
                }
            ''',
            "src/store.rs::methods": '''
                pub fn dump(&self) -> String {
                    let mut out = String::new();
                    for k in self.keys() {
                        let v = self.get(&k).unwrap_or("");
                        out.push_str(&format!("{}={}\\n", escape(&k, true), escape(v, false)));
                    }
                    out
                }

                pub fn load(&mut self, text: &str) -> Result<usize, StoreError> {
                    let mut pairs = Vec::new();
                    for (i, raw) in text.split('\\n').enumerate() {
                        let line = raw.strip_suffix('\\r').unwrap_or(raw);
                        if line.is_empty() {
                            continue;
                        }
                        match parse_line(line) {
                            Some(p) => pairs.push(p),
                            None => return Err(StoreError::Parse(i + 1)),
                        }
                    }
                    @@slot load_checks
                    for (k, v) in &pairs {
                        self.set(k, v)?;
                    }
                    Ok(pairs.len())
                }
            ''',
        },
        readme="## Dump and load\n\n`store.dump()` writes `KEY=VALUE` lines (keys escape `\\\\` and `\\=`, values escape `\\\\`, newline and carriage return); `store.load(text)` reads them back all or nothing, returns the number of lines applied, and reports `StoreError::Parse(line)` for malformed lines.\n",
        vtests='''
            #[test]
            fn dump_basic() {
                let s = store();
                assert!(s.dump().starts_with("cfg:mode=fast\\ncfg:name=kv one\\n"));
            }
        ''',
        tests='''
            #[test]
            fn dump_format_and_escapes() {
                let s = store();
                assert_eq!(s.dump(), "cfg:mode=fast\\ncfg:name=kv one\\nuser:ana=10\\nuser:bob=7\\n");
                assert_eq!(Store::new().dump(), "");
                let mut t = Store::new();
                t.set("a=b", "x=y").unwrap();
                t.set("back\\\\slash", "line1\\nline2\\r\\\\n").unwrap();
                t.set("empty", "").unwrap();
                assert_eq!(t.dump(), "a\\\\=b=x=y\\nback\\\\\\\\slash=line1\\\\nline2\\\\r\\\\\\\\n\\nempty=\\n");
            }

            #[test]
            fn load_round_trip() {
                let mut t = Store::new();
                t.set("a=b", "x=y").unwrap();
                t.set("back\\\\slash", "line1\\nline2\\r\\\\n").unwrap();
                t.set("empty", "").unwrap();
                t.set("é", "ü").unwrap();
                let mut u = Store::new();
                assert_eq!(u.load(&t.dump()), Ok(4));
                assert_eq!(u.keys(), t.keys());
                for k in t.keys() {
                    assert_eq!(u.get(&k), t.get(&k), "{}", k);
                }
                assert_eq!(u.dump(), t.dump());
            }

            #[test]
            fn load_overwrites_and_skips_blank_lines() {
                let mut s = store();
                let n = s.load("user:ana=99\\r\\n\\n\\ncfg:new=1=2\\nuser:ana=100\\r\\n").unwrap();
                assert_eq!(n, 3);
                assert_eq!(s.get("user:ana"), Some("100"));
                assert_eq!(s.get("cfg:new"), Some("1=2"));
                assert_eq!(s.len(), 5);
                assert_eq!(s.load(""), Ok(0));
                assert_eq!(s.load("\\n\\n"), Ok(0));
                assert_eq!(s.load("k=v"), Ok(1));
            }

            #[test]
            fn load_errors_are_atomic_and_numbered() {
                let cases = [
                    ("a=1\\nnoequals\\nb=2\\n", 2),
                    ("a=1\\n\\n=value\\n", 3),
                    ("a b=1\\n", 1),
                    ("a=1\\nb=\\\\x\\n", 2),
                    ("a=1\\nb\\\\nc=1\\n", 2),
                    ("a=1\\nb=ends with backslash\\\\", 2),
                    ("a\\\\=b\\n", 1),
                    ("a=1\\nb=2\\nc\\\\=\\n", 3),
                ];
                for (text, line) in cases {
                    let mut s = store();
                    assert_eq!(s.load(text), Err(StoreError::Parse(line)), "{:?}", text);
                    assert_eq!(s.len(), 4, "{:?}", text);
                    assert_eq!(s.get("a"), None);
                }
                assert_eq!(StoreError::Parse(7).to_string(), "cannot parse line 7");
            }
        ''',
        cross={
            "ttl": {
                "reqs": ("Expired keys are not dumped. Keys created by `load` have no expiry.",),
                "tests": '''
                    #[test]
                    fn dump_skips_expired_keys_and_load_has_no_expiry() {
                        let mut s = store();
                        s.set_with_ttl("tmp", "x", 1).unwrap();
                        s.set_with_ttl("later", "y", 10).unwrap();
                        assert!(s.dump().contains("tmp=x\\n"));
                        s.advance(1);
                        let text = s.dump();
                        assert!(!text.contains("tmp="));
                        assert!(text.contains("later=y\\n"));
                        let mut t = Store::new();
                        t.load(&text).unwrap();
                        assert_eq!(t.ttl("later"), None);
                        t.advance(100);
                        assert_eq!(t.get("later"), Some("y"));
                        s.set("tmp", "back").unwrap();
                        assert_eq!(s.load("later=z\\n"), Ok(1));
                        assert_eq!(s.ttl("later"), None);
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="watch", title="Watchers", d=3,
        pitch=("A cache layer next to the store has to find out when keys change, and polling every key is too slow.",
               "Other components want to be told about changes under a prefix."),
        reqs=("`store.subscribe(prefix: &str) -> usize` registers a watcher for the keys that start with the prefix (an empty prefix watches everything) and returns its id: 1, 2, 3, ... `store.unsubscribe(id) -> bool` removes it and says whether it existed. `store.take_events(id) -> Result<Vec<Event>, StoreError>` returns the events queued for the watcher so far, oldest first, and empties its queue; an unknown id is `StoreError::UnknownSubscription(id)`.",
              f"`Event` is a new public enum (derives `Debug, Clone, PartialEq, Eq`, re-exported at the crate root) with `{ev_set}(String)` and `{ev_del}(String)`, both carrying the key. Every successful `set` queues `{ev_set}` for the watchers whose prefix matches, even when the value does not change; a `delete` queues `{ev_del}` only when the key existed. Failed calls queue nothing. `Display` of the new error reads `no subscription N`."),
        code={
            "src/error.rs::variants": "UnknownSubscription(usize),",
            "src/error.rs::display": 'StoreError::UnknownSubscription(n) => write!(f, "no subscription {}", n),',
            "src/lib.rs::reexports": "pub use store::Event;",
            "src/store.rs::types": fmt('''
                /// A change to a key.
                #[derive(Debug, Clone, PartialEq, Eq)]
                pub enum Event {
                    __S__(String),
                    __D__(String),
                }

                #[derive(Debug)]
                struct Sub {
                    id: usize,
                    prefix: String,
                    pending: Vec<Event>,
                }
            ''', S=ev_set, D=ev_del),
            "src/store.rs::store_fields": '''
                subs: Vec<Sub>,
                next_sub: usize,
            ''',
            "src/store.rs::store_init": '''
                subs: Vec::new(),
                next_sub: 1,
            ''',
            "src/store.rs::on_set": f"self.notify(Event::{ev_set}(key.to_string()));",
            "src/store.rs::on_delete": f'''
                if had {{
                    self.notify(Event::{ev_del}(key.to_string()));
                }}
            ''',
            "src/store.rs::methods": '''
                pub fn subscribe(&mut self, prefix: &str) -> usize {
                    let id = self.next_sub;
                    self.next_sub += 1;
                    self.subs.push(Sub { id, prefix: prefix.to_string(), pending: Vec::new() });
                    id
                }

                pub fn unsubscribe(&mut self, id: usize) -> bool {
                    let before = self.subs.len();
                    self.subs.retain(|s| s.id != id);
                    self.subs.len() != before
                }

                pub fn take_events(&mut self, id: usize) -> Result<Vec<Event>, StoreError> {
                    match self.subs.iter_mut().find(|s| s.id == id) {
                        Some(s) => Ok(std::mem::take(&mut s.pending)),
                        None => Err(StoreError::UnknownSubscription(id)),
                    }
                }

                fn notify(&mut self, ev: Event) {
                    let key = match &ev {
                        Event::__S__(k) | Event::__D__(k) => k.clone(),
                    };
                    for s in &mut self.subs {
                        if key.starts_with(&s.prefix) {
                            s.pending.push(ev.clone());
                        }
                    }
                }
            '''.replace("__S__", ev_set).replace("__D__", ev_del),
        },
        readme=f"## Watchers\n\n`subscribe(prefix)` returns an id (1, 2, ...); `take_events(id)` drains the queued `Event::{ev_set}(key)` / `Event::{ev_del}(key)` values (every successful `set`, every `delete` of an existing key); `unsubscribe(id)` removes a watcher; `StoreError::UnknownSubscription(id)` for unknown ids.\n",
        vtests=fmt('''
            #[test]
            fn watch_basic() {
                let mut s = store();
                let id = s.subscribe("user:");
                s.set("user:cy", "1").unwrap();
                s.set("cfg:mode", "slow").unwrap();
                assert_eq!(s.take_events(id).unwrap(), vec![Event::__S__("user:cy".to_string())]);
            }
        ''', S=ev_set),
        tests=fmt('''
            fn set_ev(k: &str) -> Event {
                Event::__S__(k.to_string())
            }

            fn del_ev(k: &str) -> Event {
                Event::__D__(k.to_string())
            }

            #[test]
            fn watchers_see_matching_changes() {
                let mut s = store();
                let all = s.subscribe("");
                let users = s.subscribe("user:");
                assert_eq!((all, users), (1, 2));
                s.set("user:cy", "1").unwrap();
                s.set("cfg:mode", "slow").unwrap();
                s.set("cfg:mode", "slow").unwrap();
                assert!(s.delete("user:ana"));
                assert!(!s.delete("nothing"));
                assert!(s.set("", "x").is_err());
                assert_eq!(
                    s.take_events(all).unwrap(),
                    vec![set_ev("user:cy"), set_ev("cfg:mode"), set_ev("cfg:mode"), del_ev("user:ana")]
                );
                assert_eq!(s.take_events(users).unwrap(), vec![set_ev("user:cy"), del_ev("user:ana")]);
                assert!(s.take_events(all).unwrap().is_empty());
                assert!(s.take_events(users).unwrap().is_empty());
            }

            #[test]
            fn watchers_come_and_go() {
                let mut s = store();
                let a = s.subscribe("cfg:");
                let b = s.subscribe("cfg:m");
                s.set("cfg:mode", "x").unwrap();
                assert!(s.unsubscribe(a));
                assert!(!s.unsubscribe(a));
                assert_eq!(s.take_events(a), Err(StoreError::UnknownSubscription(a)));
                assert_eq!(s.take_events(99), Err(StoreError::UnknownSubscription(99)));
                s.set("cfg:name", "y").unwrap();
                assert_eq!(s.take_events(b).unwrap(), vec![set_ev("cfg:mode")]);
                assert_eq!(s.subscribe("late"), 3);
                s.set("late:one", "1").unwrap();
                assert_eq!(s.take_events(3).unwrap(), vec![set_ev("late:one")]);
                assert_eq!(StoreError::UnknownSubscription(4).to_string(), "no subscription 4");
            }
        ''', S=ev_set, D=ev_del),
        cross={
            "incr": {
                "reqs": ("A successful `incr` queues a set event like `set` does.",),
                "tests": fmt('''
                    #[test]
                    fn incr_is_a_set_event() {
                        let mut s = store();
                        let id = s.subscribe("user:");
                        s.incr("user:ana", 1).unwrap();
                        assert!(s.incr("cfg:mode", 1).is_err());
                        assert_eq!(s.take_events(id).unwrap(), vec![Event::__S__("user:ana".to_string())]);
                    }
                ''', S=ev_set)},
            "cas": {
                "reqs": ("A successful `compare_and_set` queues a set event; a failed comparison queues nothing.",),
                "tests": fmt('''
                    #[test]
                    fn cas_events() {
                        let mut s = store();
                        let id = s.subscribe("");
                        assert_eq!(s.compare_and_set("user:ana", Some("nope"), "1"), Ok(false));
                        assert_eq!(s.compare_and_set("user:ana", Some("10"), "1"), Ok(true));
                        assert_eq!(s.take_events(id).unwrap(), vec![Event::__S__("user:ana".to_string())]);
                    }
                ''', S=ev_set)},
            "capacity": {"tests": fmt('''
                #[test]
                fn full_store_queues_nothing() {
                    let mut s = Store::with_capacity(1).unwrap();
                    let id = s.subscribe("");
                    s.set("a", "1").unwrap();
                    assert!(s.set("b", "2").is_err());
                    assert_eq!(s.take_events(id).unwrap(), vec![Event::__S__("a".to_string())]);
                }
            ''', S=ev_set)},
            "ttl": {
                "reqs": ("`set_with_ttl` queues one set event. Expiry and `persist` queue nothing.",),
                "tests": fmt('''
                    #[test]
                    fn ttl_events() {
                        let mut s = store();
                        let id = s.subscribe("t");
                        s.set_with_ttl("tmp", "x", 1).unwrap();
                        assert!(s.persist("tmp"));
                        s.set_with_ttl("t2", "x", 1).unwrap();
                        s.advance(5);
                        assert!(!s.delete("t2"));
                        assert_eq!(s.take_events(id).unwrap(), vec![
                            Event::__S__("tmp".to_string()),
                            Event::__S__("t2".to_string()),
                        ]);
                    }
                ''', S=ev_set)},
            "dump": {
                "reqs": ("`load` queues one set event per applied line, in line order.",),
                "tests": fmt('''
                    #[test]
                    fn load_events() {
                        let mut s = store();
                        let id = s.subscribe("");
                        s.load("a=1\\nuser:ana=2\\na=3\\n").unwrap();
                        assert!(s.load("b=1\\noops\\n").is_err());
                        assert_eq!(s.take_events(id).unwrap(), vec![
                            Event::__S__("a".to_string()),
                            Event::__S__("user:ana".to_string()),
                            Event::__S__("a".to_string()),
                        ]);
                    }
                ''', S=ev_set)},
        },
    ))

    S.append(Slice(
        id="txn", title="Transactions", d=4,
        pitch=("Updating a user and its index key takes two calls, and a crash in between leaves the store inconsistent.",
               "Callers need to apply several changes as a unit that either all happen or none does."),
        reqs=("`store.transaction(f) -> Result<T, E>` runs the closure `f: FnOnce(&mut Store) -> Result<T, E>` (generic over `T` and `E`) with the store itself. If the closure returns `Ok`, all its changes stay and its value is returned. If it returns `Err`, every change made to keys, values and expiry deadlines during the closure is undone, and the error is returned. Transactions may be nested: an inner `transaction` that fails is undone on its own, and the outer one decides about the rest.",
              "Only the data is rolled back. Any other state keeps what the closure did, for example the logical clock moved by `advance` and subscriptions created or removed inside the closure."),
        code={
            "src/store.rs::methods": '''
                pub fn transaction<T, E, F>(&mut self, f: F) -> Result<T, E>
                where
                    F: FnOnce(&mut Store) -> Result<T, E>,
                {
                    let backup = self.data.clone();
                    @@slot txn_mark
                    let result = f(self);
                    if result.is_err() {
                        self.data = backup;
                        @@slot txn_rollback
                    }
                    result
                }
            ''',
        },
        readme="## Transactions\n\n`store.transaction(|s| { ... })` runs a closure returning `Result<T, E>`: on `Ok` the changes stay, on `Err` the keys, values and deadlines are restored. Nested transactions roll back independently. The logical clock and subscriptions are not rolled back.\n",
        vtests='''
            #[test]
            fn txn_basic() {
                let mut s = store();
                let r: Result<(), &str> = s.transaction(|t| {
                    t.set("user:ana", "99").unwrap();
                    Err("abort")
                });
                assert_eq!(r, Err("abort"));
                assert_eq!(s.get("user:ana"), Some("10"));
            }
        ''',
        tests='''
            #[test]
            fn commit_and_rollback() {
                let mut s = store();
                let ok: Result<i32, String> = s.transaction(|t| {
                    t.set("user:ana", "11").unwrap();
                    t.delete("user:bob");
                    t.set("user:cy", "1").unwrap();
                    Ok(42)
                });
                assert_eq!(ok, Ok(42));
                assert_eq!(s.keys(), vec!["cfg:mode", "cfg:name", "user:ana", "user:cy"]);
                let bad: Result<(), String> = s.transaction(|t| {
                    t.set("user:ana", "99").unwrap();
                    t.delete("cfg:mode");
                    t.set("new", "1").unwrap();
                    t.delete("user:cy");
                    Err("nope".to_string())
                });
                assert_eq!(bad, Err("nope".to_string()));
                assert_eq!(s.keys(), vec!["cfg:mode", "cfg:name", "user:ana", "user:cy"]);
                assert_eq!(s.get("user:ana"), Some("11"));
                assert_eq!(s.get("cfg:mode"), Some("fast"));
                assert_eq!(s.get("new"), None);
            }

            #[test]
            fn closure_sees_its_own_changes_and_errors_pass_through() {
                let mut s = store();
                let r: Result<String, StoreError> = s.transaction(|t| {
                    t.set("k", "v")?;
                    let seen = t.get("k").unwrap().to_string();
                    t.set("bad key", "x")?;
                    Ok(seen)
                });
                assert_eq!(r, Err(StoreError::BadKey("bad key".to_string())));
                assert_eq!(s.get("k"), None);
                let r: Result<String, StoreError> = s.transaction(|t| {
                    t.set("k", "v")?;
                    Ok(t.get("k").unwrap().to_string())
                });
                assert_eq!(r, Ok("v".to_string()));
            }

            #[test]
            fn nested_transactions() {
                let mut s = store();
                let r: Result<(), String> = s.transaction(|t| {
                    t.set("outer", "1").unwrap();
                    let inner: Result<(), String> = t.transaction(|u| {
                        u.set("inner", "1").unwrap();
                        u.delete("user:ana");
                        Err("inner failed".to_string())
                    });
                    assert_eq!(inner, Err("inner failed".to_string()));
                    assert_eq!(t.get("inner"), None);
                    assert_eq!(t.get("user:ana"), Some("10"));
                    let kept: Result<(), String> = t.transaction(|u| {
                        u.set("kept", "1").unwrap();
                        Ok(())
                    });
                    assert!(kept.is_ok());
                    Err("outer failed".to_string())
                });
                assert_eq!(r, Err("outer failed".to_string()));
                assert_eq!(s.get("outer"), None);
                assert_eq!(s.get("kept"), None);
                assert_eq!(s.len(), 4);
            }
        ''',
        cross={
            "ttl": {
                "reqs": ("Deadlines set or cleared inside a rolled-back transaction are restored too; the clock itself is not rolled back, so a key whose restored deadline has passed in the meantime is simply expired.",),
                "tests": '''
                    #[test]
                    fn rollback_restores_deadlines_but_not_the_clock() {
                        let mut s = store();
                        s.set_with_ttl("tmp", "x", 10).unwrap();
                        let r: Result<(), ()> = s.transaction(|t| {
                            t.set("tmp", "forever").unwrap();
                            t.advance(4);
                            Err(())
                        });
                        assert!(r.is_err());
                        assert_eq!(s.now(), 4);
                        assert_eq!((s.get("tmp"), s.ttl("tmp")), (Some("x"), Some(6)));
                        let r: Result<(), ()> = s.transaction(|t| {
                            t.advance(7);
                            Err(())
                        });
                        assert!(r.is_err());
                        assert_eq!(s.get("tmp"), None);
                        assert_eq!(s.len(), 4);
                    }
                '''},
            "watch": {
                "reqs": ("Events queued during a transaction that is rolled back are removed from the queues of all watchers (also from watchers created inside it); events queued before it stay.",),
                "code": {
                    "src/store.rs::txn_mark": "let marks: Vec<(usize, usize)> = self.subs.iter().map(|s| (s.id, s.pending.len())).collect();",
                    "src/store.rs::txn_rollback": '''
                        for s in &mut self.subs {
                            let keep = marks.iter().find(|(id, _)| *id == s.id).map(|(_, n)| *n).unwrap_or(0);
                            s.pending.truncate(keep);
                        }
                    ''',
                },
                "tests": fmt('''
                    #[test]
                    fn rollback_discards_events() {
                        let mut s = store();
                        let id = s.subscribe("");
                        s.set("before", "1").unwrap();
                        let r: Result<(), ()> = s.transaction(|t| {
                            t.set("during", "1").unwrap();
                            t.delete("user:ana");
                            Err(())
                        });
                        assert!(r.is_err());
                        let ok: Result<(), ()> = s.transaction(|t| {
                            t.set("kept", "1").unwrap();
                            Ok(())
                        });
                        assert!(ok.is_ok());
                        assert_eq!(s.take_events(id).unwrap(), vec![
                            Event::__S__("before".to_string()),
                            Event::__S__("kept".to_string()),
                        ]);
                    }
                ''', S=ev_set)},
            "capacity": {"tests": '''
                #[test]
                fn rollback_frees_capacity() {
                    let mut s = Store::with_capacity(2).unwrap();
                    s.set("a", "1").unwrap();
                    let r: Result<(), StoreError> = s.transaction(|t| {
                        t.set("b", "2")?;
                        t.set("c", "3")
                    });
                    assert_eq!(r, Err(StoreError::Full(2)));
                    assert_eq!(s.keys(), vec!["a"]);
                    s.set("b", "2").unwrap();
                }
            '''},
        },
    ))

    return S


APP = App(
    name="kvmem", lang="rust", title="the key-value store library", role="a config service developer", key="KV",
    base={
        "README.md": README + "\n@@blocks features\n",
        "Cargo.toml": langs.cargo_toml("kvmem"),
        "src/lib.rs": LIB,
        "src/error.rs": ERROR,
        "src/store.rs": STORE,
        ".gitignore": langs.GITIGNORE["rust"],
    },
    visible={"tests/basic.rs": VISIBLE},
    hidden={"tests/features.rs": HIDDEN},
)

register_app("feature-rs-kvmem", APP, make_slices, n=18, summary="in-memory key-value store: multi-get, prefixes, CAS, counters, capacity, expiry, dump/load, watchers, transactions")
