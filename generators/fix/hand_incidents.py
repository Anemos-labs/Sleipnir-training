"""Release-blocking ticket lists: several independent-looking defects of one project, in different modules, that have to
be fixed together. The projects come from the other hand-written families; the hidden suites there already check every
single defect, so a partial fix is caught."""
from fx import family
from generators.fix._hand_kit import combo, tasks_from, with_bugs
from generators.fix.hand_configmerge import _base_a as cfg_settings
from generators.fix.hand_errorflow import _base_a as err_importer, _base_b as err_confload
from generators.fix.hand_javaequality import _base_a as jeq_seats
from generators.fix.hand_money import _base_a as money_farepack, _base_b as money_locker
from generators.fix.hand_paging import _base_a as page_jobboard, _base_b as page_eventfeed
from generators.fix.hand_sharedstate import _base_a as shared_charsheet
from generators.fix.hand_stalecache import _base_a as cache_pricing
from generators.fix.hand_tzwall import _base_a as tz_pingdesk, _base_b as tz_shiftpay
from generators.fix.hand_unicode import _base_a as uni_handles, _base_b as uni_notekit


def _tasks() -> list:
    out = []

    def add(maker, ids, d, bug_id, intro, outro="Please fix all of them."):
        base = maker()
        out.append((base, combo(base, ids, d, bug_id, intro, outro)))

    add(cfg_settings, ["environment-below-file", "bool-from-truthiness"], 4, "precedence-and-booleans",
        "Two tickets against the new settings loader, both blocking the release:")
    add(cfg_settings, ["merge-modifies-its-base", "bool-from-truthiness", "environment-below-file"], 5, "settings-rollout",
        "The settings rollout to the staging cluster went wrong in three visible ways. Summary of what operations found:")
    add(err_importer, ["retry-returns-none", "missing-field-keyerror"], 4, "importer-night-run",
        "Findings from last night's import run (two different problems, reported together by the on-call engineer):")
    add(err_importer, ["sink-error-treated-as-rejection", "retry-returns-none", "missing-field-keyerror"], 5, "importer-incident",
        "Incident review for the failed overnight import. Three defects were found in three different modules:")
    add(err_confload, ["typed-nil-error", "include-error-cannot-unwrap"], 4, "confload-error-handling",
        "Error handling review of the config loader found two defects:")
    add(err_confload, ["diamond-reported-as-cycle", "typed-nil-error", "include-error-cannot-unwrap"], 5, "confload-release-blockers",
        "Release blockers for the config loader (three separate reports, the on-call wants one fix):")
    add(money_farepack, ["half-even-discounts", "tax-on-order-total"], 4, "fare-statement-cents",
        "Finance and the box office both complain about the same invoice run:")
    add(page_jobboard, ["pages-off-by-one", "next-from-item-count"], 4, "pager-and-api-links",
        "Two defects in the job board listing, reported by different teams:")
    add(page_jobboard, ["filter-after-slice", "cap-resets"], 5, "listing-filters-and-caps",
        "Support collected these reports about the job board listing during one week:")
    add(page_eventfeed, ["lenient-limit", "same-ts-skipped"], 4, "feed-limit-and-ties",
        "Two tickets on the event feed export:")
    add(shared_charsheet, ["snapshot-by-reference", "give-all-same-dict"], 5, "party-and-undo",
        "Playtest feedback on the character sheets and the party editor:")
    add(cache_pricing, ["ttl-boundary-inclusive", "misses-not-cached"], 4, "price-cache-tickets",
        "Two performance and correctness tickets about the price cache:")
    add(tz_pingdesk, ["add-days-absolute", "overlap-fold-swapped"], 4, "reminders-around-clock-changes",
        "Reminder tickets that all happen around daylight saving changes:")
    add(tz_pingdesk, ["dst-end-bound", "midnight-by-elapsed"], 5, "reminder-calendar-review",
        "Calendar review of the reminder service, two separate defects in two modules:")
    add(tz_shiftpay, ["end-uses-start-offset", "southern-no-wrap"], 5, "roster-pay-run",
        "Payroll run review: two groups of employees were paid wrongly for night shifts.")
    add(uni_handles, ["format-chars-kept", "search-query-not-normalised"], 4, "handle-abuse-tickets",
        "Two tickets from the abuse desk about handles:")
    add(uni_handles, ["rename-index-stale", "search-query-not-normalised"], 5, "handle-directory-review",
        "Directory review: users and moderators reported these problems with search and renames:")
    add(uni_notekit, ["title-order-raw", "marks-limited-range"], 4, "notes-sort-and-fold",
        "Two tickets about accents in the notes app:")
    add(uni_notekit, ["highlight-folded-indexes", "marks-limited-range"], 5, "notes-search-review",
        "Search review of the notes app found two problems that look different but touch the same feature:")
    add(jeq_seats, ["equals-without-hashcode", "waitlist-removes-by-position"], 4, "seat-bookkeeping",
        "Two tickets from the box office about seat bookkeeping:")
    add(money_locker, ["statement-vat-on-sum", "percent-via-double"], 5, "locker-statements",
        "Billing review of the locker fees, two defects in two classes:")
    return out


@family("fix-hand-incident-tickets", category="fix", lang="python", kind="fix", n=21,
        summary="release tickets that list several defects of one project across modules (config, importer, pager, calendar, notes, billing and more)")
def gen(rng, n):
    pairs = _tasks()
    bases = []
    picks = []
    for k, (base, bug) in enumerate(pairs):
        bases.append(with_bugs(base, [bug]))
        picks.append((k, 0))
    return tasks_from(bases, picks)
