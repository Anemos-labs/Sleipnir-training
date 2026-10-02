"""World generator shared by the research and recall families.

Everything here is fictional and deterministic given the ``random.Random`` you pass in. A *world* is an organisation
(``Org``) with invented people, teams, sites and assets, drawn from one of a dozen themes (a ferry line, a waterworks,
an observatory, ...). Families build *structured records* on top of it, render them to dated documents in several
styles, and compute every expected answer from the records, never by hand.

Also here: date helpers (unambiguous formats only), filler text for haystacks, document renderers (email, minutes,
memo, ticket, CSV), a ``Corpus`` container, the hidden *checker* template used by file-delivered tasks, and small
helpers that assemble ``fx.Task`` objects.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
from dataclasses import dataclass, field

from fx import Task

# --------------------------------------------------------------------------------------------------------------------
# names

FIRST = [
    "Alvara", "Bastien", "Calder", "Dessa", "Edrin", "Farrow", "Gisla", "Halden", "Isolde", "Jarrick", "Kesra", "Lorcan",
    "Maren", "Nilsa", "Orsin", "Pernel", "Quenby", "Rhosyn", "Sorrel", "Tamsen", "Ulric", "Vesna", "Wendal", "Xanthe",
    "Ysolde", "Zebedin", "Anselm", "Briony", "Corvin", "Delphine", "Emrys", "Fiora", "Garrick", "Hesper", "Ivo", "Jessamy",
    "Kasimir", "Linnea", "Merrick", "Niamh", "Osric", "Perpetua", "Rafferty", "Saskia", "Tobiah", "Una", "Verity", "Wystan",
    "Yarrow", "Zelda", "Abelard", "Brigid", "Cormac", "Dagny", "Evander", "Frida", "Gideon", "Hanneke", "Idris", "Juniper",
    "Kieran", "Leopold", "Marisol", "Nestor", "Odette", "Piers", "Radka", "Silas", "Thea", "Ugo", "Valentin", "Winifred",
    "Yannick", "Zora", "Aurelio", "Bettina", "Casimir", "Dorothea", "Elric", "Fenna", "Godfrey", "Helga", "Ignatius",
    "Jorunn", "Konrad", "Lucasta", "Matthias", "Nerys", "Oriel", "Philippa", "Quirin", "Rosalind", "Stellan", "Tilda",
    "Uriel", "Vigdis", "Willem", "Ximena", "Yvette", "Zacharia", "Ambrose", "Bernadette", "Cyrus", "Daphne", "Ezra",
    "Florentin", "Greta", "Hugo", "Ilse", "Jasper", "Katarina", "Lazlo", "Mirela", "Nikolai", "Ottoline", "Percival",
    "Romilly", "Sebastian", "Tatiana", "Ulla", "Viktor", "Wilhelmina", "Anneke", "Benedikt", "Clemence", "Dunstan",
]
SUR_A = [
    "Ash", "Bran", "Cor", "Dun", "Elm", "Fen", "Gal", "Hol", "Ire", "Jun", "Kel", "Lar", "Mar", "Nor", "Orr", "Pen", "Quin",
    "Ros", "Sel", "Thorn", "Ull", "Van", "Wex", "Yor", "Zan", "Black", "Crow", "Dray", "Ever", "Frost", "Gray", "Hale",
    "Ket", "Lind", "Moss", "Nash", "Oak", "Pike", "Rook", "Sand", "Tarn", "Wren", "Bar", "Cal", "Del", "Hav", "Mer", "Tal",
]
SUR_B = [
    "wick", "vik", "rigal", "more", "ley", "ford", "stad", "holm", "worth", "bury", "dale", "mark", "ton", "sen", "by",
    "combe", "shaw", "thorpe", "gate", "wood", "field", "ridge", "stone", "water", "hurst", "lund", "berg", "mere",
]

# invented place / thing names used for assets, sites, products
NAME_WORDS = [
    "Kittiwake", "Larkspur", "Ondine", "Marram", "Quillon", "Sandpiper", "Tamarind", "Brindle", "Corrach", "Dunnock",
    "Eskerdale", "Fulmar", "Gannet", "Harrowgate", "Ibex", "Juniper", "Kestrel", "Lumen", "Merlin", "Nettle", "Osprey",
    "Plover", "Quarrel", "Redshank", "Skerry", "Teal", "Umber", "Vesper", "Whimbrel", "Yarrow", "Zephyr", "Arran",
    "Bracken", "Cormorant", "Dapple", "Embers", "Fathom", "Gorse", "Heron", "Isle", "Jetty", "Kelp", "Lanyard", "Mistral",
    "Nacre", "Oriole", "Petrel", "Quay", "Rowan", "Sorrel", "Thistle", "Ullswater", "Vervain", "Wherry", "Xebec",
    "Yawl", "Zenith", "Alder", "Basalt", "Cinder", "Drumlin", "Estuary", "Fjordal", "Garnet", "Hazel", "Indigo", "Jasper",
    "Knoll", "Lichen", "Moraine", "Nimbus", "Obsidian", "Pumice", "Quartz", "Russet", "Shale", "Tundra", "Umbra", "Vale",
    "Willow", "Aster", "Birch", "Cobalt", "Dune", "Ember", "Flint", "Glen", "Hollow", "Iris", "Jade", "Kiln", "Loam",
]
ORG_WORDS = [
    "Brindlemoor", "Quillfeather", "Halcyon Reach", "Tarnholt", "Ostrava Bay", "Marrowgate", "Fennimore", "Kestrel Point",
    "Lowerby", "Windrush Cove", "Ashgrove", "Corrigal", "Dunlin", "Everhale", "Frostholm", "Greywater", "Highmere",
    "Ironbridge Fen", "Jollify", "Kelsey Sound", "Larkhill", "Moorcombe", "Northwick", "Oakenshaw", "Pennywhistle",
    "Rookery Lane", "Saltmarsh", "Thornbury Fell", "Underhill", "Vandermere", "Wexcombe", "Yarrowdale", "Zinnia Bay",
    "Alderney Reach", "Blackthorn", "Candlemas", "Drystone", "Elmstead", "Foxglove", "Gullwing", "Hartfell", "Inkwell",
]

THEMES: dict[str, dict] = {
    "ferry": dict(
        org=["{a} Ferries", "{a} Sound Ferry Company", "{a} Island Lines"],
        teams=["Operations", "Terminals", "Fleet Maintenance", "Ticketing", "Safety and Compliance", "Crew Rostering", "Finance"],
        asset="vessel", asset_fmt="MV {w}", site="terminal", site_fmt="{w} Terminal",
        titles=["Duty Master", "Port Captain", "Chief Engineer", "Terminal Supervisor", "Fleet Coordinator", "Safety Officer", "Purser"],
        unit="sailings", thing="crossing",
    ),
    "waterworks": dict(
        org=["{a} Water Board", "{a} Waterworks Authority", "{a} Aqueduct Trust"],
        teams=["Treatment", "Network Operations", "Metering", "Laboratory", "Capital Projects", "Customer Billing", "Environmental Compliance"],
        asset="pumping station", asset_fmt="{w} Pumping Station", site="reservoir", site_fmt="{w} Reservoir",
        titles=["Shift Supervisor", "Process Engineer", "Network Planner", "Lab Analyst", "Compliance Lead", "Field Technician", "Billing Manager"],
        unit="megalitres", thing="main",
    ),
    "observatory": dict(
        org=["{a} Observatory", "{a} Institute of Astronomy", "{a} Sky Survey"],
        teams=["Instrumentation", "Data Reduction", "Telescope Operations", "Outreach", "Facilities", "Visiting Observers", "Computing"],
        asset="instrument", asset_fmt="the {w} spectrograph", site="dome", site_fmt="{w} Dome",
        titles=["Night Assistant", "Instrument Scientist", "Operations Manager", "Data Curator", "Support Astronomer", "Facility Engineer", "Outreach Coordinator"],
        unit="exposures", thing="observation",
    ),
    "cooperative": dict(
        org=["{a} Growers' Cooperative", "{a} Orchard Cooperative", "{a} Farmers' Union"],
        teams=["Harvest", "Packing House", "Cold Storage", "Member Services", "Logistics", "Quality Control", "Accounts"],
        asset="orchard", asset_fmt="{w} Orchard", site="packing shed", site_fmt="{w} Shed",
        titles=["Harvest Lead", "Grader", "Cold Store Manager", "Member Liaison", "Dispatcher", "Quality Inspector", "Bookkeeper"],
        unit="crates", thing="lot",
    ),
    "software": dict(
        org=["{a} Systems", "{a} Labs", "{a} Software Collective"],
        teams=["Platform", "Payments", "Mobile", "Data", "Developer Experience", "Security", "Customer Support"],
        asset="service", asset_fmt="{w_lower}-svc", site="region", site_fmt="{w_lower}-1",
        titles=["Staff Engineer", "Engineering Manager", "Site Reliability Engineer", "Product Manager", "Support Lead", "Security Analyst", "Release Manager"],
        unit="requests", thing="deployment",
    ),
    "clinic": dict(
        org=["{a} Community Clinic", "{a} Health Cooperative", "{a} Medical Centre"],
        teams=["Reception", "Nursing", "Pharmacy", "Imaging", "Laboratory", "Facilities", "Administration"],
        asset="ward", asset_fmt="{w} Ward", site="annex", site_fmt="{w} Annex",
        titles=["Charge Nurse", "Practice Manager", "Pharmacist", "Radiographer", "Lab Coordinator", "Facilities Officer", "Receptionist"],
        unit="appointments", thing="clinic session",
    ),
    "railway": dict(
        org=["{a} Light Railway", "{a} Heritage Railway", "{a} Valley Line"],
        teams=["Traffic", "Locomotive Works", "Permanent Way", "Signals", "Stations", "Volunteers", "Treasury"],
        asset="locomotive", asset_fmt="No. {n} {w}", site="station", site_fmt="{w} Halt",
        titles=["Stationmaster", "Shed Foreman", "Signalman", "Guard Coordinator", "Track Inspector", "Volunteer Officer", "Treasurer"],
        unit="passengers", thing="working",
    ),
    "brewery": dict(
        org=["{a} Brewing Company", "{a} Brewhouse", "{a} Malt and Hop Works"],
        teams=["Brewhouse", "Cellar", "Packaging", "Quality Lab", "Sales", "Taproom", "Purchasing"],
        asset="tank", asset_fmt="Tank {w}", site="taproom", site_fmt="{w} Taproom",
        titles=["Head Brewer", "Cellarman", "Packaging Lead", "Lab Technician", "Sales Manager", "Taproom Manager", "Buyer"],
        unit="hectolitres", thing="batch",
    ),
    "library": dict(
        org=["{a} Library Service", "{a} Public Libraries", "{a} Reading Trust"],
        teams=["Lending", "Acquisitions", "Archives", "Digital Services", "Children's Services", "Facilities", "Finance"],
        asset="branch", asset_fmt="{w} Branch", site="reading room", site_fmt="{w} Reading Room",
        titles=["Branch Librarian", "Acquisitions Officer", "Archivist", "Systems Librarian", "Outreach Worker", "Caretaker", "Finance Officer"],
        unit="loans", thing="collection",
    ),
    "theatre": dict(
        org=["{a} Theatre Company", "{a} Playhouse", "{a} Arts Trust"],
        teams=["Production", "Box Office", "Wardrobe", "Lighting", "Front of House", "Education", "Development"],
        asset="production", asset_fmt="'{w}'", site="stage", site_fmt="{w} Stage",
        titles=["Stage Manager", "Box Office Manager", "Wardrobe Supervisor", "Chief Electrician", "House Manager", "Education Officer", "Development Director"],
        unit="tickets", thing="performance",
    ),
    "museum": dict(
        org=["{a} Museum", "{a} Heritage Centre", "{a} Natural History Society"],
        teams=["Collections", "Conservation", "Exhibitions", "Learning", "Visitor Services", "Registrar", "Trustees' Office"],
        asset="gallery", asset_fmt="{w} Gallery", site="store", site_fmt="{w} Store",
        titles=["Curator", "Conservator", "Registrar", "Exhibitions Manager", "Learning Officer", "Visitor Services Lead", "Collections Assistant"],
        unit="visitors", thing="exhibit",
    ),
    "lab": dict(
        org=["{a} Soil Research Station", "{a} Marine Laboratory", "{a} Field Station"],
        teams=["Field Sampling", "Analytical Chemistry", "Instrument Care", "Data Management", "Safety", "Stores", "Administration"],
        asset="plot", asset_fmt="Plot {w}", site="bench", site_fmt="{w} Bench",
        titles=["Principal Investigator", "Research Technician", "Instrument Manager", "Data Manager", "Safety Officer", "Stores Clerk", "Station Manager"],
        unit="samples", thing="assay",
    ),
    "depot": dict(
        org=["{a} Bus Company", "{a} Transit Cooperative", "{a} Coach Lines"],
        teams=["Dispatch", "Workshop", "Depot Yard", "Customer Care", "Driver Training", "Planning", "Payroll"],
        asset="route", asset_fmt="Route {n}", site="depot", site_fmt="{w} Depot",
        titles=["Dispatcher", "Workshop Foreman", "Yard Marshal", "Customer Care Lead", "Driver Trainer", "Planner", "Payroll Clerk"],
        unit="trips", thing="duty",
    ),
}
THEME_NAMES = sorted(THEMES)

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class Person:
    first: str
    last: str
    role: str = ""
    team: str = ""
    nick: str = ""

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def fl(self) -> str:  # "M. Quorn"
        return f"{self.first[0]}. {self.last}"

    @property
    def lf(self) -> str:  # "Quorn, Marit"
        return f"{self.last}, {self.first}"

    @property
    def handle(self) -> str:
        return (self.first[0] + self.last).lower()

    def email(self, domain: str) -> str:
        return f"{self.handle}@{domain}"


@dataclass
class Org:
    theme: str
    name: str
    short: str
    domain: str
    teams: list[str]
    people: list[Person]
    assets: list[str]
    sites: list[str]
    lex: dict

    def person(self, i: int) -> Person:
        return self.people[i % len(self.people)]


def make_people(rng: random.Random, k: int, teams: list[str] | None = None, titles: list[str] | None = None) -> list[Person]:
    firsts = rng.sample(FIRST, k)
    lasts: list[str] = []
    while len(lasts) < k:
        s = rng.choice(SUR_A) + rng.choice(SUR_B)
        if s not in lasts:
            lasts.append(s)
    out = []
    used_nicks: set[str] = set()
    for i in range(k):
        f = firsts[i]
        nick = f[:3] if len(f) > 5 else f[:4]
        if nick in used_nicks or nick == f:
            nick = f[:2] + f[-1]
        used_nicks.add(nick)
        out.append(Person(f, lasts[i], role=(titles[i % len(titles)] if titles else ""), team=(teams[i % len(teams)] if teams else ""), nick=nick))
    return out


def make_org(rng: random.Random, theme: str | None = None, n_people: int = 10, n_assets: int = 8, n_sites: int = 4) -> Org:
    theme = theme or rng.choice(THEME_NAMES)
    t = THEMES[theme]
    a = rng.choice(ORG_WORDS)
    name = rng.choice(t["org"]).format(a=a)
    short = "".join(w[0] for w in name.split() if w[0].isupper())[:4] or a[:3].upper()
    domain = re.sub(r"[^a-z]", "", a.lower())[:14] + ".example"
    words = rng.sample(NAME_WORDS, n_assets + n_sites)
    assets = [t["asset_fmt"].format(w=w, w_lower=w.lower(), n=rng.randint(2, 98)) for w in words[:n_assets]]
    sites = [t["site_fmt"].format(w=w, w_lower=w.lower(), n=rng.randint(2, 98)) for w in words[n_assets:]]
    teams = list(t["teams"])
    rng.shuffle(teams)
    people = make_people(rng, n_people, teams, t["titles"])
    return Org(theme=theme, name=name, short=short, domain=domain, teams=teams, people=people, assets=assets, sites=sites, lex=t)


# --------------------------------------------------------------------------------------------------------------------
# dates

def d_iso(d: dt.date) -> str:
    return d.isoformat()


def d_long(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def d_us(d: dt.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def d_short(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1][:3]} {d.year}"


def d_day(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def d_wd(d: dt.date) -> str:
    return f"{WEEKDAYS[d.weekday()][:3]} {d_short(d)}"


def d_wdlong(d: dt.date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d_long(d)}"


_FMT = {"iso": d_iso, "long": d_long, "us": d_us, "short": d_short, "wd": d_wd, "wdlong": d_wdlong}


def fmt_date(d: dt.date, style: str = "iso") -> str:
    return _FMT[style](d)


def rand_date(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    return start + dt.timedelta(days=rng.randint(0, (end - start).days))


def rand_dates(rng: random.Random, k: int, start: dt.date, end: dt.date, distinct: bool = True) -> list[dt.date]:
    span = (end - start).days + 1
    if distinct and k <= span:
        return sorted(start + dt.timedelta(days=x) for x in rng.sample(range(span), k))
    return sorted(rand_date(rng, start, end) for _ in range(k))


def base_date(rng: random.Random) -> dt.date:
    return dt.date(rng.randint(2030, 2034), rng.randint(1, 6), rng.randint(1, 28))


def add_months(d: dt.date, m: int, day: int | None = None) -> dt.date:
    y, mo = divmod(d.month - 1 + m, 12)
    return dt.date(d.year + y, mo + 1, day or min(d.day, 28))


def first_of_next_month(d: dt.date) -> dt.date:
    return add_months(d, 1, 1)


def hhmm(rng: random.Random, lo: int = 7, hi: int = 18) -> str:
    return f"{rng.randint(lo, hi):02d}:{rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]):02d}"


# --------------------------------------------------------------------------------------------------------------------
# filler (distractor prose and haystack fillers)

_FILLER = [
    "The {site} car park resurfacing is pencilled in for week {n}.",
    "Lost property: one {thing} handed in at {site}; collect from {team}.",
    "{p} is on leave from {d1} to {d2}; {q} is covering.",
    "Reminder: the {team} kitchen rota changes on {d1}.",
    "The kettle in the {team} office was descaled on {d1}. Please do not put the filter jug back in the cupboard.",
    "Fire drill at {site} took {n} minutes; the assembly point was too close to the bins again.",
    "{p} asked whether the {asset} could be added to the open-day tour. No decision yet.",
    "New starter {p} joins {team} on {d1}; please share a desk plan with {q}.",
    "Room {n} is double-booked on {d1}; {team} has priority until the calendar is fixed.",
    "The vending machine near {site} now takes cards. It still does not give change.",
    "Printer on level {m} is out of toner again; {p} has ordered {n} cartridges.",
    "A note from {p}: please label everything in the shared fridge, anything unlabelled goes on {d1}.",
    "Parking permits for {team} are renewed each year; the next batch is due {d1}.",
    "Pest control visited {site} on {d1}; no further action needed.",
    "The newsletter deadline for {team} is {d1}. Photos of the {asset} are welcome.",
    "{p} reports a draught in the east stairwell; facilities logged it as job {n}{m}.",
    "Canteen menu for the week of {d1}: soup, a pie of the day, and the usual salad nobody eats.",
    "Staff survey closes on {d2}; so far {n} responses, which {q} says is not enough.",
    "Courier collection moved to {hh} on weekdays; {team} please note.",
    "The visitor book at {site} was replaced on {d1}; the old one is with {p}.",
    "Training session on manual handling: {d1}, {hh}, run by {q}. Bring suitable shoes.",
    "Window cleaning at {site} scheduled for {d1}; blinds down please.",
    "The {asset} was photographed for the annual report by {p}; {q} approved the caption.",
    "Cycle shelter at {site} has a new lock; keys from {p}.",
    "Bank holiday opening: {site} closes at {hh} the day before, reopens as normal.",
    "{p} proposed a lunchtime walking group starting {d1}. {q} has offered a route.",
    "The {team} stationery order went in on {d1}; delivery expected within {n} working days.",
    "Heating at {site} has been set to {n} degrees pending the engineer's visit.",
    "Charity bake sale raised {n} for the local food bank; thanks to {p} and {q}.",
    "Lift maintenance at {site}: out of service {d1}, {hh} to {hh2}.",
]


def filler_line(rng: random.Random, org: Org, lo: dt.date = dt.date(2031, 1, 1), hi: dt.date = dt.date(2031, 12, 28)) -> str:
    t = rng.choice(_FILLER)
    p, q = rng.sample(org.people, 2)
    d1 = rand_date(rng, lo, hi)
    d2 = d1 + dt.timedelta(days=rng.randint(3, 20))
    return t.format(
        site=rng.choice(org.sites), n=rng.randint(2, 40), m=rng.randint(1, 9), thing=rng.choice(["umbrella", "scarf", "flask", "folder", "glove", "notebook"]),
        team=rng.choice(org.teams), p=p.full, q=q.full, d1=d_long(d1), d2=d_long(d2), asset=rng.choice(org.assets), hh=hhmm(rng, 8, 13), hh2=hhmm(rng, 14, 17),
    )


def filler_para(rng: random.Random, org: Org, k: int = 3, **kw) -> str:
    return " ".join(filler_line(rng, org, **kw) for _ in range(k))


# --------------------------------------------------------------------------------------------------------------------
# document renderers

def email(org: Org, frm: Person, to: list[Person], date: dt.date, subject: str, body: str, cc: list[Person] | None = None,
          time: str = "", dstyle: str = "wd") -> str:
    h = [f"From: {frm.full} <{frm.email(org.domain)}>", "To: " + ", ".join(f"{p.full} <{p.email(org.domain)}>" for p in to)]
    if cc:
        h.append("Cc: " + ", ".join(p.full for p in cc))
    h.append(f"Date: {fmt_date(date, dstyle)}" + (f" {time}" if time else ""))
    h.append(f"Subject: {subject}")
    return "\n".join(h) + "\n\n" + body.strip("\n") + "\n"


def thread(msgs: list[str]) -> str:
    return "\n\n-----\n\n".join(m.rstrip("\n") for m in msgs) + "\n"


def quote(text: str) -> str:
    return "\n".join("> " + ln if ln.strip() else ">" for ln in text.strip("\n").splitlines())


def minutes_doc(org: Org, team: str, date: dt.date, chair: Person, present: list[Person], apologies: list[Person], items: list[tuple[str, str]],
                actions: list[str] | None = None, dstyle: str = "long") -> str:
    out = [f"{org.name}", f"{team}: minutes of the meeting held on {fmt_date(date, dstyle)}", "",
           f"Chair: {chair.full}", "Present: " + ", ".join(p.full for p in present)]
    if apologies:
        out.append("Apologies: " + ", ".join(p.full for p in apologies))
    out.append("")
    for i, (head, text) in enumerate(items, 1):
        out.append(f"{i}. {head}")
        out.append(text.strip("\n"))
        out.append("")
    if actions:
        out.append("Actions")
        out.extend(f"- {a}" for a in actions)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def memo_doc(org: Org, memo_id: str, date: dt.date, frm: Person, to: str, subject: str, body: str, dstyle: str = "long") -> str:
    return (f"{org.name}\nINTERNAL MEMO {memo_id}\n\nDate:    {fmt_date(date, dstyle)}\nFrom:    {frm.full}, {frm.role}\nTo:      {to}\nSubject: {subject}\n\n"
            + body.strip("\n") + "\n")


def csv_text(header: list[str], rows: list[list], delim: str = ",") -> str:
    def cell(v) -> str:
        s = str(v)
        if delim in s or '"' in s or "\n" in s:
            s = '"' + s.replace('"', '""') + '"'
        return s
    return "\n".join(delim.join(cell(c) for c in r) for r in [header] + rows) + "\n"


def money(x: float | int, places: int = 2) -> str:
    return f"{x:.{places}f}"


# --------------------------------------------------------------------------------------------------------------------
# corpus container

class Corpus:
    """A dict of path -> text with a guard against duplicate paths."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def add(self, path: str, text: str) -> None:
        if path in self.files:
            raise KeyError(f"duplicate path {path}")
        self.files[path] = text

    def size(self) -> int:
        return sum(len(t) for t in self.files.values())


