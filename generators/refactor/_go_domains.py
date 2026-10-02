"""Go "long function" domains for the extract-function family (stages inlined in the start, extracted in the solution)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoStage:
    name: str  # helper function name
    title: str
    ins: tuple  # ((name, type), ...)
    outs: tuple  # ((name, type), ...)
    body: str  # uses FAIL(expr) for early error returns, 4-space indentation, $params
    doc: str
    optional: bool = True
    fails: bool = False


@dataclass
class GoDomain:
    key: str
    mod: str  # module name
    pkg: str
    file: str
    func: str
    inp: str  # input type
    res: str  # result type
    sig_name: str  # parameter name of the entry
    pkgdoc: str
    funcdoc: str
    header: str
    params: object  # rng -> dict
    stages: list
    epilogue: str
    cases: object  # (rng, n) -> list of dicts
    topic: str


# ----------------------------------------------------------------------------------------------------------------
POST_HEADER = '''const (
    // MaxWeightG is the heaviest parcel the desk accepts.
    MaxWeightG = $maxw
    baseCents  = $base
    stepG      = $stepg
    stepCents  = $stepc
    zoneCents  = $zonec
    sigCents   = $sigc
    freeCover  = $cover
    capCents   = $cap
)

// Parcel is what the customer hands over at the counter.
type Parcel struct {
    WeightG       int
    Zone          int
    Signature     bool
    Fragile       bool
    DeclaredCents int
}

// Quote is a price together with one explanation line per charge.
type Quote struct {
    Cents int
    Notes []string
}
'''

POST_STAGES = [
    GoStage("check", "validation", (("p", "Parcel"),), (), '''
if p.WeightG <= 0 || p.WeightG > MaxWeightG {
    FAIL(fmt.Errorf("weight %d g is outside 1..%d", p.WeightG, MaxWeightG))
}
if p.Zone < 1 || p.Zone > 4 {
    FAIL(fmt.Errorf("unknown zone %d", p.Zone))
}
''', "check rejects parcels the desk cannot carry.", optional=False, fails=True),
    GoStage("baseFare", "base fare", (("p", "Parcel"),), (("total", "int"), ("notes", "[]string")), '''
total := baseCents + ((p.WeightG-1)/stepG)*stepCents
notes := []string{fmt.Sprintf("base for %d g: %d", p.WeightG, total)}
''', "baseFare prices the weight alone.", optional=False),
    GoStage("zoneSurcharge", "zone surcharge", (("p", "Parcel"), ("total", "int"), ("notes", "[]string")), (("total", "int"), ("notes", "[]string")), '''
if p.Zone > 1 {
    extra := (p.Zone - 1) * zoneCents
    total += extra
    notes = append(notes, fmt.Sprintf("zone %d: +%d", p.Zone, extra))
}
''', "zoneSurcharge adds a fee for every zone beyond the first."),
    GoStage("signatureFee", "signature on delivery", (("p", "Parcel"), ("total", "int"), ("notes", "[]string")), (("total", "int"), ("notes", "[]string")), '''
if p.Signature {
    total += sigCents
    notes = append(notes, fmt.Sprintf("signature: +%d", sigCents))
}
''', "signatureFee charges for proof of delivery."),
    GoStage("fragileHandling", "fragile handling", (("p", "Parcel"), ("total", "int"), ("notes", "[]string")), (("total", "int"), ("notes", "[]string")), '''
if p.Fragile {
    uplift := total * $fragile / 100
    total += uplift
    notes = append(notes, fmt.Sprintf("fragile: +%d", uplift))
}
''', "fragileHandling adds a percentage for careful handling."),
    GoStage("insurance", "insurance", (("p", "Parcel"), ("total", "int"), ("notes", "[]string")), (("total", "int"), ("notes", "[]string")), '''
if p.DeclaredCents > freeCover {
    fee := (p.DeclaredCents - freeCover + 9999) / 10000 * $ins
    total += fee
    notes = append(notes, fmt.Sprintf("insurance: +%d", fee))
}
''', "insurance covers declared values above the free cover."),
    GoStage("applyCap", "price cap", (("total", "int"), ("notes", "[]string")), (("total", "int"), ("notes", "[]string")), '''
if total > capCents {
    total = capCents
    notes = append(notes, "capped")
}
''', "applyCap limits the price of heavy, expensive parcels."),
]


def post_params(rng):
    return {"maxw": rng.choice([5000, 10000, 20000]), "base": rng.randrange(300, 700, 10), "stepg": rng.choice([250, 500, 1000]), "stepc": rng.randrange(40, 160, 10),
            "zonec": rng.randrange(60, 200, 10), "sigc": rng.choice([100, 150, 200]), "cover": rng.choice([5000, 10000, 20000]), "cap": rng.choice([3000, 4500, 6000]),
            "fragile": rng.choice([10, 15, 25]), "ins": rng.choice([25, 40, 60])}


def post_cases(rng, n):
    out = []
    for i in range(n):
        out.append({"WeightG": rng.choice([1, 120, 499, 500, 501, 1500, 4999, 9000, 19999, 30000, 0 if i % 11 == 10 else 750]),
                    "Zone": rng.choice([1, 1, 2, 3, 4, 5 if i % 13 == 12 else 2]), "Signature": rng.random() < 0.4, "Fragile": rng.random() < 0.3,
                    "DeclaredCents": rng.choice([0, 2000, 15000, 45000, 120000])})
    return out


POST = GoDomain(key="post", mod="parcelpost", pkg="post", file="price.go", func="Price", inp="Parcel", res="Quote", sig_name="p",
                pkgdoc="Package post prices parcels for the mail counter.", funcdoc="Price quotes a parcel, explaining every charge.",
                header=POST_HEADER, params=post_params, stages=POST_STAGES, epilogue="return Quote{Cents: total, Notes: notes}, nil", cases=post_cases,
                topic="parcel quoting")

# ----------------------------------------------------------------------------------------------------------------
SAUNA_HEADER = '''const (
    blockMinutes = 15
    maxMinutes   = $maxm
    blockCents   = $block
    guestCents   = $guest
    towelCents   = $towel
    minCents     = $minc
)

// Booking is a request for the sauna cabin.
type Booking struct {
    Minutes   int
    StartHour int
    Members   int
    Guests    int
    Towels    bool
}

// Receipt is the price of a booking plus the lines that explain it.
type Receipt struct {
    Cents int
    Lines []string
}
'''

SAUNA_STAGES = [
    GoStage("check", "validation", (("b", "Booking"),), (), '''
if b.Minutes <= 0 || b.Minutes%blockMinutes != 0 || b.Minutes > maxMinutes {
    FAIL(fmt.Errorf("a session is 15..%d minutes in steps of 15, got %d", maxMinutes, b.Minutes))
}
if b.Members < 1 || b.Guests < 0 {
    FAIL(fmt.Errorf("a booking needs at least one member and no negative guests"))
}
if b.StartHour < 6 || b.StartHour > 22 {
    FAIL(fmt.Errorf("the sauna is open 06:00-23:00, not at %d", b.StartHour))
}
''', "check validates the length, party and opening hours of a booking.", optional=False, fails=True),
    GoStage("baseRate", "base rate", (("b", "Booking"),), (("total", "int"), ("lines", "[]string")), '''
blocks := b.Minutes / blockMinutes
total := blocks * blockCents
lines := []string{fmt.Sprintf("%d blocks x %d", blocks, blockCents)}
''', "baseRate charges per started block of 15 minutes.", optional=False),
    GoStage("offPeak", "off-peak discount", (("b", "Booking"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if b.StartHour < $peak_from {
    cut := total * $off / 100
    total -= cut
    lines = append(lines, fmt.Sprintf("off-peak: -%d", cut))
}
''', "offPeak discounts early sessions."),
    GoStage("groupDiscount", "group discount", (("b", "Booking"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if b.Members >= $group {
    cut := total * $grp / 100
    total -= cut
    lines = append(lines, fmt.Sprintf("group: -%d", cut))
}
''', "groupDiscount rewards parties of several members."),
    GoStage("guestFees", "guest fees", (("b", "Booking"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if b.Guests > 0 {
    fee := b.Guests * guestCents * (b.Minutes / blockMinutes)
    total += fee
    lines = append(lines, fmt.Sprintf("%d guests: +%d", b.Guests, fee))
}
''', "guestFees charges non-members per block."),
    GoStage("towelHire", "towel hire", (("b", "Booking"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if b.Towels {
    n := b.Members + b.Guests
    total += n * towelCents
    lines = append(lines, fmt.Sprintf("towels x%d: +%d", n, n*towelCents))
}
''', "towelHire adds a fee per person."),
    GoStage("minimumCharge", "minimum charge", (("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if total < minCents {
    lines = append(lines, "minimum charge applied")
    total = minCents
}
''', "minimumCharge lifts tiny bookings to the minimum."),
]


def sauna_params(rng):
    return {"maxm": rng.choice([120, 180]), "block": rng.randrange(150, 400, 10), "guest": rng.randrange(30, 120, 10), "towel": rng.randrange(40, 150, 10),
            "minc": rng.choice([300, 500, 800]), "peak_from": rng.choice([14, 16, 17]), "off": rng.choice([10, 15, 25]), "group": rng.choice([3, 4, 5]),
            "grp": rng.choice([5, 10, 12])}


def sauna_cases(rng, n):
    return [{"Minutes": rng.choice([15, 30, 45, 60, 90, 120, 180, 200, 0 if i % 12 == 11 else 75, 20 if i % 10 == 9 else 60]),
             "StartHour": rng.choice([6, 9, 12, 15, 16, 18, 22, 23 if i % 14 == 13 else 20]), "Members": rng.choice([0 if i % 15 == 14 else 1, 1, 2, 3, 4, 6]),
             "Guests": rng.choice([0, 0, 1, 3]), "Towels": rng.random() < 0.4} for i in range(n)]


SAUNA = GoDomain(key="sauna", mod="saunabook", pkg="sauna", file="booking.go", func="Charge", inp="Booking", res="Receipt", sig_name="b",
                 pkgdoc="Package sauna prices bookings of the community sauna.", funcdoc="Charge prices a booking and lists how the price came about.",
                 header=SAUNA_HEADER, params=sauna_params, stages=SAUNA_STAGES, epilogue="return Receipt{Cents: total, Lines: lines}, nil", cases=sauna_cases,
                 topic="sauna pricing")

# ----------------------------------------------------------------------------------------------------------------
SEEDS_HEADER = '''const (
    bulkFrom      = $bulk_from
    bulkPercent   = $bulk_pct
    freeShipFrom  = $free_from
    giftWrapCents = $gift
)

var shipping = map[string]int{
$ship_rows
}

// Line is one product in an order.
type Line struct {
    SKU       string
    Qty       int
    UnitCents int
}

// Order is a basket going to one country.
type Order struct {
    Lines   []Line
    Country string
    Gift    bool
}

// Invoice is the amount due and the lines that explain it.
type Invoice struct {
    Cents int
    Lines []string
}
'''

SEEDS_STAGES = [
    GoStage("check", "validation", (("o", "Order"),), (), '''
if len(o.Lines) == 0 {
    FAIL(errors.New("an order needs at least one line"))
}
for _, l := range o.Lines {
    if l.Qty <= 0 || l.UnitCents < 0 {
        FAIL(fmt.Errorf("bad line for %s", l.SKU))
    }
}
if _, ok := shipping[o.Country]; !ok {
    FAIL(fmt.Errorf("we do not ship to %q", o.Country))
}
''', "check rejects empty orders, bad lines and unknown countries.", optional=False, fails=True),
    GoStage("subtotal", "subtotal", (("o", "Order"),), (("total", "int"), ("lines", "[]string")), '''
total := 0
var lines []string
for _, l := range o.Lines {
    amount := l.Qty * l.UnitCents
    total += amount
    lines = append(lines, fmt.Sprintf("%s x%d: %d", l.SKU, l.Qty, amount))
}
''', "subtotal adds up the lines.", optional=False),
    GoStage("bulkDiscount", "bulk discount", (("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if total >= bulkFrom {
    cut := total * bulkPercent / 100
    total -= cut
    lines = append(lines, fmt.Sprintf("bulk discount: -%d", cut))
}
''', "bulkDiscount takes a percentage off large baskets."),
    GoStage("shippingFee", "shipping", (("o", "Order"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if total >= freeShipFrom {
    lines = append(lines, "free shipping")
} else {
    fee := shipping[o.Country]
    total += fee
    lines = append(lines, fmt.Sprintf("shipping to %s: +%d", o.Country, fee))
}
''', "shippingFee adds postage unless the basket qualifies for free shipping."),
    GoStage("giftWrap", "gift wrap", (("o", "Order"), ("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if o.Gift {
    total += giftWrapCents
    lines = append(lines, fmt.Sprintf("gift wrap: +%d", giftWrapCents))
}
''', "giftWrap adds a flat fee."),
    GoStage("roundUp", "rounding", (("total", "int"), ("lines", "[]string")), (("total", "int"), ("lines", "[]string")), '''
if r := total % 5; r != 0 {
    lines = append(lines, fmt.Sprintf("rounded up by %d", 5-r))
    total += 5 - r
}
''', "roundUp rounds the amount due up to the next 5 cents."),
]


def seeds_params(rng):
    countries = rng.sample(["NL", "DE", "FR", "IE", "SE", "PL", "ES", "IT"], 4)
    rows = "\n".join(f'    "{c}": {rng.randrange(300, 1400, 25)},' for c in countries)
    return {"bulk_from": rng.choice([4000, 6000, 8000]), "bulk_pct": rng.choice([5, 8, 10]), "free_from": rng.choice([5000, 7500, 10000]), "gift": rng.choice([150, 250, 400]),
            "ship_rows": rows, "_countries": countries}


def seeds_cases_for(params):
    def cases(rng, n):
        out = []
        skus = ["tomato-heirloom", "basil-genovese", "kale-red", "pea-sugar", "leek-bleu", "radish-icicle"]
        for i in range(n):
            lines = [{"SKU": rng.choice(skus), "Qty": rng.choice([1, 2, 5, 10, 24, 0 if i % 12 == 11 else 3]), "UnitCents": rng.choice([199, 349, 425, 899, 1250])}
                     for _ in range(rng.randrange(0 if i % 14 == 13 else 1, 5))]
            out.append({"Lines": lines, "Country": rng.choice(params["_countries"] + (["ZZ"] if i % 9 == 8 else [])), "Gift": rng.random() < 0.3})
        return out
    return cases


SEEDS = GoDomain(key="seeds", mod="seedshop", pkg="seeds", file="invoice.go", func="Bill", inp="Order", res="Invoice", sig_name="o",
                 pkgdoc="Package seeds prices orders for the seed catalogue shop.", funcdoc="Bill prices an order and itemises the invoice.",
                 header=SEEDS_HEADER, params=seeds_params, stages=SEEDS_STAGES, epilogue="return Invoice{Cents: total, Lines: lines}, nil", cases=None, topic="seed shop invoicing")

GO_DOMAINS = [POST, SAUNA, SEEDS]
