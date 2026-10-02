"""Which configuration layer wins? Precedence decided by loader code, locked keys, files that are not in the repo, environment variables and flags."""
from __future__ import annotations

from fx import family

from . import _cfg as G
from . import _check as C
from . import _fam as F
from . import _voice as V

L4 = ["python", "javascript", "go", "ruby"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _build(rng, lang, tier):
    for _ in range(60):
        c = G.make_cfg(rng, lang, tier)
        envf = G.env_files_for(rng, c)
        sc = G.scenario(rng, c, tier)
        files = G.render(c, envf)
        vals, prov = G.simulate(c, sc, envf)
        real = G.run_real(c, files, sc)
        if real != vals:
            raise AssertionError(f"config simulation differs from the real loader: {sorted(set(real.items()) ^ set(vals.items()))[:4]}")
        yield_ok = [k for k in c.keys if prov[k] != c.layer_label["defaults"]]
        if len(yield_ok) >= 2:
            return c, envf, sc, files, vals, prov
    raise RuntimeError("config: nothing suitable")


def _scenario_text(c, sc) -> str:
    return "`" + G.command(c, sc) + "`"


@family("explain-config-layers", category="explain", lang="mixed", kind="lookup", n=10, mode="answer",
        summary="effective value of one setting and the layer that supplies it, given the files, APP_ENV, environment variables and --set flags (precedence lives in the loader code)")
def config_layers(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        c, envf, sc, files, vals, prov = _build(rng, lang, tier)
        # prefer keys touched by several sources (including a locked key when there is one)
        env = sc["app_env"] or c.env_name
        contenders = {}
        for k in c.keys:
            ls = ["defaults"] if k in c.files["defaults"] else []
            ls += [l for l in ("site", "local") if l in c.layers and c.present.get(l, False) and k in c.files.get(l, {})]
            if k in envf.get(env, {}):
                ls.append("env")
            if k in sc["environ"]:
                ls.append("environ")
            if k in sc["cli"]:
                ls.append("cli")
            contenders[k] = ls
        pool = sorted(k for k in c.keys if len(contenders[k]) >= (3 if tier >= 3 else 2))
        pool = pool or sorted(c.keys, key=lambda k: -len(contenders[k]))[:3]
        key = rng.choice([k for k in pool if k in c.locked] if (c.locked and rng.random() < 0.6 and any(k in c.locked and len(contenders[k]) >= 2 for k in pool)) else pool)
        value, layer = vals[key], prov[key]
        cmd = _scenario_text(c, sc)
        ask = rng.choice([
            f"I start the program with {cmd}. What is the effective value of `{key}`, and which layer of the loader supplies it? Name the layer the way it is spelled in the loader's list of layers.",
            f"With this invocation, {cmd}, which value does `{key}` end up with and where does it come from (the layer name used in the loader code)?",
            f"Run {cmd}. For the setting `{key}`: value and winning layer, please. The files in `config/` and the loader decide it.",
        ])
        fmt = "End your reply with two lines: `Value: [VALUE]` and `Layer: [layer name]`."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Production shows a different value than I expect.", "Someone says the env var is ignored."]), tag=c.name[:3].upper())
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{key.replace('.', '-').replace('_', '-')}", prompt=prompt, difficulty=d, start=files,
                         contains=[f"Value: [{value}]", f"Layer: [{layer}]"], gold=f"`{key}` is {value}, supplied by the `{layer}` layer.\n\nValue: [{value}]\nLayer: [{layer}]", lang=lang,
                         tags=["config", "precedence", lang], notes={"tier": tier, "key": key, "layers": c.layers, "locked": c.locked, "scenario": sc})


@family("explain-config-provenance", category="explain", lang="mixed", kind="greenfield", n=8,
        summary="for several settings, which layer supplies the effective value under a given invocation (answer.json map; locked keys, missing files, order decided by the loader)")
def config_provenance(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (0, 20, 36, 28, 16))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        c, envf, sc, files, vals, prov = _build(rng, lang, tier)
        k = min(len(c.keys), {2: 4, 3: 5, 4: 7, 5: 9}[tier])
        keys = rng.sample(c.keys, k)
        ans = {key: prov[key] for key in keys}
        cmd = _scenario_text(c, sc)
        ask = rng.choice([
            f"Under the invocation {cmd}, which layer supplies the effective value of each of these settings: {', '.join('`' + x + '`' for x in sorted(keys))}? Use the layer names from the loader.",
            f"For {cmd}, tell me where each of {', '.join('`' + x + '`' for x in sorted(keys))} comes from. The answer is a layer name per setting, as the loader spells them.",
        ])
        spec = C.json_spec({"layers": C.jf("map", ans, sub="str", knorm="exact", norm="exact")})
        fmt = "Write `answer.json` as {\"layers\": {\"section.key\": \"layer name\", ...}} with one entry per setting asked about."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I'm writing a config-debugging section for the runbook."]), tag=c.name[:3].upper())
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{k}-keys", prompt=prompt, difficulty=F.clamp(tier), start=files, spec=spec, answer={"layers": ans}, lang=lang,
                          tags=["config", "precedence", lang, "answer-json"], notes={"tier": tier, "layers": c.layers, "locked": c.locked, "scenario": sc})
