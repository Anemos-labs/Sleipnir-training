"""Native constrained-writing tasks in French (narrow no-break spaces, guillemets, lengths, bullet lists)."""
from fx import family

from ._writing import writing_task

N = " "
T = " "
TERMS = ".!?"


def phrase_sentences(p):
    return ("exactement %d phrases" % p["min"] if p["min"] == p["max"] else "entre %d et %d phrases" % (p["min"], p["max"])) + " (une phrase se termine par . ! ou ?)"


PH = {
    "sentences": phrase_sentences,
    "words": lambda p: "entre %d et %d mots en tout" % (p["min"], p["max"]),
    "include": lambda p: "à reprendre mot pour mot : " + ", ".join("« %s »" % w for w in p["words"]).replace("« ", "«" + N).replace(" »", N + "»"),
    "exclude": lambda p: "ne pas employer : " + ", ".join("« %s »" % w for w in p["words"]).replace("« ", "«" + N).replace(" »", N + "»"),
    "fr_spacing": lambda p: "respecter la typographie française : une espace fine insécable (U+202F) avant ? ! ; une espace insécable (U+00A0) avant : et à l'intérieur des "
    "guillemets « » ; jamais d'espace ordinaire à ces endroits",
    "marks": lambda p: "employer au moins une fois chacun de ces signes : " + " ".join(p["marks"]),
    "bullets": lambda p: "une liste d'exactement %d puces, une par ligne, chacune commençant par « - » (rien d'autre dans le fichier, à part le titre s'il y en a un)" % p["n"],
    "title": lambda p: "la première ligne est un titre qui commence par « # »",
}


def render(constraints):
    return "\n".join("- " + PH[c["kind"]](c) for c in constraints if c["kind"] in PH)


def sent(lo, hi):
    return {"kind": "sentences", "min": lo, "max": hi, "terms": TERMS}


