"""SQL tasks on an invented clinic's appointment slots (free-slot logic, interval overlaps, idle gaps, waitlist matching, utilisation)."""
from datetime import date, datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE doctors (
      doctor_id  INTEGER PRIMARY KEY,
      name       TEXT NOT NULL UNIQUE,
      specialty  TEXT NOT NULL
    );
    CREATE TABLE patients (
      patient_id  INTEGER PRIMARY KEY,
      name        TEXT NOT NULL,
      birth_year  INTEGER NOT NULL
    );
    CREATE TABLE slots (
      slot_id    INTEGER PRIMARY KEY,
      doctor_id  INTEGER NOT NULL REFERENCES doctors(doctor_id),
      starts_at  TEXT NOT NULL,               -- YYYY-MM-DD HH:MM
      minutes    INTEGER NOT NULL
    );
    CREATE TABLE appointments (
      appt_id     INTEGER PRIMARY KEY,
      slot_id     INTEGER NOT NULL REFERENCES slots(slot_id),
      patient_id  INTEGER NOT NULL REFERENCES patients(patient_id),
      status      TEXT NOT NULL CHECK (status IN ('booked', 'done', 'no-show', 'cancelled')),
      booked_on   TEXT NOT NULL
    );
    CREATE TABLE waitlist (
      wait_id       INTEGER PRIMARY KEY,
      patient_id    INTEGER NOT NULL REFERENCES patients(patient_id),
      specialty     TEXT NOT NULL,
      requested_on  TEXT NOT NULL,
      earliest      TEXT NOT NULL             -- the patient can come from this date on (YYYY-MM-DD)
    );
''')

DOC = dd('''
    The Brackenhill Clinic offers appointment **slots** (a doctor, a start time and a length in minutes) and records the appointments booked into them.

    * A slot is **free** when it has no appointment with a status other than `cancelled`. A slot occupies the time from `starts_at` for `minutes` minutes; it ends when the next minute begins.
      (A slot that ends exactly when another one starts does not overlap it.)
    * `done` and `no-show` appointments are in the past; `booked` ones are today or later. Today is **2038-03-15**. A *no-show* is a patient who did not come.
    * A slot should hold at most one non-cancelled appointment, and the slots of one doctor should not overlap; the data has mistakes of both kinds.
    * `waitlist` lists patients waiting for any doctor of a specialty; `earliest` is the first date they can come.
    * Dates and times are ISO text; ages are counted as `2038 - birth_year`.
