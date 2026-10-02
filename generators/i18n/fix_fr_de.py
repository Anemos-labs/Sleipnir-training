"""Derived fix tasks in French, shell tasks in German."""
from fx import family

from ._derive import derive, take

FR = [
    ("fix-hand-config-merge-09-undefined-overrides", "01-merge-undefined", "slack",
     "Salut, petit bug dans le merge de config : quand on passe `{ verbose: undefined }` (qui vient d'options CLI optionnelles "
     "non renseignées), ça écrase la valeur par défaut et on se retrouve avec `verbose: undefined` dans la config fusionnée. "
     "`undefined` doit vouloir dire « non fourni », alors que `null`, `0`, `false` et `''` sont de vraies valeurs."),
    ("fix-hand-backup-ctl-07-dry-run-deletes", "02-prune-dry-run", "terse",
     "`backupctl prune /backup --keep-last 3 -n` affiche bien des lignes 'would delete ...' et supprime quand même les snapshots. "
     "Un dry-run ne doit rien modifier du tout, c'est quand même le principe."),
    ("fix-hand-cart-flow-04-fixed-coupon-can-exceed-the-goods", "03-coupon-negatif", "ticket",
     "Le coupon FIVE sur un tout petit panier (deux trombones, 2.04) laisse un montant de marchandises négatif sur la facture. "
     "Un coupon ne retire jamais plus que la valeur des articles."),
    ("fix-hand-date-ranges-05-iso-week-with-the-calendar-year", "04-semaine-iso", "ticket",
     "Le rapport hebdomadaire porte l'étiquette `2024-W01` pour le 30 décembre 2024, alors que c'est une semaine qu'on a déjà "
     "utilisée en janvier 2024. L'étiquette doit reprendre l'année ISO qui correspond au numéro de semaine "
     "(ce jour-là appartient à `2025-W01`)."),
    ("fix-hand-error-flow-09-typed-nil-error", "05-erreur-nil-typee", "detailed",
     "Depuis l'ajout du contrôle des noms de clés, plus aucun fichier de config ne se charge, même un simple `a = 1` sur une ligne : "
     "l'erreur renvoyée a pour message soit une panique de nil-pointer, soit juste `<nil>`. Les erreurs de syntaxe, elles, sont "
     "bien remontées. Le contrôle en lui-même est correct ; c'est la manière dont son résultat est retourné qui cloche."),
    ("fix-hand-date-ranges-07-leap-day-birthday-built-with-replace", "06-anniversaire-29-fevrier", "report",
     "Chez nous, le contrôle d'âge plante pour les clients nés un 29 février dès que la date de vérification tombe une année "
     "non bissextile : `§0`. Selon la règle, ils prennent un an le 1er mars. Pouvez-vous corriger ça, sans toucher au reste ?"),
    ("fix-hand-cart-flow-14-coupon-base-and-allocation", "07-compta-coupons", "ticket",
     "Retour de la compta sur les commandes avec coupon, deux constats. (1) SAVE10 s'applique au prix avant remises de quantité : "
     "son minimum comme ses 10 % sont donc calculés sur le mauvais montant. (2) Après le coupon, les montants des lignes ne "
     "s'additionnent pas au total des marchandises (il manque un centime ou deux). Corrigez les deux, s'il vous plaît."),
    ("fix-hand-event-ledger-08-ignored-duplicate-does-not-advance-applied", "08-vue-figee", "story",
     "La vue du stock en direct s'est figée à l'événement 310 mardi : `Pending()` a grossi tout l'après-midi alors que la "
     "reconstruction de nuit depuis le journal montrait tous les événements comme corrects. La première chose arrivée à "
     "l'événement 310, c'était un retry tout à fait ordinaire du processeur de paiement (même clé qu'un événement une minute avant)."),
    ("fix-hand-fake-race-05-sell-unlocked-and-transfer-order", "09-stock-concurrence", "detailed",
     "Deux incidents en production sur le stock des entrepôts, que je crois indépendants : (1) des articles vendus en trop quand "
     "deux paiements passent en même temps, (2) deux transferts de stock en sens inverse qui restent bloqués pour toujours. "
     "Les deux dépendent de l'entrelacement des opérations. Merci de rendre `sell` et `transfer` corrects pour tous les "
     "entrelacements ; les tests visibles ne permettent pas de le voir."),
]