def slugify(s: str, maxlen: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:maxlen]


# --------------------------------------------------------------------------------------------------------------------
# hidden checker (file-delivered answers)

CHECK_PATH = "checks/check_answer.py"

CHECK_PY = r'''#!/usr/bin/env python3
"""Checks the file(s) the agent was asked to write. Prints a short explanation and, as the last line, {"score": x}."""
import csv, io, json, os, re, sys

SPEC = json.loads(r"""__SPEC__""")
notes = []


def norm(v):
    s = re.sub(r"\s+", " ", str(v).strip()).casefold()
    return s.strip("`'\" ").rstrip(".")


def num(v):
    if isinstance(v, bool):
        raise ValueError("bool")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("_", "")
    return float(s)


def same(kind, got, want, tol=0.0):
    try:
        if kind == "str":
            return norm(got) == norm(want)
        if kind == "int":
            return num(got) == int(want) and float(num(got)).is_integer()
        if kind == "num":
            return abs(num(got) - float(want)) <= tol + 1e-9
        if kind == "bool":
            if isinstance(got, bool):
                return got == want
            return norm(got) in (("true", "yes") if want else ("false", "no"))
        if kind == "date":
            return str(got).strip() == want
        if kind == "none":
            return got is None or norm(got) in ("none", "null", "n/a", "")
    except (ValueError, TypeError):
        return False
    return False


def score_field(f, got):
    """returns 0..1 for one expected field"""
    kind, want = f["type"], f["value"]
    if kind in ("set", "list"):
        if not isinstance(got, list):
            return 0.0
        g = [norm(x) for x in got]
        w = [norm(x) for x in want]
        if kind == "list":
            return 1.0 if g == w else 0.0
        gs, ws = set(g), set(w)
        if len(g) != len(gs):
            return 0.0 if gs == ws and False else (len(gs & ws) / max(1, len(gs | ws)) if gs != ws else 0.0)
        return len(gs & ws) / max(1, len(gs | ws))
    if kind == "map":  # str -> number/str, graded per key
        if not isinstance(got, dict):
            return 0.0
        tol = f.get("tol", 0.0)
        sub = f.get("sub", "str")
        gm = {norm(k): v for k, v in got.items()}
        hit = sum(1 for k, v in want.items() if norm(k) in gm and same(sub, gm[norm(k)], v, tol))
        extra = sum(1 for k in gm if k not in {norm(x) for x in want})
        return max(0.0, (hit - 0.5 * extra) / max(1, len(want)))
    return 1.0 if same(kind, got, want, f.get("tol", 0.0)) else 0.0


def load_json(path):
    if not os.path.exists(path):
        notes.append(f"{path}: not found")
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # noqa: BLE001
        notes.append(f"{path}: not valid JSON ({e})")
        return None


def check_json():
    data = load_json(SPEC["file"])
    if data is None:
        return 0.0
    if not isinstance(data, dict):
        notes.append("top level of the file must be a JSON object")
        return 0.0
    total, got_w = 0.0, 0.0
    for key, f in SPEC["fields"].items():
        w = f.get("weight", 1.0)
        total += w
        if key not in data:
            notes.append(f"missing key {key!r}")
            continue
        s = score_field(f, data[key])
        got_w += w * s
        if s < 1.0:
            notes.append(f"key {key!r}: not right ({s:.2f})")
    return got_w / total if total else 0.0


def check_csv():
    path = SPEC["file"]
    if not os.path.exists(path):
        notes.append(f"{path}: not found")
        return 0.0
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    except Exception as e:  # noqa: BLE001
        notes.append(f"{path}: unreadable ({e})")
        return 0.0
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        notes.append("empty csv")
        return 0.0
    head = [norm(c) for c in rows[0]]
    cols = SPEC["columns"]
    if head != [norm(c) for c in cols]:
        notes.append(f"header must be exactly: {','.join(cols)}")
        return 0.0
    kinds = SPEC["kinds"]
    tol = SPEC.get("tol", 0.0)
    want = SPEC["rows"]
    got = rows[1:]
    keyi = SPEC.get("key", [0])

    def key(r):
        return tuple(norm(r[i]) for i in keyi) if len(r) > max(keyi) else None

    gmap = {}
    dup = 0
    for r in got:
        k = key(r)
        if k is None:
            continue
        if k in gmap:
            dup += 1
        gmap[k] = r
    good = 0
    for w in want:
        k = tuple(norm(w[i]) for i in keyi)
        r = gmap.get(k)
        if r is None or len(r) != len(w):
            notes.append(f"missing or malformed row for {'/'.join(k)}")
            continue
        if all(same(kinds[i], r[i], w[i], tol) for i in range(len(w))):
            good += 1
        else:
            notes.append(f"row {'/'.join(k)}: wrong values")
    wk = {tuple(norm(w[i]) for i in keyi) for w in want}
    extra = len([k for k in gmap if k not in wk]) + dup
    if extra:
        notes.append(f"{extra} unexpected or duplicate rows")
    s = max(0.0, (good - 0.5 * extra) / max(1, len(want)))
    if SPEC.get("ordered") and s >= 1.0:
        order = [tuple(norm(r[i]) for i in keyi) for r in got]
        if order != [tuple(norm(w[i]) for i in keyi) for w in want]:
            notes.append("rows are right but not in the requested order")
            return 0.5
    return s


def check_report():
    path = SPEC["file"]
    if not os.path.exists(path):
        notes.append(f"{path}: not found")
        return 0.0
    text = open(path, encoding="utf-8", errors="replace").read()
    words = len(re.findall(r"\w+", text))
    found = []
    for fact in SPEC["facts"]:
        if any(re.search(p, text, re.I) for p in fact["any"]):
            found.append(fact["id"])
        else:
            notes.append(f"fact not found: {fact['id']}")
    need = SPEC["need"]
    s = min(1.0, len(found) / need)
    for bad in SPEC.get("forbid", []):
        if re.search(bad["pat"], text, re.I):
            notes.append(f"states something false: {bad['why']}")
            s -= 1.0 / max(1, need) + 0.2
    for group in SPEC.get("cite", []):
        if not any(re.search(r"(?<![A-Za-z0-9-])" + re.escape(c) + r"(?![A-Za-z0-9])", text) for c in group["any"]):
            notes.append(f"missing citation: {group['why']}")
            s -= 0.2
    for bad in SPEC.get("bad_cites", []):
        if re.search(r"(?<![A-Za-z0-9-])" + re.escape(bad) + r"(?![A-Za-z0-9])", text):
            notes.append(f"cites {bad}, which does not support any claim here")
            s -= 0.15
    lo, hi = SPEC.get("words", [0, 10**6])
    if words < lo:
        notes.append(f"too short ({words} words, need {lo})")
        s -= 0.3
    if words > hi:
        notes.append(f"too long ({words} words, at most {hi})")
        s -= 0.3
    return max(0.0, min(1.0, s))


def check_seq():
    """ordered list of {key..} objects: graded by exact positions and membership"""
    data = load_json(SPEC["file"])
    if data is None:
        return 0.0
    items = data.get(SPEC["list_key"]) if isinstance(data, dict) else data
    if not isinstance(items, list):
        notes.append("expected a list")
        return 0.0
    fields = SPEC["fields"]  # [[name, kind], ...]
    want = SPEC["rows"]

    def row(it):
        try:
            return [it[f] for f, _ in fields] if isinstance(it, dict) else list(it)
        except Exception:  # noqa: BLE001
            return None
    got = [row(it) for it in items]
    hit = 0
    for r in want:
        for g in got:
            if g is not None and len(g) == len(r) and all(same(fields[i][1], g[i], r[i]) for i in range(len(r))):
                hit += 1
                break
    member = hit / max(1, len(want))
    pos = 0
    for i, r in enumerate(want):
        if i < len(got) and got[i] is not None and len(got[i]) == len(r) and all(same(fields[j][1], got[i][j], r[j]) for j in range(len(r))):
            pos += 1
    ordered = pos / max(1, len(want))
    extra = max(0, len(got) - len(want))
    if member < 1.0:
        notes.append(f"{len(want) - hit} expected entries are missing or wrong")
    if ordered < 1.0:
        notes.append("entries are not all in the right order/position")
    if extra:
        notes.append(f"{extra} extra entries")
    return max(0.0, 0.5 * member + 0.5 * ordered - 0.1 * extra) if (member < 1 or ordered < 1 or extra) else 1.0


def check_files():
    """several small text files must exist and satisfy line-level constraints"""
    s = 0.0
    n = 0
    for f in SPEC["files"]:
        n += 1
        if not os.path.exists(f["path"]):
            notes.append(f"{f['path']}: not found")
            continue
        text = open(f["path"], encoding="utf-8", errors="replace").read()
        ok = True
        for pat in f.get("must", []):
            if not re.search(pat, text, re.M):
                notes.append(f"{f['path']}: lacks {pat}")
                ok = False
        for pat in f.get("must_not", []):
            if re.search(pat, text, re.M):
                notes.append(f"{f['path']}: contains forbidden {pat}")
                ok = False
        s += 1.0 if ok else 0.0
    return s / max(1, n)


KIND = SPEC["kind"]
score = {"json": check_json, "csv": check_csv, "report": check_report, "seq": check_seq, "files": check_files}[KIND]()
for n in notes[:14]:
    print(n)
print(json.dumps({"score": round(score, 4)}))
sys.exit(0 if score >= 0.9999 else 1)
'''


