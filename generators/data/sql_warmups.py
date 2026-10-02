"""Easy SQL tasks (single table or one join, filter, group, order) on four of the invented databases: the warm-up level of the data category."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_huts import DOMAIN as HUTS
from generators.data.sql_podcast import DOMAIN as PODCAST
from generators.data.sql_toolshed import DOMAIN as TOOLS
from generators.data.sql_tramdepot import DOMAIN as TRAMS


def E(slug, prompt, sql, cols, ordered=True, **kw):
    return K.Spec(slug, 1, prompt, sql.strip(), cols, ordered=ordered, **kw)


TRAM_SPECS = [
    E("trams-by-model", "How many trams are there of each model, and what is the newest build year of each? Columns: model, trams, newest year. Order by model.",
      "SELECT model, COUNT(*) AS trams, MAX(built_year) AS newest FROM trams GROUP BY model ORDER BY model;", ["model", "trams", "newest"]),
    E("five-oldest-trams", "The five oldest trams by build year (ties by fleet number): fleet number, model, built year, depot.",
      "SELECT fleet_no, model, built_year, depot FROM trams ORDER BY built_year, fleet_no LIMIT 5;", ["fleet_no", "model", "built_year", "depot"]),
    E("boardings-per-zone", "Passengers per fare zone over the whole log: zone, total boarded and total alighted. Order by zone.",
      "SELECT s.zone, SUM(e.boarded) AS boarded, SUM(e.alighted) AS alighted FROM stop_events e JOIN stops s ON s.stop_id = e.stop_id GROUP BY s.zone ORDER BY s.zone;", ["zone", "boarded", "alighted"]),
    E("cancelled-per-line", "How many runs were cancelled on each line? Show every line code and the count (0 allowed), ordered by the count descending and then the code.",
      "SELECT l.code, COALESCE(SUM(r.cancelled), 0) AS cancelled FROM lines l LEFT JOIN runs r ON r.line_id = l.line_id GROUP BY l.line_id ORDER BY cancelled DESC, l.code;", ["code", "cancelled"]),
    E("faults-per-category", "Number of faults per category and the number of them that are still open (`fixed_on` is NULL). Columns: category, faults, open. Order by faults descending, then category.",
      "SELECT category, COUNT(*) AS faults, SUM(fixed_on IS NULL) AS open FROM faults GROUP BY category ORDER BY faults DESC, category;", ["category", "faults", "open"]),
    E("serious-faults", "Faults of severity 4 or 5: fleet number, category, severity and the report date. Most severe first, then oldest report, then fleet number.",
      "SELECT t.fleet_no, f.category, f.severity, f.reported_on FROM faults f JOIN trams t ON t.tram_id = f.tram_id WHERE f.severity >= 4 ORDER BY f.severity DESC, f.reported_on, t.fleet_no;", ["fleet_no", "category", "severity", "reported_on"], allow_empty=True),
    E("north-depot-modern", "Trams of the `North` depot built in 2005 or later: fleet number and build year, newest first, ties by fleet number.",
      "SELECT fleet_no, built_year FROM trams WHERE depot = 'North' AND built_year >= 2005 ORDER BY built_year DESC, fleet_no;", ["fleet_no", "built_year"]),
    E("busiest-stop-boardings", "The five stops with the most boardings in total: stop name and the total number of people who boarded. Ties by stop name.",
      "SELECT s.name, SUM(e.boarded) AS boarded FROM stop_events e JOIN stops s ON s.stop_id = e.stop_id GROUP BY s.stop_id ORDER BY boarded DESC, s.name LIMIT 5;", ["name", "boarded"]),
]

TOOL_SPECS = [
    E("members-per-tier", "How many members are in each tier and what is their average deposit in euros (cents divided by 100, 2 decimals)? Columns: tier, members, avg deposit. Order by tier.",
      "SELECT tier, COUNT(*) AS members, ROUND(AVG(deposit_cents) / 100.0, 2) AS avg_deposit_eur FROM members GROUP BY tier ORDER BY tier;", ["tier", "members", "avg_deposit_eur"], places=2),
    E("costly-tools", "Tools that cost 15000 cents or more to replace: label and replacement cost, most expensive first, ties by label.",
      "SELECT label, replacement_cents FROM tools WHERE replacement_cents >= 15000 ORDER BY replacement_cents DESC, label;", ["label", "replacement_cents"], allow_empty=True),
    E("big-fees", "Fees above 1000 cents: fee id, kind, amount and assessment date. Largest first, ties by fee id.",
      "SELECT fee_id, kind, amount_cents, assessed_on FROM fees WHERE amount_cents > 1000 ORDER BY amount_cents DESC, fee_id;", ["fee_id", "kind", "amount_cents", "assessed_on"], allow_empty=True),
    E("most-loans", "The five members with the most loans (all loans): name and number of loans. Ties by name.",
      "SELECT m.name, COUNT(*) AS loans FROM loans l JOIN members m ON m.member_id = l.member_id GROUP BY m.member_id ORDER BY loans DESC, m.name LIMIT 5;", ["name", "loans"]),
    E("reservations-per-tool", "How many reservations does each tool have? Show every tool label (0 for none) with the count, most reservations first, ties by label.",
      "SELECT t.label, COUNT(r.res_id) AS reservations FROM tools t LEFT JOIN reservations r ON r.tool_id = t.tool_id GROUP BY t.tool_id ORDER BY reservations DESC, t.label;", ["label", "reservations"]),
    E("returned-on-time", "How many loans were returned on or before their due date, and how many after it? One row: on_time, late. (Loans that are still out are in neither count.)",
      "SELECT SUM(returned_on <= due_on) AS on_time, SUM(returned_on > due_on) AS late FROM loans WHERE returned_on IS NOT NULL;", ["on_time", "late"]),
    E("early-members", "Members who joined in 2032 or earlier: name, join date and tier, oldest membership first, ties by name.",
      "SELECT name, joined_on, tier FROM members WHERE joined_on < '2033-01-01' ORDER BY joined_on, name;", ["name", "joined_on", "tier"], allow_empty=True),
    E("retired-list", "The retired tools with their category name: label, category, replacement cost. Order by category, then label.",
      "SELECT t.label, c.name AS category, t.replacement_cents FROM tools t JOIN categories c ON c.cat_id = t.cat_id WHERE t.retired = 1 ORDER BY c.name, t.label;", ["label", "category", "replacement_cents"]),
]

HUT_SPECS = [
    E("roomy-huts", "Huts with at least 32 beds: name, altitude and beds, the highest first, ties by name.",
      "SELECT name, altitude_m, beds FROM huts WHERE beds >= 32 ORDER BY altitude_m DESC, name;", ["name", "altitude_m", "beds"]),
    E("bookings-by-status", "Number of bookings and total people per status: status, bookings, people. Order by status.",
      "SELECT status, COUNT(*) AS bookings, SUM(party) AS people FROM bookings GROUP BY status ORDER BY status;", ["status", "bookings", "people"]),
    E("average-party", "The average party size of the confirmed bookings, with 2 decimals, and the largest party. One row: avg_party, largest.",
      "SELECT ROUND(AVG(party), 2) AS avg_party, MAX(party) AS largest FROM bookings WHERE status = 'confirmed';", ["avg_party", "largest"], places=2),
    E("meal-portions", "Portions ordered per meal kind: meal, portions, and the revenue in euros with 2 decimals (portions times price in cents divided by 100). Order by revenue descending, then meal.",
      "SELECT meal, SUM(qty) AS portions, ROUND(SUM(qty * price_cents) / 100.0, 2) AS revenue_eur FROM meals GROUP BY meal ORDER BY revenue_eur DESC, meal;", ["meal", "portions", "revenue_eur"], places=2),
    E("price-range", "The cheapest and the most expensive nightly price of each hut: hut name, minimum and maximum price in cents. Order by hut name.",
      "SELECT h.name, MIN(r.per_night_cents) AS cheapest, MAX(r.per_night_cents) AS dearest FROM huts h JOIN rates r ON r.hut_id = h.hut_id GROUP BY h.hut_id ORDER BY h.name;", ["name", "cheapest", "dearest"]),
    E("large-groups", "Bookings of 6 people or more that were not cancelled: booking id, guest, hut name, party. Largest party first, ties by booking id.",
      "SELECT b.booking_id, b.guest, h.name AS hut, b.party FROM bookings b JOIN huts h ON h.hut_id = b.hut_id WHERE b.party >= 6 AND b.status <> 'cancelled' ORDER BY b.party DESC, b.booking_id;", ["booking_id", "guest", "hut", "party"], allow_empty=True),
    E("frequent-guests", "Guests with at least 3 bookings (any status): guest and the number of bookings. Most first, ties by guest.",
      "SELECT guest, COUNT(*) AS bookings FROM bookings GROUP BY guest HAVING COUNT(*) >= 3 ORDER BY bookings DESC, guest;", ["guest", "bookings"]),
    E("long-stays", "Non-cancelled bookings of 3 nights or more: booking id, guest, check-in date, nights. Longest first, ties by booking id.",
      "SELECT booking_id, guest, check_in, nights FROM bookings WHERE status <> 'cancelled' AND nights >= 3 ORDER BY nights DESC, booking_id;", ["booking_id", "guest", "check_in", "nights"]),
]

POD_SPECS = [
    E("episodes-per-show", "Number of episodes and total minutes per show: show title, episodes, total minutes. Order by episodes descending, then title.",
      "SELECT s.title, COUNT(*) AS episodes, SUM(e.minutes) AS total_minutes FROM episodes e JOIN shows s ON s.show_id = e.show_id GROUP BY s.show_id ORDER BY episodes DESC, s.title;", ["title", "episodes", "total_minutes"]),
    E("longest-episodes", "The five longest episodes: show title, episode number and minutes. Ties by title then episode number.",
      "SELECT s.title, e.ep_no, e.minutes FROM episodes e JOIN shows s ON s.show_id = e.show_id ORDER BY e.minutes DESC, s.title, e.ep_no LIMIT 5;", ["title", "ep_no", "minutes"]),
    E("shows-by-genre-list", "Shows of the genres `news`, `music` and `tech`: title, genre and launch date, ordered by genre then title.",
      "SELECT title, genre, launched_on FROM shows WHERE genre IN ('news', 'music', 'tech') ORDER BY genre, title;", ["title", "genre", "launched_on"], allow_empty=True),
    E("spots-per-sponsor", "How many spots has each sponsor bought, and at what average CPM (cents, 1 decimal)? Show every sponsor, with 0 spots and a NULL average if none. Order by spots descending, then name.",
      "SELECT sp.name, COUNT(s.spot_id) AS spots, ROUND(AVG(s.cpm_cents), 1) AS avg_cpm FROM sponsors sp LEFT JOIN spots s ON s.sponsor_id = sp.sponsor_id GROUP BY sp.sponsor_id ORDER BY spots DESC, sp.name;", ["name", "spots", "avg_cpm"], places=1),
    E("mid-roll-count", "How many spots are there in each position (`pre`, `mid`, `post`) and what is their highest CPM? Columns: position, spots, highest cpm. Order by position.",
      "SELECT position, COUNT(*) AS spots, MAX(cpm_cents) AS highest_cpm FROM spots GROUP BY position ORDER BY position;", ["position", "spots", "highest_cpm"]),
    E("premium-spots", "Spots with a CPM of 3200 cents or more: spot id, sponsor name, position and CPM, highest first, ties by spot id.",
      "SELECT s.spot_id, sp.name AS sponsor, s.position, s.cpm_cents FROM spots s JOIN sponsors sp ON sp.sponsor_id = s.sponsor_id WHERE s.cpm_cents >= 3200 ORDER BY s.cpm_cents DESC, s.spot_id;", ["spot_id", "sponsor", "position", "cpm_cents"], allow_empty=True),
    E("latest-episodes", "The five most recently published episodes: show title, episode number, publication date. Ties by title then episode number.",
      "SELECT s.title, e.ep_no, e.published_on FROM episodes e JOIN shows s ON s.show_id = e.show_id ORDER BY e.published_on DESC, s.title, e.ep_no LIMIT 5;", ["title", "ep_no", "published_on"]),
    E("best-download-days", "The five days with the most downloads over the whole network: day and total downloads. Ties by day.",
      "SELECT day, SUM(count) AS total FROM downloads GROUP BY day ORDER BY total DESC, day LIMIT 5;", ["day", "total"]),
]


@family("data-warmup-trams", category="data", lang="sql", kind="feature", n=len(TRAM_SPECS), summary="easy SQL warm-ups on the tram operator database: counts, simple filters, top lists")
def warmup_trams(rng, n):
    return K.query_tasks(TRAMS, TRAM_SPECS, rng, n)


@family("data-warmup-tools", category="data", lang="sql", kind="feature", n=len(TOOL_SPECS), summary="easy SQL warm-ups on the tool library database: counts, simple filters, top lists")
def warmup_tools(rng, n):
    return K.query_tasks(TOOLS, TOOL_SPECS, rng, n)


@family("data-warmup-huts", category="data", lang="sql", kind="feature", n=len(HUT_SPECS), summary="easy SQL warm-ups on the mountain hut database: counts, simple filters, top lists")
def warmup_huts(rng, n):
    return K.query_tasks(HUTS, HUT_SPECS, rng, n)


@family("data-warmup-podcasts", category="data", lang="sql", kind="feature", n=len(POD_SPECS), summary="easy SQL warm-ups on the podcast network database: counts, simple filters, top lists")
def warmup_podcasts(rng, n):
    return K.query_tasks(PODCAST, POD_SPECS, rng, n)
