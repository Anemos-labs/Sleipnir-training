"""Seat apportionment for a guild council (c++): D'Hondt, Sainte-Lague and largest remainder with an eligibility threshold, tie rules and a one-seat floor; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # seatshare

    Turns votes into council seats. All arithmetic is exact integer arithmetic (no floating point), so ties are real ties.

        enum class Method { DHondt, SainteLague, Hamilton };
        struct Party   { std::string name; long votes; };
        struct Options { Method method = Method::DHondt; int threshold_permille = 0; bool floor_one = false; };

        std::vector<int> allocate(const std::vector<Party> &parties, int seats, const Options &opt);

    `allocate` returns one seat count per party, in the order of `parties`; the counts add up to `seats` unless the rules below say otherwise.

    ## Validation

    `std::invalid_argument` is thrown when `seats < 0` or `seats > 1000`, when any `votes` is negative or above `1000000000`, when
    `threshold_permille` is outside `0..1000`, or when `seats > 0` and `parties` is empty. With `seats == 0`, or when the total of all votes
    is 0, every party gets 0 seats.

    ## Eligibility

    Let `total` be the sum of the votes of **all** parties. A party is *eligible* when `votes * 1000 >= threshold_permille * total` (a party that
    exactly reaches the threshold is in). Ineligible parties get 0 seats and take no part in the counting below; their votes are ignored there.
    If no party is eligible, every party gets 0 seats.

    ## Methods

    Let `s_i` be the seats a party holds so far, starting at 0.

    * **D'Hondt**: seats are given one at a time. Each time, the eligible party with the largest quotient `votes / (s_i + 1)` gets the seat.
    * **Sainte-Lague**: the same, with the quotient `votes / (2 * s_i + 1)`.
    * **Hamilton** (largest remainder): each eligible party first gets `floor(votes * seats / eligible_total)`, where `eligible_total` is the sum of the votes of the eligible parties. The
      seats still unassigned are given one each to the parties with the largest remainders `votes * seats mod eligible_total`.

    **Ties** (equal quotients, or equal remainders) are broken in favour of the party with more votes; if the votes are also equal, the party that comes first in `parties`.
    Compare quotients exactly (cross-multiply), never with floating point.

    ## The one-seat floor

    With `floor_one` set, after the allocation every *eligible* party that still has 0 seats gets one, taken from another party. Parties without a seat are served in order of
    votes, largest first (equal votes: the one earlier in `parties`). Each takes one seat from the party with the **most seats at that moment**; among parties with the same
    number of seats the donor is the one with **fewer votes**, and if the votes are equal too, the one **later** in `parties`. Only a party with at least 2 seats can give; when there is no such party the
    floor stops (some eligible parties then stay at 0).
''')

F2 = dd(r'''
    #ifndef SEATSHARE_HPP
    #define SEATSHARE_HPP

    #include <stdexcept>
    #include <string>
    #include <vector>

    namespace seatshare {

    enum class Method { DHondt, SainteLague, Hamilton };

    struct Party {
        std::string name;
        long votes;
    };

    struct Options {
        Method method = Method::DHondt;
        int threshold_permille = 0;
        bool floor_one = false;
    };

    std::vector<int> allocate(const std::vector<Party> &parties, int seats, const Options &opt);

    }  // namespace seatshare

    #endif
''')

F3 = dd(r'''
    #include "seatshare.hpp"

    namespace seatshare {

    /* is party a better pick than party b for a quotient num/den ? (exact) */
    static bool better(const std::vector<Party> &p, size_t a, long long na, long long da, size_t b, long long nb, long long db) {
        long long left = na * db, right = nb * da;
        if (left != right) return left > right;
        if (p[a].votes != p[b].votes) return p[a].votes > p[b].votes;
        return a < b;
    }

    static void divisor_method(const std::vector<Party> &p, const std::vector<bool> &eligible, int seats, int step, std::vector<int> &out) {
        for (int k = 0; k < seats; k++) {
            long best = -1;
            for (size_t i = 0; i < p.size(); i++) {
                if (!eligible[i]) continue;
                if (best < 0) {
                    best = static_cast<long>(i);
                    continue;
                }
                size_t b = static_cast<size_t>(best);
                long long di = static_cast<long long>(step) * out[i] + 1;
                long long db = static_cast<long long>(step) * out[b] + 1;
                if (better(p, i, p[i].votes, di, b, p[b].votes, db)) best = static_cast<long>(i);
            }
            if (best >= 0) out[static_cast<size_t>(best)]++;
        }
    }

    static void hamilton(const std::vector<Party> &p, const std::vector<bool> &eligible, int seats, long long total, std::vector<int> &out) {
        std::vector<long long> rem(p.size(), 0);
        int given = 0;
        for (size_t i = 0; i < p.size(); i++) {
            if (!eligible[i]) continue;
            long long prod = static_cast<long long>(p[i].votes) * seats;
            out[i] = static_cast<int>(prod / total);
            rem[i] = prod % total;
            given += out[i];
        }
        for (int k = given; k < seats; k++) {
            long best = -1;
            for (size_t i = 0; i < p.size(); i++) {
                if (!eligible[i]) continue;
                if (best < 0) {
                    best = static_cast<long>(i);
                    continue;
                }
                size_t b = static_cast<size_t>(best);
                bool win;
                if (rem[i] != rem[b]) win = rem[i] > rem[b];
                else if (p[i].votes != p[b].votes) win = p[i].votes > p[b].votes;
                else win = false;
                if (win) best = static_cast<long>(i);
            }
            out[static_cast<size_t>(best)]++;
            rem[static_cast<size_t>(best)] = -1;
        }
    }

    static void apply_floor(const std::vector<Party> &p, const std::vector<bool> &eligible, std::vector<int> &out) {
        std::vector<size_t> needy;
        for (size_t i = 0; i < p.size(); i++) {
            if (eligible[i] && out[i] == 0) needy.push_back(i);
        }
        /* order: more votes first, then earlier in the list */
        for (size_t i = 1; i < needy.size(); i++) {
            size_t v = needy[i];
            size_t j = i;
            while (j > 0 && (p[needy[j - 1]].votes < p[v].votes)) {
                needy[j] = needy[j - 1];
                j--;
            }
            needy[j] = v;
        }
        for (size_t n : needy) {
            long donor = -1;
            for (size_t i = 0; i < p.size(); i++) {
                if (out[i] < 2) continue;
                if (donor < 0) {
                    donor = static_cast<long>(i);
                    continue;
                }
                size_t d = static_cast<size_t>(donor);
                if (out[i] > out[d] || (out[i] == out[d] && (p[i].votes < p[d].votes || (p[i].votes == p[d].votes && i > d)))) donor = static_cast<long>(i);
            }
            if (donor < 0) return;
            out[static_cast<size_t>(donor)]--;
            out[n] = 1;
        }
    }

    std::vector<int> allocate(const std::vector<Party> &parties, int seats, const Options &opt) {
        if (seats < 0 || seats > 1000) throw std::invalid_argument("seats out of range");
        if (opt.threshold_permille < 0 || opt.threshold_permille > 1000) throw std::invalid_argument("threshold out of range");
        long long total = 0;
        for (const Party &p : parties) {
            if (p.votes < 0 || p.votes > 1000000000L) throw std::invalid_argument("votes out of range");
            total += p.votes;
        }
        if (seats > 0 && parties.empty()) throw std::invalid_argument("no parties");
        std::vector<int> out(parties.size(), 0);
        if (seats == 0 || total == 0) return out;
        std::vector<bool> eligible(parties.size(), false);
        long long eligible_total = 0;
        bool any = false;
        for (size_t i = 0; i < parties.size(); i++) {
            eligible[i] = static_cast<long long>(parties[i].votes) * 1000 >= static_cast<long long>(opt.threshold_permille) * total;
            if (eligible[i]) {
                eligible_total += parties[i].votes;
                any = true;
            }
        }
        if (!any) return out;
        switch (opt.method) {
        case Method::DHondt:
            divisor_method(parties, eligible, seats, 1, out);
            break;
        case Method::SainteLague:
            divisor_method(parties, eligible, seats, 2, out);
            break;
        case Method::Hamilton:
            hamilton(parties, eligible, seats, eligible_total, out);
            break;
        }
        if (opt.floor_one) apply_floor(parties, eligible, out);
        return out;
    }

    }  // namespace seatshare
''')

V4 = dd(r'''
    #include "harness.hpp"
    #include "seatshare.hpp"

    using namespace seatshare;

    int main() {
        h_init();
        std::vector<Party> parties = {{"Reeds", 340000}, {"Oaks", 280000}, {"Pines", 160000}, {"Ferns", 60000}};
        Options o;
        std::vector<int> r = allocate(parties, 7, o);
        CHECK_EQ(r.size(), 4u);
        int sum = 0;
        for (int x : r) sum += x;
        CHECK_EQ(sum, 7);
        CHECK_EQ(allocate(parties, 0, o)[0], 0);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <string>
    #include <vector>

    #include "harness.hpp"
    #include "seatshare.hpp"

    using namespace seatshare;

    struct Case {
        Method method;
        int threshold;
        bool floor_one;
        int seats;
        int n;
        int invalid;
        long votes[8];
        int expect[8];
    };

    static const Case CASES[] = {
        {Method::DHondt, 0, false, 7, 4, 0, {340000,280000,160000,60000}, {3,3,1,0}},
        {Method::SainteLague, 0, false, 7, 4, 0, {340000,280000,160000,60000}, {3,2,1,1}},
        {Method::Hamilton, 0, false, 7, 4, 0, {340000,280000,160000,60000}, {3,2,1,1}},
        {Method::DHondt, 0, false, 4, 3, 0, {100,100,100}, {2,1,1}},
        {Method::SainteLague, 0, false, 4, 3, 0, {100,100,100}, {2,1,1}},
        {Method::Hamilton, 0, false, 4, 3, 0, {100,100,100}, {2,1,1}},
        {Method::DHondt, 0, false, 5, 3, 0, {100,100,50}, {2,2,1}},
        {Method::SainteLague, 0, false, 5, 3, 0, {100,100,50}, {2,2,1}},
        {Method::Hamilton, 0, false, 5, 3, 0, {100,100,50}, {2,2,1}},
        {Method::DHondt, 0, false, 5, 3, 0, {100,50,100}, {2,1,2}},
        {Method::DHondt, 0, false, 3, 2, 0, {60,100}, {1,2}},
        {Method::DHondt, 0, false, 3, 2, 0, {100,60}, {2,1}},
        {Method::DHondt, 0, false, 5, 3, 0, {0,0,0}, {0,0,0}},
        {Method::DHondt, 0, false, 0, 3, 0, {0,0,0}, {0,0,0}},
        {Method::Hamilton, 0, false, 3, 1, 0, {5}, {3}},
        {Method::SainteLague, 0, false, 3, 2, 0, {0,7}, {0,3}},
        {Method::DHondt, 0, false, 0, 0, 0, {}, {}},
        {Method::DHondt, 0, false, 3, 0, 1, {}, {}},
        {Method::DHondt, 0, false, -1, 2, 1, {5,6}, {}},
        {Method::DHondt, 0, false, 1001, 2, 1, {5,6}, {}},
        {Method::DHondt, 0, false, 1000, 2, 0, {5,6}, {454,546}},
        {Method::DHondt, 0, false, 1, 2, 0, {5,6}, {0,1}},
        {Method::DHondt, 0, false, 3, 2, 1, {5,-6}, {}},
        {Method::DHondt, 0, false, 3, 2, 1, {5,1000000001}, {}},
        {Method::DHondt, 0, false, 3, 2, 0, {5,1000000000}, {0,3}},
        {Method::DHondt, -1, false, 3, 2, 1, {5,6}, {}},
        {Method::DHondt, 1001, false, 3, 2, 1, {5,6}, {}},
        {Method::DHondt, 1000, false, 3, 2, 0, {5,6}, {0,0}},
        {Method::DHondt, 500, false, 3, 2, 0, {5,5}, {2,1}},
        {Method::DHondt, 500, false, 3, 3, 0, {5,5,5}, {0,0,0}},
        {Method::DHondt, 500, false, 3, 3, 0, {10,5,5}, {3,0,0}},
        {Method::DHondt, 0, false, 8, 4, 0, {500,250,150,100}, {5,2,1,0}},
        {Method::Hamilton, 0, false, 8, 4, 0, {500,250,150,100}, {4,2,1,1}},
        {Method::DHondt, 50, false, 8, 4, 0, {500,250,150,100}, {5,2,1,0}},
        {Method::Hamilton, 50, false, 8, 4, 0, {500,250,150,100}, {4,2,1,1}},
        {Method::DHondt, 100, false, 8, 4, 0, {500,250,150,100}, {5,2,1,0}},
        {Method::Hamilton, 100, false, 8, 4, 0, {500,250,150,100}, {4,2,1,1}},
        {Method::DHondt, 250, false, 8, 4, 0, {500,250,150,100}, {6,2,0,0}},
        {Method::Hamilton, 250, false, 8, 4, 0, {500,250,150,100}, {5,3,0,0}},
        {Method::DHondt, 251, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::Hamilton, 251, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::DHondt, 300, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::Hamilton, 300, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::DHondt, 334, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::Hamilton, 334, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::DHondt, 500, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::Hamilton, 500, false, 8, 4, 0, {500,250,150,100}, {8,0,0,0}},
        {Method::DHondt, 1, false, 10, 4, 0, {1,1,1,997}, {0,0,0,10}},
        {Method::DHondt, 2, false, 10, 4, 0, {1,1,1,997}, {0,0,0,10}},
        {Method::DHondt, 10, false, 10, 2, 0, {10,990}, {0,10}},
        {Method::DHondt, 11, false, 10, 2, 0, {10,990}, {0,10}},
        {Method::SainteLague, 0, false, 1000, 3, 0, {1000000000,1000000000,1000000000}, {334,333,333}},
        {Method::Hamilton, 0, false, 1000, 3, 0, {1000000000,1,1}, {1000,0,0}},
        {Method::DHondt, 0, false, 999, 3, 0, {999999999,1000000000,1}, {499,500,0}},
        {Method::DHondt, 0, true, 10, 4, 0, {900,50,30,20}, {7,1,1,1}},
        {Method::Hamilton, 0, true, 10, 4, 0, {900,50,30,20}, {7,1,1,1}},
        {Method::DHondt, 0, true, 3, 4, 0, {900,50,30,20}, {1,1,1,0}},
        {Method::DHondt, 0, true, 2, 4, 0, {900,50,30,20}, {1,1,0,0}},
        {Method::DHondt, 0, true, 1, 4, 0, {900,50,30,20}, {1,0,0,0}},
        {Method::DHondt, 0, true, 6, 5, 0, {500,500,10,10,10}, {2,1,1,1,1}},
        {Method::SainteLague, 0, true, 7, 5, 0, {400,400,100,100,1}, {2,2,1,1,1}},
        {Method::Hamilton, 0, true, 4, 6, 0, {100,100,100,1,1,1}, {1,1,1,1,0,0}},
        {Method::DHondt, 150, false, 8, 7, 0, {1,1,2,50210,91815,11776,100000}, {0,0,0,2,3,0,3}},
        {Method::DHondt, 20, false, 2, 7, 0, {100,2,92,0,61,35,1}, {1,0,1,0,0,0,0}},
        {Method::DHondt, 20, false, 3, 4, 0, {0,0,0,0}, {0,0,0,0}},
        {Method::DHondt, 150, false, 21, 7, 0, {0,0,0,0,0,3,9}, {0,0,0,0,0,5,16}},
        {Method::DHondt, 150, false, 8, 3, 0, {0,1,1}, {0,4,4}},
        {Method::DHondt, 150, false, 10, 8, 0, {2,0,0,2,28,44,48,0}, {0,0,0,0,2,4,4,0}},
        {Method::DHondt, 150, false, 8, 8, 0, {1,2,100,100,1,50,97,0}, {0,0,3,3,0,0,2,0}},
        {Method::DHondt, 100, false, 5, 8, 0, {2,85,21,87,100,57,2,2}, {0,1,0,1,2,1,0,0}},
        {Method::DHondt, 50, false, 15, 3, 0, {999,999,0}, {8,7,0}},
        {Method::DHondt, 150, false, 40, 4, 0, {10,3,10,8}, {15,0,14,11}},
        {Method::DHondt, 150, false, 2, 5, 0, {0,9,3,48,90}, {0,0,0,1,1}},
        {Method::DHondt, 50, false, 12, 7, 0, {22578,1,100000,54810,2,2,100000}, {1,0,5,2,0,0,4}},
        {Method::DHondt, 20, false, 1, 8, 0, {1,1,1,1,1,1,1,1}, {1,0,0,0,0,0,0,0}},
        {Method::DHondt, 0, false, 12, 1, 0, {1}, {12}},
        {Method::DHondt, 50, false, 3, 7, 0, {25,2,0,26,2,0,0}, {1,0,0,2,0,0,0}},
        {Method::DHondt, 0, false, 3, 2, 0, {1,4}, {0,3}},
        {Method::DHondt, 0, false, 2, 1, 0, {828}, {2}},
        {Method::DHondt, 0, false, 7, 8, 0, {10,4,0,3,2,1,2,0}, {5,1,0,1,0,0,0,0}},
        {Method::DHondt, 0, true, 40, 2, 0, {0,21490}, {1,39}},
        {Method::DHondt, 150, true, 1, 1, 0, {1}, {1}},
        {Method::DHondt, 150, true, 1, 5, 0, {100000,22827,1,2,0}, {1,0,0,0,0}},
        {Method::DHondt, 0, true, 12, 4, 0, {2,2,2,2}, {3,3,3,3}},
        {Method::DHondt, 100, true, 5, 3, 0, {1,1,1}, {2,2,1}},
        {Method::DHondt, 0, true, 40, 2, 0, {0,99999}, {1,39}},
        {Method::DHondt, 0, true, 21, 3, 0, {4,4,4}, {7,7,7}},
        {Method::DHondt, 50, true, 7, 8, 0, {0,0,0,0,0,72,99,0}, {0,0,0,0,0,3,4,0}},
        {Method::DHondt, 0, true, 1, 5, 0, {0,0,0,0,0}, {0,0,0,0,0}},
        {Method::DHondt, 20, true, 8, 4, 0, {2,100,0,0}, {0,8,0,0}},
        {Method::DHondt, 50, true, 12, 7, 0, {2,2,2,2,2,2,2}, {2,2,2,2,2,1,1}},
        {Method::DHondt, 150, true, 12, 1, 0, {78}, {12}},
        {Method::DHondt, 0, true, 10, 8, 0, {42060,42060,42060,42060,42060,42060,42060,42060}, {2,2,1,1,1,1,1,1}},
        {Method::DHondt, 0, true, 15, 7, 0, {0,9,0,0,9,0,3}, {1,5,1,1,4,1,2}},
        {Method::DHondt, 0, true, 15, 5, 0, {100,100,100,100,100}, {3,3,3,3,3}},
        {Method::DHondt, 50, true, 10, 8, 0, {1000,1000,1000,1000,1000,1000,1000,1000}, {2,2,1,1,1,1,1,1}},
        {Method::DHondt, 150, true, 2, 2, 0, {7,7}, {1,1}},
        {Method::DHondt, 150, true, 1, 4, 0, {0,0,0,0}, {0,0,0,0}},
        {Method::SainteLague, 100, false, 8, 4, 0, {342,342,342,342}, {2,2,2,2}},
        {Method::SainteLague, 0, false, 7, 4, 0, {67,55,2,100}, {2,2,0,3}},
        {Method::SainteLague, 50, false, 40, 1, 0, {157}, {40}},
        {Method::SainteLague, 100, false, 3, 5, 0, {0,0,0,0,0}, {0,0,0,0,0}},
        {Method::SainteLague, 0, false, 10, 2, 0, {56196,2}, {10,0}},
        {Method::SainteLague, 0, false, 10, 2, 0, {0,0}, {0,0}},
        {Method::SainteLague, 50, false, 10, 4, 0, {0,0,9,9}, {0,0,5,5}},
        {Method::SainteLague, 0, false, 12, 3, 0, {1000,1000,1000}, {4,4,4}},
        {Method::SainteLague, 0, false, 12, 4, 0, {0,1,0,1}, {0,6,0,6}},
        {Method::SainteLague, 150, false, 8, 8, 0, {0,0,1,1,16461,0,2,0}, {0,0,0,0,8,0,0,0}},
        {Method::SainteLague, 0, false, 21, 8, 0, {2,100,43,1,100,23,0,50}, {0,7,3,0,7,1,0,3}},
        {Method::SainteLague, 100, false, 12, 8, 0, {0,1,3,2,2,2,0,3}, {0,0,3,2,2,2,0,3}},
        {Method::SainteLague, 0, false, 15, 6, 0, {1,0,52,1,28,16}, {0,0,8,0,4,3}},
        {Method::SainteLague, 100, false, 5, 6, 0, {0,0,0,0,0,0}, {0,0,0,0,0,0}},
        {Method::SainteLague, 0, false, 21, 5, 0, {0,85512,56184,0,0}, {0,13,8,0,0}},
        {Method::SainteLague, 150, false, 12, 3, 0, {1,89998,78244}, {0,6,6}},
        {Method::SainteLague, 150, false, 8, 2, 0, {4386,2}, {8,0}},
        {Method::SainteLague, 0, false, 1, 1, 0, {16}, {1}},
        {Method::SainteLague, 0, true, 21, 3, 0, {2,2,2}, {7,7,7}},
        {Method::SainteLague, 150, true, 1, 4, 0, {0,0,0,9}, {0,0,0,1}},
        {Method::SainteLague, 0, true, 1, 4, 0, {0,99999,99999,39531}, {0,1,0,0}},
        {Method::SainteLague, 0, true, 1, 2, 0, {0,1000}, {0,1}},
        {Method::SainteLague, 150, true, 2, 6, 0, {2,2,2,2,2,2}, {1,1,0,0,0,0}},
        {Method::SainteLague, 150, true, 7, 2, 0, {15,15}, {4,3}},
        {Method::SainteLague, 100, true, 7, 7, 0, {0,39,99,99,0,0,0}, {0,1,3,3,0,0,0}},
        {Method::SainteLague, 0, true, 10, 6, 0, {1,2,0,0,1,653}, {1,1,1,1,1,5}},
        {Method::SainteLague, 100, true, 1, 3, 0, {55,59,1}, {0,1,0}},
        {Method::SainteLague, 0, true, 1, 4, 0, {1000,103,0,1}, {1,0,0,0}},
        {Method::SainteLague, 150, true, 7, 2, 0, {0,0}, {0,0}},
        {Method::SainteLague, 100, true, 1, 6, 0, {179,614,1,2,2,2}, {0,1,0,0,0,0}},
        {Method::SainteLague, 0, true, 1, 4, 0, {66,100,31,35}, {0,1,0,0}},
        {Method::SainteLague, 50, true, 12, 8, 0, {0,0,0,3,9,9,6,0}, {0,0,0,1,4,4,3,0}},
        {Method::SainteLague, 0, true, 10, 6, 0, {32127,0,0,0,16431,99999}, {2,1,1,1,1,4}},
        {Method::SainteLague, 50, true, 21, 6, 0, {1,2,10,6,2,1}, {0,2,11,6,2,0}},
        {Method::SainteLague, 0, true, 3, 2, 0, {1,100000}, {1,2}},
        {Method::SainteLague, 0, true, 21, 5, 0, {2,0,3,5,2}, {4,1,5,8,3}},
        {Method::Hamilton, 50, false, 21, 6, 0, {4,0,2,86,75,0}, {0,0,0,11,10,0}},
        {Method::Hamilton, 150, false, 10, 6, 0, {0,0,1,100,1,30}, {0,0,0,8,0,2}},
        {Method::Hamilton, 0, false, 12, 8, 0, {1000,1,0,189,706,215,2,0}, {6,0,0,1,4,1,0,0}},
        {Method::Hamilton, 20, false, 3, 4, 0, {1,9,10,6}, {0,1,1,1}},
        {Method::Hamilton, 20, false, 5, 3, 0, {19,19,19}, {2,2,1}},
        {Method::Hamilton, 20, false, 2, 1, 0, {55937}, {2}},
        {Method::Hamilton, 150, false, 1, 7, 0, {1,32528,1,1,100000,2,8331}, {0,0,0,0,1,0,0}},
        {Method::Hamilton, 50, false, 8, 4, 0, {100000,100000,100000,100000}, {2,2,2,2}},
        {Method::Hamilton, 20, false, 21, 7, 0, {10,10,10,10,10,10,10}, {3,3,3,3,3,3,3}},
        {Method::Hamilton, 150, false, 5, 7, 0, {0,0,9,0,0,9,0}, {0,0,3,0,0,2,0}},
        {Method::Hamilton, 0, false, 7, 4, 0, {1000,1,2,1}, {7,0,0,0}},
        {Method::Hamilton, 0, false, 15, 8, 0, {10,0,1,2,9,10,6,1}, {4,0,0,1,4,4,2,0}},
        {Method::Hamilton, 100, false, 8, 7, 0, {2,1,0,2,0,0,1}, {3,1,0,3,0,0,1}},
        {Method::Hamilton, 150, false, 21, 2, 0, {2,2}, {11,10}},
        {Method::Hamilton, 0, false, 12, 8, 0, {100,2,100,0,0,2,58,100}, {4,0,3,0,0,0,2,3}},
        {Method::Hamilton, 50, false, 3, 4, 0, {2,0,2,1}, {1,0,1,1}},
        {Method::Hamilton, 100, false, 5, 1, 0, {0}, {0}},
        {Method::Hamilton, 0, false, 2, 7, 0, {7,0,42,100,25,29,95}, {0,0,0,1,0,0,1}},
        {Method::Hamilton, 20, true, 40, 1, 0, {0}, {0}},
        {Method::Hamilton, 20, true, 5, 3, 0, {0,1,57}, {0,0,5}},
        {Method::Hamilton, 20, true, 15, 5, 0, {2,2,2,2,2}, {3,3,3,3,3}},
        {Method::Hamilton, 20, true, 2, 5, 0, {2,1,2,0,100000}, {0,0,0,0,2}},
        {Method::Hamilton, 0, true, 21, 3, 0, {60511,0,3590}, {19,1,1}},
        {Method::Hamilton, 100, true, 5, 1, 0, {1}, {5}},
        {Method::Hamilton, 0, true, 15, 5, 0, {596,0,1,1000,1}, {6,1,1,6,1}},
        {Method::Hamilton, 50, true, 2, 6, 0, {0,2,1,100,100,2}, {0,0,0,1,1,0}},
        {Method::Hamilton, 50, true, 5, 7, 0, {0,0,1,2,1,8,8}, {0,0,1,1,1,1,1}},
        {Method::Hamilton, 0, true, 21, 8, 0, {0,1,2,174,0,2,0,0}, {1,1,1,14,1,1,1,1}},
        {Method::Hamilton, 100, true, 5, 7, 0, {9,9,9,9,9,9,9}, {1,1,1,1,1,0,0}},
        {Method::Hamilton, 20, true, 3, 6, 0, {0,1000,2,1,652,707}, {0,1,0,0,1,1}},
        {Method::Hamilton, 150, true, 8, 2, 0, {2,3}, {3,5}},
        {Method::Hamilton, 0, true, 8, 6, 0, {1,0,10,9,10,1}, {1,1,2,1,2,1}},
        {Method::Hamilton, 20, true, 7, 2, 0, {87,0}, {7,0}},
        {Method::Hamilton, 50, true, 10, 1, 0, {72}, {10}},
        {Method::Hamilton, 0, true, 5, 3, 0, {1,2,56955}, {1,1,3}},
        {Method::Hamilton, 0, true, 5, 7, 0, {1,4,10,0,2,0,1}, {1,1,1,0,1,0,1}},
    };

    static std::string show_case(size_t i, const Case &c) {
        std::string s = "case " + std::to_string(i) + " [" + (c.method == Method::DHondt ? "dhondt" : c.method == Method::SainteLague ? "sainte-lague" : "hamilton") +
                        " seats=" + std::to_string(c.seats) + " thr=" + std::to_string(c.threshold) + (c.floor_one ? " floor" : "") + " votes=";
        for (int k = 0; k < c.n; k++) s += (k ? "," : "") + std::to_string(c.votes[k]);
        return s + "]";
    }

    static void test_cases() {
        for (size_t i = 0; i < sizeof CASES / sizeof CASES[0]; i++) {
            const Case &c = CASES[i];
            std::vector<Party> parties;
            for (int k = 0; k < c.n; k++) parties.push_back(Party{"p" + std::to_string(k), c.votes[k]});
            Options o;
            o.method = c.method;
            o.threshold_permille = c.threshold;
            o.floor_one = c.floor_one;
            std::string ctx = show_case(i, c);
            if (c.invalid) {
                bool threw = false;
                try {
                    allocate(parties, c.seats, o);
                } catch (const std::invalid_argument &) {
                    threw = true;
                }
                CHECK_EQ_CTX(ctx, threw, true);
                continue;
            }
            std::vector<int> got = allocate(parties, c.seats, o);
            CHECK_EQ_CTX(ctx, got.size(), static_cast<size_t>(c.n));
            for (int k = 0; k < c.n && k < static_cast<int>(got.size()); k++) {
                CHECK_EQ_CTX(ctx + " party " + std::to_string(k), got[static_cast<size_t>(k)], c.expect[k]);
            }
        }
    }

    static void test_defaults() {
        std::vector<Party> parties = {{"a", 100}, {"b", 100}, {"c", 100}};
        Options o;
        CHECK(o.method == Method::DHondt);
        CHECK_EQ(o.threshold_permille, 0);
        CHECK(!o.floor_one);
        std::vector<int> r = allocate(parties, 4, o);
        CHECK_EQ(r[0], 2);
        CHECK_EQ(r[1], 1);
        CHECK_EQ(r[2], 1);
    }

    static void test_names_irrelevant() {
        std::vector<Party> a = {{"zebra", 30}, {"apple", 30}, {"", 20}};
        std::vector<Party> b = {{"x", 30}, {"y", 30}, {"z", 20}};
        Options o;
        for (Method m : {Method::DHondt, Method::SainteLague, Method::Hamilton}) {
            o.method = m;
            CHECK_EQ(allocate(a, 5, o) == allocate(b, 5, o), true);
        }
    }

    int main() {
        h_init();
        test_cases();
        test_defaults();
        test_names_irrelevant();
        return h_report();
    }
''')

LIB = Lib(
    name="seatshare", lang="cpp", title="the seatshare apportionment library",
    blurb="The guild's election software turns member votes into council seats with seatshare, under whichever counting method the charter currently prescribes.",
    files={"README.md": README1, "include/seatshare.hpp": F2, "src/seatshare.cpp": F3},
    visible_tests={"tests/test_main.cpp": V4, "tests/harness.hpp": _lang3.CPP_HARNESS},
    hidden_tests={"tests/test_main.cpp": H5},
    mutate=["src/seatshare.cpp"], difficulty=3, tags=["voting", "apportionment", "ties"],
    verify=_lang3.CPP_VERIFY,
)

_lang3.add(LIB, n=8)