def checker(spec: dict) -> dict[str, str]:
    """The hidden-files dict holding the checker for ``spec``."""
    s = json.dumps(spec, ensure_ascii=False, sort_keys=True)
    assert '"""' not in s
    return {CHECK_PATH: CHECK_PY.replace("__SPEC__", s)}


def jf(kind: str, value, weight: float = 1.0, **kw) -> dict:
    """one expected field of a json answer"""
    d = {"type": kind, "value": value, "weight": weight}
    d.update(kw)
    return d


def json_spec(fields: dict[str, dict], file: str = "answer.json") -> dict:
    return {"kind": "json", "file": file, "fields": fields}


def csv_spec(columns: list[str], kinds: list[str], rows: list[list], key: list[int] | None = None, tol: float = 0.0,
             ordered: bool = False, file: str = "out.csv") -> dict:
    return {"kind": "csv", "file": file, "columns": columns, "kinds": kinds, "rows": rows, "key": key or [0], "tol": tol, "ordered": ordered}


def seq_spec(list_key: str, fields: list[list[str]], rows: list[list], file: str = "timeline.json") -> dict:
    return {"kind": "seq", "file": file, "list_key": list_key, "fields": fields, "rows": rows}


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------------------------------------
# task assembly

def file_task(*, slug: str, prompt: str, difficulty: int, start: dict[str, str], spec: dict, solution: dict[str, str],
              scored: bool = True, tags: list[str] | None = None, notes: dict | None = None, context_window: int | None = None,
              timeout_s: int = 60) -> Task:
    """A file-delivered answer: the agent writes the file(s) named in ``spec``; the hidden checker grades them.
    ``solution`` holds the reference files (computed from the records). ``scored`` picks json-score (partial credit)."""
    return Task(
        slug=slug, prompt=prompt, difficulty=difficulty, start=start, hidden=checker(spec), solution=solution,
        verify=f"python3 {CHECK_PATH}", pass_mode="json-score" if scored else "", tags=list(tags or []), notes=notes or {},
        context_window=context_window, timeout_s=timeout_s,
    )


