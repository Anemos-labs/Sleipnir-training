"""Layered configuration lookup: read many small config files and report the effective value of one key."""
from fx import Task, dd, family

WORDS = ["amber", "birch", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "juniper", "kelp", "lumen", "marble",
         "nectar", "onyx", "pebble", "quartz", "russet", "sable", "tundra", "umber", "velvet", "willow", "yarrow", "zephyr"]
KEYS = ["retry_limit", "cache_ttl_s", "batch_size", "pool_max", "http_timeout_ms", "queue_depth", "shard_count", "log_sample_rate"]
ENVS = ["dev", "staging", "prod", "canary", "eu", "us", "apac"]


@family("recall-layered-config", category="recall", lang="text", kind="lookup", n=24, mode="answer",
        summary="effective value of a key after a chain of include/override files")
def gen(rng, n):
    for i in range(n):
        depth = rng.randint(3, 8)
        key = rng.choice(KEYS)
        env = rng.choice(ENVS)
        names = [f"{rng.choice(WORDS)}{rng.randint(10, 99)}" for _ in range(depth + 6)]
        names = list(dict.fromkeys(names))
        chain = names[:depth]
        decoys = names[depth:depth + 4]
        files, answer, setter = {}, None, None
        # files chain: <env>.conf includes chain[0]; chain[k] includes chain[k+1]; the LAST file that sets the key
        # before reaching the end of the include walk (depth-first, includes processed first, then own settings) wins.
        values = {}
        for k, name in enumerate(chain):
            lines = [f"# layer {name}"]
            if k + 1 < len(chain):
                lines.append(f"include conf.d/{chain[k + 1]}.conf")
            if rng.random() < 0.55 or k == len(chain) - 1:
                v = rng.randint(2, 900)
                lines.append(f"{key} = {v}")
                values[name] = v
            for other in rng.sample(KEYS, 2):
                if other != key:
                    lines.append(f"{other} = {rng.randint(2, 900)}")
            files[f"conf.d/{name}.conf"] = "\n".join(lines) + "\n"
        for d in decoys:
            files[f"conf.d/{d}.conf"] = f"# unused layer {d}\n{key} = {rng.randint(2, 900)}\n"
        files[f"{env}.conf"] = f"# entry point for {env}\ninclude conf.d/{chain[0]}.conf\nlog_level = info\n"
        # semantics (documented in README): includes are expanded where they appear; later settings override earlier ones.
        # chain[k] includes chain[k+1] BEFORE its own settings, so a file's own setting overrides everything deeper.
        for name in chain:  # outermost (chain[0]) is applied last
            if name in values:
                answer, setter = values[name], name
                break
        files["README.md"] = dd(f'''
            # Layered configuration

            `<env>.conf` is the entry point of an environment. A line `include PATH` is replaced by the contents of
            that file, at that position. All other lines are `key = value`. When a key is set more than once in the
            expanded result, the **last** setting wins. Lines starting with `#` are comments.
        ''')
        yield Task(
            slug=f"{i + 1:02d}-{key.replace('_', '-')}",
            prompt=(f"In this repository, what is the effective value of `{key}` for the `{env}` environment, following the rules in "
                    f"README.md? Reply with the number and the name of the file whose line decides it."),
            difficulty=2 if depth <= 4 else 3 if depth <= 6 else 4,
            start=files,
            answer={"contains": [f"{answer}", f"{setter}.conf"]},
            gold_answer=f"`{key}` is {answer} for {env}; it is set in conf.d/{setter}.conf.",
            context_window=24000 if depth >= 6 else None,
            tags=["include-chain", "reading"],
            notes={"depth": depth, "key": key, "env": env},
        )
