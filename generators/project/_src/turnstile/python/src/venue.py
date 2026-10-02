"""The venue: zones, doors, badges, the clock, and the decision for one swipe."""
import config as C
import hours as H

OUTSIDE = "outside"
WEEK = 10080


def stamp(t):
    return "%s %02d:%02d" % (H.DAYS[(t // 1440) % 7], t % 1440 // 60, t % 60)


class Zone:
    def __init__(self, name, level, cap, windows):
        self.name = name
        self.level = level
        self.cap = cap  # 0: unlimited
        self.windows = windows
        self.locked = False


class Door:
    def __init__(self, ident, outer, inner):
        self.ident = ident
        self.outer = outer
        self.inner = inner


class Badge:
    def __init__(self, ident, level, expires):
        self.ident = ident
        self.level = level
        self.expires = expires  # absolute minute, or None
        self.loc = OUTSIDE
        self.since = None  # minute of the last grant or timeout


class Venue:
    def __init__(self):
        self.zones = {}
        self.doors = {}
        self.badges = {}
        self.now = 0
        self.grants = 0
        self.denies = 0
        self.timeouts = 0
        self.reasons = {}

    def occupants(self, zone):
        return sorted(b.ident for b in self.badges.values() if b.loc == zone)

    def count_text(self, zone):
        z = self.zones[zone]
        return "%d/%s" % (len(self.occupants(zone)), z.cap if z.cap else "-")

    # -- the clock
    def set_clock(self, t, out):
        before, self.now = self.now, t
        if C.EVICT and t > before:
            for b in sorted(self.badges.values(), key=lambda x: x.ident):
                if b.loc != OUTSIDE and t - b.since >= C.EVICT:
                    out.append("[%s] TIMEOUT %s left %s" % (stamp(t), b.ident, b.loc))
                    b.loc, b.since = OUTSIDE, t
                    self.timeouts += 1

    def next_at(self, day, tod):
        """The first minute at or after now that is weekday `day` at `tod`."""
        t = self.now // WEEK * WEEK + day * 1440 + tod
        return t if t >= self.now else t + WEEK

    # -- one swipe
    def swipe(self, badge, door, direction, escort):
        members = [badge] + ([escort] if escort else [])
        inward = direction == "in"
        zone = self.zones[door.inner]
        target = zone.name if inward else door.outer
        fails = {
            "expired": lambda: any(m.expires is not None and self.now >= m.expires for m in members) if (inward or C.EXP_OUT) else False,
            "lockdown": lambda: zone.locked if (inward or C.SEAL) else False,
            "passback": lambda: any(self.passback(m, door, inward) for m in members),
            "level": lambda: inward and max(m.level for m in members) < zone.level,
            "hours": lambda: inward and not H.is_open(zone.windows, self.now),
            "full": lambda: inward and zone.cap > 0 and len(self.occupants(zone.name)) + sum(1 for m in members if m.loc != zone.name) > zone.cap,
        }
        who = "+".join(m.ident for m in members)
        for reason in C.ORDER:
            if fails[reason]():
                self.denies += 1
                self.reasons[reason] = self.reasons.get(reason, 0) + 1
                return "[%s] DENY %s %s %s: %s" % (stamp(self.now), who, door.ident, direction, reason)
        for m in members:
            m.loc, m.since = target, self.now
        self.grants += 1
        where = "outside" if target == OUTSIDE else "%s (%s)" % (target, self.count_text(target))
        return "[%s] GRANT %s %s %s -> %s" % (stamp(self.now), who, door.ident, direction, where)

    def passback(self, m, door, inward):
        if C.APB == "off":
            return False
        here, there = (door.outer, door.inner) if inward else (door.inner, door.outer)
        if C.APB == "soft":
            return m.loc == there
        return m.loc != here
