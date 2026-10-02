"""Generation-checked handle pool (c++): slot reuse in LIFO order, stale-handle detection, wrapping 16-bit generations; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # handlepool

    A pool of strings addressed by *handles* instead of pointers. A handle stays valid until its object is destroyed; after that it is
    **stale** even when the slot behind it has been reused for another object.

        struct Handle { uint16_t index; uint16_t gen; };

    `{0, 0}` is the null handle: it is never valid (generations start at 1).

    ## Slots and generations

    * The pool owns slots numbered `0, 1, 2, ...`. A slot is *live* (holds an object) or *free*. At most `Pool::kMaxSlots` (4096) slots
      exist.
    * Every slot has a generation, a `uint16_t` that is **1** when the slot is first created. A handle is valid exactly when its `index`
      names an existing live slot and its `gen` equals that slot's generation.
    * Destroying an object increments its slot's generation, wrapping `65535 -> 1` (**never 0**), and puts the slot on a *free stack*.

    ## API (`include/handlepool.hpp`, namespace `hpool`)

    * `Handle Pool::create(std::string value)` stores the value and returns its handle. The slot used is the **most recently freed** one
      (top of the free stack), and if none is free a new slot with the next index (`capacity()`) is created. Throws `std::length_error`
      (changing nothing) when `size() == kMaxSlots`.
    * `bool Pool::destroy(Handle h)`: destroys the object when `h` is valid and returns true; for a stale, null or out-of-range handle it
      returns false and changes nothing.
    * `bool Pool::alive(Handle h) const`, `const std::string *Pool::get(Handle h) const` and `std::string *Pool::get(Handle h)`:
      whether the handle is valid, and a pointer to the object (nullptr for an invalid handle).
    * `size_t Pool::size() const`: live objects. `size_t Pool::capacity() const`: slots ever created.
    * `std::vector<Handle> Pool::live_handles() const`: the handles of all live objects, in slot order.
    * `void Pool::clear()` destroys every live object in slot order, exactly as if `destroy` were called on each live handle in turn
      (so generations advance and the free stack ends with the highest slot on top). Capacity does not shrink.

    ## Packing

    * `uint32_t pack(Handle h)` is `(gen << 16) | index`; `Handle unpack(uint32_t raw)` is its inverse.
    * `bool same(Handle a, Handle b)`: both fields equal.
''')

F2 = dd(r'''
    #ifndef HANDLEPOOL_HPP
    #define HANDLEPOOL_HPP

    #include <cstddef>
    #include <cstdint>
    #include <stdexcept>
    #include <string>
    #include <vector>

    namespace hpool {

    struct Handle {
        uint16_t index;
        uint16_t gen;
    };

    uint32_t pack(Handle h);
    Handle unpack(uint32_t raw);
    bool same(Handle a, Handle b);

    class Pool {
    public:
        static constexpr size_t kMaxSlots = 4096;

        Handle create(std::string value);
        bool destroy(Handle h);
        bool alive(Handle h) const;
        const std::string *get(Handle h) const;
        std::string *get(Handle h);
        size_t size() const;
        size_t capacity() const;
        std::vector<Handle> live_handles() const;
        void clear();

    private:
        struct Slot {
            std::string value;
            uint16_t gen;
            bool live;
        };
        std::vector<Slot> slots_;
        std::vector<uint16_t> free_;
        size_t live_ = 0;
    };

    }  // namespace hpool

    #endif
''')

F3 = dd(r'''
    #include "handlepool.hpp"

    namespace hpool {

    uint32_t pack(Handle h) { return (static_cast<uint32_t>(h.gen) << 16) | h.index; }

    Handle unpack(uint32_t raw) { return Handle{static_cast<uint16_t>(raw & 0xFFFFu), static_cast<uint16_t>(raw >> 16)}; }

    bool same(Handle a, Handle b) { return a.index == b.index && a.gen == b.gen; }

    Handle Pool::create(std::string value) {
        if (live_ >= kMaxSlots) throw std::length_error("handle pool is full");
        uint16_t at;
        if (!free_.empty()) {
            at = free_.back();
            free_.pop_back();
        } else {
            at = static_cast<uint16_t>(slots_.size());
            slots_.push_back(Slot{std::string(), 1, false});
        }
        Slot &s = slots_[at];
        s.value = std::move(value);
        s.live = true;
        live_++;
        return Handle{at, s.gen};
    }

    bool Pool::alive(Handle h) const {
        if (h.gen == 0 || h.index >= slots_.size()) return false;
        const Slot &s = slots_[h.index];
        return s.live && s.gen == h.gen;
    }

    bool Pool::destroy(Handle h) {
        if (!alive(h)) return false;
        Slot &s = slots_[h.index];
        s.live = false;
        s.value.clear();
        s.gen = s.gen == 65535 ? 1 : static_cast<uint16_t>(s.gen + 1);
        free_.push_back(h.index);
        live_--;
        return true;
    }

    const std::string *Pool::get(Handle h) const { return alive(h) ? &slots_[h.index].value : nullptr; }

    std::string *Pool::get(Handle h) { return alive(h) ? &slots_[h.index].value : nullptr; }

    size_t Pool::size() const { return live_; }

    size_t Pool::capacity() const { return slots_.size(); }

    std::vector<Handle> Pool::live_handles() const {
        std::vector<Handle> out;
        for (size_t i = 0; i < slots_.size(); i++) {
            if (slots_[i].live) out.push_back(Handle{static_cast<uint16_t>(i), slots_[i].gen});
        }
        return out;
    }

    void Pool::clear() {
        for (size_t i = 0; i < slots_.size(); i++) {
            if (slots_[i].live) destroy(Handle{static_cast<uint16_t>(i), slots_[i].gen});
        }
    }

    }  // namespace hpool
''')

V4 = dd(r'''
    #include "handlepool.hpp"
    #include "harness.hpp"

    using namespace hpool;

    int main() {
        h_init();
        Pool p;
        Handle a = p.create("alpha");
        Handle b = p.create("beta");
        CHECK_EQ(a.index, 0);
        CHECK_EQ(a.gen, 1);
        CHECK_EQ(b.index, 1);
        CHECK_EQ(*p.get(b), std::string("beta"));
        CHECK(p.destroy(a));
        CHECK(!p.alive(a));
        CHECK_EQ(p.size(), 1u);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <map>
    #include <string>
    #include <vector>

    #include "handlepool.hpp"
    #include "harness.hpp"

    using namespace hpool;

    static void test_basic() {
        Pool p;
        CHECK_EQ(p.size(), 0u);
        CHECK_EQ(p.capacity(), 0u);
        Handle a = p.create("alpha");
        Handle b = p.create("beta");
        Handle c = p.create("gamma");
        CHECK_EQ(a.index, 0);
        CHECK_EQ(a.gen, 1);
        CHECK_EQ(b.index, 1);
        CHECK_EQ(b.gen, 1);
        CHECK_EQ(c.index, 2);
        CHECK_EQ(p.size(), 3u);
        CHECK_EQ(p.capacity(), 3u);
        CHECK_EQ(*p.get(a), std::string("alpha"));
        CHECK_EQ(*p.get(c), std::string("gamma"));
        *p.get(b) = "BETA";
        const Pool &cp = p;
        CHECK_EQ(*cp.get(b), std::string("BETA"));
        CHECK(p.alive(a) && p.alive(b) && p.alive(c));
        CHECK(p.destroy(b));
        CHECK(!p.alive(b));
        CHECK(p.get(b) == nullptr);
        CHECK(cp.get(b) == nullptr);
        CHECK(!p.destroy(b));
        CHECK_EQ(p.size(), 2u);
        CHECK_EQ(p.capacity(), 3u);
        /* the slot is reused with the next generation, the old handle stays stale */
        Handle d = p.create("delta");
        CHECK_EQ(d.index, 1);
        CHECK_EQ(d.gen, 2);
        CHECK(!p.alive(b));
        CHECK(p.alive(d));
        CHECK(p.get(b) == nullptr);
        CHECK_EQ(*p.get(d), std::string("delta"));
        CHECK_EQ(p.capacity(), 3u);
    }

    static void test_invalid_handles() {
        Pool p;
        Handle null_h{0, 0};
        CHECK(!p.alive(null_h));
        CHECK(!p.destroy(null_h));
        CHECK(p.get(null_h) == nullptr);
        Handle a = p.create("a");
        CHECK(p.alive(a));
        CHECK(!p.alive(null_h));
        CHECK(!p.alive(Handle{0, 0}));
        CHECK(!p.alive(Handle{0, 2}));
        CHECK(!p.alive(Handle{1, 1}));
        CHECK(!p.alive(Handle{4095, 1}));
        CHECK(!p.alive(Handle{65535, 65535}));
        CHECK(!p.destroy(Handle{1, 1}));
        CHECK(!p.destroy(Handle{0, 2}));
        CHECK(p.get(Handle{7, 1}) == nullptr);
        CHECK_EQ(p.size(), 1u);
        CHECK(p.alive(a));
    }

    static void test_free_stack_is_lifo() {
        Pool p;
        Handle h[5];
        for (int i = 0; i < 5; i++) h[i] = p.create("v" + std::to_string(i));
        p.destroy(h[1]);
        p.destroy(h[3]);
        p.destroy(h[0]);
        /* freed order 1, 3, 0: the most recent is reused first */
        Handle x = p.create("x");
        Handle y = p.create("y");
        Handle z = p.create("z");
        Handle w = p.create("w");
        CHECK_EQ(x.index, 0);
        CHECK_EQ(y.index, 3);
        CHECK_EQ(z.index, 1);
        CHECK_EQ(w.index, 5);
        CHECK_EQ(x.gen, 2);
        CHECK_EQ(y.gen, 2);
        CHECK_EQ(z.gen, 2);
        CHECK_EQ(w.gen, 1);
        CHECK_EQ(p.capacity(), 6u);
        CHECK_EQ(p.size(), 6u);
        std::vector<Handle> live = p.live_handles();
        CHECK_EQ(live.size(), 6u);
        for (size_t i = 0; i < live.size(); i++) CHECK_EQ(live[i].index, i);
        CHECK_EQ(live[0].gen, 2);
        CHECK_EQ(live[1].gen, 2);
        CHECK_EQ(live[2].gen, 1);
        CHECK_EQ(live[3].gen, 2);
        CHECK_EQ(live[4].gen, 1);
        CHECK_EQ(live[5].gen, 1);
    }

    static void test_destroy_clears_value() {
        Pool p;
        Handle a = p.create("payload");
        p.destroy(a);
        Handle b = p.create("");
        CHECK_EQ(b.index, 0);
        CHECK_EQ(*p.get(b), std::string(""));
        Handle c = p.create("kept");
        CHECK_EQ(*p.get(c), std::string("kept"));
        CHECK_EQ(*p.get(b), std::string(""));
    }

    static void test_generation_wrap() {
        Pool p;
        Handle h = p.create("first");
        CHECK_EQ(h.gen, 1);
        for (int i = 1; i <= 65534; i++) {
            CHECK(p.destroy(h));
            h = p.create("again");
            if (i < 5 || i > 65530) CHECK_EQ(h.gen, i + 1);
            CHECK_EQ(h.index, 0);
        }
        CHECK_EQ(h.gen, 65535);
        Handle old = h;
        CHECK(p.destroy(h));
        h = p.create("wrapped");
        CHECK_EQ(h.gen, 1);   /* 0 is skipped */
        CHECK(!p.alive(old));
        CHECK(p.alive(h));
        CHECK(!p.alive(Handle{0, 0}));
        CHECK(p.destroy(h));
        h = p.create("second lap");
        CHECK_EQ(h.gen, 2);
        CHECK_EQ(p.capacity(), 1u);
    }

    static void test_capacity_limit() {
        Pool p;
        std::vector<Handle> hs;
        for (size_t i = 0; i < Pool::kMaxSlots; i++) hs.push_back(p.create(std::to_string(i)));
        CHECK_EQ(p.size(), Pool::kMaxSlots);
        CHECK_EQ(p.capacity(), Pool::kMaxSlots);
        CHECK_EQ(hs.back().index, 4095);
        CHECK_THROWS(p.create("one too many"), std::length_error);
        CHECK_EQ(p.size(), Pool::kMaxSlots);
        CHECK_EQ(p.capacity(), Pool::kMaxSlots);
        CHECK(p.destroy(hs[100]));
        Handle again = p.create("fits now");
        CHECK_EQ(again.index, 100);
        CHECK_EQ(again.gen, 2);
        CHECK_THROWS(p.create("full again"), std::length_error);
        CHECK_EQ(*p.get(hs[4095]), std::string("4095"));
        CHECK_EQ(*p.get(hs[0]), std::string("0"));
    }

    static void test_clear() {
        Pool p;
        Handle a = p.create("a");
        Handle b = p.create("b");
        Handle c = p.create("c");
        Handle d = p.create("d");
        p.destroy(b);
        p.clear();
        CHECK_EQ(p.size(), 0u);
        CHECK_EQ(p.capacity(), 4u);
        CHECK(!p.alive(a) && !p.alive(c) && !p.alive(d));
        CHECK_EQ(p.live_handles().size(), 0u);
        /* cleared in slot order: freed 0, 2, 3 after the earlier 1 -> reuse starts at the highest slot */
        Handle n1 = p.create("n1");
        Handle n2 = p.create("n2");
        Handle n3 = p.create("n3");
        Handle n4 = p.create("n4");
        CHECK_EQ(n1.index, 3);
        CHECK_EQ(n2.index, 2);
        CHECK_EQ(n3.index, 0);
        CHECK_EQ(n4.index, 1);
        CHECK_EQ(n1.gen, 2);
        CHECK_EQ(n2.gen, 2);
        CHECK_EQ(n3.gen, 2);
        CHECK_EQ(n4.gen, 2);   /* slot 1 was already free (destroyed once) before the clear */
        Pool q;
        q.clear();
        CHECK_EQ(q.size(), 0u);
        CHECK_EQ(q.capacity(), 0u);
    }

    static void test_pack() {
        CHECK_EQ(pack(Handle{0, 0}), 0u);
        CHECK_EQ(pack(Handle{5, 1}), 0x10005u);
        CHECK_EQ(pack(Handle{0xFFFF, 0xFFFF}), 0xFFFFFFFFu);
        CHECK_EQ(pack(Handle{0x1234, 0xABCD}), 0xABCD1234u);
        Handle h = unpack(0xABCD1234u);
        CHECK_EQ(h.index, 0x1234);
        CHECK_EQ(h.gen, 0xABCD);
        CHECK(same(unpack(pack(Handle{77, 9})), Handle{77, 9}));
        CHECK(same(Handle{1, 2}, Handle{1, 2}));
        CHECK(!same(Handle{1, 2}, Handle{2, 2}));
        CHECK(!same(Handle{1, 2}, Handle{1, 3}));
        CHECK(!same(Handle{1, 2}, Handle{2, 1}));
    }

    static unsigned next_rand(unsigned &s) {
        s = s * 1664525u + 1013904223u;
        return s >> 8;
    }

    /* an independent model of the pool, driven by a pseudo-random script */
    static void test_model() {
        Pool p;
        unsigned seed = 12345;
        struct M { bool live; uint16_t gen; std::string v; };
        std::vector<M> model;
        std::vector<uint16_t> freeStack;
        std::vector<Handle> issued;
        for (int step = 0; step < 6000; step++) {
            unsigned r = next_rand(seed) % 100;
            if (r < 45 && p.size() < 200) {
                std::string v = "v" + std::to_string(step);
                uint16_t at;
                if (!freeStack.empty()) { at = freeStack.back(); freeStack.pop_back(); }
                else { at = static_cast<uint16_t>(model.size()); model.push_back(M{false, 1, ""}); }
                model[at].live = true;
                model[at].v = v;
                Handle h = p.create(v);
                CHECK_EQ(h.index, at);
                CHECK_EQ(h.gen, model[at].gen);
                issued.push_back(h);
            } else if (r < 85 && !issued.empty()) {
                Handle h = issued[next_rand(seed) % issued.size()];
                bool expect = h.index < model.size() && model[h.index].live && model[h.index].gen == h.gen;
                CHECK_EQ(p.alive(h), expect);
                CHECK_EQ(p.destroy(h), expect);
                if (expect) {
                    model[h.index].live = false;
                    model[h.index].gen = model[h.index].gen == 65535 ? 1 : model[h.index].gen + 1;
                    freeStack.push_back(h.index);
                }
                CHECK(!p.alive(h));
            } else if (!issued.empty()) {
                Handle h = issued[next_rand(seed) % issued.size()];
                bool expect = h.index < model.size() && model[h.index].live && model[h.index].gen == h.gen;
                const std::string *s = p.get(h);
                CHECK_EQ(s != nullptr, expect);
                if (expect && s) CHECK_EQ(*s, model[h.index].v);
            }
            if (step % 500 == 499) {
                size_t live = 0;
                for (const M &m : model) live += m.live ? 1 : 0;
                CHECK_EQ(p.size(), live);
                CHECK_EQ(p.capacity(), model.size());
                std::vector<Handle> lh = p.live_handles();
                CHECK_EQ(lh.size(), live);
                size_t k = 0;
                for (size_t i = 0; i < model.size(); i++) {
                    if (!model[i].live) continue;
                    CHECK_EQ(lh[k].index, i);
                    CHECK_EQ(lh[k].gen, model[i].gen);
                    k++;
                }
            }
        }
    }

    int main() {
        h_init();
        test_basic();
        test_invalid_handles();
        test_free_stack_is_lifo();
        test_destroy_clears_value();
        test_generation_wrap();
        test_capacity_limit();
        test_clear();
        test_pack();
        test_model();
        return h_report();
    }
''')

LIB = Lib(
    name="handlepool", lang="cpp", title="the handlepool container",
    blurb="The game server's entity store hands out handles to its objects and must reject a handle whose object has been destroyed, even when its slot was reused.",
    files={"README.md": README1, "include/handlepool.hpp": F2, "src/handlepool.cpp": F3},
    visible_tests={"tests/test_main.cpp": V4, "tests/harness.hpp": _lang3.CPP_HARNESS},
    hidden_tests={"tests/test_main.cpp": H5},
    mutate=["src/handlepool.cpp"], difficulty=2, tags=["handles", "generations", "containers"],
    verify=_lang3.CPP_VERIFY,
)

_lang3.add(LIB, n=8)
