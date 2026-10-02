"""Derived answer-mode chat tasks in German and Hindi (Devanagari with English technical terms)."""
from fx import family

from ._derive import derive, take

DE = [
    ("chat-quick-time-02-diff", "01-dauer-zeit", "casual",
     "Moin! Wie lange ist es von 10:15 bis 11:50? Bitte als H:MM antworten. Danke dir!"),
    ("chat-quick-format-02-name", "02-name-umdrehen", "polite",
     "Mach bitte aus 'Castellano, Konrad' ein 'Vorname Nachname', also den Vornamen zuerst. Nur so nebenbei: Der Nachbar "
     "mäht gerade den Rasen, natürlich zur ungünstigsten Zeit. Vielen Dank!"),
    ("chat-code-output-01-py-up-d1", "03-python-ausgabe", "learner",
     "Kurze Frage aus meiner Lerngruppe (Vorbereitung aufs Vorstellungsgespräch), aber so etwas passiert wirklich im echten "
     "Code: eine handgetippte Liste aufräumen, Python 3.11.\n\n```python\n¶0\n```\n\n"
     "Gib mir bitte genau den Text aus, den das ausgibt, Zeile für Zeile."),
    ("chat-diff-apply-01-len", "04-diff-zeilen", "chatty",
     "Hallo! Ein Kollege hat mir einen Patch für unsere Service-Konfiguration geschickt, und ich möchte vorher wissen, wie die "
     "Datei danach aussieht. Die aktuelle Datei:\n\n```\n¶0\n```\n\nund der Diff:\n\n```\n¶1\n```\n\n"
     "Wie viele Zeilen hat die Datei, nachdem der Patch angewendet wurde?"),
    ("chat-date-offset-02-age_days", "05-kurs-tage", "chatty",
     "Hallo zusammen! Mein Kurs beginnt am Freitag, den 7. Januar 2028 und endet am Freitag, den 9. November 2029. "
     "Die Anzahl der Tage möchte ich in die Broschüre schreiben. Nebenbei: Der Nachbar mäht den Rasen gerade zur "
     "schlechtestmöglichen Zeit. Wie viele Tage sind das, wenn man den ersten und den letzten Tag mitzählt?"),
    ("chat-json-read-02-cancel_count", "06-bestell-export", "paste",
     "Hier ein Export aus dem Bestellsystem unseres kleinen Shops.\n\n```\n¶0\n```\n\n"
     "Wie viele Bestellungen sind storniert (cancelled), und wie viele Stück waren insgesamt in diesen stornierten Bestellungen?"),
    ("chat-probability-small-01-draw", "07-sicherungen", "long",
     "Hallo! Kurz gesagt (es wird nicht kurz): In einem Kasten liegen 9 Sicherungen, 4 davon sind durchgebrannt (der Rest ist "
     "in Ordnung). Ich greife blind 3 heraus und lege keine zurück. Wie hoch ist die Wahrscheinlichkeit, dass mindestens eine "
     "der 3 durchgebrannt ist? Gib sie als gekürzten Bruch an, zum Beispiel 7/20. Sorry für den Textblock und danke!"),
    ("chat-regex-match-07-findall", "08-regex-findall", "careful",
     "Guten Morgen. Ich schätze meine Regexe ständig falsch ein, deshalb frage ich lieber, bevor ich das ausliefere.\n\n"
     "```\n¶0\n```\n\nWie viele Einträge liefert `§0` zurück, und wie groß ist die Summe aller erfassten Zahlen, wenn man jedes "
     "erfasste Stück mit int() umwandelt?\n\nDas war's, danke.\n(Bitte nur Ziffern, ohne Tausendertrennzeichen.)"),
    ("chat-sql-reading-06-above_avg", "09-sql-null-avg", "quiz",
     "Entscheide bitte einen Streit in unserem Team: Was liefert diese Abfrage für diese Zeilen? (SQLite-Semantik.)\n\n"
     "```\n¶0\n```\n\nWelche einzelne Zahl kommt heraus? (Denk daran, wie SQL mit NULL in AVG und in Vergleichen umgeht.)\n\nDanke!"),
    ("chat-text-transform-06-names_sort2", "10-namensliste", "rushed",
     "Sorry, bin in Eile: Eine Ehrenamtliche hat unsere Anmeldeliste in eine Textdatei getippt, und ich räume sie gerade auf.\n\n"
     "```\n¶0\n```\n\nJede Zeile ist 'Nachname, Vorname' mit wilder Groß-/Kleinschreibung und Leerzeichen. Wandle sie in "
     "'Vorname Nachname' um (normale Schreibweise), sortiere die Liste dann nach Nachname (A bis Z, Groß-/Kleinschreibung "
     "egal), bei Gleichstand nach Vorname. Welcher Eintrag steht an Position 6 der sortierten Liste, und welche Position hat "
     "Farida Brandt? Nenne außerdem den letzten Eintrag der sortierten Liste."),
    ("chat-counting-small-08-seating2", "11-sitzordnung", "puzzle",
     "Wir setzen 7 Leute in eine einzelne Reihe mit 7 Stühlen: Freya, Anika, Ebony, Joaquin, Pavel, Delphine, Malik. Einige "
     "haben sich zerstritten, deshalb dürfen diese Paare nicht nebeneinander sitzen: Anika und Ebony; Ebony und Delphine; "
     "Anika und Joaquin. Auf wie viele verschiedene Arten kann die Reihe besetzt werden? Jede verschiedene Reihenfolge von "
     "links nach rechts zählt als eine Möglichkeit. (Nur Ziffern bitte, ohne Tausendertrennzeichen.) Brauche es bald."),
]