@family("i18n-fr-fixbug", category="i18n", lang="mixed", kind="fix", n=len(FR), mode="fixture",
        summary="derived: bug reports written in French (js, go, python, bash), d1-d5")
def fr_fixbug(rng, n):
    for src, slug, style, prompt in take(FR, n):
        yield derive(src, prompt, slug, "fr", style=style)


DE = [
    ("shell-batch-rename-01-fix-ls-loop", "01-tidy-leerzeichen", "casual",
     "Moin, `tidy.sh` soll alle `.txt`-Dateien im Ordner in `.md` umbenennen. Das klappt auch, bis jemand eine Datei mit "
     "Leerzeichen oder Bindestrich im Namen hat. Kannst du das so fixen, dass jeder Dateiname funktioniert?"),
    ("shell-quoting-fixes-04-fix-heredoc-expansion", "02-heredoc-expandiert", "report",
     "`mkconfig.sh` schreibt eine `config.ini`, aber die Shell expandiert dabei `$HOME`, Backticks und `$5`, und in der Datei "
     "steht danach der falsche Text. Diese Stellen sollen wörtlich in der Datei landen (nur der Name wird eingesetzt)."),
    ("shell-makefile-repair-05-fix-recipe-lines-are-separate-shells", "03-make-cd-stage", "terse",
     "`make` bricht mit 'no manifest.txt in the current directory' ab: das `cd stage` im Rezept wirkt sich nicht auf die "
     "nächste Zeile aus. Bitte die Regel reparieren."),
    ("shell-strict-mode-fixes-03-fix-post-increment", "04-sum-sizes-stirbt", "report",
     "`sum-sizes.sh` zählt die Dateien in einem Verzeichnis und addiert ihre Größen, beendet sich aber gleich nach der "
     "ersten Datei, ohne irgendetwas auszugeben. Bitte reparieren."),
    ("shell-strict-mode-fixes-06-fix-sigpipe", "05-status-141", "detailed",
     "Ein Rätsel aus unserer CI: `firstword.sh` gibt das erste Wort der ersten nicht-leeren Zeile der Eingabe aus. Bei langen "
     "Eingaben endet das Skript mit Status 141, obwohl das Ergebnis korrekt ausgegeben wird. Finde bitte heraus, warum das so ist, "
     "und behebe es."),
    ("shell-posix-portability-07-posix-reverse-lines", "06-revlines-dash", "detailed",
     "Auf dem Build-Server gibt es nur `sh` (dash). `§0` gibt eine Datei rückwärts mit den ursprünglichen Zeilennummern aus, "
     "benutzt aber `§1` und eine C-artige Schleife. Bitte nach POSIX-`§2` portieren, ohne die Ausgabe zu verändern, auch nicht "
     "in den Sonderfällen."),
    ("shell-batch-rename-06-artist-title-year", "07-musik-umbenennen", "brief",
     "Unsere Musikdateien heißen `§0`, ich hätte sie aber lieber als `§1`. Schreib dafür bitte `§2`; im README stehen das genaue "
     "Muster und was mit Dateien passieren soll, die nicht passen."),
    ("shell-batch-rename-05-flatten-tree", "08-baum-flachklopfen", "brief",
     "Ich habe einen wild gewachsenen Baum aus Unterordnern und möchte jede Datei in einen einzigen Ordner `flat/` verschieben. "
     "Bei gleichen Namen darf nichts verloren gehen. Bitte schreib `tidy.sh` so, wie es im README steht."),
    ("shell-ops-scripts-02-dotenv-layers-with-references", "09-envmerge", "brief",
     "Neues Skript, bitte: `envmerge.sh` legt mehrere dotenv-Dateien übereinander, löst in den Endwerten die Referenzen "
     "`${NAME}` und `${NAME:-default}` auf und meldet zirkuläre Referenzen. Lies das README bitte gründlich, die Details "
     "sind wichtig."),
]


@family("i18n-de-shell", category="i18n", lang="bash", kind="fix", n=len(DE), mode="fixture",
        summary="derived: shell script fixes and tools requested in German, d1-d5")
def de_shell(rng, n):
    for src, slug, style, prompt in take(DE, n):
        yield derive(src, prompt, slug, "de", style=style)
