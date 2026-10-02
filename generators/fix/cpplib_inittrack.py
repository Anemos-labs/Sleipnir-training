"""Tabletop initiative tracker (c++): turn order with tie-breaks, rounds, combatants joining and leaving mid-fight, status effects that tick at the end of their owner's turn; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # inittrack

    A turn tracker for a tabletop role-playing fight (`include/inittrack.hpp`, namespace `inittrack`, class `Tracker`).

    ## Order

    Combatants act in order of **initiative, highest first**; ties go to the higher `dex`; remaining ties to the name that comes first in plain ASCII order **ignoring case**. Names are unique: two names that differ only in ASCII
    case are the same name (`add` rejects the second one), and every lookup by name ignores ASCII case. `order()` returns the names as they were given to `add`.

    ## State

    `round()` is 0 until the first `next_turn()`. A fight has a *current* combatant (the one whose turn it is) after the first `next_turn()`.

    ## API

    * `void add(const std::string &name, int initiative, int dex)`: `std::invalid_argument` for an empty name or a name that exists (ignoring case). A combatant may join in the middle of a fight: it takes its place in the order; the
      current combatant stays the current one whether the newcomer sorts before or after it (a newcomer that sorts before the current one will act in the next round, one that sorts after it still acts in this round). What `add` does while the turn is vacant (see `remove`) is not specified; call `next_turn()` first.
    * `bool remove(const std::string &name)`: removes the combatant and its status effects; false when unknown. Removing a combatant that is **not** the current one changes nothing else. Removing the **current** one leaves the turn *vacant*:
      `current()` is empty until the next `next_turn()`, which then starts the turn of the combatant that followed the removed one (if it was the last in order, the next round begins with the first one) **without** ticking anybody's status effects.
    * `std::vector<std::string> order() const`, `std::optional<std::string> current() const`, `int round() const`.
    * `void add_status(const std::string &who, const std::string &status, int turns)`: gives `who` a status effect lasting `turns` of **its own turns**. Unknown `who` or `turns < 1` is `std::invalid_argument`. A status that the combatant
      already has (same name, ignoring nothing: statuses are case-sensitive) keeps the larger of the remaining and the new number of turns.
    * `std::vector<std::pair<std::string, int>> statuses(const std::string &who) const`: `(status, remaining turns)` sorted by status name (plain byte order); empty for an unknown combatant.
    * `std::vector<Event> next_turn()`: ends the current turn and starts the next one, returning what happened, in order:
      1. if a turn was in progress (there is a current combatant): every status effect of the current combatant loses one turn; each that reaches 0 is removed and reported as `StatusEnded` (`who` = the combatant, `detail` = the status), in status-name order;
      2. the turn passes to the next combatant in order (the first one at the very beginning, or after a vacated turn the successor as described above); when this wraps past the end of the order the round number goes up by one and a `RoundStart` event
         (`round` = the new round number) is reported first; the very first call starts round 1 and reports its `RoundStart` too;
      3. a `TurnStart` event (`who` = the new current combatant).
      With no combatants nothing happens and the result is empty. With a single combatant, every call starts a new round.

    `struct Event { enum Kind { RoundStart, TurnStart, StatusEnded } kind; std::string who; std::string detail; int round; }`: `round` is the round number at the time of the event; `who` is empty for `RoundStart`; `detail` is only used by `StatusEnded`.
''')

F2 = dd(r'''
    #ifndef INITTRACK_HPP
    #define INITTRACK_HPP

    #include <optional>
    #include <stdexcept>
    #include <string>
    #include <utility>
    #include <vector>

    namespace inittrack {

    struct Event {
        enum Kind { RoundStart, TurnStart, StatusEnded } kind;
        std::string who;
        std::string detail;
        int round;
    };

    class Tracker {
    public:
        void add(const std::string &name, int initiative, int dex);
        bool remove(const std::string &name);
        std::vector<std::string> order() const;
        std::optional<std::string> current() const;
        int round() const { return round_; }
        void add_status(const std::string &who, const std::string &status, int turns);
        std::vector<std::pair<std::string, int>> statuses(const std::string &who) const;
        std::vector<Event> next_turn();

    private:
        struct Combatant {
            std::string name;
            int initiative;
            int dex;
            std::vector<std::pair<std::string, int>> statuses; /* kept sorted by name */
        };
        std::vector<Combatant> list_; /* in turn order */
        int round_ = 0;
        long pos_ = -1;     /* index of the current combatant, or of the one who acts next when vacant */
        bool vacant_ = false;
        int find(const std::string &name) const;
    };

    }  // namespace inittrack

    #endif
''')

F3 = dd(r'''
    #include "inittrack.hpp"

    namespace inittrack {

    static std::string lower(const std::string &s) {
        std::string out = s;
        for (char &c : out) {
            if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
        }
        return out;
    }

    static bool acts_before(const std::string &an, int ai, int ad, const std::string &bn, int bi, int bd) {
        if (ai != bi) return ai > bi;
        if (ad != bd) return ad > bd;
        return lower(an) < lower(bn);
    }

    int Tracker::find(const std::string &name) const {
        std::string key = lower(name);
        for (size_t i = 0; i < list_.size(); i++) {
            if (lower(list_[i].name) == key) return static_cast<int>(i);
        }
        return -1;
    }

    void Tracker::add(const std::string &name, int initiative, int dex) {
        if (name.empty() || find(name) >= 0) throw std::invalid_argument("bad combatant name");
        size_t at = 0;
        while (at < list_.size() && acts_before(list_[at].name, list_[at].initiative, list_[at].dex, name, initiative, dex)) at++;
        list_.insert(list_.begin() + static_cast<long>(at), Combatant{name, initiative, dex, {}});
        if (pos_ >= 0 && static_cast<long>(at) <= pos_) pos_++;
    }

    bool Tracker::remove(const std::string &name) {
        int at = find(name);
        if (at < 0) return false;
        list_.erase(list_.begin() + at);
        if (pos_ >= 0) {
            if (at < pos_) {
                pos_--;
            } else if (at == pos_ && !vacant_) {
                vacant_ = true;
            }
        }
        return true;
    }

    std::vector<std::string> Tracker::order() const {
        std::vector<std::string> out;
        for (const Combatant &c : list_) out.push_back(c.name);
        return out;
    }

    std::optional<std::string> Tracker::current() const {
        if (pos_ < 0 || vacant_) return std::nullopt;
        return list_[static_cast<size_t>(pos_)].name;
    }

    void Tracker::add_status(const std::string &who, const std::string &status, int turns) {
        int at = find(who);
        if (at < 0 || turns < 1) throw std::invalid_argument("bad status request");
        auto &sts = list_[static_cast<size_t>(at)].statuses;
        for (auto &s : sts) {
            if (s.first == status) {
                if (turns > s.second) s.second = turns;
                return;
            }
        }
        size_t i = 0;
        while (i < sts.size() && sts[i].first < status) i++;
        sts.insert(sts.begin() + static_cast<long>(i), std::make_pair(status, turns));
    }

    std::vector<std::pair<std::string, int>> Tracker::statuses(const std::string &who) const {
        int at = find(who);
        if (at < 0) return {};
        return list_[static_cast<size_t>(at)].statuses;
    }

    std::vector<Event> Tracker::next_turn() {
        std::vector<Event> ev;
        if (list_.empty()) return ev;
        long next;
        if (pos_ < 0) {
            round_ = 1;
            next = 0;
            ev.push_back(Event{Event::RoundStart, "", "", round_});
        } else {
            if (!vacant_) {
                Combatant &cur = list_[static_cast<size_t>(pos_)];
                std::vector<std::pair<std::string, int>> keep;
                for (auto &s : cur.statuses) {
                    if (s.second - 1 <= 0) ev.push_back(Event{Event::StatusEnded, cur.name, s.first, round_});
                    else keep.emplace_back(s.first, s.second - 1);
                }
                cur.statuses = keep;
                next = pos_ + 1;
            } else {
                next = pos_;
            }
            if (next >= static_cast<long>(list_.size())) {
                next = 0;
                round_++;
                ev.push_back(Event{Event::RoundStart, "", "", round_});
            }
        }
        pos_ = next;
        vacant_ = false;
        ev.push_back(Event{Event::TurnStart, list_[static_cast<size_t>(next)].name, "", round_});
        return ev;
    }

    }  // namespace inittrack
''')

V4 = dd(r'''
    #include "harness.hpp"
    #include "inittrack.hpp"

    using namespace inittrack;

    int main() {
        h_init();
        Tracker t;
        t.add("Mira", 17, 3);
        t.add("Orc", 12, 1);
        t.add("Brann", 17, 4);
        CHECK_EQ(t.order(), (std::vector<std::string>{"Brann", "Mira", "Orc"}));
        auto ev = t.next_turn();
        CHECK_EQ(ev.size(), 2u);
        CHECK_EQ(t.round(), 1);
        CHECK_EQ(*t.current(), std::string("Brann"));
        return h_report();
    }
''')

H5 = dd(r'''
    #include <string>
    #include <vector>

    #include "harness.hpp"
    #include "inittrack.hpp"

    using namespace inittrack;

    struct Step {
        char op;
        const char *name;
        const char *text;
        int n1, n2;
        const char *result;
        const char *snap;
    };

    static const Step scriptA[] = {
        {'a', "_x", "", 10, 2, "ok", "_x|-|0"},
        {'a', "Ogre", "", 17, 1, "ok", "Ogre,_x|-|0"},
        {'a', "Pip", "", 17, 3, "ok", "Pip,Ogre,_x|-|0"},
        {'n', "", "", 0, 0, "R1,T:Pip@1", "Pip,Ogre,_x|Pip|1"},
        {'n', "", "", 0, 0, "T:Ogre@1", "Pip,Ogre,_x|Ogre|1"},
        {'n', "", "", 0, 0, "T:_x@1", "Pip,Ogre,_x|_x|1"},
        {'r', "_x", "", 0, 0, "true", "Pip,Ogre|-|1"},
        {'r', "Orc", "", 0, 0, "false", "Pip,Ogre|-|1"},
        {'n', "", "", 0, 0, "R2,T:Pip@2", "Pip,Ogre|Pip|2"},
        {'a', "Imp", "", 5, 3, "ok", "Pip,Ogre,Imp|Pip|2"},
        {'n', "", "", 0, 0, "T:Ogre@2", "Pip,Ogre,Imp|Ogre|2"},
        {'n', "", "", 0, 0, "T:Imp@2", "Pip,Ogre,Imp|Imp|2"},
        {'n', "", "", 0, 0, "R3,T:Pip@3", "Pip,Ogre,Imp|Pip|3"},
        {'q', "Pip", "", 0, 0, "", "Pip,Ogre,Imp|Pip|3"},
        {'n', "", "", 0, 0, "T:Ogre@3", "Pip,Ogre,Imp|Ogre|3"},
        {'n', "", "", 0, 0, "T:Imp@3", "Pip,Ogre,Imp|Imp|3"},
        {'s', "Ogre", "Stun", 2, 0, "ok", "Pip,Ogre,Imp|Imp|3"},
        {'n', "", "", 0, 0, "R4,T:Pip@4", "Pip,Ogre,Imp|Pip|4"},
        {'s', "Brann", "bless", -1, 0, "ERR", "Pip,Ogre,Imp|Pip|4"},
        {'n', "", "", 0, 0, "T:Ogre@4", "Pip,Ogre,Imp|Ogre|4"},
        {'n', "", "", 0, 0, "T:Imp@4", "Pip,Ogre,Imp|Imp|4"},
        {'a', "ZED", "", 17, 3, "ok", "Pip,ZED,Ogre,Imp|Imp|4"},
        {'n', "", "", 0, 0, "R5,T:Pip@5", "Pip,ZED,Ogre,Imp|Pip|5"},
        {'n', "", "", 0, 0, "T:ZED@5", "Pip,ZED,Ogre,Imp|ZED|5"},
        {'r', "kobold", "", 0, 0, "false", "Pip,ZED,Ogre,Imp|ZED|5"},
        {'n', "", "", 0, 0, "T:Ogre@5", "Pip,ZED,Ogre,Imp|Ogre|5"},
        {'q', "Ogre", "", 0, 0, "Stun:1", "Pip,ZED,Ogre,Imp|Ogre|5"},
        {'s', "Orc", "Stun", 1, 0, "ERR", "Pip,ZED,Ogre,Imp|Ogre|5"},
        {'n', "", "", 0, 0, "S:Ogre:Stun@5,T:Imp@5", "Pip,ZED,Ogre,Imp|Imp|5"},
        {'s', "aldo", "burn", 0, 0, "ERR", "Pip,ZED,Ogre,Imp|Imp|5"},
        {'n', "", "", 0, 0, "R6,T:Pip@6", "Pip,ZED,Ogre,Imp|Pip|6"},
        {'n', "", "", 0, 0, "T:ZED@6", "Pip,ZED,Ogre,Imp|ZED|6"},
        {'n', "", "", 0, 0, "T:Ogre@6", "Pip,ZED,Ogre,Imp|Ogre|6"},
        {'a', "Orc", "", 12, 3, "ok", "Pip,ZED,Ogre,Orc,Imp|Ogre|6"},
        {'n', "", "", 0, 0, "T:Orc@6", "Pip,ZED,Ogre,Orc,Imp|Orc|6"},
        {'s', "Mira", "Stun", 1, 0, "ERR", "Pip,ZED,Ogre,Orc,Imp|Orc|6"},
        {'r', "Pip", "", 0, 0, "true", "ZED,Ogre,Orc,Imp|Orc|6"},
        {'n', "", "", 0, 0, "T:Imp@6", "ZED,Ogre,Orc,Imp|Imp|6"},
        {'n', "", "", 0, 0, "R7,T:ZED@7", "ZED,Ogre,Orc,Imp|ZED|7"},
        {'s', "aldo", "bless", 0, 0, "ERR", "ZED,Ogre,Orc,Imp|ZED|7"},
        {'r', "Mira", "", 0, 0, "false", "ZED,Ogre,Orc,Imp|ZED|7"},
        {'n', "", "", 0, 0, "T:Ogre@7", "ZED,Ogre,Orc,Imp|Ogre|7"},
        {'q', "Imp", "", 0, 0, "", "ZED,Ogre,Orc,Imp|Ogre|7"},
        {'r', "Imp", "", 0, 0, "true", "ZED,Ogre,Orc|Ogre|7"},
        {'s', "ZED", "Stun", 2, 0, "ok", "ZED,Ogre,Orc|Ogre|7"},
        {'n', "", "", 0, 0, "T:Orc@7", "ZED,Ogre,Orc|Orc|7"},
        {'n', "", "", 0, 0, "R8,T:ZED@8", "ZED,Ogre,Orc|ZED|8"},
        {'n', "", "", 0, 0, "T:Ogre@8", "ZED,Ogre,Orc|Ogre|8"},
        {'s', "Orc", "bless", 0, 0, "ERR", "ZED,Ogre,Orc|Ogre|8"},
        {'n', "", "", 0, 0, "T:Orc@8", "ZED,Ogre,Orc|Orc|8"},
        {'a', "Ogre", "", 17, 3, "ERR", "ZED,Ogre,Orc|Orc|8"},
        {'n', "", "", 0, 0, "R9,T:ZED@9", "ZED,Ogre,Orc|ZED|9"},
        {'n', "", "", 0, 0, "S:ZED:Stun@9,T:Ogre@9", "ZED,Ogre,Orc|Ogre|9"},
        {'s', "ZED", "Stun", 2, 0, "ok", "ZED,Ogre,Orc|Ogre|9"},
        {'a', "_x", "", 17, 3, "ok", "_x,ZED,Ogre,Orc|Ogre|9"},
        {'n', "", "", 0, 0, "T:Orc@9", "_x,ZED,Ogre,Orc|Orc|9"},
        {'n', "", "", 0, 0, "R10,T:_x@10", "_x,ZED,Ogre,Orc|_x|10"},
        {'n', "", "", 0, 0, "T:ZED@10", "_x,ZED,Ogre,Orc|ZED|10"},
        {'n', "", "", 0, 0, "T:Ogre@10", "_x,ZED,Ogre,Orc|Ogre|10"},
        {'a', "Imp", "", 15, 0, "ok", "_x,ZED,Ogre,Imp,Orc|Ogre|10"},
        {'n', "", "", 0, 0, "T:Imp@10", "_x,ZED,Ogre,Imp,Orc|Imp|10"},
        {'n', "", "", 0, 0, "T:Orc@10", "_x,ZED,Ogre,Imp,Orc|Orc|10"},
        {'a', "Mira", "", 15, 1, "ok", "_x,ZED,Ogre,Mira,Imp,Orc|Orc|10"},
        {'r', "_x", "", 0, 0, "true", "ZED,Ogre,Mira,Imp,Orc|Orc|10"},
        {'n', "", "", 0, 0, "R11,T:ZED@11", "ZED,Ogre,Mira,Imp,Orc|ZED|11"},
        {'s', "brann", "bless", 1, 0, "ERR", "ZED,Ogre,Mira,Imp,Orc|ZED|11"},
        {'r', "brann", "", 0, 0, "false", "ZED,Ogre,Mira,Imp,Orc|ZED|11"},
        {'n', "", "", 0, 0, "S:ZED:Stun@11,T:Ogre@11", "ZED,Ogre,Mira,Imp,Orc|Ogre|11"},
        {'n', "", "", 0, 0, "T:Mira@11", "ZED,Ogre,Mira,Imp,Orc|Mira|11"},
        {'r', "ZED", "", 0, 0, "true", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'s', "Mira", "stun", 1, 0, "ok", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'r', "aldo", "", 0, 0, "false", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'s', "Aldo", "burn", 1, 0, "ERR", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'r', "ZED", "", 0, 0, "false", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'q', "Aldo", "", 0, 0, "", "Ogre,Mira,Imp,Orc|Mira|11"},
        {'n', "", "", 0, 0, "S:Mira:stun@11,T:Imp@11", "Ogre,Mira,Imp,Orc|Imp|11"},
        {'s', "Mira", "bless", 1, 0, "ok", "Ogre,Mira,Imp,Orc|Imp|11"},
        {'s', "Orc", "haste", 1, 0, "ok", "Ogre,Mira,Imp,Orc|Imp|11"},
        {'s', "Imp", "haste", 3, 0, "ok", "Ogre,Mira,Imp,Orc|Imp|11"},
        {'q', "Ogre", "", 0, 0, "", "Ogre,Mira,Imp,Orc|Imp|11"},
        {'n', "", "", 0, 0, "T:Orc@11", "Ogre,Mira,Imp,Orc|Orc|11"},
        {'n', "", "", 0, 0, "S:Orc:haste@11,R12,T:Ogre@12", "Ogre,Mira,Imp,Orc|Ogre|12"},
        {'n', "", "", 0, 0, "T:Mira@12", "Ogre,Mira,Imp,Orc|Mira|12"},
        {'s', "Imp", "haste", 1, 0, "ok", "Ogre,Mira,Imp,Orc|Mira|12"},
        {'s', "Zoe", "haste", -1, 0, "ERR", "Ogre,Mira,Imp,Orc|Mira|12"},
        {'s', "kobold", "bless", 1, 0, "ERR", "Ogre,Mira,Imp,Orc|Mira|12"},
        {'n', "", "", 0, 0, "S:Mira:bless@12,T:Imp@12", "Ogre,Mira,Imp,Orc|Imp|12"},
        {'r', "Pip", "", 0, 0, "false", "Ogre,Mira,Imp,Orc|Imp|12"},
        {'a', "Zed", "", 12, 3, "ok", "Ogre,Mira,Imp,Orc,Zed|Imp|12"},
        {'n', "", "", 0, 0, "T:Orc@12", "Ogre,Mira,Imp,Orc,Zed|Orc|12"},
        {'a', "Pip", "", 5, 3, "ok", "Ogre,Mira,Imp,Orc,Zed,Pip|Orc|12"},
        {'n', "", "", 0, 0, "T:Zed@12", "Ogre,Mira,Imp,Orc,Zed,Pip|Zed|12"},
        {'n', "", "", 0, 0, "T:Pip@12", "Ogre,Mira,Imp,Orc,Zed,Pip|Pip|12"},
        {'n', "", "", 0, 0, "R13,T:Ogre@13", "Ogre,Mira,Imp,Orc,Zed,Pip|Ogre|13"},
        {'a', "_x", "", 5, 3, "ok", "Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'a', "kobold", "", 17, 3, "ok", "kobold,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'a', "Zoe", "", 17, 2, "ok", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'q', "Mira", "", 0, 0, "", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'s', "_x", "burn", 1, 0, "ok", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'a', "_x", "", 12, 2, "ERR", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'s', "Imp", "haste", 1, 0, "ok", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|13"},
        {'n', "", "", 0, 0, "T:Mira@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Mira|13"},
        {'n', "", "", 0, 0, "T:Imp@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Imp|13"},
        {'s', "_x", "poison", 3, 0, "ok", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Imp|13"},
        {'n', "", "", 0, 0, "S:Imp:haste@13,T:Orc@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Orc|13"},
        {'q', "brann", "", 0, 0, "", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Orc|13"},
        {'n', "", "", 0, 0, "T:Zed@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Zed|13"},
        {'a', "Imp", "", 12, 2, "ERR", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Zed|13"},
        {'n', "", "", 0, 0, "T:_x@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|_x|13"},
        {'n', "", "", 0, 0, "S:_x:burn@13,T:Pip@13", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Pip|13"},
        {'n', "", "", 0, 0, "R14,T:kobold@14", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|kobold|14"},
        {'s', "Zoe", "stun", 2, 0, "ok", "kobold,Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|kobold|14"},
        {'r', "kobold", "", 0, 0, "true", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|-|14"},
        {'n', "", "", 0, 0, "T:Zoe@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Zoe|14"},
        {'n', "", "", 0, 0, "T:Ogre@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|14"},
        {'q', "Orc", "", 0, 0, "", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Ogre|14"},
        {'n', "", "", 0, 0, "T:Mira@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Mira|14"},
        {'a', "Orc", "", 17, 1, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Mira|14"},
        {'n', "", "", 0, 0, "T:Imp@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Imp|14"},
        {'s', "Zed", "poison", 3, 0, "ok", "Zoe,Ogre,Mira,Imp,Orc,Zed,_x,Pip|Imp|14"},
        {'a', "kobold", "", 10, 2, "ok", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Imp|14"},
        {'s', "kobold", "poison", 0, 0, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Imp|14"},
        {'n', "", "", 0, 0, "T:Orc@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Orc|14"},
        {'s', "Imp", "stun", 1, 0, "ok", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Orc|14"},
        {'n', "", "", 0, 0, "T:Zed@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Zed|14"},
        {'a', "Orc", "", 17, 0, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Zed|14"},
        {'n', "", "", 0, 0, "T:kobold@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|kobold|14"},
        {'n', "", "", 0, 0, "T:_x@14", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|_x|14"},
        {'a', "kobold", "", 17, 1, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|_x|14"},
        {'a', "Brann", "", 12, 4, "ok", "Zoe,Ogre,Mira,Imp,Brann,Orc,Zed,kobold,_x,Pip|_x|14"},
        {'n', "", "", 0, 0, "T:Pip@14", "Zoe,Ogre,Mira,Imp,Brann,Orc,Zed,kobold,_x,Pip|Pip|14"},
        {'s', "_x", "poison", 2, 0, "ok", "Zoe,Ogre,Mira,Imp,Brann,Orc,Zed,kobold,_x,Pip|Pip|14"},
        {'n', "", "", 0, 0, "R15,T:Zoe@15", "Zoe,Ogre,Mira,Imp,Brann,Orc,Zed,kobold,_x,Pip|Zoe|15"},
        {'n', "", "", 0, 0, "S:Zoe:stun@15,T:Ogre@15", "Zoe,Ogre,Mira,Imp,Brann,Orc,Zed,kobold,_x,Pip|Ogre|15"},
        {'r', "Brann", "", 0, 0, "true", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Ogre|15"},
        {'n', "", "", 0, 0, "T:Mira@15", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Mira|15"},
        {'a', "", "", 15, 4, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Mira|15"},
        {'n', "", "", 0, 0, "T:Imp@15", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Imp|15"},
        {'s', "Zoe", "Stun", 1, 0, "ok", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Imp|15"},
        {'a', "kobold", "", 20, 0, "ERR", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,_x,Pip|Imp|15"},
        {'r', "_x", "", 0, 0, "true", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,Pip|Imp|15"},
        {'n', "", "", 0, 0, "S:Imp:stun@15,T:Orc@15", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,Pip|Orc|15"},
        {'n', "", "", 0, 0, "T:Zed@15", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,Pip|Zed|15"},
        {'q', "Ogre", "", 0, 0, "", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,Pip|Zed|15"},
        {'n', "", "", 0, 0, "T:kobold@15", "Zoe,Ogre,Mira,Imp,Orc,Zed,kobold,Pip|kobold|15"},
        {'r', "Imp", "", 0, 0, "true", "Zoe,Ogre,Mira,Orc,Zed,kobold,Pip|kobold|15"},
        {'a', "aldo", "", 10, 2, "ok", "Zoe,Ogre,Mira,Orc,Zed,aldo,kobold,Pip|kobold|15"},
        {'a', "Orc", "", 17, 1, "ERR", "Zoe,Ogre,Mira,Orc,Zed,aldo,kobold,Pip|kobold|15"},
        {'s', "kobold", "stun", 2, 0, "ok", "Zoe,Ogre,Mira,Orc,Zed,aldo,kobold,Pip|kobold|15"},
        {'a', "kobold", "", 15, 1, "ERR", "Zoe,Ogre,Mira,Orc,Zed,aldo,kobold,Pip|kobold|15"},
    };

    static const Step scriptB[] = {
        {'n', "", "", 0, 0, "", "|-|0"},
        {'n', "", "", 0, 0, "", "|-|0"},
        {'a', "Pip", "", 12, 4, "ok", "Pip|-|0"},
        {'n', "", "", 0, 0, "R1,T:Pip@1", "Pip|Pip|1"},
        {'n', "", "", 0, 0, "R2,T:Pip@2", "Pip|Pip|2"},
        {'r', "Brann", "", 0, 0, "false", "Pip|Pip|2"},
        {'n', "", "", 0, 0, "R3,T:Pip@3", "Pip|Pip|3"},
        {'n', "", "", 0, 0, "R4,T:Pip@4", "Pip|Pip|4"},
        {'a', "Aldo", "", 17, 3, "ok", "Aldo,Pip|Pip|4"},
        {'n', "", "", 0, 0, "R5,T:Aldo@5", "Aldo,Pip|Aldo|5"},
        {'q', "Orc", "", 0, 0, "", "Aldo,Pip|Aldo|5"},
        {'n', "", "", 0, 0, "T:Pip@5", "Aldo,Pip|Pip|5"},
        {'s', "Zoe", "Stun", 3, 0, "ERR", "Aldo,Pip|Pip|5"},
        {'n', "", "", 0, 0, "R6,T:Aldo@6", "Aldo,Pip|Aldo|6"},
        {'q', "aldo", "", 0, 0, "", "Aldo,Pip|Aldo|6"},
        {'r', "Mira", "", 0, 0, "false", "Aldo,Pip|Aldo|6"},
        {'a', "Imp", "", 17, 3, "ok", "Aldo,Imp,Pip|Aldo|6"},
        {'n', "", "", 0, 0, "T:Imp@6", "Aldo,Imp,Pip|Imp|6"},
        {'a', "_x", "", 17, 4, "ok", "_x,Aldo,Imp,Pip|Imp|6"},
        {'q', "ZED", "", 0, 0, "", "_x,Aldo,Imp,Pip|Imp|6"},
        {'n', "", "", 0, 0, "T:Pip@6", "_x,Aldo,Imp,Pip|Pip|6"},
        {'s', "_x", "bless", 3, 0, "ok", "_x,Aldo,Imp,Pip|Pip|6"},
        {'n', "", "", 0, 0, "R7,T:_x@7", "_x,Aldo,Imp,Pip|_x|7"},
        {'s', "Imp", "bless", 3, 0, "ok", "_x,Aldo,Imp,Pip|_x|7"},
        {'r', "Ogre", "", 0, 0, "false", "_x,Aldo,Imp,Pip|_x|7"},
        {'q', "ZED", "", 0, 0, "", "_x,Aldo,Imp,Pip|_x|7"},
        {'n', "", "", 0, 0, "T:Aldo@7", "_x,Aldo,Imp,Pip|Aldo|7"},
        {'s', "_x", "burn", 0, 0, "ERR", "_x,Aldo,Imp,Pip|Aldo|7"},
        {'n', "", "", 0, 0, "T:Imp@7", "_x,Aldo,Imp,Pip|Imp|7"},
        {'n', "", "", 0, 0, "T:Pip@7", "_x,Aldo,Imp,Pip|Pip|7"},
        {'s', "Ogre", "burn", -1, 0, "ERR", "_x,Aldo,Imp,Pip|Pip|7"},
        {'n', "", "", 0, 0, "R8,T:_x@8", "_x,Aldo,Imp,Pip|_x|8"},
        {'n', "", "", 0, 0, "T:Aldo@8", "_x,Aldo,Imp,Pip|Aldo|8"},
        {'n', "", "", 0, 0, "T:Imp@8", "_x,Aldo,Imp,Pip|Imp|8"},
        {'n', "", "", 0, 0, "T:Pip@8", "_x,Aldo,Imp,Pip|Pip|8"},
        {'q', "kobold", "", 0, 0, "", "_x,Aldo,Imp,Pip|Pip|8"},
        {'n', "", "", 0, 0, "R9,T:_x@9", "_x,Aldo,Imp,Pip|_x|9"},
        {'n', "", "", 0, 0, "S:_x:bless@9,T:Aldo@9", "_x,Aldo,Imp,Pip|Aldo|9"},
        {'q', "Imp", "", 0, 0, "bless:1", "_x,Aldo,Imp,Pip|Aldo|9"},
        {'q', "Pip", "", 0, 0, "", "_x,Aldo,Imp,Pip|Aldo|9"},
        {'r', "Brann", "", 0, 0, "false", "_x,Aldo,Imp,Pip|Aldo|9"},
        {'q', "ZED", "", 0, 0, "", "_x,Aldo,Imp,Pip|Aldo|9"},
        {'n', "", "", 0, 0, "T:Imp@9", "_x,Aldo,Imp,Pip|Imp|9"},
        {'n', "", "", 0, 0, "S:Imp:bless@9,T:Pip@9", "_x,Aldo,Imp,Pip|Pip|9"},
        {'a', "ZED", "", 5, 1, "ok", "_x,Aldo,Imp,Pip,ZED|Pip|9"},
        {'n', "", "", 0, 0, "T:ZED@9", "_x,Aldo,Imp,Pip,ZED|ZED|9"},
        {'a', "Mira", "", 15, 3, "ok", "_x,Aldo,Imp,Mira,Pip,ZED|ZED|9"},
        {'r', "Orc", "", 0, 0, "false", "_x,Aldo,Imp,Mira,Pip,ZED|ZED|9"},
        {'n', "", "", 0, 0, "R10,T:_x@10", "_x,Aldo,Imp,Mira,Pip,ZED|_x|10"},
        {'a', "Pip", "", 12, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|_x|10"},
        {'s', "Orc", "stun", 2, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|_x|10"},
        {'s', "Ogre", "haste", 1, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|_x|10"},
        {'a', "Mira", "", 5, 4, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|_x|10"},
        {'n', "", "", 0, 0, "T:Aldo@10", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|10"},
        {'s', "Zed", "bless", -1, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|10"},
        {'a', "Aldo", "", 5, 1, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|10"},
        {'a', "aldo", "", 10, 2, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|10"},
        {'s', "Mira", "burn", 3, 0, "ok", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|10"},
        {'n', "", "", 0, 0, "T:Imp@10", "_x,Aldo,Imp,Mira,Pip,ZED|Imp|10"},
        {'n', "", "", 0, 0, "T:Mira@10", "_x,Aldo,Imp,Mira,Pip,ZED|Mira|10"},
        {'a', "Aldo", "", 12, 3, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Mira|10"},
        {'n', "", "", 0, 0, "T:Pip@10", "_x,Aldo,Imp,Mira,Pip,ZED|Pip|10"},
        {'a', "Pip", "", 10, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Pip|10"},
        {'s', "Zed", "poison", 0, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|Pip|10"},
        {'n', "", "", 0, 0, "T:ZED@10", "_x,Aldo,Imp,Mira,Pip,ZED|ZED|10"},
        {'q', "Zoe", "", 0, 0, "", "_x,Aldo,Imp,Mira,Pip,ZED|ZED|10"},
        {'a', "Zed", "", 15, 3, "ERR", "_x,Aldo,Imp,Mira,Pip,ZED|ZED|10"},
        {'n', "", "", 0, 0, "R11,T:_x@11", "_x,Aldo,Imp,Mira,Pip,ZED|_x|11"},
        {'n', "", "", 0, 0, "T:Aldo@11", "_x,Aldo,Imp,Mira,Pip,ZED|Aldo|11"},
        {'n', "", "", 0, 0, "T:Imp@11", "_x,Aldo,Imp,Mira,Pip,ZED|Imp|11"},
        {'n', "", "", 0, 0, "T:Mira@11", "_x,Aldo,Imp,Mira,Pip,ZED|Mira|11"},
        {'n', "", "", 0, 0, "T:Pip@11", "_x,Aldo,Imp,Mira,Pip,ZED|Pip|11"},
        {'r', "brann", "", 0, 0, "false", "_x,Aldo,Imp,Mira,Pip,ZED|Pip|11"},
        {'a', "Zoe", "", 12, 3, "ok", "_x,Aldo,Imp,Mira,Pip,Zoe,ZED|Pip|11"},
        {'n', "", "", 0, 0, "T:Zoe@11", "_x,Aldo,Imp,Mira,Pip,Zoe,ZED|Zoe|11"},
        {'n', "", "", 0, 0, "T:ZED@11", "_x,Aldo,Imp,Mira,Pip,Zoe,ZED|ZED|11"},
        {'a', "ZED", "", 20, 0, "ERR", "_x,Aldo,Imp,Mira,Pip,Zoe,ZED|ZED|11"},
        {'r', "kobold", "", 0, 0, "false", "_x,Aldo,Imp,Mira,Pip,Zoe,ZED|ZED|11"},
        {'r', "_x", "", 0, 0, "true", "Aldo,Imp,Mira,Pip,Zoe,ZED|ZED|11"},
        {'n', "", "", 0, 0, "R12,T:Aldo@12", "Aldo,Imp,Mira,Pip,Zoe,ZED|Aldo|12"},
        {'n', "", "", 0, 0, "T:Imp@12", "Aldo,Imp,Mira,Pip,Zoe,ZED|Imp|12"},
        {'r', "Aldo", "", 0, 0, "true", "Imp,Mira,Pip,Zoe,ZED|Imp|12"},
        {'r', "_x", "", 0, 0, "false", "Imp,Mira,Pip,Zoe,ZED|Imp|12"},
        {'a', "Aldo", "", 12, 0, "ok", "Imp,Mira,Pip,Zoe,Aldo,ZED|Imp|12"},
        {'q', "brann", "", 0, 0, "", "Imp,Mira,Pip,Zoe,Aldo,ZED|Imp|12"},
        {'r', "Orc", "", 0, 0, "false", "Imp,Mira,Pip,Zoe,Aldo,ZED|Imp|12"},
        {'a', "Orc", "", 12, 0, "ok", "Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Imp|12"},
        {'q', "Imp", "", 0, 0, "", "Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Imp|12"},
        {'s', "Zoe", "haste", 3, 0, "ok", "Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Imp|12"},
        {'a', "Brann", "", 17, 3, "ok", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Imp|12"},
        {'q', "Zoe", "", 0, 0, "haste:3", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Imp|12"},
        {'n', "", "", 0, 0, "T:Mira@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Mira|12"},
        {'n', "", "", 0, 0, "S:Mira:burn@12,T:Pip@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Pip|12"},
        {'n', "", "", 0, 0, "T:Zoe@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Zoe|12"},
        {'n', "", "", 0, 0, "T:Aldo@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Aldo|12"},
        {'n', "", "", 0, 0, "T:Orc@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Orc|12"},
        {'n', "", "", 0, 0, "T:ZED@12", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|ZED|12"},
        {'q', "Mira", "", 0, 0, "", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|ZED|12"},
        {'q', "Brann", "", 0, 0, "", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|ZED|12"},
        {'n', "", "", 0, 0, "R13,T:Brann@13", "Brann,Imp,Mira,Pip,Zoe,Aldo,Orc,ZED|Brann|13"},
        {'r', "aldo", "", 0, 0, "true", "Brann,Imp,Mira,Pip,Zoe,Orc,ZED|Brann|13"},
        {'r', "Pip", "", 0, 0, "true", "Brann,Imp,Mira,Zoe,Orc,ZED|Brann|13"},
        {'n', "", "", 0, 0, "T:Imp@13", "Brann,Imp,Mira,Zoe,Orc,ZED|Imp|13"},
        {'a', "Pip", "", 5, 3, "ok", "Brann,Imp,Mira,Zoe,Orc,Pip,ZED|Imp|13"},
        {'a', "Ogre", "", 12, 3, "ok", "Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Imp|13"},
        {'n', "", "", 0, 0, "T:Mira@13", "Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Mira|13"},
        {'a', "Zed", "", 10, 1, "ERR", "Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Mira|13"},
        {'n', "", "", 0, 0, "T:Ogre@13", "Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Ogre|13"},
        {'a', "Aldo", "", 20, 1, "ok", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Ogre|13"},
        {'n', "", "", 0, 0, "T:Zoe@13", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Zoe|13"},
        {'s', "Brann", "burn", 1, 0, "ok", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Zoe|13"},
        {'a', "aldo", "", 17, 1, "ERR", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Zoe|13"},
        {'n', "", "", 0, 0, "T:Orc@13", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,Pip,ZED|Orc|13"},
        {'a', "_x", "", 5, 4, "ok", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,_x,Pip,ZED|Orc|13"},
        {'n', "", "", 0, 0, "T:_x@13", "Aldo,Brann,Imp,Mira,Ogre,Zoe,Orc,_x,Pip,ZED|_x|13"},
        {'r', "Ogre", "", 0, 0, "true", "Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|_x|13"},
        {'a', "Ogre", "", 20, 4, "ok", "Ogre,Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|_x|13"},
        {'n', "", "", 0, 0, "T:Pip@13", "Ogre,Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Pip|13"},
        {'n', "", "", 0, 0, "T:ZED@13", "Ogre,Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|ZED|13"},
        {'n', "", "", 0, 0, "R14,T:Ogre@14", "Ogre,Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Ogre|14"},
        {'n', "", "", 0, 0, "T:Aldo@14", "Ogre,Aldo,Brann,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Aldo|14"},
        {'r', "Brann", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Aldo|14"},
        {'a', "Imp", "", 17, 4, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Aldo|14"},
        {'n', "", "", 0, 0, "T:Imp@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Imp|14"},
        {'n', "", "", 0, 0, "T:Mira@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|14"},
        {'n', "", "", 0, 0, "T:Zoe@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Zoe|14"},
        {'n', "", "", 0, 0, "S:Zoe:haste@14,T:Orc@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Orc|14"},
        {'a', "Imp", "", 12, 3, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Orc|14"},
        {'n', "", "", 0, 0, "T:_x@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|_x|14"},
        {'n', "", "", 0, 0, "T:Pip@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Pip|14"},
        {'n', "", "", 0, 0, "T:ZED@14", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|ZED|14"},
        {'n', "", "", 0, 0, "R15,T:Ogre@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Ogre|15"},
        {'n', "", "", 0, 0, "T:Aldo@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Aldo|15"},
        {'a', "Aldo", "", 12, 4, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Aldo|15"},
        {'n', "", "", 0, 0, "T:Imp@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Imp|15"},
        {'n', "", "", 0, 0, "T:Mira@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'s', "Imp", "burn", 1, 0, "ok", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'a', "_x", "", 17, 0, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'s', "Ogre", "haste", 0, 0, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'r', "brann", "", 0, 0, "false", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'s', "ZED", "bless", 3, 0, "ok", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Mira|15"},
        {'n', "", "", 0, 0, "T:Zoe@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Zoe|15"},
        {'s', "Zoe", "haste", 1, 0, "ok", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Zoe|15"},
        {'s', "Mira", "poison", 3, 0, "ok", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Zoe|15"},
        {'n', "", "", 0, 0, "S:Zoe:haste@15,T:Orc@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Orc|15"},
        {'a', "Ogre", "", 15, 3, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip,ZED|Orc|15"},
        {'r', "ZED", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Orc|15"},
        {'n', "", "", 0, 0, "T:_x@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|_x|15"},
        {'n', "", "", 0, 0, "T:Pip@15", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'q', "Mira", "", 0, 0, "poison:3", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'s', "Pip", "stun", -1, 0, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'r', "kobold", "", 0, 0, "false", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'a', "Aldo", "", 5, 2, "ERR", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'s', "Ogre", "haste", 1, 0, "ok", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Pip|15"},
        {'n', "", "", 0, 0, "R16,T:Ogre@16", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,Pip|Ogre|16"},
        {'a', "ZED", "", 17, 1, "ok", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,Pip|Ogre|16"},
        {'n', "", "", 0, 0, "S:Ogre:haste@16,T:Aldo@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,Pip|Aldo|16"},
        {'a', "_x", "", 12, 2, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,Pip|Aldo|16"},
        {'n', "", "", 0, 0, "T:Imp@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,Pip|Imp|16"},
        {'n', "", "", 0, 0, "S:Imp:burn@16,T:ZED@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,Pip|ZED|16"},
        {'a', "brann", "", 5, 3, "ok", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|ZED|16"},
        {'n', "", "", 0, 0, "T:Mira@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Mira|16"},
        {'q', "Imp", "", 0, 0, "", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Mira|16"},
        {'n', "", "", 0, 0, "T:Zoe@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Zoe|16"},
        {'s', "Aldo", "stun", 2, 0, "ok", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Zoe|16"},
        {'a', "Pip", "", 10, 3, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Zoe|16"},
        {'q', "_x", "", 0, 0, "", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Zoe|16"},
        {'n', "", "", 0, 0, "T:Orc@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Orc|16"},
        {'s', "Imp", "Stun", 1, 0, "ok", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Orc|16"},
        {'n', "", "", 0, 0, "T:_x@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|_x|16"},
        {'n', "", "", 0, 0, "T:brann@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|brann|16"},
        {'s', "_x", "burn", -1, 0, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|brann|16"},
        {'n', "", "", 0, 0, "T:Pip@16", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Pip|16"},
        {'n', "", "", 0, 0, "R17,T:Ogre@17", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Ogre|17"},
        {'n', "", "", 0, 0, "T:Aldo@17", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Aldo|17"},
        {'a', "Ogre", "", 15, 1, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Aldo|17"},
        {'a', "Mira", "", 17, 0, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Aldo|17"},
        {'q', "_x", "", 0, 0, "", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Aldo|17"},
        {'n', "", "", 0, 0, "T:Imp@17", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Imp|17"},
        {'a', "Ogre", "", 12, 3, "ERR", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Imp|17"},
        {'n', "", "", 0, 0, "S:Imp:Stun@17,T:ZED@17", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|ZED|17"},
        {'n', "", "", 0, 0, "T:Mira@17", "Ogre,Aldo,Imp,ZED,Mira,Zoe,Orc,_x,brann,Pip|Mira|17"},
        {'r', "Zed", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,brann,Pip|Mira|17"},
        {'n', "", "", 0, 0, "T:Zoe@17", "Ogre,Aldo,Imp,Mira,Zoe,Orc,_x,brann,Pip|Zoe|17"},
        {'r', "Zoe", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|-|17"},
        {'n', "", "", 0, 0, "T:Orc@17", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|Orc|17"},
        {'r', "Zoe", "", 0, 0, "false", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|Orc|17"},
        {'s', "brann", "poison", -1, 0, "ERR", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|Orc|17"},
        {'a', "Pip", "", 12, 3, "ERR", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|Orc|17"},
        {'n', "", "", 0, 0, "T:_x@17", "Ogre,Aldo,Imp,Mira,Orc,_x,brann,Pip|_x|17"},
        {'r', "Brann", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|_x|17"},
        {'n', "", "", 0, 0, "T:Pip@17", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|Pip|17"},
        {'n', "", "", 0, 0, "R18,T:Ogre@18", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|Ogre|18"},
        {'q', "Orc", "", 0, 0, "", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|Ogre|18"},
        {'n', "", "", 0, 0, "T:Aldo@18", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|Aldo|18"},
        {'a', "Aldo", "", 17, 1, "ERR", "Ogre,Aldo,Imp,Mira,Orc,_x,Pip|Aldo|18"},
        {'r', "Orc", "", 0, 0, "true", "Ogre,Aldo,Imp,Mira,_x,Pip|Aldo|18"},
        {'s', "ZED", "bless", 3, 0, "ERR", "Ogre,Aldo,Imp,Mira,_x,Pip|Aldo|18"},
        {'s', "kobold", "Stun", 1, 0, "ERR", "Ogre,Aldo,Imp,Mira,_x,Pip|Aldo|18"},
        {'n', "", "", 0, 0, "S:Aldo:stun@18,T:Imp@18", "Ogre,Aldo,Imp,Mira,_x,Pip|Imp|18"},
    };

    static const Step scriptC[] = {
        {'r', "Imp", "", 0, 0, "false", "|-|0"},
        {'a', "Ogre", "", 10, 3, "ok", "Ogre|-|0"},
        {'a', "Zed", "", 12, 1, "ok", "Zed,Ogre|-|0"},
        {'n', "", "", 0, 0, "R1,T:Zed@1", "Zed,Ogre|Zed|1"},
        {'q', "Ogre", "", 0, 0, "", "Zed,Ogre|Zed|1"},
        {'s', "Zed", "bless", -1, 0, "ERR", "Zed,Ogre|Zed|1"},
        {'a', "Aldo", "", 5, 4, "ok", "Zed,Ogre,Aldo|Zed|1"},
        {'n', "", "", 0, 0, "T:Ogre@1", "Zed,Ogre,Aldo|Ogre|1"},
        {'a', "Mira", "", 15, 0, "ok", "Mira,Zed,Ogre,Aldo|Ogre|1"},
        {'n', "", "", 0, 0, "T:Aldo@1", "Mira,Zed,Ogre,Aldo|Aldo|1"},
        {'r', "kobold", "", 0, 0, "false", "Mira,Zed,Ogre,Aldo|Aldo|1"},
        {'n', "", "", 0, 0, "R2,T:Mira@2", "Mira,Zed,Ogre,Aldo|Mira|2"},
        {'n', "", "", 0, 0, "T:Zed@2", "Mira,Zed,Ogre,Aldo|Zed|2"},
        {'n', "", "", 0, 0, "T:Ogre@2", "Mira,Zed,Ogre,Aldo|Ogre|2"},
        {'n', "", "", 0, 0, "T:Aldo@2", "Mira,Zed,Ogre,Aldo|Aldo|2"},
        {'s', "Mira", "bless", 2, 0, "ok", "Mira,Zed,Ogre,Aldo|Aldo|2"},
        {'a', "Brann", "", 15, 4, "ok", "Brann,Mira,Zed,Ogre,Aldo|Aldo|2"},
        {'s', "kobold", "Stun", 0, 0, "ERR", "Brann,Mira,Zed,Ogre,Aldo|Aldo|2"},
        {'n', "", "", 0, 0, "R3,T:Brann@3", "Brann,Mira,Zed,Ogre,Aldo|Brann|3"},
        {'n', "", "", 0, 0, "T:Mira@3", "Brann,Mira,Zed,Ogre,Aldo|Mira|3"},
        {'q', "Pip", "", 0, 0, "", "Brann,Mira,Zed,Ogre,Aldo|Mira|3"},
        {'n', "", "", 0, 0, "T:Zed@3", "Brann,Mira,Zed,Ogre,Aldo|Zed|3"},
        {'n', "", "", 0, 0, "T:Ogre@3", "Brann,Mira,Zed,Ogre,Aldo|Ogre|3"},
        {'n', "", "", 0, 0, "T:Aldo@3", "Brann,Mira,Zed,Ogre,Aldo|Aldo|3"},
        {'n', "", "", 0, 0, "R4,T:Brann@4", "Brann,Mira,Zed,Ogre,Aldo|Brann|4"},
        {'n', "", "", 0, 0, "T:Mira@4", "Brann,Mira,Zed,Ogre,Aldo|Mira|4"},
        {'n', "", "", 0, 0, "S:Mira:bless@4,T:Zed@4", "Brann,Mira,Zed,Ogre,Aldo|Zed|4"},
        {'n', "", "", 0, 0, "T:Ogre@4", "Brann,Mira,Zed,Ogre,Aldo|Ogre|4"},
        {'a', "Imp", "", 10, 4, "ok", "Brann,Mira,Zed,Imp,Ogre,Aldo|Ogre|4"},
        {'n', "", "", 0, 0, "T:Aldo@4", "Brann,Mira,Zed,Imp,Ogre,Aldo|Aldo|4"},
        {'n', "", "", 0, 0, "R5,T:Brann@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Brann|5"},
        {'n', "", "", 0, 0, "T:Mira@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|5"},
        {'r', "Orc", "", 0, 0, "false", "Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|5"},
        {'a', "Ogre", "", 10, 2, "ERR", "Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|5"},
        {'n', "", "", 0, 0, "T:Zed@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Zed|5"},
        {'s', "Zed", "stun", 2, 0, "ok", "Brann,Mira,Zed,Imp,Ogre,Aldo|Zed|5"},
        {'s', "Pip", "stun", 1, 0, "ERR", "Brann,Mira,Zed,Imp,Ogre,Aldo|Zed|5"},
        {'n', "", "", 0, 0, "T:Imp@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Imp|5"},
        {'n', "", "", 0, 0, "T:Ogre@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Ogre|5"},
        {'s', "Ogre", "burn", 0, 0, "ERR", "Brann,Mira,Zed,Imp,Ogre,Aldo|Ogre|5"},
        {'n', "", "", 0, 0, "T:Aldo@5", "Brann,Mira,Zed,Imp,Ogre,Aldo|Aldo|5"},
        {'n', "", "", 0, 0, "R6,T:Brann@6", "Brann,Mira,Zed,Imp,Ogre,Aldo|Brann|6"},
        {'q', "Orc", "", 0, 0, "", "Brann,Mira,Zed,Imp,Ogre,Aldo|Brann|6"},
        {'r', "Orc", "", 0, 0, "false", "Brann,Mira,Zed,Imp,Ogre,Aldo|Brann|6"},
        {'a', "Brann", "", 17, 2, "ERR", "Brann,Mira,Zed,Imp,Ogre,Aldo|Brann|6"},
        {'n', "", "", 0, 0, "T:Mira@6", "Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|6"},
        {'a', "Pip", "", 17, 2, "ok", "Pip,Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|6"},
        {'s', "Zed", "Stun", 3, 0, "ok", "Pip,Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|6"},
        {'s', "Mira", "Stun", -1, 0, "ERR", "Pip,Brann,Mira,Zed,Imp,Ogre,Aldo|Mira|6"},
        {'n', "", "", 0, 0, "T:Zed@6", "Pip,Brann,Mira,Zed,Imp,Ogre,Aldo|Zed|6"},
        {'n', "", "", 0, 0, "S:Zed:stun@6,T:Imp@6", "Pip,Brann,Mira,Zed,Imp,Ogre,Aldo|Imp|6"},
        {'a', "_x", "", 15, 3, "ok", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Imp|6"},
        {'n', "", "", 0, 0, "T:Ogre@6", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Ogre|6"},
        {'n', "", "", 0, 0, "T:Aldo@6", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Aldo|6"},
        {'n', "", "", 0, 0, "R7,T:Pip@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Pip|7"},
        {'s', "Imp", "poison", 2, 0, "ok", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Pip|7"},
        {'q', "Mira", "", 0, 0, "", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Pip|7"},
        {'n', "", "", 0, 0, "T:Brann@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|Brann|7"},
        {'n', "", "", 0, 0, "T:_x@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre,Aldo|_x|7"},
        {'r', "Aldo", "", 0, 0, "true", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|_x|7"},
        {'n', "", "", 0, 0, "T:Mira@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|Mira|7"},
        {'n', "", "", 0, 0, "T:Zed@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|Zed|7"},
        {'a', "Ogre", "", 17, 4, "ERR", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|Zed|7"},
        {'n', "", "", 0, 0, "T:Imp@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|Imp|7"},
        {'n', "", "", 0, 0, "T:Ogre@7", "Pip,Brann,_x,Mira,Zed,Imp,Ogre|Ogre|7"},
        {'r', "Ogre", "", 0, 0, "true", "Pip,Brann,_x,Mira,Zed,Imp|-|7"},
        {'r', "Mira", "", 0, 0, "true", "Pip,Brann,_x,Zed,Imp|-|7"},
        {'n', "", "", 0, 0, "R8,T:Pip@8", "Pip,Brann,_x,Zed,Imp|Pip|8"},
        {'a', "Zoe", "", 20, 2, "ok", "Zoe,Pip,Brann,_x,Zed,Imp|Pip|8"},
        {'n', "", "", 0, 0, "T:Brann@8", "Zoe,Pip,Brann,_x,Zed,Imp|Brann|8"},
        {'s', "ZED", "bless", 2, 0, "ok", "Zoe,Pip,Brann,_x,Zed,Imp|Brann|8"},
        {'n', "", "", 0, 0, "T:_x@8", "Zoe,Pip,Brann,_x,Zed,Imp|_x|8"},
        {'n', "", "", 0, 0, "T:Zed@8", "Zoe,Pip,Brann,_x,Zed,Imp|Zed|8"},
        {'r', "_x", "", 0, 0, "true", "Zoe,Pip,Brann,Zed,Imp|Zed|8"},
        {'s', "Mira", "poison", -1, 0, "ERR", "Zoe,Pip,Brann,Zed,Imp|Zed|8"},
        {'n', "", "", 0, 0, "S:Zed:Stun@8,T:Imp@8", "Zoe,Pip,Brann,Zed,Imp|Imp|8"},
        {'r', "Brann", "", 0, 0, "true", "Zoe,Pip,Zed,Imp|Imp|8"},
        {'n', "", "", 0, 0, "S:Imp:poison@8,R9,T:Zoe@9", "Zoe,Pip,Zed,Imp|Zoe|9"},
        {'r', "aldo", "", 0, 0, "false", "Zoe,Pip,Zed,Imp|Zoe|9"},
        {'a', "ZED", "", 10, 0, "ERR", "Zoe,Pip,Zed,Imp|Zoe|9"},
        {'n', "", "", 0, 0, "T:Pip@9", "Zoe,Pip,Zed,Imp|Pip|9"},
        {'n', "", "", 0, 0, "T:Zed@9", "Zoe,Pip,Zed,Imp|Zed|9"},
        {'n', "", "", 0, 0, "S:Zed:bless@9,T:Imp@9", "Zoe,Pip,Zed,Imp|Imp|9"},
        {'r', "_x", "", 0, 0, "false", "Zoe,Pip,Zed,Imp|Imp|9"},
        {'n', "", "", 0, 0, "R10,T:Zoe@10", "Zoe,Pip,Zed,Imp|Zoe|10"},
        {'a', "Zoe", "", 12, 3, "ERR", "Zoe,Pip,Zed,Imp|Zoe|10"},
        {'s', "Ogre", "stun", 1, 0, "ERR", "Zoe,Pip,Zed,Imp|Zoe|10"},
        {'q', "Aldo", "", 0, 0, "", "Zoe,Pip,Zed,Imp|Zoe|10"},
        {'r', "Pip", "", 0, 0, "true", "Zoe,Zed,Imp|Zoe|10"},
        {'n', "", "", 0, 0, "T:Zed@10", "Zoe,Zed,Imp|Zed|10"},
        {'a', "_x", "", 10, 3, "ok", "Zoe,Zed,Imp,_x|Zed|10"},
        {'s', "Zed", "Stun", 2, 0, "ok", "Zoe,Zed,Imp,_x|Zed|10"},
        {'q', "Imp", "", 0, 0, "", "Zoe,Zed,Imp,_x|Zed|10"},
        {'s', "Pip", "burn", 3, 0, "ERR", "Zoe,Zed,Imp,_x|Zed|10"},
        {'n', "", "", 0, 0, "T:Imp@10", "Zoe,Zed,Imp,_x|Imp|10"},
        {'a', "Brann", "", 5, 3, "ok", "Zoe,Zed,Imp,_x,Brann|Imp|10"},
        {'n', "", "", 0, 0, "T:_x@10", "Zoe,Zed,Imp,_x,Brann|_x|10"},
        {'n', "", "", 0, 0, "T:Brann@10", "Zoe,Zed,Imp,_x,Brann|Brann|10"},
        {'n', "", "", 0, 0, "R11,T:Zoe@11", "Zoe,Zed,Imp,_x,Brann|Zoe|11"},
        {'s', "Ogre", "stun", -1, 0, "ERR", "Zoe,Zed,Imp,_x,Brann|Zoe|11"},
        {'s', "Imp", "burn", 0, 0, "ERR", "Zoe,Zed,Imp,_x,Brann|Zoe|11"},
        {'s', "Ogre", "stun", 0, 0, "ERR", "Zoe,Zed,Imp,_x,Brann|Zoe|11"},
        {'n', "", "", 0, 0, "T:Zed@11", "Zoe,Zed,Imp,_x,Brann|Zed|11"},
        {'a', "Mira", "", 12, 3, "ok", "Zoe,Mira,Zed,Imp,_x,Brann|Zed|11"},
        {'n', "", "", 0, 0, "S:Zed:Stun@11,T:Imp@11", "Zoe,Mira,Zed,Imp,_x,Brann|Imp|11"},
        {'a', "brann", "", 15, 1, "ERR", "Zoe,Mira,Zed,Imp,_x,Brann|Imp|11"},
        {'n', "", "", 0, 0, "T:_x@11", "Zoe,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'q', "Pip", "", 0, 0, "", "Zoe,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'a', "Orc", "", 17, 1, "ok", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'r', "Pip", "", 0, 0, "false", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'q', "Orc", "", 0, 0, "", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'s', "Aldo", "stun", 0, 0, "ERR", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|_x|11"},
        {'n', "", "", 0, 0, "T:Brann@11", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Brann|11"},
        {'a', "Zed", "", 12, 0, "ERR", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Brann|11"},
        {'q', "Imp", "", 0, 0, "", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Brann|11"},
        {'n', "", "", 0, 0, "R12,T:Zoe@12", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Zoe|12"},
        {'a', "Zed", "", 17, 0, "ERR", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Zoe|12"},
        {'q', "Mira", "", 0, 0, "", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Zoe|12"},
        {'n', "", "", 0, 0, "T:Orc@12", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Orc|12"},
        {'n', "", "", 0, 0, "T:Mira@12", "Zoe,Orc,Mira,Zed,Imp,_x,Brann|Mira|12"},
        {'a', "Ogre", "", 5, 4, "ok", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Mira|12"},
        {'a', "aldo", "", 12, 2, "ok", "Zoe,Orc,Mira,aldo,Zed,Imp,_x,Ogre,Brann|Mira|12"},
        {'a', "Aldo", "", 15, 2, "ERR", "Zoe,Orc,Mira,aldo,Zed,Imp,_x,Ogre,Brann|Mira|12"},
        {'r', "aldo", "", 0, 0, "true", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Mira|12"},
        {'s', "Zed", "poison", 1, 0, "ok", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Mira|12"},
        {'n', "", "", 0, 0, "T:Zed@12", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Zed|12"},
        {'s', "brann", "poison", 1, 0, "ok", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Zed|12"},
        {'a', "Zoe", "", 17, 4, "ERR", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Zed|12"},
        {'n', "", "", 0, 0, "S:Zed:poison@12,T:Imp@12", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Imp|12"},
        {'n', "", "", 0, 0, "T:_x@12", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|_x|12"},
        {'s', "ZED", "haste", 3, 0, "ok", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|_x|12"},
        {'n', "", "", 0, 0, "T:Ogre@12", "Zoe,Orc,Mira,Zed,Imp,_x,Ogre,Brann|Ogre|12"},
        {'r', "ZED", "", 0, 0, "true", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|Ogre|12"},
        {'s', "Mira", "bless", 1, 0, "ok", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|Ogre|12"},
        {'q', "_x", "", 0, 0, "", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|Ogre|12"},
        {'a', "Aldo", "", 12, 0, "ok", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Ogre|12"},
        {'n', "", "", 0, 0, "T:Brann@12", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Brann|12"},
        {'s', "Aldo", "burn", 1, 0, "ok", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Brann|12"},
        {'s', "Brann", "haste", -1, 0, "ERR", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Brann|12"},
        {'n', "", "", 0, 0, "S:Brann:poison@12,R13,T:Zoe@13", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Zoe|13"},
        {'q', "_x", "", 0, 0, "", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Zoe|13"},
        {'n', "", "", 0, 0, "T:Orc@13", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Orc|13"},
        {'n', "", "", 0, 0, "T:Mira@13", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Mira|13"},
        {'n', "", "", 0, 0, "S:Mira:bless@13,T:Aldo@13", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Aldo|13"},
        {'a', "Mira", "", 20, 1, "ERR", "Zoe,Orc,Mira,Aldo,Imp,_x,Ogre,Brann|Aldo|13"},
        {'r', "Aldo", "", 0, 0, "true", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|-|13"},
        {'r', "Orc", "", 0, 0, "true", "Zoe,Mira,Imp,_x,Ogre,Brann|-|13"},
        {'n', "", "", 0, 0, "T:Imp@13", "Zoe,Mira,Imp,_x,Ogre,Brann|Imp|13"},
        {'n', "", "", 0, 0, "T:_x@13", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|13"},
        {'s', "Mira", "burn", 1, 0, "ok", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|13"},
        {'a', "Ogre", "", 15, 3, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|13"},
        {'r', "Orc", "", 0, 0, "false", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|13"},
        {'a', "Imp", "", 12, 0, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|13"},
        {'n', "", "", 0, 0, "T:Ogre@13", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|13"},
        {'a', "Imp", "", 17, 3, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|13"},
        {'a', "brann", "", 12, 3, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|13"},
        {'n', "", "", 0, 0, "T:Brann@13", "Zoe,Mira,Imp,_x,Ogre,Brann|Brann|13"},
        {'n', "", "", 0, 0, "R14,T:Zoe@14", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|14"},
        {'s', "ZED", "poison", 3, 0, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|14"},
        {'n', "", "", 0, 0, "T:Mira@14", "Zoe,Mira,Imp,_x,Ogre,Brann|Mira|14"},
        {'n', "", "", 0, 0, "S:Mira:burn@14,T:Imp@14", "Zoe,Mira,Imp,_x,Ogre,Brann|Imp|14"},
        {'n', "", "", 0, 0, "T:_x@14", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|14"},
        {'s', "Ogre", "Stun", -1, 0, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|14"},
        {'n', "", "", 0, 0, "T:Ogre@14", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|14"},
        {'s', "Ogre", "poison", -1, 0, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|14"},
        {'n', "", "", 0, 0, "T:Brann@14", "Zoe,Mira,Imp,_x,Ogre,Brann|Brann|14"},
        {'n', "", "", 0, 0, "R15,T:Zoe@15", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|15"},
        {'a', "brann", "", 12, 0, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|15"},
        {'q', "Mira", "", 0, 0, "", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|15"},
        {'n', "", "", 0, 0, "T:Mira@15", "Zoe,Mira,Imp,_x,Ogre,Brann|Mira|15"},
        {'q', "Zoe", "", 0, 0, "", "Zoe,Mira,Imp,_x,Ogre,Brann|Mira|15"},
        {'n', "", "", 0, 0, "T:Imp@15", "Zoe,Mira,Imp,_x,Ogre,Brann|Imp|15"},
        {'n', "", "", 0, 0, "T:_x@15", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|15"},
        {'a', "brann", "", 17, 1, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|15"},
        {'n', "", "", 0, 0, "T:Ogre@15", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|15"},
        {'q', "kobold", "", 0, 0, "", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|15"},
        {'n', "", "", 0, 0, "T:Brann@15", "Zoe,Mira,Imp,_x,Ogre,Brann|Brann|15"},
        {'n', "", "", 0, 0, "R16,T:Zoe@16", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|16"},
        {'n', "", "", 0, 0, "T:Mira@16", "Zoe,Mira,Imp,_x,Ogre,Brann|Mira|16"},
        {'n', "", "", 0, 0, "T:Imp@16", "Zoe,Mira,Imp,_x,Ogre,Brann|Imp|16"},
        {'n', "", "", 0, 0, "T:_x@16", "Zoe,Mira,Imp,_x,Ogre,Brann|_x|16"},
        {'n', "", "", 0, 0, "T:Ogre@16", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|16"},
        {'r', "Zed", "", 0, 0, "false", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|16"},
        {'q', "_x", "", 0, 0, "", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|16"},
        {'a', "Brann", "", 17, 3, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Ogre|16"},
        {'n', "", "", 0, 0, "T:Brann@16", "Zoe,Mira,Imp,_x,Ogre,Brann|Brann|16"},
        {'a', "Ogre", "", 12, 3, "ERR", "Zoe,Mira,Imp,_x,Ogre,Brann|Brann|16"},
        {'n', "", "", 0, 0, "R17,T:Zoe@17", "Zoe,Mira,Imp,_x,Ogre,Brann|Zoe|17"},
        {'n', "", "", 0, 0, "T:Mira@17", "Zoe,Mira,Imp,_x,Ogre,Brann|Mira|17"},
        {'n', "", "", 0, 0, "T:Imp@17", "Zoe,Mira,Imp,_x,Ogre,Brann|Imp|17"},
        {'a', "Orc", "", 17, 4, "ok", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|Imp|17"},
        {'n', "", "", 0, 0, "T:_x@17", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|_x|17"},
        {'a', "Brann", "", 10, 1, "ERR", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|_x|17"},
        {'n', "", "", 0, 0, "T:Ogre@17", "Zoe,Orc,Mira,Imp,_x,Ogre,Brann|Ogre|17"},
        {'r', "Brann", "", 0, 0, "true", "Zoe,Orc,Mira,Imp,_x,Ogre|Ogre|17"},
        {'n', "", "", 0, 0, "R18,T:Zoe@18", "Zoe,Orc,Mira,Imp,_x,Ogre|Zoe|18"},
        {'a', "Zoe", "", 5, 2, "ERR", "Zoe,Orc,Mira,Imp,_x,Ogre|Zoe|18"},
        {'a', "brann", "", 17, 0, "ok", "Zoe,Orc,brann,Mira,Imp,_x,Ogre|Zoe|18"},
        {'n', "", "", 0, 0, "T:Orc@18", "Zoe,Orc,brann,Mira,Imp,_x,Ogre|Orc|18"},
        {'a', "Pip", "", 15, 0, "ok", "Zoe,Orc,brann,Pip,Mira,Imp,_x,Ogre|Orc|18"},
    };

    static const Step scriptD[] = {
        {'r', "Orc", "", 0, 0, "false", "|-|0"},
        {'n', "", "", 0, 0, "", "|-|0"},
        {'q', "Orc", "", 0, 0, "", "|-|0"},
        {'a', "Zed", "", 5, 1, "ok", "Zed|-|0"},
        {'q', "aldo", "", 0, 0, "", "Zed|-|0"},
        {'r', "brann", "", 0, 0, "false", "Zed|-|0"},
        {'n', "", "", 0, 0, "R1,T:Zed@1", "Zed|Zed|1"},
        {'r', "Mira", "", 0, 0, "false", "Zed|Zed|1"},
        {'n', "", "", 0, 0, "R2,T:Zed@2", "Zed|Zed|2"},
        {'n', "", "", 0, 0, "R3,T:Zed@3", "Zed|Zed|3"},
        {'n', "", "", 0, 0, "R4,T:Zed@4", "Zed|Zed|4"},
        {'a', "Zoe", "", 17, 0, "ok", "Zoe,Zed|Zed|4"},
        {'n', "", "", 0, 0, "R5,T:Zoe@5", "Zoe,Zed|Zoe|5"},
        {'s', "_x", "poison", 1, 0, "ERR", "Zoe,Zed|Zoe|5"},
        {'a', "Orc", "", 15, 0, "ok", "Zoe,Orc,Zed|Zoe|5"},
        {'n', "", "", 0, 0, "T:Orc@5", "Zoe,Orc,Zed|Orc|5"},
        {'n', "", "", 0, 0, "T:Zed@5", "Zoe,Orc,Zed|Zed|5"},
        {'n', "", "", 0, 0, "R6,T:Zoe@6", "Zoe,Orc,Zed|Zoe|6"},
        {'n', "", "", 0, 0, "T:Orc@6", "Zoe,Orc,Zed|Orc|6"},
        {'q', "Pip", "", 0, 0, "", "Zoe,Orc,Zed|Orc|6"},
        {'s', "kobold", "Stun", 3, 0, "ERR", "Zoe,Orc,Zed|Orc|6"},
        {'a', "Pip", "", 5, 0, "ok", "Zoe,Orc,Zed,Pip|Orc|6"},
        {'a', "Zed", "", 20, 4, "ERR", "Zoe,Orc,Zed,Pip|Orc|6"},
        {'s', "Aldo", "stun", 3, 0, "ERR", "Zoe,Orc,Zed,Pip|Orc|6"},
        {'n', "", "", 0, 0, "T:Zed@6", "Zoe,Orc,Zed,Pip|Zed|6"},
        {'n', "", "", 0, 0, "T:Pip@6", "Zoe,Orc,Zed,Pip|Pip|6"},
        {'s', "aldo", "burn", 3, 0, "ERR", "Zoe,Orc,Zed,Pip|Pip|6"},
        {'n', "", "", 0, 0, "R7,T:Zoe@7", "Zoe,Orc,Zed,Pip|Zoe|7"},
        {'s', "Pip", "bless", 2, 0, "ok", "Zoe,Orc,Zed,Pip|Zoe|7"},
        {'a', "Brann", "", 15, 3, "ok", "Zoe,Brann,Orc,Zed,Pip|Zoe|7"},
        {'n', "", "", 0, 0, "T:Brann@7", "Zoe,Brann,Orc,Zed,Pip|Brann|7"},
        {'r', "aldo", "", 0, 0, "false", "Zoe,Brann,Orc,Zed,Pip|Brann|7"},
        {'n', "", "", 0, 0, "T:Orc@7", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'r', "Mira", "", 0, 0, "false", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'a', "Zed", "", 17, 0, "ERR", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'s', "Zoe", "bless", -1, 0, "ERR", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'s', "brann", "burn", 0, 0, "ERR", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'a', "brann", "", 15, 3, "ERR", "Zoe,Brann,Orc,Zed,Pip|Orc|7"},
        {'n', "", "", 0, 0, "T:Zed@7", "Zoe,Brann,Orc,Zed,Pip|Zed|7"},
        {'a', "aldo", "", 5, 3, "ok", "Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'a', "aldo", "", 15, 3, "ERR", "Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'a', "Aldo", "", 12, 0, "ERR", "Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'a', "brann", "", 12, 3, "ERR", "Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'a', "Brann", "", 17, 0, "ERR", "Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'a', "_x", "", 17, 4, "ok", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|Zed|7"},
        {'n', "", "", 0, 0, "T:Pip@7", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|Pip|7"},
        {'q', "Ogre", "", 0, 0, "", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|Pip|7"},
        {'s', "Zoe", "stun", 1, 0, "ok", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|Pip|7"},
        {'s', "Ogre", "haste", 3, 0, "ERR", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|Pip|7"},
        {'n', "", "", 0, 0, "R8,T:_x@8", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|_x|8"},
        {'q', "Orc", "", 0, 0, "", "_x,Zoe,Brann,Orc,aldo,Zed,Pip|_x|8"},
        {'a', "Imp", "", 12, 1, "ok", "_x,Zoe,Brann,Orc,Imp,aldo,Zed,Pip|_x|8"},
        {'s', "Imp", "bless", 2, 0, "ok", "_x,Zoe,Brann,Orc,Imp,aldo,Zed,Pip|_x|8"},
        {'a', "kobold", "", 10, 3, "ok", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|_x|8"},
        {'s', "aldo", "haste", -1, 0, "ERR", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|_x|8"},
        {'n', "", "", 0, 0, "T:Zoe@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zoe|8"},
        {'q', "brann", "", 0, 0, "", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zoe|8"},
        {'s', "Imp", "bless", 2, 0, "ok", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zoe|8"},
        {'r', "Ogre", "", 0, 0, "false", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zoe|8"},
        {'n', "", "", 0, 0, "S:Zoe:stun@8,T:Brann@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Brann|8"},
        {'n', "", "", 0, 0, "T:Orc@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Orc|8"},
        {'n', "", "", 0, 0, "T:Imp@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Imp|8"},
        {'q', "aldo", "", 0, 0, "", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Imp|8"},
        {'n', "", "", 0, 0, "T:kobold@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|kobold|8"},
        {'n', "", "", 0, 0, "T:aldo@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|aldo|8"},
        {'s', "_x", "Stun", 1, 0, "ok", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|aldo|8"},
        {'n', "", "", 0, 0, "T:Zed@8", "_x,Zoe,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zed|8"},
        {'r', "Zoe", "", 0, 0, "true", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Zed|8"},
        {'n', "", "", 0, 0, "T:Pip@8", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Pip|8"},
        {'a', "brann", "", 15, 4, "ERR", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Pip|8"},
        {'n', "", "", 0, 0, "S:Pip:bless@8,R9,T:_x@9", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|_x|9"},
        {'n', "", "", 0, 0, "S:_x:Stun@9,T:Brann@9", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Brann|9"},
        {'n', "", "", 0, 0, "T:Orc@9", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Orc|9"},
        {'s', "Brann", "haste", 3, 0, "ok", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Orc|9"},
        {'n', "", "", 0, 0, "T:Imp@9", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Imp|9"},
        {'a', "", "", 12, 0, "ERR", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|Imp|9"},
        {'n', "", "", 0, 0, "S:Imp:bless@9,T:kobold@9", "_x,Brann,Orc,Imp,kobold,aldo,Zed,Pip|kobold|9"},
        {'r', "Aldo", "", 0, 0, "true", "_x,Brann,Orc,Imp,kobold,Zed,Pip|kobold|9"},
        {'n', "", "", 0, 0, "T:Zed@9", "_x,Brann,Orc,Imp,kobold,Zed,Pip|Zed|9"},
        {'n', "", "", 0, 0, "T:Pip@9", "_x,Brann,Orc,Imp,kobold,Zed,Pip|Pip|9"},
        {'n', "", "", 0, 0, "R10,T:_x@10", "_x,Brann,Orc,Imp,kobold,Zed,Pip|_x|10"},
        {'n', "", "", 0, 0, "T:Brann@10", "_x,Brann,Orc,Imp,kobold,Zed,Pip|Brann|10"},
        {'n', "", "", 0, 0, "T:Orc@10", "_x,Brann,Orc,Imp,kobold,Zed,Pip|Orc|10"},
        {'a', "aldo", "", 20, 3, "ok", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Orc|10"},
        {'s', "brann", "stun", -1, 0, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Orc|10"},
        {'n', "", "", 0, 0, "T:Imp@10", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Imp|10"},
        {'q', "Imp", "", 0, 0, "", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Imp|10"},
        {'n', "", "", 0, 0, "T:kobold@10", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|kobold|10"},
        {'a', "_x", "", 5, 2, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|kobold|10"},
        {'n', "", "", 0, 0, "T:Zed@10", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Zed|10"},
        {'n', "", "", 0, 0, "T:Pip@10", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Pip|10"},
        {'a', "Aldo", "", 12, 2, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Pip|10"},
        {'s', "_x", "Stun", 1, 0, "ok", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Pip|10"},
        {'a', "_x", "", 17, 3, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Pip|10"},
        {'n', "", "", 0, 0, "R11,T:aldo@11", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|aldo|11"},
        {'s', "aldo", "stun", -1, 0, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|aldo|11"},
        {'n', "", "", 0, 0, "T:_x@11", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|_x|11"},
        {'a', "Pip", "", 20, 3, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|_x|11"},
        {'a', "aldo", "", 12, 1, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|_x|11"},
        {'n', "", "", 0, 0, "S:_x:Stun@11,T:Brann@11", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Brann|11"},
        {'s', "Zoe", "burn", 0, 0, "ERR", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Brann|11"},
        {'n', "", "", 0, 0, "T:Orc@11", "aldo,_x,Brann,Orc,Imp,kobold,Zed,Pip|Orc|11"},
        {'a', "Zoe", "", 15, 0, "ok", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed,Pip|Orc|11"},
        {'q', "_x", "", 0, 0, "", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed,Pip|Orc|11"},
        {'n', "", "", 0, 0, "T:Zoe@11", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed,Pip|Zoe|11"},
        {'n', "", "", 0, 0, "T:Imp@11", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed,Pip|Imp|11"},
        {'q', "Brann", "", 0, 0, "haste:1", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed,Pip|Imp|11"},
        {'r', "Pip", "", 0, 0, "true", "aldo,_x,Brann,Orc,Zoe,Imp,kobold,Zed|Imp|11"},
        {'r', "Brann", "", 0, 0, "true", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|11"},
        {'n', "", "", 0, 0, "T:kobold@11", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|11"},
        {'n', "", "", 0, 0, "T:Zed@11", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|11"},
        {'n', "", "", 0, 0, "R12,T:aldo@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|aldo|12"},
        {'n', "", "", 0, 0, "T:_x@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|_x|12"},
        {'n', "", "", 0, 0, "T:Orc@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|12"},
        {'r', "Ogre", "", 0, 0, "false", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|12"},
        {'n', "", "", 0, 0, "T:Zoe@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zoe|12"},
        {'n', "", "", 0, 0, "T:Imp@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|12"},
        {'n', "", "", 0, 0, "T:kobold@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|12"},
        {'q', "aldo", "", 0, 0, "", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|12"},
        {'n', "", "", 0, 0, "T:Zed@12", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|12"},
        {'s', "Zed", "burn", 0, 0, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|12"},
        {'s', "Zoe", "bless", 3, 0, "ok", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|12"},
        {'a', "_x", "", 12, 2, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|12"},
        {'n', "", "", 0, 0, "R13,T:aldo@13", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|aldo|13"},
        {'s', "Imp", "burn", -1, 0, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|aldo|13"},
        {'n', "", "", 0, 0, "T:_x@13", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|_x|13"},
        {'a', "brann", "", 17, 4, "ok", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|_x|13"},
        {'s', "aldo", "burn", 1, 0, "ok", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|_x|13"},
        {'n', "", "", 0, 0, "T:brann@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|brann|13"},
        {'q', "brann", "", 0, 0, "", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|brann|13"},
        {'n', "", "", 0, 0, "T:Orc@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|Orc|13"},
        {'n', "", "", 0, 0, "T:Zoe@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|Zoe|13"},
        {'n', "", "", 0, 0, "T:Imp@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|Imp|13"},
        {'a', "Ogre", "", 10, 0, "ok", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|Imp|13"},
        {'a', "ZED", "", 12, 3, "ERR", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|Imp|13"},
        {'n', "", "", 0, 0, "T:kobold@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|kobold|13"},
        {'n', "", "", 0, 0, "T:Ogre@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|Ogre|13"},
        {'n', "", "", 0, 0, "T:Zed@13", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|Zed|13"},
        {'n', "", "", 0, 0, "R14,T:aldo@14", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|aldo|14"},
        {'n', "", "", 0, 0, "S:aldo:burn@14,T:_x@14", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Ogre,Zed|_x|14"},
        {'r', "Ogre", "", 0, 0, "true", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|_x|14"},
        {'n', "", "", 0, 0, "T:brann@14", "aldo,_x,brann,Orc,Zoe,Imp,kobold,Zed|brann|14"},
        {'r', "Brann", "", 0, 0, "true", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|-|14"},
        {'n', "", "", 0, 0, "T:Orc@14", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|14"},
        {'q', "Orc", "", 0, 0, "", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|14"},
        {'n', "", "", 0, 0, "T:Zoe@14", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zoe|14"},
        {'n', "", "", 0, 0, "T:Imp@14", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|14"},
        {'s', "_x", "burn", 2, 0, "ok", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|14"},
        {'s', "Imp", "stun", 2, 0, "ok", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|14"},
        {'a', "ZED", "", 17, 3, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|14"},
        {'n', "", "", 0, 0, "T:kobold@14", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|14"},
        {'n', "", "", 0, 0, "T:Zed@14", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|14"},
        {'a', "Zoe", "", 17, 3, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|14"},
        {'n', "", "", 0, 0, "R15,T:aldo@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|aldo|15"},
        {'n', "", "", 0, 0, "T:_x@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|_x|15"},
        {'n', "", "", 0, 0, "T:Orc@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|15"},
        {'q', "Zed", "", 0, 0, "", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Orc|15"},
        {'n', "", "", 0, 0, "T:Zoe@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zoe|15"},
        {'n', "", "", 0, 0, "S:Zoe:bless@15,T:Imp@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Imp|15"},
        {'n', "", "", 0, 0, "S:Imp:stun@15,T:kobold@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|15"},
        {'a', "Zed", "", 12, 0, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|15"},
        {'a', "Zoe", "", 15, 0, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|15"},
        {'q', "aldo", "", 0, 0, "", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|kobold|15"},
        {'n', "", "", 0, 0, "T:Zed@15", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|15"},
        {'a', "Orc", "", 10, 2, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|15"},
        {'a', "Zed", "", 12, 4, "ERR", "aldo,_x,Orc,Zoe,Imp,kobold,Zed|Zed|15"},
        {'a', "brann", "", 10, 3, "ok", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Zed|15"},
        {'s', "Mira", "haste", 0, 0, "ERR", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Zed|15"},
        {'a', "Brann", "", 15, 3, "ERR", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Zed|15"},
        {'q', "_x", "", 0, 0, "burn:1", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Zed|15"},
        {'a', "Zed", "", 17, 3, "ERR", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Zed|15"},
        {'n', "", "", 0, 0, "R16,T:aldo@16", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|aldo|16"},
        {'n', "", "", 0, 0, "T:_x@16", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|_x|16"},
        {'s', "_x", "stun", 3, 0, "ok", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|_x|16"},
        {'n', "", "", 0, 0, "S:_x:burn@16,T:Orc@16", "aldo,_x,Orc,Zoe,Imp,brann,kobold,Zed|Orc|16"},
        {'r', "Zoe", "", 0, 0, "true", "aldo,_x,Orc,Imp,brann,kobold,Zed|Orc|16"},
        {'a', "brann", "", 10, 1, "ERR", "aldo,_x,Orc,Imp,brann,kobold,Zed|Orc|16"},
        {'a', "Mira", "", 12, 1, "ok", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Orc|16"},
        {'n', "", "", 0, 0, "T:Imp@16", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Imp|16"},
        {'q', "Imp", "", 0, 0, "", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Imp|16"},
        {'a', "ZED", "", 17, 2, "ERR", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Imp|16"},
        {'n', "", "", 0, 0, "T:Mira@16", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Mira|16"},
        {'n', "", "", 0, 0, "T:brann@16", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|brann|16"},
        {'n', "", "", 0, 0, "T:kobold@16", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|kobold|16"},
        {'a', "aldo", "", 15, 4, "ERR", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|kobold|16"},
        {'n', "", "", 0, 0, "T:Zed@16", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Zed|16"},
        {'s', "Orc", "haste", 1, 0, "ok", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Zed|16"},
        {'r', "Pip", "", 0, 0, "false", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Zed|16"},
        {'n', "", "", 0, 0, "R17,T:aldo@17", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|aldo|17"},
        {'n', "", "", 0, 0, "T:_x@17", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|_x|17"},
        {'n', "", "", 0, 0, "T:Orc@17", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Orc|17"},
        {'q', "Zoe", "", 0, 0, "", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Orc|17"},
        {'n', "", "", 0, 0, "S:Orc:haste@17,T:Imp@17", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Imp|17"},
        {'a', "aldo", "", 10, 4, "ERR", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Imp|17"},
        {'n', "", "", 0, 0, "T:Mira@17", "aldo,_x,Orc,Imp,Mira,brann,kobold,Zed|Mira|17"},
        {'a', "Ogre", "", 17, 0, "ok", "aldo,_x,Ogre,Orc,Imp,Mira,brann,kobold,Zed|Mira|17"},
        {'a', "Imp", "", 12, 0, "ERR", "aldo,_x,Ogre,Orc,Imp,Mira,brann,kobold,Zed|Mira|17"},
        {'a', "_x", "", 12, 4, "ERR", "aldo,_x,Ogre,Orc,Imp,Mira,brann,kobold,Zed|Mira|17"},
        {'r', "Imp", "", 0, 0, "true", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|Mira|17"},
        {'n', "", "", 0, 0, "T:brann@17", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|brann|17"},
        {'n', "", "", 0, 0, "T:kobold@17", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|kobold|17"},
        {'q', "Mira", "", 0, 0, "", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|kobold|17"},
        {'a', "Zed", "", 5, 4, "ERR", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|kobold|17"},
        {'n', "", "", 0, 0, "T:Zed@17", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|Zed|17"},
        {'a', "Brann", "", 17, 1, "ERR", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|Zed|17"},
        {'n', "", "", 0, 0, "R18,T:aldo@18", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|aldo|18"},
        {'n', "", "", 0, 0, "T:_x@18", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|_x|18"},
        {'n', "", "", 0, 0, "S:_x:stun@18,T:Ogre@18", "aldo,_x,Ogre,Orc,Mira,brann,kobold,Zed|Ogre|18"},
        {'r', "Aldo", "", 0, 0, "true", "_x,Ogre,Orc,Mira,brann,kobold,Zed|Ogre|18"},
        {'n', "", "", 0, 0, "T:Orc@18", "_x,Ogre,Orc,Mira,brann,kobold,Zed|Orc|18"},
        {'s', "aldo", "Stun", 3, 0, "ERR", "_x,Ogre,Orc,Mira,brann,kobold,Zed|Orc|18"},
        {'n', "", "", 0, 0, "T:Mira@18", "_x,Ogre,Orc,Mira,brann,kobold,Zed|Mira|18"},
        {'n', "", "", 0, 0, "T:brann@18", "_x,Ogre,Orc,Mira,brann,kobold,Zed|brann|18"},
        {'n', "", "", 0, 0, "T:kobold@18", "_x,Ogre,Orc,Mira,brann,kobold,Zed|kobold|18"},
        {'r', "ZED", "", 0, 0, "true", "_x,Ogre,Orc,Mira,brann,kobold|kobold|18"},
        {'r', "Brann", "", 0, 0, "true", "_x,Ogre,Orc,Mira,kobold|kobold|18"},
        {'n', "", "", 0, 0, "R19,T:_x@19", "_x,Ogre,Orc,Mira,kobold|_x|19"},
        {'s', "aldo", "bless", 1, 0, "ERR", "_x,Ogre,Orc,Mira,kobold|_x|19"},
        {'q', "Pip", "", 0, 0, "", "_x,Ogre,Orc,Mira,kobold|_x|19"},
        {'n', "", "", 0, 0, "T:Ogre@19", "_x,Ogre,Orc,Mira,kobold|Ogre|19"},
        {'r', "_x", "", 0, 0, "true", "Ogre,Orc,Mira,kobold|Ogre|19"},
        {'n', "", "", 0, 0, "T:Orc@19", "Ogre,Orc,Mira,kobold|Orc|19"},
        {'n', "", "", 0, 0, "T:Mira@19", "Ogre,Orc,Mira,kobold|Mira|19"},
        {'n', "", "", 0, 0, "T:kobold@19", "Ogre,Orc,Mira,kobold|kobold|19"},
        {'s', "Aldo", "burn", 2, 0, "ERR", "Ogre,Orc,Mira,kobold|kobold|19"},
        {'q', "Mira", "", 0, 0, "", "Ogre,Orc,Mira,kobold|kobold|19"},
        {'s', "kobold", "haste", -1, 0, "ERR", "Ogre,Orc,Mira,kobold|kobold|19"},
        {'a', "Orc", "", 12, 3, "ERR", "Ogre,Orc,Mira,kobold|kobold|19"},
        {'a', "Zed", "", 12, 4, "ok", "Ogre,Orc,Zed,Mira,kobold|kobold|19"},
        {'q', "Brann", "", 0, 0, "", "Ogre,Orc,Zed,Mira,kobold|kobold|19"},
        {'n', "", "", 0, 0, "R20,T:Ogre@20", "Ogre,Orc,Zed,Mira,kobold|Ogre|20"},
        {'a', "Brann", "", 12, 0, "ok", "Ogre,Orc,Zed,Mira,Brann,kobold|Ogre|20"},
        {'r', "Pip", "", 0, 0, "false", "Ogre,Orc,Zed,Mira,Brann,kobold|Ogre|20"},
        {'a', "aldo", "", 15, 3, "ok", "Ogre,aldo,Orc,Zed,Mira,Brann,kobold|Ogre|20"},
        {'n', "", "", 0, 0, "T:aldo@20", "Ogre,aldo,Orc,Zed,Mira,Brann,kobold|aldo|20"},
        {'a', "Zoe", "", 12, 4, "ok", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann,kobold|aldo|20"},
        {'n', "", "", 0, 0, "T:Orc@20", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann,kobold|Orc|20"},
        {'n', "", "", 0, 0, "T:Zed@20", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann,kobold|Zed|20"},
        {'n', "", "", 0, 0, "T:Zoe@20", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann,kobold|Zoe|20"},
        {'n', "", "", 0, 0, "T:Mira@20", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann,kobold|Mira|20"},
        {'r', "kobold", "", 0, 0, "true", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Mira|20"},
        {'s', "Zoe", "haste", 0, 0, "ERR", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Mira|20"},
        {'n', "", "", 0, 0, "T:Brann@20", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Brann|20"},
        {'n', "", "", 0, 0, "R21,T:Ogre@21", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Ogre|21"},
        {'a', "Mira", "", 5, 1, "ERR", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Ogre|21"},
        {'n', "", "", 0, 0, "T:aldo@21", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|aldo|21"},
        {'n', "", "", 0, 0, "T:Orc@21", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Orc|21"},
        {'a', "ZED", "", 20, 0, "ERR", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Orc|21"},
        {'n', "", "", 0, 0, "T:Zed@21", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Zed|21"},
        {'n', "", "", 0, 0, "T:Zoe@21", "Ogre,aldo,Orc,Zed,Zoe,Mira,Brann|Zoe|21"},
    };

    static std::string snap_of(const Tracker &t) {
        std::string s;
        std::vector<std::string> o = t.order();
        for (size_t i = 0; i < o.size(); i++) s += (i ? "," : "") + o[i];
        std::optional<std::string> c = t.current();
        return s + "|" + (c ? *c : std::string("-")) + "|" + std::to_string(t.round());
    }

    static std::string events_of(const std::vector<Event> &ev) {
        std::string s;
        for (size_t i = 0; i < ev.size(); i++) {
            if (i) s += ",";
            if (ev[i].kind == Event::RoundStart) s += "R" + std::to_string(ev[i].round);
            else if (ev[i].kind == Event::TurnStart) s += "T:" + ev[i].who + "@" + std::to_string(ev[i].round);
            else s += "S:" + ev[i].who + ":" + ev[i].detail + "@" + std::to_string(ev[i].round);
        }
        return s;
    }

    static void replay(const char *name, const Step *steps, size_t count) {
        Tracker t;
        for (size_t k = 0; k < count; k++) {
            const Step &s = steps[k];
            std::string ctx = std::string(name) + " step " + std::to_string(k) + " (" + s.op + " " + s.name + ")";
            std::string res;
            try {
                switch (s.op) {
                case 'a':
                    t.add(s.name, s.n1, s.n2);
                    res = "ok";
                    break;
                case 'r':
                    res = t.remove(s.name) ? "true" : "false";
                    break;
                case 's':
                    t.add_status(s.name, s.text, s.n1);
                    res = "ok";
                    break;
                case 'q': {
                    for (const auto &p : t.statuses(s.name)) res += (res.empty() ? "" : ",") + p.first + ":" + std::to_string(p.second);
                    break;
                }
                default:
                    res = events_of(t.next_turn());
                    break;
                }
            } catch (const std::invalid_argument &) {
                res = "ERR";
            }
            CHECK_EQ_CTX(ctx, res, std::string(s.result));
            CHECK_EQ_CTX(ctx, snap_of(t), std::string(s.snap));
        }
    }

    static void test_directed() {
        Tracker t;
        CHECK_EQ(t.round(), 0);
        CHECK(!t.current().has_value());
        CHECK_EQ(t.next_turn().size(), 0u);
        CHECK_EQ(t.round(), 0);
        t.add("solo", 10, 1);
        auto ev = t.next_turn();
        CHECK_EQ(ev.size(), 2u);
        CHECK(ev[0].kind == Event::RoundStart);
        CHECK_EQ(ev[0].round, 1);
        CHECK_EQ(ev[0].who, std::string(""));
        CHECK(ev[1].kind == Event::TurnStart);
        CHECK_EQ(ev[1].who, std::string("solo"));
        ev = t.next_turn();
        CHECK_EQ(ev.size(), 2u);
        CHECK_EQ(t.round(), 2);
        CHECK_EQ(ev[0].round, 2);
        CHECK_EQ(ev[1].round, 2);
        CHECK_EQ(t.next_turn().size(), 2u);
        CHECK_EQ(t.round(), 3);
        CHECK_THROWS(t.add("", 1, 1), std::invalid_argument);
        CHECK_THROWS(t.add("SOLO", 1, 1), std::invalid_argument);
        CHECK_THROWS(t.add("Solo", 1, 1), std::invalid_argument);
        CHECK_EQ(t.order().size(), 1u);
        CHECK_THROWS(t.add_status("ghost", "x", 1), std::invalid_argument);
        CHECK_THROWS(t.add_status("solo", "x", 0), std::invalid_argument);
        CHECK_THROWS(t.add_status("solo", "x", -2), std::invalid_argument);
        CHECK_EQ(t.statuses("ghost").size(), 0u);
        CHECK(t.remove("SoLo"));
        CHECK(!t.remove("solo"));
        CHECK(!t.current().has_value());
        CHECK_EQ(t.next_turn().size(), 0u);
    }

    static void test_tie_breaks() {
        Tracker t;
        t.add("b", 10, 2);
        t.add("A", 10, 2);
        t.add("c", 10, 3);
        t.add("d", 11, 0);
        t.add("e", 10, 1);
        t.add("B2", 10, 2);
        std::vector<std::string> want = {"d", "c", "A", "b", "B2", "e"};
        CHECK_EQ(t.order(), want);
    }

    static void test_vacant_turn() {
        Tracker t;
        t.add("a", 30, 0);
        t.add("b", 20, 0);
        t.add("c", 10, 0);
        t.add("d", 5, 0);
        t.next_turn();
        t.next_turn();
        CHECK_EQ(*t.current(), std::string("b"));
        t.add_status("b", "x", 1);
        t.add_status("c", "y", 1);
        t.add_status("a", "z", 2);
        CHECK(t.remove("b"));   /* the current one leaves */
        CHECK(!t.current().has_value());
        CHECK_EQ(t.round(), 1);
        CHECK_EQ(t.statuses("b").size(), 0u);
        std::vector<Event> ev = t.next_turn();    /* c starts; nobody's statuses tick */
        CHECK_EQ(ev.size(), 1u);
        CHECK(ev[0].kind == Event::TurnStart);
        CHECK_EQ(ev[0].who, std::string("c"));
        CHECK_EQ(ev[0].round, 1);
        CHECK_EQ(t.statuses("c").size(), 1u);
        CHECK_EQ(t.statuses("c")[0].second, 1);
        CHECK_EQ(t.statuses("a")[0].second, 2);
        CHECK(t.remove("d"));   /* not the current one: nothing else changes */
        CHECK_EQ(*t.current(), std::string("c"));
        ev = t.next_turn();     /* c's statuses tick, then wrap to a: round 2 */
        CHECK_EQ(ev.size(), 3u);
        CHECK(ev[0].kind == Event::StatusEnded);
        CHECK_EQ(ev[0].who, std::string("c"));
        CHECK_EQ(ev[0].detail, std::string("y"));
        CHECK(ev[1].kind == Event::RoundStart);
        CHECK_EQ(ev[1].round, 2);
        CHECK(ev[2].kind == Event::TurnStart);
        CHECK_EQ(ev[2].who, std::string("a"));
        CHECK(t.remove("c"));   /* a is current; c was after it */
        CHECK_EQ(*t.current(), std::string("a"));
        CHECK(t.remove("a"));   /* the only combatant leaves: vacant, nobody to act */
        CHECK(!t.current().has_value());
        CHECK_EQ(t.next_turn().size(), 0u);
        CHECK_EQ(t.round(), 2);
    }

    static void test_vacant_last_and_successor() {
        Tracker t;
        t.add("a", 30, 0);
        t.add("b", 20, 0);
        t.add("c", 10, 0);
        t.next_turn();
        t.next_turn();
        t.next_turn();
        CHECK_EQ(*t.current(), std::string("c"));
        CHECK(t.remove("c"));   /* the last one leaves: the next round starts with a */
        std::vector<Event> ev = t.next_turn();
        CHECK_EQ(ev.size(), 2u);
        CHECK(ev[0].kind == Event::RoundStart);
        CHECK_EQ(ev[0].round, 2);
        CHECK_EQ(ev[1].who, std::string("a"));
        ev = t.next_turn();
        CHECK_EQ(*t.current(), std::string("b"));
        CHECK(t.remove("b"));   /* b (last) leaves again */
        CHECK(t.remove("a") == true);
        CHECK(!t.current().has_value());
        Tracker u;
        u.add("p", 30, 0);
        u.add("q", 20, 0);
        u.add("r", 10, 0);
        u.next_turn();
        CHECK(u.remove("p"));   /* the first one leaves while current: q follows */
        CHECK(!u.current().has_value());
        CHECK(u.remove("q"));   /* the successor leaves while the turn is vacant: r follows */
        ev = u.next_turn();
        CHECK_EQ(ev.size(), 1u);
        CHECK_EQ(ev[0].who, std::string("r"));
        CHECK_EQ(ev[0].round, 1);
    }

    static void test_statuses_api() {
        Tracker t;
        t.add("a", 1, 1);
        t.add_status("a", "stun", 2);
        t.add_status("A", "bless", 3);
        t.add_status("a", "Stun", 1);
        t.add_status("a", "stun", 1);   /* keeps the larger */
        t.add_status("a", "bless", 5);  /* raises */
        auto s = t.statuses("A");
        CHECK_EQ(s.size(), 3u);
        CHECK_EQ(s[0].first, std::string("Stun"));
        CHECK_EQ(s[0].second, 1);
        CHECK_EQ(s[1].first, std::string("bless"));
        CHECK_EQ(s[1].second, 5);
        CHECK_EQ(s[2].first, std::string("stun"));
        CHECK_EQ(s[2].second, 2);
    }

    int main() {
        h_init();
        test_directed();
        test_tie_breaks();
        test_vacant_turn();
        test_vacant_last_and_successor();
        test_statuses_api();
        replay("scriptA", scriptA, sizeof scriptA / sizeof scriptA[0]);
        replay("scriptB", scriptB, sizeof scriptB / sizeof scriptB[0]);
        replay("scriptC", scriptC, sizeof scriptC / sizeof scriptC[0]);
        replay("scriptD", scriptD, sizeof scriptD / sizeof scriptD[0]);
        return h_report();
    }
''')

LIB = Lib(
    name="inittrack", lang="cpp", title="the inittrack turn tracker",
    blurb="The game-master's table app keeps the turn order of a fight in an inittrack Tracker: who acts next, which round it is, and which status effects wear off when.",
    files={"README.md": README1, "include/inittrack.hpp": F2, "src/inittrack.cpp": F3},
    visible_tests={"tests/test_main.cpp": V4, "tests/harness.hpp": _lang3.CPP_HARNESS},
    hidden_tests={"tests/test_main.cpp": H5},
    mutate=["src/inittrack.cpp"], difficulty=4, tags=["game", "state-machine", "ordering"],
    verify=_lang3.CPP_VERIFY,
)

_lang3.add(LIB, n=8)
