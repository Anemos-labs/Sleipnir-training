"""turnstile: a scripted door-access controller."""
import re
import sys

import config as C
import hours as H
from venue import OUTSIDE, Badge, Door, Venue, Zone, stamp

NAME = re.compile(r"^[a-z][a-z0-9-]{0,11}$")
NUMBER = re.compile(r"^(0|[1-9][0-9]{0,4})$")


class Bad(Exception):
    pass


def number(text, lo, hi, what):
    if not NUMBER.match(text) or not lo <= int(text) <= hi:
        raise Bad("bad %s '%s'" % (what, text))
    return int(text)


def name(text):
    if not NAME.match(text):
        raise Bad("bad name '%s'" % text)
    return text


class Script:
    def __init__(self):
        self.v = Venue()
        self.out = []
        self.errors = 0

    def say(self, line):
        self.out.append(line)

    # -- definitions
    def zone(self, a):
        usage = Bad("usage: zone NAME [level N] [cap N] [hours SPEC]")
        if not a or len(a) % 2 == 0:
            raise usage
        opts = {}
        for key, val in zip(a[1::2], a[2::2]):
            if key not in ("level", "cap", "hours") or key in opts:
                raise usage
            opts[key] = val
        zid = name(a[0])
        if zid == OUTSIDE:
            raise Bad("'outside' is reserved")
        if zid in self.v.zones:
            raise Bad("zone '%s' exists" % zid)
        level, cap, windows = 0, 0, None
        for key in a[1::2]:
            val = opts[key]
            if key == "level":
                level = number(val, 0, 9, "level")
            elif key == "cap":
                cap = number(val, 1, 99, "cap")
            else:
                windows = H.parse(val)
                if windows is None:
                    raise Bad("bad hours '%s'" % val)
        self.v.zones[zid] = Zone(zid, level, cap, windows)

    def door(self, a):
        if len(a) != 3:
            raise Bad("usage: door ID A B")
        did = name(a[0])
        if did in self.v.doors:
            raise Bad("door '%s' exists" % did)
        for z in a[1:]:
            if z != OUTSIDE and z not in self.v.zones:
                raise Bad("unknown zone '%s'" % z)
        if a[2] == OUTSIDE:
            raise Bad("'outside' can only be the outer side")
        if a[1] == a[2]:
            raise Bad("door '%s' joins a zone to itself" % did)
        self.v.doors[did] = Door(did, a[1], a[2])

    def badge(self, a):
        usage = Bad("usage: badge ID level N [expires in MINUTES]")
        if len(a) not in (3, 6) or a[1] != "level" or (len(a) == 6 and (a[3] != "expires" or a[4] != "in")):
            raise usage
        bid = name(a[0])
        if bid in self.v.badges:
            raise Bad("badge '%s' exists" % bid)
        level = number(a[2], 0, 9, "level")
        expires = None
        if len(a) == 6:
            expires = self.v.now + number(a[5], 1, 99999, "expiry")
        self.v.badges[bid] = Badge(bid, level, expires)

    # -- the clock and the doors
    def at(self, a):
        v = self.v
        if len(a) == 1 and a[0].startswith("+"):
            if not NUMBER.match(a[0][1:]) or not 1 <= int(a[0][1:]) <= 10080:
                raise Bad("bad time '%s'" % a[0])
            t = v.now + int(a[0][1:])
        elif len(a) == 2:
            if a[0] not in H.DAYS:
                raise Bad("bad day '%s'" % a[0])
            tod = H.clock(a[1])
            if tod is None:
                raise Bad("bad time '%s'" % a[1])
            t = v.next_at(H.DAYS.index(a[0]), tod)
        else:
            raise Bad("usage: at DAY HH:MM | at +MINUTES")
        v.set_clock(t, self.out)

    def lockdown(self, a):
        if len(a) != 2 or a[1] not in ("on", "off"):
            raise Bad("usage: lockdown ZONE on|off")
        if a[0] not in self.v.zones:
            raise Bad("unknown zone '%s'" % a[0])
        self.v.zones[a[0]].locked = a[1] == "on"
        self.say("[%s] lockdown %s %s" % (stamp(self.v.now), a[0], a[1]))

    def swipe(self, a):
        v = self.v
        form = "usage: swipe BADGE DOOR in|out" + (" [with BADGE]" if C.ESCORT else "")
        if len(a) not in (3, 5) or a[2] not in ("in", "out"):
            raise Bad(form)
        if len(a) == 5 and not (C.ESCORT and a[2] == "in" and a[3] == "with"):
            raise Bad(form)
        if a[0] not in v.badges:
            raise Bad("unknown badge '%s'" % a[0])
        if a[1] not in v.doors:
            raise Bad("unknown door '%s'" % a[1])
        escort = None
        if len(a) == 5:
            if a[4] not in v.badges:
                raise Bad("unknown badge '%s'" % a[4])
            if a[4] == a[0]:
                raise Bad("an escort must be another badge")
            escort = v.badges[a[4]]
        self.say(v.swipe(v.badges[a[0]], v.doors[a[1]], a[2], escort))

    # -- questions
    def where(self, a):
        if len(a) != 1:
            raise Bad("usage: where BADGE")
        if a[0] not in self.v.badges:
            raise Bad("unknown badge '%s'" % a[0])
        b = self.v.badges[a[0]]
        self.say("%s: %s" % (b.ident, b.loc) + ("" if b.since is None else " since " + stamp(b.since)))

    def who(self, a):
        if len(a) != 1:
            raise Bad("usage: who ZONE")
        z = a[0]
        if z != OUTSIDE and z not in self.v.zones:
            raise Bad("unknown zone '%s'" % z)
        ids = self.v.occupants(z)
        count = "%d/-" % len(ids) if z == OUTSIDE else self.v.count_text(z)
        self.say("%s (%s): %s" % (z, count, " ".join(ids) if ids else "-"))

    def report(self, a):
        if a:
            raise Bad("usage: report")
        v = self.v
        for z in v.zones.values():
            self.say("%s: %s level %d %s%s" % (z.name, v.count_text(z.name), z.level, "open" if H.is_open(z.windows, v.now) else "closed", " lockdown" if z.locked else ""))

    def stats(self, a):
        if a:
            raise Bad("usage: stats")
        v = self.v
        self.say("grants=%d denies=%d timeouts=%d" % (v.grants, v.denies, v.timeouts))
        for reason in C.ORDER:
            if v.reasons.get(reason):
                self.say("deny %s %d" % (reason, v.reasons[reason]))

    def run(self, line):
        words = line.split()
        if not words or words[0].startswith("#"):
            return
        handler = {"zone": self.zone, "door": self.door, "badge": self.badge, "at": self.at, "swipe": self.swipe, "lockdown": self.lockdown,
                   "where": self.where, "who": self.who, "report": self.report, "stats": self.stats}.get(words[0])
        try:
            if handler is None:
                raise Bad("unknown command '%s'" % words[0])
            handler(words[1:])
        except Bad as e:
            self.say("error: " + str(e))
            self.errors += 1


def main():
    script = Script()
    for line in sys.stdin.read().split("\n"):
        script.run(line)
    sys.stdout.write("".join(l + "\n" for l in script.out))
    return 1 if script.errors else 0


if __name__ == "__main__":
    sys.exit(main())
