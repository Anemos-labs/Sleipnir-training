"""Callback-style JavaScript flows and their async/await rewrites (for the callbacks-to-async family)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    kind: str  # call | guard | let | when
    a: str = ""  # call: "svc.method"; guard: condition; let: variable; when: condition
    args: tuple = ()
    res: str = ""  # variable bound to the result (call) / expression (let) / message expr (guard)
    wrap: str = ""  # error message prefix for call failures
    inner: "Step | None" = None
    opt: float = 1.0  # probability that the step is part of an instance
    needs: str = ""  # only included together with the step that binds this variable


def call(target, args=(), res="", wrap="", opt=1.0):
    return Step("call", target, tuple(args), res, wrap, opt=opt)


def guard(cond, msg, opt=1.0, needs=""):
    return Step("guard", cond, res=msg, opt=opt, needs=needs)


def let(var, expr, opt=1.0):
    return Step("let", var, res=expr, opt=opt)


def when(cond, inner, opt=1.0):
    return Step("when", cond, inner=inner, opt=opt)


@dataclass
class Flow:
    key: str
    name: str  # exported function
    file: str  # e.g. src/fulfil.js
    param: str  # first parameter name
    steps: list
    result: str  # JS expression
    fakes: str  # JS object literal text: { service: { method: (state, ...args) => value } }
    doc: str
    noun: str
    cases: object  # callable (rng, n) -> list of {"input":..., "state":...}


def _ind(n):
    return "  " * n


def _call_expr(step, cbvar, cbbody_open):
    svc, method = step.a.split(".")
    args = ", ".join(step.args)
    return svc, method, args


def emit_callbacks(flow: Flow, steps: list) -> str:
    """Nested-callback version."""
    lines = []

    def err_return(step, ind):
        if step.wrap:
            return f"{_ind(ind)}if (err) return cb(new Error('{step.wrap}' + err.message));"
        return f"{_ind(ind)}if (err) return cb(err);"

    def call_open(step, ind, tail):
        svc, method = step.a.split(".")
        args = ", ".join(step.args)
        argpart = (args + ", ") if args else ""
        resname = step.res if step.res else "_"
        params = f"(err, {step.res})" if step.res else "(err)"
        lines.append(f"{_ind(ind)}svc.{svc}.{method}({argpart}{params} => {{")
        lines.append(err_return(step, ind + 1))
        if tail is not None:
            tail(ind + 1)
        lines.append(f"{_ind(ind)}}});")

    def emit(i, ind):
        if i == len(steps):
            lines.append(f"{_ind(ind)}cb(null, {flow.result});")
            return
        s = steps[i]
        if s.kind == "guard":
            lines.append(f"{_ind(ind)}if ({s.a}) return cb(new Error({s.res}));")
            emit(i + 1, ind)
        elif s.kind == "let":
            lines.append(f"{_ind(ind)}const {s.a} = {s.res};")
            emit(i + 1, ind)
        elif s.kind == "call":
            call_open(s, ind, lambda n: emit(i + 1, n))
        elif s.kind == "when":
            join = "after" + "".join(p.capitalize() for p in s.inner.a.replace(".", " ").split())
            lines.append(f"{_ind(ind)}const {join} = () => {{")
            emit(i + 1, ind + 1)
            lines.append(f"{_ind(ind)}}};")
            lines.append(f"{_ind(ind)}if ({s.a}) {{")
            call_open(s.inner, ind + 1, lambda n: lines.append(f"{_ind(n)}{join}();"))
            lines.append(f"{_ind(ind)}}} else {{")
            lines.append(f"{_ind(ind + 1)}{join}();")
            lines.append(f"{_ind(ind)}}}")

    lines.append(f"function {flow.name}({flow.param}, svc, cb) {{")
    emit(0, 1)
    lines.append("}")
    return "\n".join(lines)


def emit_async(flow: Flow, steps: list, dual: bool) -> str:
    lines = []

    def call_line(step, ind, bind=True):
        svc, method = step.a.split(".")
        args = ", ".join(step.args)
        argpart = (", " + args) if args else ""
        expr = f"call(svc.{svc}, '{method}'{argpart})"
        if step.wrap:
            if step.res and bind:
                lines.append(f"{_ind(ind)}let {step.res};")
            lines.append(f"{_ind(ind)}try {{")
            lines.append(f"{_ind(ind + 1)}{step.res + ' = ' if (step.res and bind) else ''}await {expr};")
            lines.append(f"{_ind(ind)}}} catch (err) {{")
            lines.append(f"{_ind(ind + 1)}throw new Error('{step.wrap}' + err.message);")
            lines.append(f"{_ind(ind)}}}")
        else:
            prefix = f"const {step.res} = " if (step.res and bind) else ""
            lines.append(f"{_ind(ind)}{prefix}await {expr};")

    for s in steps:
        if s.kind == "guard":
            lines.append(f"  if ({s.a}) throw new Error({s.res});")
        elif s.kind == "let":
            lines.append(f"  const {s.a} = {s.res};")
        elif s.kind == "call":
            call_line(s, 1)
        elif s.kind == "when":
            lines.append(f"  if ({s.a}) {{")
            call_line(s.inner, 2)
            lines.append("  }")
    lines.append(f"  return {flow.result};")
    inner = "\n".join(lines)
    head = f"""function call(obj, method, ...args) {{
  return new Promise((resolve, reject) => {{
    obj[method](...args, (err, result) => (err ? reject(err) : resolve(result)));
  }});
}}
"""
    if not dual:
        return f"{head}\nasync function {flow.name}({flow.param}, svc) {{\n{inner}\n}}"
    return (f"{head}\nasync function {flow.name}Async({flow.param}, svc) {{\n{inner}\n}}\n\n"
            f"// Promise when called without a callback, node-style callback otherwise.\n"
            f"function {flow.name}({flow.param}, svc, cb) {{\n  const promise = {flow.name}Async({flow.param}, svc);\n"
            f"  if (typeof cb !== 'function') return promise;\n  promise.then((value) => cb(null, value), (err) => cb(err));\n}}")


FAKES_HELPER = '''// Fake callback-style services: every method records the call, answers on a later tick and can be scripted to fail.
function makeServices(state) {
  const impls = IMPLS;
  const log = [];
  const svc = {};
  for (const [name, methods] of Object.entries(impls)) {
    svc[name] = {};
    for (const [method, impl] of Object.entries(methods)) {
      svc[name][method] = (...args) => {
        const cb = args.pop();
        log.push(name + '.' + method + '(' + args.map((a) => JSON.stringify(a)).join(',') + ')');
        setImmediate(() => {
          const failure = state.fail && state.fail[name + '.' + method];
          if (failure) return cb(new Error(failure));
          let out;
          try {
            out = impl(state, ...args);
          } catch (e) {
            return cb(e);
          }
          cb(null, out);
        });
      };
    }
  }
  return { svc, log };
}

module.exports = { makeServices };
'''


def helpers_js(flow: Flow) -> str:
    return FAKES_HELPER.replace("IMPLS", flow.fakes.strip())


# ---------------------------------------------------------------------------------------------------------------
# domains
# ---------------------------------------------------------------------------------------------------------------
def _order_cases(rng, n):
    out = []
    skus = ["kettle-2", "lamp-9", "rug-4", "pan-1", "clock-7"]
    for i in range(n):
        items = {s: {"sku": s, "price": rng.randrange(8, 90) * 100, "stock": rng.randrange(0, 12)} for s in skus}
        o = {"sku": rng.choice(skus + (["ghost-0"] if i % 9 == 8 else [])), "qty": rng.randrange(1, 9)}
        if rng.random() < 0.6:
            o["email"] = "buyer%d@example.test" % i
        if rng.random() < 0.4:
            o["budget"] = rng.randrange(5, 120) * 100
        fail = {}
        if i % 7 == 6:
            fail[rng.choice(["pricing.quote", "store.reserve", "mailer.send", "ledger.record", "audit.note"])] = "service down"
        out.append({"input": o, "state": {"items": items, "ledger": [], "fail": fail}})
    return out


ORDER = Flow(
    key="orders", name="fulfilOrder", file="src/fulfil.js", param="order", doc="fulfil an order", noun="order fulfilment",
    steps=[
        call("store.getItem", ["order.sku"], "item"),
        guard("!item", "'unknown sku ' + order.sku"),
        guard("item.stock < order.qty", "'only ' + item.stock + ' left of ' + order.sku"),
        call("pricing.quote", ["item", "order.qty"], "price", wrap="pricing failed: "),
        let("total", "price.unit * order.qty + price.shipping"),
        guard("order.budget !== undefined && total > order.budget", "'over budget: ' + total", opt=0.5),
        call("store.reserve", ["order.sku", "order.qty"], "left"),
        when("order.email", call("mailer.send", ["order.email", "'Order ' + order.sku"], wrap="mail failed: "), opt=0.8),
        call("audit.note", ["'fulfilled ' + order.sku"], opt=0.5),
        call("ledger.record", ["{ sku: order.sku, total }"], "entries"),
    ],
    result="{ sku: order.sku, total, left, entries, notified: Boolean(order.email) }",
    fakes='''{
    store: {
      getItem: (state, sku) => (state.items[sku] ? { ...state.items[sku] } : null),
      reserve: (state, sku, qty) => { state.items[sku].stock -= qty; return state.items[sku].stock; },
    },
    pricing: { quote: (state, item, qty) => ({ unit: item.price, shipping: qty > 5 ? 0 : 450 }) },
    mailer: { send: (state, to, subject) => 'queued' },
    audit: { note: (state, msg) => 'ok' },
    ledger: { record: (state, entry) => state.ledger.push(entry) },
  }''', cases=_order_cases)


def _signup_cases(rng, n):
    out = []
    for i in range(n):
        users = {"taken%d@example.test" % j: {"id": j} for j in range(2)}
        email = rng.choice(["new%d@example.test" % i, "taken0@example.test", "taken1@example.test"]) if i % 5 else "new%d@example.test" % i
        req = {"email": email, "password": rng.choice(["pw", "longer-password", "x" * 12]), "plan": rng.choice(["free", "pro", "team"])}
        fail = {}
        if i % 8 == 7:
            fail[rng.choice(["hasher.hash", "users.create", "mailer.welcome", "quota.check", "audit.log"])] = "boom"
        out.append({"input": req, "state": {"users": users, "next_id": 10, "limits": {"free": 1, "pro": 5, "team": 20}, "seats": {"free": rng.randrange(0, 3),
                                                                                                                              "pro": rng.randrange(0, 6), "team": rng.randrange(0, 21)}, "fail": fail}})
    return out


SIGNUP = Flow(
    key="signup", name="signUp", file="src/signup.js", param="request", doc="register a new user", noun="sign-up",
    steps=[
        call("users.findByEmail", ["request.email"], "existing"),
        guard("existing", "'email already registered: ' + request.email"),
        call("quota.check", ["request.plan"], "quota", wrap="quota lookup failed: ", opt=0.7),
        guard("quota !== undefined && quota.used >= quota.limit", "'no seats left on ' + request.plan", needs="quota"),
        call("hasher.hash", ["request.password"], "hash", wrap="hashing failed: "),
        call("users.create", ["{ email: request.email, hash, plan: request.plan }"], "user"),
        when("request.plan !== 'free'", call("mailer.welcome", ["request.email"], wrap="welcome mail failed: "), opt=0.8),
        call("audit.log", ["'signup ' + user.id"], opt=0.6),
    ],
    result="{ id: user.id, plan: request.plan }",
    fakes='''{
    users: {
      findByEmail: (state, email) => state.users[email] || null,
      create: (state, rec) => { const id = state.next_id++; state.users[rec.email] = { id }; return { id }; },
    },
    quota: { check: (state, plan) => ({ used: state.seats[plan], limit: state.limits[plan] }) },
    hasher: { hash: (state, pw) => 'h:' + pw.split('').reverse().join('') },
    mailer: { welcome: (state, to) => 'sent' },
    audit: { log: (state, msg) => 'ok' },
  }''', cases=_signup_cases)


def _report_cases(rng, n):
    out = []
    for i in range(n):
        sites = ["north", "south", "dock"]
        st = {"stock": {s: rng.randrange(0, 500) for s in sites}, "sales": {s: [rng.randrange(0, 90) for _ in range(rng.randrange(1, 8))] for s in sites},
              "cache": {}, "fail": {}}
        if i % 7 == 6:
            st["fail"][rng.choice(["warehouse.stock", "sales.week", "forecast.predict", "cache.put"])] = "timeout"
        out.append({"input": {"site": rng.choice(sites + (["moon"] if i % 9 == 8 else [])), "weeks": rng.randrange(1, 5)}, "state": st})
    return out


REPORT = Flow(
    key="report", name="buildReport", file="src/report.js", param="req", doc="build the weekly stock report", noun="stock report",
    steps=[
        call("warehouse.stock", ["req.site"], "stock", wrap="warehouse: "),
        guard("stock === undefined", "'unknown site ' + req.site"),
        call("sales.week", ["req.site"], "sales", wrap="sales: "),
        let("sold", "sales.reduce((a, b) => a + b, 0)"),
        guard("sold < 0", "'negative sales'", opt=0.3),
        call("forecast.predict", ["stock", "sales"], "forecast", wrap="forecast: "),
        let("weeksLeft", "forecast.perWeek === 0 ? null : Math.floor(stock / forecast.perWeek)"),
        when("weeksLeft !== null && weeksLeft < req.weeks", call("notes.flag", ["req.site", "weeksLeft"], wrap="notes: "), opt=0.7),
        call("cache.put", ["'report:' + req.site", "{ stock, sold, weeksLeft }"], opt=0.8),
    ],
    result="{ site: req.site, stock, sold, weeksLeft }",
    fakes='''{
    warehouse: { stock: (state, site) => state.stock[site] },
    sales: { week: (state, site) => state.sales[site] },
    forecast: { predict: (state, stock, sales) => ({ perWeek: Math.round(sales.reduce((a, b) => a + b, 0) / sales.length) }) },
    notes: { flag: (state, site, weeks) => 'flagged' },
    cache: { put: (state, key, value) => { state.cache[key] = value; return true; } },
  }''', cases=_report_cases)


FLOWS = [ORDER, SIGNUP, REPORT]