SCENARIOS = [
    ("01-brocante", 3,
     "Je dois rédiger l'annonce de la brocante de notre village pour le panneau de la mairie. Les infos sont dans `infos.txt`.",
     "Événement : brocante de printemps\nDate : samedi 7 juin\nLieu : salle des fêtes\nSur place : buvette et crêpes\n",
     "annonce.md",
     [sent(3, 4), {"kind": "words", "min": 25, "max": 70}, {"kind": "include", "words": ["samedi 7 juin", "salle des fêtes"]}, {"kind": "fr_spacing"},
      {"kind": "marks", "marks": ["?", "!", ":"]}],
     "Envie de chasser les bonnes affaires" + T + "? La brocante de printemps se tient samedi 7 juin à la salle des fêtes" + N + ": vide-greniers, buvette et crêpes "
     "toute la journée. Venez nombreux" + T + "!"),
    ("02-courriel-client", 3,
     "Écris le corps d'un courriel pour dire à une cliente que sa commande a du retard (infos dans `infos.txt`). Ton aimable, pas de langue de bois.",
     "Cliente : Mme Fabre\nCommande : lampe en laiton, référence L-208\nNouveau délai : jeudi 12 juin\nGeste commercial : livraison offerte\n",
     "courriel.md",
     [sent(4, 5), {"kind": "words", "min": 40, "max": 85}, {"kind": "include", "words": ["Mme Fabre", "jeudi 12 juin", "L-208"]}, {"kind": "exclude", "words": ["malheureusement"]},
      {"kind": "fr_spacing"}, {"kind": "marks", "marks": ["«", "»", ":"]}],
     "Bonjour Mme Fabre, votre commande L-208 prendra un peu de retard. Notre fournisseur nous a répondu «" + N + "livraison la semaine prochaine" + N + "» et le nouveau délai est donc jeudi 12 juin. "
     "Pour nous faire pardonner" + N + ": la livraison est offerte. Nous restons à votre disposition si vous souhaitez en parler" + T + "; une réponse à ce message suffit. Bien cordialement."),
    ("03-message-absence", 2,
     "Rédige mon message d'absence automatique pour les congés d'été (détails dans `infos.txt`).",
     "Absence : du 21 juillet au 15 août\nRemplaçante : Camille Roux\nContact : camille.roux@example.org\nUrgences : téléphone du standard\n",
     "absence.md",
     [sent(3, 4), {"kind": "include", "words": ["15 août", "Camille Roux"]}, {"kind": "exclude", "words": ["malheureusement", "désolé"]}, {"kind": "fr_spacing"},
      {"kind": "marks", "marks": [":", ";"]}, {"kind": "words", "min": 25, "max": 60}],
     "Je suis absent du 21 juillet au 15 août. Pendant ce temps, Camille Roux me remplace" + N + ": vous pouvez lui écrire directement" + T + "; "
     "pour les urgences, appelez le standard. Je répondrai à mon retour."),
    ("04-legende-photo", 2,
     "Écris la légende d'une photo pour le bulletin municipal. Contexte dans `infos.txt`.",
     "Photo : les enfants du centre de loisirs plantent un chêne\nLieu : parc de la Mairie\nDate : 14 mars\nCitation de la directrice : « Chaque arbre est une promesse. »\n",
     "legende.md",
     [sent(2, 3), {"kind": "words", "min": 15, "max": 40}, {"kind": "include", "words": ["parc de la Mairie", "chêne"]}, {"kind": "fr_spacing"}, {"kind": "marks", "marks": ["«", "»"]}],
     "Le 14 mars, les enfants du centre de loisirs ont planté un chêne dans le parc de la Mairie. La directrice résume la journée en une phrase" + N + ": «" + N + "Chaque arbre est une promesse."
     + N + "» Merci à tous les participants."),
    ("05-liste-courses-voyage", 3,
     "Fais-moi une liste de ce qu'il faut emporter pour la randonnée de samedi, avec un titre. Le programme est dans `infos.txt`.",
     "Sortie : randonnée au lac Blanc\nDépart : samedi 6 h 30 au parking\nDurée : environ 5 heures\nMétéo : orages possibles l'après-midi\n",
     "liste.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 4}, {"kind": "include", "words": ["lac Blanc", "orages"]}, {"kind": "fr_spacing"}, {"kind": "marks", "marks": [":"]},
      {"kind": "words", "min": 25, "max": 70}],
     "# Randonnée au lac Blanc\n- Eau et en-cas pour environ 5 heures de marche.\n- Veste de pluie" + N + ": des orages sont possibles l'après-midi.\n"
     "- Chaussures de randonnée et chaussettes de rechange.\n- Rendez-vous samedi à 6 h 30 au parking, sans retard."),
    ("06-mot-d-excuse", 3,
     "Aide-moi à écrire un petit mot d'excuse à une voisine dont j'ai raté l'anniversaire. Les faits sont dans `infos.txt`.",
     "Voisine : Josette\nCe qui s'est passé : j'ai oublié son anniversaire samedi\nProposition : lui offrir un gâteau dimanche\n",
     "mot.md",
     [sent(4, 5), {"kind": "words", "min": 30, "max": 70}, {"kind": "include", "words": ["Josette", "dimanche"]}, {"kind": "exclude", "words": ["problème"]}, {"kind": "fr_spacing"},
      {"kind": "marks", "marks": ["!", "?"]}],
     "Chère Josette, quelle étourderie" + T + "! J'ai complètement oublié ton anniversaire samedi et je m'en veux. Accepterais-tu que je me fasse pardonner dimanche avec un gâteau" + T + "? "
     "Je passerai vers quinze heures. À bientôt et encore toutes mes excuses."),
]


@family("i18n-fr-write-notices", category="i18n", lang="text", kind="feature", n=len(SCENARIOS), mode="fixture",
        summary="native: French constrained-writing tasks (narrow no-break spaces, guillemets, lengths, bullets) checked by a hidden script")
def fr_write(rng, n):
    voices = [
        "{intro}\n\nContraintes :\n{rules}\n\nEnregistre le texte dans `{path}`.",
        "{intro} Voici les règles :\n{rules}\nMerci de mettre le résultat dans `{path}`.",
        "{intro}\n\n{rules}\n\n(Le texte va dans `{path}`.)",
    ]
    for i, (slug, d, intro, facts, path, constraints, solution) in enumerate(SCENARIOS[:n]):
        prompt = voices[i % 3].format(intro=intro, rules=render(constraints), path=path)
        yield writing_task(slug, d, prompt, {"infos.txt": facts}, path, constraints, solution, ["fr"], {"prompt_lang": "fr", "constraints": [c["kind"] for c in constraints]})
