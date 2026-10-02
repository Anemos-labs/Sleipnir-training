"""SQL script tasks on the clinic database: generating slots, rescheduling, repairing double bookings, merging duplicate patients, purging, anonymising, triggers and views."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_clinic import DOMAIN

S = K.ScriptSpec

SPECS = [
    S("generate-slots", 3,
      "Dr. Alvarez (doctor id 1) opens the week of 2038-04-04: create her slots for Monday 2038-04-04 to Friday 2038-04-08, six slots of 30 minutes each day starting at 09:00, 09:30, ... 11:30. "
      "Use plain `INSERT` statements (a recursive CTE helps); `slot_id` is assigned by the database. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""WITH RECURSIVE d(day) AS (SELECT '2038-04-04' UNION ALL SELECT date(day, '+1 day') FROM d WHERE day < '2038-04-08'),
t(m) AS (SELECT 0 UNION ALL SELECT m + 30 FROM t WHERE m < 150)
INSERT INTO slots (doctor_id, starts_at, minutes) SELECT 1, day || ' ' || printf('%02d:%02d', 9 + m / 60, m % 60), 30 FROM d, t;""",
      checks=["SELECT doctor_id, starts_at, minutes FROM slots WHERE starts_at >= '2038-04-01'", "SELECT COUNT(*) FROM slots"],
      wrong=("INSERT INTO slots (doctor_id, starts_at, minutes) VALUES (1, '2038-04-04 09:00', 30), (1, '2038-04-04 09:30', 30);",)),
    S("shift-day", 2,
      "Dr. Alvarez (doctor id 1) is unavailable on 2038-03-16: move all her slots of that day exactly one day later (the start date changes, the time of day stays), appointments stay attached to their slots. Other doctors and days are untouched. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE slots SET starts_at = datetime(starts_at, '+1 day') WHERE doctor_id = 1 AND substr(starts_at, 1, 10) = '2038-03-16';",
      checks=["SELECT slot_id, doctor_id, starts_at, minutes FROM slots", "SELECT appt_id, slot_id, status FROM appointments"],
      buggy="UPDATE slots SET starts_at = datetime(starts_at, '+1 day') WHERE substr(starts_at, 1, 10) = '2038-03-16';",
      wrong=("UPDATE slots SET starts_at = date(starts_at, '+1 day') WHERE doctor_id = 1 AND substr(starts_at, 1, 10) = '2038-03-16';",)),
    S("resolve-double-bookings", 3,
      "Repair the double bookings: where a slot holds more than one non-cancelled appointment, keep the one with the lowest `appt_id` and set the status of the others to `cancelled`. Slots with at most one non-cancelled appointment are untouched. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""UPDATE appointments SET status = 'cancelled' WHERE status <> 'cancelled' AND appt_id > (SELECT MIN(b.appt_id) FROM appointments b WHERE b.slot_id = appointments.slot_id AND b.status <> 'cancelled');""",
      checks=["SELECT appt_id, status FROM appointments"],
      wrong=("""UPDATE appointments SET status = 'cancelled' WHERE slot_id IN (SELECT slot_id FROM appointments WHERE status <> 'cancelled' GROUP BY slot_id HAVING COUNT(*) > 1);""",)),
    S("merge-duplicate-patients", 4,
      "Some patients were entered twice: the same `name` and `birth_year` under two ids. For every such group keep the patient with the lowest `patient_id`, point all their appointments and waitlist entries to it, and delete the other copies. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE TEMP TABLE keep AS SELECT patient_id AS dup, (SELECT MIN(q.patient_id) FROM patients q WHERE q.name = p.name AND q.birth_year = p.birth_year) AS keep FROM patients p;
UPDATE appointments SET patient_id = (SELECT keep FROM keep WHERE dup = appointments.patient_id);
UPDATE waitlist SET patient_id = (SELECT keep FROM keep WHERE dup = waitlist.patient_id);
DELETE FROM patients WHERE patient_id IN (SELECT dup FROM keep WHERE dup <> keep);""",
      checks=["SELECT patient_id, name, birth_year FROM patients", "SELECT appt_id, patient_id FROM appointments", "SELECT wait_id, patient_id FROM waitlist"],
      wrong=("""DELETE FROM patients WHERE patient_id NOT IN (SELECT MIN(patient_id) FROM patients GROUP BY name, birth_year);""",
             """UPDATE appointments SET patient_id = (SELECT MIN(q.patient_id) FROM patients q, patients p WHERE p.patient_id = appointments.patient_id AND q.name = p.name AND q.birth_year = p.birth_year);
DELETE FROM patients WHERE patient_id NOT IN (SELECT MIN(patient_id) FROM patients GROUP BY name, birth_year);""")),
    S("purge-old-bookings", 3,
      "Clean up the history: delete every `cancelled` appointment whose slot started before 2038-03-10, and then delete every slot that started before 2038-03-10 and has no appointment left at all (of any status). "
      "Slots and appointments from 2038-03-10 on, and past appointments that are `done` or `no-show`, stay. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""DELETE FROM appointments WHERE status = 'cancelled' AND slot_id IN (SELECT slot_id FROM slots WHERE starts_at < '2038-03-10');
DELETE FROM slots WHERE starts_at < '2038-03-10' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = slots.slot_id);""",
      checks=["SELECT slot_id FROM slots", "SELECT appt_id FROM appointments"],
      wrong=("""DELETE FROM appointments WHERE status = 'cancelled' AND slot_id IN (SELECT slot_id FROM slots WHERE starts_at < '2038-03-10');
DELETE FROM slots WHERE starts_at < '2038-03-10';""",)),
    S("no-overlap-trigger", 4,
      "Stop overlapping slots at the source: create a trigger that makes an `INSERT` into `slots` fail with `RAISE(ABORT, ...)` when the new slot overlaps an existing slot of the same doctor. Slots overlap when they share at least one minute; a slot that starts exactly when another ends is fine. "
      "Other inserts keep working. Existing rows are not touched. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE TRIGGER slots_no_overlap BEFORE INSERT ON slots
WHEN EXISTS (SELECT 1 FROM slots s WHERE s.doctor_id = NEW.doctor_id AND s.starts_at < datetime(NEW.starts_at, '+' || NEW.minutes || ' minutes') AND NEW.starts_at < datetime(s.starts_at, '+' || s.minutes || ' minutes'))
BEGIN SELECT RAISE(ABORT, 'overlapping slot'); END;""",
      post=[{"sql": "INSERT INTO slots (doctor_id, starts_at, minutes) SELECT doctor_id, starts_at, 10 FROM slots ORDER BY slot_id LIMIT 1"},
            {"sql": "INSERT INTO slots (doctor_id, starts_at, minutes) SELECT doctor_id, datetime(starts_at, '+5 minutes'), 10 FROM slots ORDER BY slot_id DESC LIMIT 1"},
            {"sql": "INSERT INTO slots (doctor_id, starts_at, minutes) SELECT doctor_id, datetime(starts_at, '-10 minutes'), 15 FROM slots WHERE starts_at LIKE '2038-03-1%' ORDER BY slot_id LIMIT 1"},
            {"sql": "INSERT INTO slots (doctor_id, starts_at, minutes) SELECT doctor_id, datetime(starts_at, '+' || minutes || ' minutes'), 5 FROM slots WHERE starts_at LIKE '2038-03-0%' ORDER BY slot_id DESC LIMIT 1"},
            {"sql": "INSERT INTO slots (doctor_id, starts_at, minutes) VALUES (1, '2039-01-02 08:00', 30)"}],
      checks=["SELECT COUNT(*) FROM slots", "SELECT name FROM sqlite_master WHERE type = 'trigger'"], struct=["triggers"],
      wrong=("""CREATE TRIGGER slots_no_overlap BEFORE INSERT ON slots WHEN EXISTS (SELECT 1 FROM slots s WHERE s.doctor_id = NEW.doctor_id AND s.starts_at = NEW.starts_at) BEGIN SELECT RAISE(ABORT, 'overlapping slot'); END;""",)),
    S("no-show-counter", 4,
      "Track no-shows on the patient: add `no_shows` (INTEGER, NOT NULL, default 0) to `patients`, fill it with the current number of `no-show` appointments of each patient, and add a trigger that increases it when an appointment's status is *changed* to `no-show` "
      "(an update from another status; setting `no-show` on a row that already is `no-show` changes nothing). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""ALTER TABLE patients ADD COLUMN no_shows INTEGER NOT NULL DEFAULT 0;
UPDATE patients SET no_shows = (SELECT COUNT(*) FROM appointments a WHERE a.patient_id = patients.patient_id AND a.status = 'no-show');
CREATE TRIGGER appt_no_show AFTER UPDATE OF status ON appointments WHEN NEW.status = 'no-show' AND OLD.status <> 'no-show'
BEGIN UPDATE patients SET no_shows = no_shows + 1 WHERE patient_id = NEW.patient_id; END;""",
      post=[{"sql": "UPDATE appointments SET status = 'no-show' WHERE status = 'done' AND appt_id % 4 = 0; UPDATE appointments SET status = 'no-show' WHERE status = 'no-show' AND appt_id % 2 = 0;", "script": True}],
      checks=["SELECT patient_id, no_shows FROM patients"], struct=["columns:patients", "triggers"],
      wrong=("""ALTER TABLE patients ADD COLUMN no_shows INTEGER NOT NULL DEFAULT 0;
UPDATE patients SET no_shows = (SELECT COUNT(*) FROM appointments a WHERE a.patient_id = patients.patient_id AND a.status = 'no-show');
CREATE TRIGGER appt_no_show AFTER UPDATE OF status ON appointments WHEN NEW.status = 'no-show' BEGIN UPDATE patients SET no_shows = no_shows + 1 WHERE patient_id = NEW.patient_id; END;""",)),
    S("rename-specialty", 2,
      "Switch to the American spelling: every specialty `paediatrics` becomes `pediatrics`, in `doctors` and in `waitlist`. Nothing else changes. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE doctors SET specialty = 'pediatrics' WHERE specialty = 'paediatrics';\nUPDATE waitlist SET specialty = 'pediatrics' WHERE specialty = 'paediatrics';",
      checks=["SELECT doctor_id, specialty FROM doctors", "SELECT wait_id, specialty FROM waitlist"],
      wrong=("UPDATE doctors SET specialty = 'pediatrics' WHERE specialty = 'paediatrics';",)),
    S("anonymise-patients", 3,
      "Prepare a research export: replace every patient's name by `patient-` followed by the id (`patient-7`) and generalise the birth year to its decade (1987 becomes 1980). Appointments and waitlist entries are untouched. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE patients SET name = 'patient-' || patient_id, birth_year = birth_year / 10 * 10;",
      checks=["SELECT patient_id, name, birth_year FROM patients"],
      wrong=("UPDATE patients SET name = 'patient-' || patient_id, birth_year = birth_year - birth_year % 5;",)),
    S("free-slots-view", 2,
      "Create a view `open_slots` with the columns `slot_id`, `doctor` (the doctor's name), `specialty`, `starts_at` and `minutes` for every slot that starts on or after 2038-03-15 and is free (no appointment with a status other than `cancelled`). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE VIEW open_slots AS SELECT s.slot_id, d.name AS doctor, d.specialty, s.starts_at, s.minutes FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id
WHERE s.starts_at >= '2038-03-15' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled');""",
      checks=["SELECT slot_id, doctor, specialty, starts_at, minutes FROM open_slots"], struct=["views", "tables"],
      wrong=("""CREATE VIEW open_slots AS SELECT s.slot_id, d.name AS doctor, d.specialty, s.starts_at, s.minutes FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id WHERE s.starts_at >= '2038-03-15' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id);""",)),
    S("lock-future-cancellations", 3,
      "Create `cancellation_log (appt_id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL, patient_id INTEGER NOT NULL)` and fill it with every appointment that is cancelled and whose slot starts on or after 2038-03-15; then delete those rows from `appointments`. "
      "Everything else stays. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE TABLE cancellation_log (appt_id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL, patient_id INTEGER NOT NULL);
INSERT INTO cancellation_log SELECT a.appt_id, a.slot_id, a.patient_id FROM appointments a JOIN slots s ON s.slot_id = a.slot_id WHERE a.status = 'cancelled' AND s.starts_at >= '2038-03-15';
DELETE FROM appointments WHERE appt_id IN (SELECT appt_id FROM cancellation_log);""",
      checks=["SELECT * FROM cancellation_log", "SELECT appt_id FROM appointments"], struct=["tables", "columns:cancellation_log"],
      wrong=("""CREATE TABLE cancellation_log (appt_id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL, patient_id INTEGER NOT NULL);
INSERT INTO cancellation_log SELECT appt_id, slot_id, patient_id FROM appointments WHERE status = 'cancelled';
DELETE FROM appointments WHERE status = 'cancelled';""",)),
    S("unique-booking-index", 4,
      "A slot may hold only one live booking. First repair the data: for every slot with several non-cancelled appointments keep the lowest `appt_id` and cancel the rest. Then create a *partial unique index* named `one_live_booking` on `appointments (slot_id)` that applies only "
      "to rows whose status is not `cancelled`, so the database refuses a second live booking. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""UPDATE appointments SET status = 'cancelled' WHERE status <> 'cancelled' AND appt_id > (SELECT MIN(b.appt_id) FROM appointments b WHERE b.slot_id = appointments.slot_id AND b.status <> 'cancelled');
CREATE UNIQUE INDEX one_live_booking ON appointments (slot_id) WHERE status <> 'cancelled';""",
      post=[{"sql": "INSERT INTO appointments (slot_id, patient_id, status, booked_on) SELECT slot_id, 1, 'booked', '2038-03-15' FROM appointments WHERE status <> 'cancelled' ORDER BY appt_id LIMIT 1"},
            {"sql": "INSERT INTO appointments (slot_id, patient_id, status, booked_on) SELECT slot_id, 1, 'cancelled', '2038-03-15' FROM appointments WHERE status <> 'cancelled' ORDER BY appt_id LIMIT 1"}],
      checks=["SELECT appt_id, status FROM appointments"], struct=["indexes:appointments"],
      wrong=("""CREATE UNIQUE INDEX one_live_booking ON appointments (slot_id);""",)),
]


@family("data-clinic-maintenance", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL maintenance scripts on a clinic database: recursive slot generation, rescheduling, double-booking repair, duplicate merge, purge, overlap and counter triggers, partial unique index")
def clinic_maintenance(rng, n):
    return K.script_tasks(DOMAIN, SPECS, rng, n)