def say_task(*, slug: str, prompt: str, difficulty: int, start: dict[str, str], contains: list[str], gold: str, fold: bool = True,
             tags: list[str] | None = None, notes: dict | None = None, context_window: int | None = None,
             verify: str = "", hidden: dict[str, str] | None = None, solution: dict[str, str] | None = None) -> Task:
    """Answer-mode: the final message must contain every string in ``contains``."""
    return Task(
        slug=slug, prompt=prompt, difficulty=difficulty, start=start, answer={"contains": contains, "fold": fold}, gold_answer=gold,
        tags=list(tags or []), notes=notes or {}, context_window=context_window, verify=verify, hidden=hidden or {}, solution=solution or {},
    )


# --------------------------------------------------------------------------------------------------------------------
# prompt voice

OPENERS = [
    "", "", "", "Quick one: ", "Hi, ", "Could you help me with something? ", "I'm picking this up from a colleague who left. ",
    "Sorry to ask, but ", "Before tomorrow's meeting I need this: ", "Question from the {team} team. ", "Another one for the pile: ",
    "I inherited this folder and can't find my way around it. ", "Boss wants this by end of day. ", "No rush, but ",
]
CLOSERS = [
    "", "", "", " Thanks!", " Thanks in advance.", " Please keep it short.", " Show me which file you got it from.", " Don't guess; if the files don't say, tell me.",
    " I only need the final answer, not a walkthrough.", " Cheers.", " Please double-check against the later documents; things get changed.",
]


def voice(rng: random.Random, org: Org, body: str, closers: bool = True) -> str:
    o = rng.choice(OPENERS).format(team=rng.choice(org.teams))
    c = rng.choice(CLOSERS) if closers else ""
    if o and body[:1].isupper() is False and o.endswith(". "):
        body = body[:1].upper() + body[1:]
    return (o + body + c).strip()


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def pad_files(rng: random.Random, org: Org, files: dict[str, str], k: int, folder: str, lo: dt.date, hi: dt.date, paras: int = 2) -> None:
    """Add ``k`` filler notes (office chatter) under ``folder`` to enlarge a corpus."""
    for i in range(k):
        d = rand_date(rng, lo, hi)
        p = rng.choice(org.people)
        name = f"{folder}/{d_iso(d)}-note-{rng.randint(100, 999)}.txt"
        while name in files:
            name = f"{folder}/{d_iso(d)}-note-{rng.randint(100, 999)}.txt"
        files[name] = f"Note from {p.full} ({p.team}), {d_long(d)}\n\n" + filler_para(rng, org, paras, lo=lo, hi=hi) + "\n"