@family("i18n-de-chat", category="i18n", lang="text", kind="chat", n=len(DE), mode="answer",
        summary="derived: chat questions with computed answers in German (answers are digits, times, names)")
def de_chat(rng, n):
    for src, slug, style, prompt in take(DE, n):
        yield derive(src, prompt, slug, "de", style=style)


HI = [
    ("chat-quick-math-05-avg", "01-run-average", "terse",
     "मेरी पिछली तीन रन की टाइमिंग (मिनट में) 7, 19 और 13 थीं। औसत कितना हुआ?"),
    ("chat-sheet-formula-01-sum", "02-sheet-sum", "polite",
     "नमस्ते! मैं एक सहकर्मी की शीट ऑडिट कर रहा हूँ। संबंधित हिस्सा यह है (खाली सेल सचमुच खाली हैं, n/a टेक्स्ट है)। "
     "माफ़ कीजिए अगर थोड़ा बिखरा हुआ लगे, मीटिंगों के बीच जवाब दे रहा हूँ।\n\n```\n¶0\n```\n\n"
     "अगर मैं सेल E1 में `§0` डालूँ तो वह कौन-सी वैल्यू दिखाएगा? सिर्फ़ संख्या बताइए (दशमलव बिंदु के साथ, बिना मुद्रा चिह्न के)।"),
    ("chat-price-traps-02-tax_rev", "03-tax-reverse", "chatty",
     "देखिए, ऊनी कोट की रसीद पर बस ₹24.75 कुल लिखा है, टैक्स समेत। यहाँ टैक्स दर 6% है। वैसे बात ज़रूरी नहीं है, पर पड़ोसी "
     "ठीक इसी वक़्त लॉन की घास काट रहे हैं। इसमें से टैक्स से पहले की कीमत कितनी है और टैक्स ख़ुद कितना है? दोनों को सबसे "
     "नज़दीकी पैसे तक पूरा करें (दशमलव बिंदु के साथ)।"),
    ("chat-counting-small-01-handout", "04-raffle-prizes", "casual",
     "ऐसे ही एक सवाल: मेरे पास 9 एक जैसे रैफ़ल इनाम हैं जो 4 नाम वाले विजेताओं में बाँटने हैं। हर किसी को पूरी संख्या में इनाम "
     "मिलना चाहिए (शून्य भी चलेगा), लेकिन किसी को भी 6 से ज़्यादा नहीं। इन्हें कितने अलग-अलग तरीक़ों से बाँटा जा सकता है? दो तरीक़े "
     "तब अलग माने जाएँगे जब किसी विजेता को अलग संख्या में इनाम मिले।"),
    ("chat-file-modes-01-umask027-d2", "05-umask-bits", "terse",
     "Linux पर यह कमांड-क्रम चलाने के बाद permission bits कैसे दिखेंगे? पहले से डायरेक्टरी खाली है।\n\n```\n¶0\n```\n\n"
     "`§0` में `§1` के लिए permission वाले कॉलम में क्या दिखेगा (जैसे -rw-r--r--), और उसका octal mode क्या है?"),
    ("chat-cron-next-03-d2-20", "06-cron-agli-baar", "chatty",
     "नमस्ते, एक जल्दी का cron सवाल: रात की रिपोर्ट वाली स्क्रिप्ट की एंट्री `§0` है, और मशीन का समय UTC में है।\n\n"
     "Day-of-week में 0 = रविवार, 1 = सोमवार ... 6 = शनिवार होता है; रेंज दोनों सिरों समेत होती हैं, और `§1` या `§2` का मतलब है "
     "रेंज की शुरुआत से हर s-वाँ मान।\n\nअभी 2026-08-17 19:54 UTC हुए हैं। अगली 3 बार जब यह चलेगी, वे समय लिखिए, हर लाइन में एक, "
     "YYYY-MM-DD HH:MM फ़ॉर्मेट में। चाय चढ़ी है, इसलिए कुछ मिनट हैं मेरे पास। धन्यवाद :)"),
    ("chat-business-days-03-deadline", "07-sla-last-day", "formal",
     "सुप्रभात! सपोर्ट टिकट सोमवार 12 अक्टूबर 2026 को मिला। SLA 14 कार्यदिवस का है, जो आने के अगले दिन से गिना जाता है। "
     "(छोटी-सी बात: मैं गणित में कमज़ोर हूँ, इसलिए कृपया धैर्य रखिए।) कार्यदिवस यहाँ सोमवार से शुक्रवार हैं। जवाब देने की आख़िरी "
     "तारीख़ (YYYY-MM-DD) क्या है, और वह कौन-सा वार होगा?"),
    ("chat-earlier-mistake-02-fuel", "08-fuel-earlier-mistake", "paste",
     "आज पहले जो बात हुई थी वह नीचे है, उसके बाद मेरा अगला सवाल।\n\n```\nमैं: मेरी कार 100 km पर 6.5 लीटर पीती है और सफ़र 520 km का है। "
     "कितने लीटर लगेंगे?\n\nआप: 520 km यानी 520 / 100 = 5.2 सौ-km इकाइयाँ, और 5.2 x 6.5 = 23.8 लीटर।\n\n"
     "मैं: ईंधन 1.59 डॉलर प्रति लीटर है। कुल ईंधन ख़र्च कितना होगा (नज़दीकी सेंट तक), और अगर हम 4 यात्री इसे बराबर बाँटें तो "
     "हर एक कितना देगा (नज़दीकी सेंट तक)? और कितने लीटर, यह भी बताइए।\n```\n\nक्या आप इस बातचीत में मेरे आख़िरी संदेश का जवाब दे सकते हैं?"),
    ("chat-probability-small-08-game", "09-dice-game-expected", "puzzle",
     "अरे! स्कूल मेले में एक खेल है जिसमें एक सामान्य छह-फलक वाला पासा है। 2 आने पर -3 सिक्के, 3 आने पर +10 सिक्के, 5 आने पर +8 "
     "सिक्के और 6 आने पर +8 सिक्के मिलते हैं, और बाक़ी किसी भी संख्या पर कुछ नहीं मिलता। हर फेंक पर अपेक्षित भुगतान कितना है, "
     "सटीक संक्षिप्त भिन्न के रूप में (या पूर्ण संख्या)? ऋणात्मक संख्या को minus चिह्न के साथ लिखिए। बहुत धन्यवाद!"),
]


@family("i18n-hi-chat", category="i18n", lang="text", kind="chat", n=len(HI), mode="answer",
        summary="derived: chat questions with computed answers in Hindi (Devanagari plus English technical terms)")
def hi_chat(rng, n):
    for src, slug, style, prompt in take(HI, n):
        yield derive(src, prompt, slug, "hi", style=style)