''')

DOCTORS = [("Dr. Alvarez", "general"), ("Dr. Brandt", "general"), ("Dr. Chowdhury", "paediatrics"), ("Dr. Dalgaard", "dermatology"), ("Dr. Eze", "paediatrics"), ("Dr. Fontaine", "dermatology")]
FIRST = ["Aino", "Bas", "Corin", "Dilnoza", "Eero", "Faye", "Goran", "Hedda", "Idris", "Jarmila", "Kofi", "Liv", "Milos", "Nadja", "Osk", "Pia", "Rue", "Sven", "Tamsin", "Uri"]


def gen(rng, big):
    nd = 6 if big else 3
    doctors = [(i + 1, DOCTORS[i][0], rng.choice(["general", "paediatrics", "dermatology"])) for i in range(nd)]
    patients = [(i + 1, FIRST[i % len(FIRST)] + (" " + chr(65 + i // len(FIRST)) if i >= len(FIRST) else ""), rng.randint(1938, 2036)) for i in range(34 if big else 10)]
    slots, appts, sid, aid = [], [], 0, 0
    days = [date(2038, 3, 7) + timedelta(days=d) for d in range(19 if big else 12) if (date(2038, 3, 7) + timedelta(days=d)).weekday() < 5]
    for d in doctors:
        for day in days:
            t = datetime(day.year, day.month, day.day, rng.choice([8, 9]), 0)
            for _ in range(rng.randint(4, 8) if big else rng.randint(3, 5)):
                length = rng.choice([20, 30, 30, 45])
                sid += 1
                slots.append((sid, d[0], t.strftime("%Y-%m-%d %H:%M"), length))
                t += timedelta(minutes=length + rng.choice([0, 0, 0, 10, 40, 90]))
    for s in slots:
        r = rng.random()
        if r < 0.7:
            past = s[2] < "2038-03-15"
            status = rng.choice(["done", "done", "done", "no-show", "cancelled"]) if past else rng.choice(["booked", "booked", "cancelled"])
            aid += 1
            appts.append((aid, s[0], rng.choice(patients)[0], status, (datetime.fromisoformat(s[2]) - timedelta(days=rng.randint(2, 30))).strftime("%Y-%m-%d")))
    # plant: double-booked slots, an overlapping slot, back-to-back slots, a cancelled slot that is free again, repeat no-shows, a cancel-and-rebook pair
    free_future = [s for s in slots if s[2] >= "2038-03-16"]
    for s in rng.sample(free_future, 2):
        for _ in range(2):
            aid += 1
            appts.append((aid, s[0], rng.choice(patients)[0], "booked", "2038-03-10"))
    d0 = doctors[0][0]
    sid += 1
    slots.append((sid, d0, "2038-03-16 10:00", 30))
    sid += 1
    slots.append((sid, d0, "2038-03-16 10:20", 30))  # overlaps the previous one by 10 minutes
    sid += 1
    slots.append((sid, d0, "2038-03-16 10:50", 20))  # starts exactly when the previous one ends
    for st, ln in (("2038-03-17 14:00", 45), ("2038-03-17 14:10", 20), ("2038-03-17 15:30", 30)):  # a short slot nested in a long one hides the real idle gap
        sid += 1
        slots.append((sid, d0, st, ln))
    p0 = patients[0][0]
    past = [s for s in slots if s[2] < "2038-03-15"]
    for s in rng.sample(past, 3):
        aid += 1
        appts.append((aid, s[0], p0, "no-show", "2038-02-01"))
    p1 = patients[1][0]  # two old no-shows (outside the 90-day window) and one recent one
    for st in ("2037-10-05 09:00", "2037-10-06 09:00"):
        sid += 1
        slots.append((sid, d0, st, 30))
        aid += 1
        appts.append((aid, sid, p1, "no-show", "2037-09-20"))
    recent = rng.choice([sl for sl in slots if "2038-03-07" <= sl[2] < "2038-03-15"])
    aid += 1
    appts.append((aid, recent[0], p1, "no-show", "2038-03-01"))
    # plant: two patients exist twice (same name and birth year, different ids), each copy with some appointments
    for src in patients[2:4]:
        nid = len(patients) + 1
        patients.append((nid, src[1], src[2]))
        for idx in rng.sample(range(len(appts)), 2):
            a = appts[idx]
            appts[idx] = (a[0], a[1], nid, a[3], a[4])
    waits = [(i + 1, rng.choice(patients)[0], rng.choice(sorted({d[2] for d in doctors})), f"2038-03-{rng.randint(1, 14):02d}", f"2038-03-{rng.randint(15, 24):02d}") for i in range(8 if big else 4)]
    return {"doctors": doctors, "patients": patients, "slots": slots, "appointments": appts, "waitlist": waits}


DOMAIN = K.Domain("clinic", "Brackenhill Clinic: appointment slots", SCHEMA, DOC, gen)
S = K.Spec

FREE = "NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled')"

SPECS = [
    S("doctors-per-specialty", 1, "How many doctors does each specialty have, and what are their names? Columns: specialty, doctors, and the names joined with `, ` in alphabetical order. Order by specialty.",
      "SELECT specialty, COUNT(*) AS doctors, GROUP_CONCAT(name, ', ') AS names FROM (SELECT * FROM doctors ORDER BY name) GROUP BY specialty ORDER BY specialty;", ["specialty", "doctors", "names"], ordered=True),
    S("free-slots-next-week", 2,
      f"Free slots next week: for every doctor (also those without any free slot) the number of free slots that start between 2038-03-16 and 2038-03-22 (both days included) and the total free minutes. Columns: doctor name, free slots, free minutes. Order by free slots descending, then name.",
      f"""SELECT d.name AS doctor, COUNT(s.slot_id) AS free_slots, COALESCE(SUM(s.minutes), 0) AS free_minutes FROM doctors d LEFT JOIN slots s ON s.doctor_id = d.doctor_id AND s.starts_at >= '2038-03-16' AND s.starts_at < '2038-03-23' AND {FREE} GROUP BY d.doctor_id ORDER BY free_slots DESC, d.name;""",
      ["doctor", "free_slots", "free_minutes"], ordered=True,
      wrong=("""SELECT d.name, COUNT(s.slot_id), COALESCE(SUM(s.minutes), 0) FROM doctors d LEFT JOIN slots s ON s.doctor_id = d.doctor_id AND s.starts_at >= '2038-03-16' AND s.starts_at < '2038-03-23' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id) GROUP BY d.doctor_id ORDER BY 2 DESC, d.name;""",)),
    S("no-show-rate", 2,
      "No-show rate per specialty over the past appointments (status `done` or `no-show`): specialty, past appointments, no-shows, the rate in percent with 1 decimal. Specialties without past appointments do not appear. Highest rate first, ties by specialty.",
      """SELECT d.specialty, COUNT(*) AS past, SUM(a.status = 'no-show') AS no_shows, ROUND(100.0 * SUM(a.status = 'no-show') / COUNT(*), 1) AS rate FROM appointments a JOIN slots s ON s.slot_id = a.slot_id JOIN doctors d ON d.doctor_id = s.doctor_id WHERE a.status IN ('done', 'no-show') GROUP BY d.specialty ORDER BY rate DESC, d.specialty;""",
      ["specialty", "past", "no_shows", "rate"], ordered=True,
      wrong=("""SELECT d.specialty, COUNT(*), SUM(a.status = 'no-show'), ROUND(100.0 * SUM(a.status = 'no-show') / COUNT(*), 1) AS r FROM appointments a JOIN slots s ON s.slot_id = a.slot_id JOIN doctors d ON d.doctor_id = s.doctor_id GROUP BY d.specialty ORDER BY r DESC, d.specialty;""",)),
    S("double-booked", 2,
      "Slots that hold more than one non-cancelled appointment: slot id, doctor name, start and the number of such appointments. Order by start, then slot id.",
      "SELECT s.slot_id, d.name AS doctor, s.starts_at, COUNT(*) AS appointments FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id JOIN appointments a ON a.slot_id = s.slot_id AND a.status <> 'cancelled' GROUP BY s.slot_id HAVING COUNT(*) > 1 ORDER BY s.starts_at, s.slot_id;",
      ["slot_id", "doctor", "starts_at", "appointments"], ordered=True, allow_empty=True),
    S("overlapping-slots", 3,
      "Overlapping slots of the same doctor: report every pair (lower slot id first) whose time ranges share at least one minute, with the number of shared minutes. A slot that starts exactly when the other ends does not overlap. "
      "Columns: doctor name, the two slot ids, shared minutes. Order by doctor name, then the first slot id, then the second.",
      """SELECT d.name AS doctor, a.slot_id AS slot_a, b.slot_id AS slot_b,
       CAST(ROUND((julianday(MIN(datetime(a.starts_at, '+' || a.minutes || ' minutes'), datetime(b.starts_at, '+' || b.minutes || ' minutes'))) - julianday(MAX(a.starts_at, b.starts_at))) * 1440) AS INTEGER) AS shared_minutes
FROM slots a JOIN slots b ON b.doctor_id = a.doctor_id AND b.slot_id > a.slot_id AND b.starts_at < datetime(a.starts_at, '+' || a.minutes || ' minutes') AND a.starts_at < datetime(b.starts_at, '+' || b.minutes || ' minutes')
JOIN doctors d ON d.doctor_id = a.doctor_id ORDER BY d.name, a.slot_id, b.slot_id;""",
      ["doctor", "slot_a", "slot_b", "shared_minutes"], ordered=True, allow_empty=True,
      wrong=("""SELECT d.name, a.slot_id, b.slot_id, 0 FROM slots a JOIN slots b ON b.doctor_id = a.doctor_id AND b.slot_id > a.slot_id AND b.starts_at <= datetime(a.starts_at, '+' || a.minutes || ' minutes') AND a.starts_at <= datetime(b.starts_at, '+' || b.minutes || ' minutes') JOIN doctors d ON d.doctor_id = a.doctor_id ORDER BY d.name, a.slot_id, b.slot_id;""",)),
    S("repeat-no-shows", 3,
      "Patients with at least 2 no-shows whose appointment slot started in the 90 days up to and including 2038-03-15 (slots from 2037-12-16 on): patient name, number of no-shows, date of the latest one. Most first, ties by name.",
      """SELECT p.name, COUNT(*) AS no_shows, MAX(substr(s.starts_at, 1, 10)) AS latest FROM appointments a JOIN slots s ON s.slot_id = a.slot_id JOIN patients p ON p.patient_id = a.patient_id
WHERE a.status = 'no-show' AND s.starts_at >= '2037-12-16' AND s.starts_at < '2038-03-16' GROUP BY p.patient_id HAVING COUNT(*) >= 2 ORDER BY no_shows DESC, p.name;""",
      ["name", "no_shows", "latest"], ordered=True,
      wrong=("""SELECT p.name, COUNT(*), MAX(substr(s.starts_at, 1, 10)) FROM appointments a JOIN slots s ON s.slot_id = a.slot_id JOIN patients p ON p.patient_id = a.patient_id WHERE a.status = 'no-show' GROUP BY p.name HAVING COUNT(*) >= 2 ORDER BY 2 DESC, p.name;""",)),
    S("idle-gaps", 4,
      "Idle time inside a doctor's day: for each doctor and date, look at the slots in start order and find the gaps between the end of a slot and the start of the next one on the same day. "
      "Report the gaps of 30 minutes or more: doctor name, date, gap start (HH:MM, the end of the earlier slot), gap length in minutes. Overlapping slots leave no gap. Order by gap length descending, then doctor, then date, then gap start.",
      """WITH x AS (SELECT doctor_id, substr(starts_at, 1, 10) AS day, starts_at, datetime(starts_at, '+' || minutes || ' minutes') AS ends_at,
  MAX(datetime(starts_at, '+' || minutes || ' minutes')) OVER (PARTITION BY doctor_id, substr(starts_at, 1, 10) ORDER BY starts_at, slot_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_end FROM slots)
SELECT d.name AS doctor, x.day, substr(x.prev_end, 12, 5) AS gap_start, CAST(ROUND((julianday(x.starts_at) - julianday(x.prev_end)) * 1440) AS INTEGER) AS gap FROM x JOIN doctors d ON d.doctor_id = x.doctor_id
WHERE x.prev_end IS NOT NULL AND (julianday(x.starts_at) - julianday(x.prev_end)) * 1440 >= 29.5 ORDER BY gap DESC, d.name, x.day, gap_start;""",
      ["doctor", "day", "gap_start", "gap"], ordered=True,
      wrong=("""WITH x AS (SELECT doctor_id, substr(starts_at, 1, 10) AS day, starts_at, LAG(datetime(starts_at, '+' || minutes || ' minutes')) OVER (PARTITION BY doctor_id, substr(starts_at, 1, 10) ORDER BY starts_at, slot_id) AS prev_end FROM slots)
SELECT d.name, x.day, substr(x.prev_end, 12, 5), CAST(ROUND((julianday(x.starts_at) - julianday(x.prev_end)) * 1440) AS INTEGER) AS gap FROM x JOIN doctors d ON d.doctor_id = x.doctor_id WHERE x.prev_end IS NOT NULL AND (julianday(x.starts_at) - julianday(x.prev_end)) * 1440 >= 29.5 ORDER BY gap DESC, d.name, x.day, 3;""",)),
    S("waitlist-matches", 4,
      "Match the waiting list: for every waiting entry find the earliest free slot (any doctor of the requested specialty, slot starting on or after the entry's `earliest` date at 00:00; ties on the start time go to the doctor with the lower id). "
      "Columns: wait id, patient name, specialty, slot start and doctor name; both of the last two are NULL when no free slot exists. Order by wait id.",
      f"""WITH c AS (SELECT w.wait_id, s.starts_at, d.name AS doctor, ROW_NUMBER() OVER (PARTITION BY w.wait_id ORDER BY s.starts_at, d.doctor_id, s.slot_id) AS rn
  FROM waitlist w JOIN doctors d ON d.specialty = w.specialty JOIN slots s ON s.doctor_id = d.doctor_id AND s.starts_at >= w.earliest AND {FREE})
SELECT w.wait_id, p.name AS patient, w.specialty, c.starts_at, c.doctor FROM waitlist w JOIN patients p ON p.patient_id = w.patient_id LEFT JOIN c ON c.wait_id = w.wait_id AND c.rn = 1 ORDER BY w.wait_id;""",
      ["wait_id", "patient", "specialty", "starts_at", "doctor"], ordered=True,
      wrong=("""SELECT w.wait_id, p.name, w.specialty, MIN(s.starts_at), d.name FROM waitlist w JOIN patients p ON p.patient_id = w.patient_id LEFT JOIN doctors d ON d.specialty = w.specialty LEFT JOIN slots s ON s.doctor_id = d.doctor_id AND s.starts_at >= w.earliest GROUP BY w.wait_id ORDER BY w.wait_id;""",)),
    S("weekly-utilisation", 4,
      "Utilisation: for each doctor and week (`strftime('%W', starts_at)`, Monday-based week number of the year) add up the minutes of all slots and the minutes of the slots that carry at least one non-cancelled appointment. "
      "Report the doctor-weeks where at least 60% of the minutes are used: doctor name, week number (text like `10`), total minutes, used minutes, and the percentage with 1 decimal. Order by percentage descending, then doctor, then week.",
      """SELECT d.name AS doctor, strftime('%W', s.starts_at) AS week, SUM(s.minutes) AS total, SUM(CASE WHEN EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled') THEN s.minutes ELSE 0 END) AS used,
       ROUND(100.0 * SUM(CASE WHEN EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled') THEN s.minutes ELSE 0 END) / SUM(s.minutes), 1) AS pct
FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id GROUP BY d.doctor_id, week HAVING 100.0 * used / total >= 60 ORDER BY pct DESC, d.name, week;""",
      ["doctor", "week", "total", "used", "pct"], ordered=True,
      wrong=("""SELECT d.name, strftime('%W', s.starts_at) AS week, SUM(s.minutes) AS total, SUM(s.minutes * (a.appt_id IS NOT NULL)) AS used, ROUND(100.0 * SUM(s.minutes * (a.appt_id IS NOT NULL)) / SUM(s.minutes), 1) AS pct
FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id LEFT JOIN appointments a ON a.slot_id = s.slot_id GROUP BY d.doctor_id, week HAVING pct >= 60 ORDER BY pct DESC, d.name, week;""",)),
    S("age-groups", 3,
      "Done appointments by age group of the patient (age = 2038 minus birth year): `child` under 18, `adult` 18 to 64, `senior` 65 and over. For each group: done appointments, distinct patients and the average age of the appointments' patients with 1 decimal. Order child, adult, senior.",
      """SELECT CASE WHEN 2038 - p.birth_year < 18 THEN 'child' WHEN 2038 - p.birth_year < 65 THEN 'adult' ELSE 'senior' END AS grp, COUNT(*) AS done, COUNT(DISTINCT p.patient_id) AS patients, ROUND(AVG(2038 - p.birth_year), 1) AS avg_age
FROM appointments a JOIN patients p ON p.patient_id = a.patient_id WHERE a.status = 'done' GROUP BY grp ORDER BY CASE grp WHEN 'child' THEN 1 WHEN 'adult' THEN 2 ELSE 3 END;""",
      ["group", "done", "patients", "avg_age"], ordered=True,
      wrong=("""SELECT CASE WHEN 2038 - p.birth_year <= 18 THEN 'child' WHEN 2038 - p.birth_year <= 65 THEN 'adult' ELSE 'senior' END AS g, COUNT(*), COUNT(DISTINCT p.patient_id), ROUND(AVG(2038 - p.birth_year), 1) FROM appointments a JOIN patients p ON p.patient_id = a.patient_id WHERE a.status = 'done' GROUP BY g ORDER BY CASE g WHEN 'child' THEN 1 WHEN 'adult' THEN 2 ELSE 3 END;""",)),
    S("cancelled-then-rebooked", 4,
      "Quick rebookings: a patient cancelled an appointment and has a different appointment (status `booked`, `done` or `no-show`) with the **same doctor** whose slot starts 1 to 14 days after the cancelled slot's start (by calendar date: the date of the new slot minus the date of the cancelled slot). "
      "List each such pair: patient name, doctor name, date of the cancelled slot, date of the new slot. Order by patient name, then the cancelled date, then the new date.",
      """SELECT p.name AS patient, d.name AS doctor, substr(s1.starts_at, 1, 10) AS cancelled_on, substr(s2.starts_at, 1, 10) AS rebooked_on
FROM appointments a1 JOIN slots s1 ON s1.slot_id = a1.slot_id JOIN appointments a2 ON a2.patient_id = a1.patient_id AND a2.appt_id <> a1.appt_id AND a2.status IN ('booked', 'done', 'no-show')
JOIN slots s2 ON s2.slot_id = a2.slot_id AND s2.doctor_id = s1.doctor_id AND julianday(substr(s2.starts_at, 1, 10)) - julianday(substr(s1.starts_at, 1, 10)) BETWEEN 1 AND 14
JOIN patients p ON p.patient_id = a1.patient_id JOIN doctors d ON d.doctor_id = s1.doctor_id WHERE a1.status = 'cancelled' ORDER BY p.name, cancelled_on, rebooked_on;""",
      ["patient", "doctor", "cancelled_on", "rebooked_on"], ordered=True, allow_empty=True,
      wrong=("""SELECT p.name, d.name, substr(s1.starts_at, 1, 10), substr(s2.starts_at, 1, 10) FROM appointments a1 JOIN slots s1 ON s1.slot_id = a1.slot_id JOIN appointments a2 ON a2.patient_id = a1.patient_id AND a2.appt_id <> a1.appt_id AND a2.status <> 'cancelled' JOIN slots s2 ON s2.slot_id = a2.slot_id AND s2.starts_at > s1.starts_at AND julianday(s2.starts_at) - julianday(s1.starts_at) <= 14 JOIN patients p ON p.patient_id = a1.patient_id JOIN doctors d ON d.doctor_id = s1.doctor_id WHERE a1.status = 'cancelled' ORDER BY p.name, 3, 4;""",)),
    S("busiest-start-hour", 3,
      "For each hour of the day at which slots start, how many slots start then, how many of them are free, and the share of free ones in percent (1 decimal)? Show the hour as a number 0 to 23. Order by hour.",
      f"""SELECT CAST(substr(s.starts_at, 12, 2) AS INTEGER) AS hour, COUNT(*) AS slots, SUM({FREE}) AS free, ROUND(100.0 * SUM({FREE}) / COUNT(*), 1) AS free_pct FROM slots s GROUP BY hour ORDER BY hour;""",
      ["hour", "slots", "free", "free_pct"], ordered=True),
    S("fix-free-slot-count", 3,
      "`query.sql` counts the free slots per doctor, but it treats a slot with a *cancelled* appointment as taken, and doctors without any free slot vanish from the result. "
      "Fix it: for every doctor the number of free slots (no non-cancelled appointment) among all of their slots, 0 when none. Columns: doctor name, free slots. Order by free slots descending, then name.",
      ref=f"""SELECT d.name AS doctor, COUNT(s.slot_id) AS free_slots FROM doctors d LEFT JOIN slots s ON s.doctor_id = d.doctor_id AND {FREE} GROUP BY d.doctor_id ORDER BY free_slots DESC, d.name;""",
      cols=["doctor", "free_slots"], ordered=True, show=False,
      buggy="""SELECT d.name AS doctor, COUNT(*) AS free_slots FROM doctors d JOIN slots s ON s.doctor_id = d.doctor_id WHERE NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id) GROUP BY d.doctor_id ORDER BY free_slots DESC, d.name;"""),
]


@family("data-clinic-slots", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on clinic appointment slots: free-slot logic with cancellations, interval overlaps, idle gaps, waitlist matching with ROW_NUMBER, weekly utilisation")
def clinic_slots(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
