"""Phrase books for the native bug-fix families: how a person writing in each language words a bug report.

Every entry has the same keys. Templates take {blurb} (domain context sentence), {title} (what the library is called),
{excerpt} (a CI excerpt), {lines} (bullet lines built from ``d_*``), {verify}, {path}, {end} (a closing constraint),
{diff1} (one probe difference) and {sal} (the salient failure line). Words that the corpus validator rejects as
placeholders must not appear (note Spanish and Portuguese "todo").
"""

PHRASES: dict[str, dict] = {
    "fr": dict(
        ci=["{blurb} Depuis une modification récente, les tests de {title} échouent. Voici ce que rapporte l'exécution en échec "
            "(extrait) :\n\n```\n{excerpt}\n```\n\nTrouve la cause racine et corrige-la. {end}"],
        report=["{blurb} Un utilisateur signale des résultats faux avec {title} :\n\n{lines}\n\nTrouve le bug dans le code et corrige-le. {end}",
                "Retour d'un utilisateur sur {title} :\n\n{lines}\n\nPeux-tu chercher d'où ça vient dans le code et le corriger ? {end}"],
        visible=["`{verify}` échoue sur le dépôt actuel de {title}. Rends le code correct. Il y a plus de vérifications que celles du "
                 "dépôt ; `README.md` décrit le comportement attendu. {end}"],
        spec=["{blurb} Après une modification récente, {title} ne se comporte plus comme le dit `README.md` dans au moins un cas. "
              "Le changement touchait `{path}`. Compare le code avec la spécification, trouve l'écart et corrige-le. {end}"],
        vague=["Quelque chose dans {title} s'est écarté de sa spécification (`README.md`). Je ne sais pas quel comportement est faux ; "
               "des vérifications cachées couvrent le comportement documenté. Trouve et corrige le défaut. {end}"],
        terse=["Bug dans {title} : {diff1}. À corriger. {end}", "{title} : {diff1}. Tu peux regarder ? {end}"],
        review=["Le dernier commit d'un collègue a touché `{path}` et la suite de {title} est rouge depuis. Un des échecs dit : `{sal}`. "
                "Merci de réparer. {end}"],
        end=["Ne modifie pas les tests.", "Garde l'API publique telle quelle.", "Corrige la cause, pas le symptôme.", "Le README fait foi.",
             "Ne touche pas au reste du code.", ""],
        d_wrong="`{e}` donne `{bad}` au lieu de `{good}`",
        d_raises="`{e}` lève `{bad}` au lieu de renvoyer `{good}`",
        d_expect_raise="`{e}` renvoie `{bad}` au lieu de lever `{good}`",
    ),
    "es": dict(
        ci=["{blurb} Desde un cambio reciente fallan las pruebas de {title}. Esto es lo que reporta la ejecución fallida "
            "(extracto):\n\n```\n{excerpt}\n```\n\nEncuentra la causa raíz y corrígela. {end}"],
        report=["{blurb} Un usuario reporta resultados incorrectos en {title}:\n\n{lines}\n\nBusca el error en el código y corrígelo. {end}",
                "Nos escribieron por {title}:\n\n{lines}\n\n¿Puedes ver qué pasa en el código y arreglarlo? {end}"],
        visible=["`{verify}` falla en el checkout actual de {title}. Haz que el código sea correcto. Hay más comprobaciones que las del "
                 "repositorio; `README.md` describe el comportamiento esperado. {end}"],
        spec=["{blurb} Tras una edición reciente, {title} ya no se comporta como dice `README.md` en al menos un caso. El cambio tocó "
              "`{path}`. Compara el código con la especificación, encuentra la discrepancia y corrígela. {end}"],
        vague=["Algo en {title} se ha desviado de su especificación (`README.md`). No sé qué comportamiento está mal; hay comprobaciones "
               "ocultas que cubren lo documentado. Encuentra y corrige el defecto. {end}"],
        terse=["Bug en {title}: {diff1}. Arréglalo. {end}", "{title}: {diff1}. ¿Lo miras? {end}"],
        review=["El último commit de un compañero tocó `{path}` y la suite de {title} está en rojo desde entonces. Uno de los fallos dice: "
                "`{sal}`. Por favor, repáralo. {end}"],
        end=["No cambies las pruebas.", "Mantén la API pública como está.", "Corrige la causa, no el síntoma.", "El README es la especificación.",
             "No toques código que no tenga que ver.", ""],
        d_wrong="`{e}` da `{bad}`, pero debería dar `{good}`",
        d_raises="`{e}` lanza `{bad}`, pero debería devolver `{good}`",
        d_expect_raise="`{e}` devuelve `{bad}`, pero debería lanzar `{good}`",
    ),
    "de": dict(
        ci=["{blurb} Seit einer kürzlichen Änderung schlagen die Prüfungen von {title} fehl. Das meldet der fehlgeschlagene Lauf "
            "(Auszug):\n\n```\n{excerpt}\n```\n\nFinde die Ursache und behebe sie. {end}"],
        report=["{blurb} Ein Nutzer meldet falsche Ergebnisse bei {title}:\n\n{lines}\n\nSuch den Fehler im Code und behebe ihn. {end}",
                "Rückmeldung zu {title}:\n\n{lines}\n\nKannst du dir den Code ansehen und das fixen? {end}"],
        visible=["`{verify}` schlägt im aktuellen Stand von {title} fehl. Bring den Code in Ordnung. Es gibt mehr Prüfungen als die im "
                 "Repository; `README.md` beschreibt das Sollverhalten. {end}"],
        spec=["{blurb} Nach einer kürzlichen Änderung verhält sich {title} in mindestens einem Fall nicht mehr so, wie `README.md` es "
              "beschreibt. Die Änderung betraf `{path}`. Vergleiche den Code mit der Spezifikation, finde die Abweichung und behebe sie. {end}"],
        vague=["In {title} ist etwas von der Spezifikation (`README.md`) abgewichen. Ich weiß nicht, welches Verhalten falsch ist; versteckte "
               "Prüfungen decken das dokumentierte Verhalten ab. Finde und behebe den Fehler. {end}"],
        terse=["Bug in {title}: {diff1}. Bitte fixen. {end}", "{title}: {diff1}. Schaust du mal? {end}"],
        review=["Der letzte Commit eines Kollegen hat `{path}` angefasst, und die Tests von {title} sind seitdem rot. Eine der Fehlermeldungen "
                "lautet: `{sal}`. Bitte reparieren. {end}"],
        end=["Ändere die Tests nicht.", "Die öffentliche API bleibt, wie sie ist.", "Behebe die Ursache, nicht das Symptom.",
             "Das README ist die Spezifikation.", "Fass unbeteiligten Code nicht an.", ""],
        d_wrong="`{e}` liefert `{bad}`, soll aber `{good}` liefern",
        d_raises="`{e}` wirft `{bad}`, soll aber `{good}` zurückgeben",
        d_expect_raise="`{e}` gibt `{bad}` zurück, soll aber `{good}` werfen",
    ),
    "pt": dict(
        ci=["{blurb} Depois de uma mudança recente, os testes de {title} começaram a falhar. Isto é o que a execução com falha relata "
            "(trecho):\n\n```\n{excerpt}\n```\n\nEncontre a causa raiz e corrija. {end}"],
        report=["{blurb} Um usuário relata resultados errados em {title}:\n\n{lines}\n\nAche o bug no código e corrija. {end}",
                "Chegou um relato sobre {title}:\n\n{lines}\n\nDá uma olhada no código e conserta? {end}"],
        visible=["`{verify}` falha no checkout atual de {title}. Deixe o código correto. Existem mais verificações do que as do repositório; "
                 "o `README.md` descreve o comportamento esperado. {end}"],
        spec=["{blurb} Depois de uma edição recente, {title} deixou de se comportar como o `README.md` diz em pelo menos um caso. A mudança "
              "mexeu em `{path}`. Compare o código com a especificação, encontre a divergência e corrija. {end}"],
        vague=["Alguma coisa em {title} se afastou da especificação (`README.md`). Não sei qual comportamento está errado; há verificações "
               "ocultas que cobrem o que está documentado. Encontre e corrija o defeito. {end}"],
        terse=["Bug em {title}: {diff1}. Corrige, por favor. {end}", "{title}: {diff1}. Consegue ver isso? {end}"],
        review=["O último commit de um colega mexeu em `{path}` e a suíte de {title} está vermelha desde então. Uma das falhas diz: `{sal}`. "
                "Por favor, conserte. {end}"],
        end=["Não altere os testes.", "Mantenha a API pública como está.", "Corrija a causa, não o sintoma.", "O README é a especificação.",
             "Não mexa no que não tem relação.", ""],
        d_wrong="`{e}` dá `{bad}`, mas deveria dar `{good}`",
        d_raises="`{e}` lança `{bad}`, mas deveria retornar `{good}`",
        d_expect_raise="`{e}` retorna `{bad}`, mas deveria lançar `{good}`",
    ),
    "it": dict(
        ci=["{blurb} Dopo una modifica recente i test di {title} hanno iniziato a fallire. Questo è ciò che riporta l'esecuzione fallita "
            "(estratto):\n\n```\n{excerpt}\n```\n\nTrova la causa e correggila. {end}"],
        report=["{blurb} Un utente segnala risultati sbagliati in {title}:\n\n{lines}\n\nTrova il bug nel codice e correggilo. {end}",
                "Segnalazione su {title}:\n\n{lines}\n\nPuoi dare un'occhiata al codice e sistemarlo? {end}"],
        visible=["`{verify}` fallisce sul checkout attuale di {title}. Rendi il codice corretto. Ci sono più controlli di quelli nel "
                 "repository; `README.md` descrive il comportamento atteso. {end}"],
        spec=["{blurb} Dopo una modifica recente, {title} non si comporta più come dice `README.md` in almeno un caso. La modifica ha "
              "toccato `{path}`. Confronta il codice con la specifica, trova la discrepanza e correggila. {end}"],
        vague=["Qualcosa in {title} si è allontanato dalla sua specifica (`README.md`). Non so quale comportamento sia sbagliato; controlli "
               "nascosti coprono il comportamento documentato. Trova e correggi il difetto. {end}"],
        terse=["Bug in {title}: {diff1}. Da correggere. {end}", "{title}: {diff1}. Ci dai un'occhiata? {end}"],
        review=["L'ultimo commit di un collega ha toccato `{path}` e la suite di {title} è rossa da allora. Uno dei fallimenti dice: `{sal}`. "
                "Per favore, ripara. {end}"],
        end=["Non modificare i test.", "Lascia l'API pubblica com'è.", "Correggi la causa, non il sintomo.", "Il README è la specifica.",
             "Non toccare il codice che non c'entra.", ""],
        d_wrong="`{e}` restituisce `{bad}`, ma dovrebbe restituire `{good}`",
        d_raises="`{e}` solleva `{bad}`, ma dovrebbe restituire `{good}`",
        d_expect_raise="`{e}` restituisce `{bad}`, ma dovrebbe sollevare `{good}`",
    ),
    "nl": dict(
        ci=["{blurb} Sinds een recente wijziging falen de controles van {title}. Dit meldt de mislukte run "
            "(uittreksel):\n\n```\n{excerpt}\n```\n\nZoek de oorzaak en los die op. {end}"],
        report=["{blurb} Een gebruiker meldt verkeerde resultaten van {title}:\n\n{lines}\n\nZoek de bug in de code en repareer hem. {end}",
                "Melding over {title}:\n\n{lines}\n\nKun je in de code kijken en dit fixen? {end}"],
        visible=["`{verify}` faalt op de huidige checkout van {title}. Maak de code correct. Er zijn meer controles dan die in de "
                 "repository; `README.md` beschrijft het bedoelde gedrag. {end}"],
        spec=["{blurb} Na een recente wijziging gedraagt {title} zich in minstens één geval niet meer zoals `README.md` zegt. De wijziging "
              "raakte `{path}`. Vergelijk de code met de specificatie, vind het verschil en herstel het. {end}"],
        vague=["Er is iets in {title} afgeweken van de specificatie (`README.md`). Ik weet niet welk gedrag fout is; verborgen controles "
               "dekken het gedocumenteerde gedrag. Vind en herstel het defect. {end}"],
        terse=["Bug in {title}: {diff1}. Graag fixen. {end}", "{title}: {diff1}. Kun je ernaar kijken? {end}"],
        review=["De laatste commit van een collega raakte `{path}` en de suite van {title} is sindsdien rood. Eén van de fouten zegt: "
                "`{sal}`. Repareer het alsjeblieft. {end}"],
        end=["Pas de tests niet aan.", "Laat de publieke API zoals hij is.", "Los de oorzaak op, niet het symptoom.", "De README is de specificatie.",
             "Blijf van code af die er niets mee te maken heeft.", ""],
        d_wrong="`{e}` geeft `{bad}`, maar moet `{good}` geven",
        d_raises="`{e}` gooit `{bad}`, maar moet `{good}` teruggeven",
        d_expect_raise="`{e}` geeft `{bad}` terug, maar moet `{good}` gooien",
    ),
    "pl": dict(
        ci=["{blurb} Po niedawnej zmianie testy {title} zaczęły się wywalać. Tak wygląda nieudany przebieg "
            "(fragment):\n\n```\n{excerpt}\n```\n\nZnajdź przyczynę źródłową i napraw ją. {end}"],
        report=["{blurb} Użytkownik zgłasza błędne wyniki w {title}:\n\n{lines}\n\nZnajdź błąd w kodzie i popraw go. {end}",
                "Zgłoszenie dotyczące {title}:\n\n{lines}\n\nMożesz zajrzeć do kodu i to naprawić? {end}"],
        visible=["`{verify}` nie przechodzi na obecnym stanie {title}. Doprowadź kod do poprawności. Sprawdzeń jest więcej niż te w "
                 "repozytorium; `README.md` opisuje zamierzone zachowanie. {end}"],
        spec=["{blurb} Po niedawnej edycji {title} w co najmniej jednym przypadku nie zachowuje się już tak, jak mówi `README.md`. Zmiana "
              "dotknęła `{path}`. Porównaj kod ze specyfikacją, znajdź rozbieżność i popraw ją. {end}"],
        vague=["Coś w {title} odbiegło od specyfikacji (`README.md`). Nie wiem, które zachowanie jest błędne; ukryte sprawdzenia obejmują "
               "udokumentowane zachowanie. Znajdź i napraw defekt. {end}"],
        terse=["Bug w {title}: {diff1}. Do poprawy. {end}", "{title}: {diff1}. Rzucisz okiem? {end}"],
        review=["Ostatni commit kolegi dotknął `{path}` i od tamtej pory zestaw testów {title} jest czerwony. Jedna z porażek mówi: `{sal}`. "
                "Proszę o naprawę. {end}"],
        end=["Nie zmieniaj testów.", "Zostaw publiczne API bez zmian.", "Napraw przyczynę, nie objaw.", "README jest specyfikacją.",
             "Nie ruszaj niepowiązanego kodu.", ""],
        d_wrong="`{e}` daje `{bad}`, a powinno dać `{good}`",
        d_raises="`{e}` rzuca `{bad}`, a powinno zwrócić `{good}`",
        d_expect_raise="`{e}` zwraca `{bad}`, a powinno rzucić `{good}`",
    ),
    "tr": dict(
        ci=["{blurb} Yakın zamandaki bir değişiklikten beri {title} testleri başarısız oluyor. Başarısız çalıştırmanın bildirdiği şu "
            "(çıktının bir bölümü):\n\n```\n{excerpt}\n```\n\nKök nedeni bul ve düzelt. {end}"],
        report=["{blurb} Bir kullanıcı {title} için yanlış sonuçlar bildiriyor:\n\n{lines}\n\nHatayı kodda bul ve düzelt. {end}",
                "{title} hakkında bir bildirim geldi:\n\n{lines}\n\nKoda bakıp düzeltebilir misin? {end}"],
        visible=["`{verify}` komutu {title} deposunun şu anki halinde başarısız oluyor. Kodu doğru hale getir. Depodakilerden daha fazla "
                 "kontrol var; `README.md` beklenen davranışı anlatıyor. {end}"],
        spec=["{blurb} Yakın zamandaki bir düzenlemeden sonra {title}, en az bir durumda `README.md` dosyasında yazdığı gibi davranmıyor. "
              "Değişiklik `{path}` dosyasına dokunmuş. Kodu şartnameyle karşılaştır, farkı bul ve düzelt. {end}"],
        vague=["{title} içinde bir şey şartnameden (`README.md`) sapmış. Hangi davranışın yanlış olduğunu bilmiyorum; gizli kontroller "
               "belgelenmiş davranışı kapsıyor. Hatayı bul ve düzelt. {end}"],
        terse=["{title} içinde hata: {diff1}. Düzelt. {end}", "{title}: {diff1}. Bakar mısın? {end}"],
        review=["Bir arkadaşın son commit'i `{path}` dosyasına dokundu ve o günden beri {title} test takımı kırmızı. Başarısızlıklardan biri "
                "şunu diyor: `{sal}`. Lütfen onar. {end}"],
        end=["Testleri değiştirme.", "Genel API'yi olduğu gibi bırak.", "Belirtiyi değil, nedeni düzelt.", "README şartnamedir.",
             "Alakasız koda dokunma.", ""],
        d_wrong="`{e}` ifadesi `{bad}` veriyor, ama `{good}` vermeli",
        d_raises="`{e}` ifadesi `{bad}` hatası fırlatıyor, ama `{good}` döndürmeli",
        d_expect_raise="`{e}` ifadesi `{bad}` döndürüyor, ama `{good}` hatası fırlatmalı",
    ),
    "ru": dict(
        ci=["{blurb} После недавнего изменения проверки {title} начали падать. Вот что сообщает упавший прогон "
            "(фрагмент):\n\n```\n{excerpt}\n```\n\nНайди первопричину и исправь. {end}"],
        report=["{blurb} Пользователь сообщает о неверных результатах в {title}:\n\n{lines}\n\nНайди ошибку в коде и исправь её. {end}",
                "Пришёл репорт по {title}:\n\n{lines}\n\nПосмотришь код и починишь? {end}"],
        visible=["`{verify}` падает на текущем состоянии {title}. Приведи код в порядок. Проверок больше, чем в репозитории; `README.md` "
                 "описывает задуманное поведение. {end}"],
        spec=["{blurb} После недавней правки {title} хотя бы в одном случае ведёт себя не так, как сказано в `README.md`. Изменение "
              "затронуло `{path}`. Сравни код со спецификацией, найди расхождение и исправь его. {end}"],
        vague=["Что-то в {title} разошлось со спецификацией (`README.md`). Я не знаю, какое поведение неверно; скрытые проверки покрывают "
               "описанное поведение. Найди и исправь дефект. {end}"],
        terse=["Баг в {title}: {diff1}. Исправь. {end}", "{title}: {diff1}. Глянешь? {end}"],
        review=["Последний коммит коллеги затронул `{path}`, и с тех пор набор тестов {title} красный. Одно из падений говорит: `{sal}`. "
                "Почини, пожалуйста. {end}"],
        end=["Тесты не меняй.", "Публичный API оставь как есть.", "Чини причину, а не симптом.", "README — это спецификация.",
             "Не трогай несвязанный код.", ""],
        d_wrong="`{e}` даёт `{bad}`, а должно давать `{good}`",
        d_raises="`{e}` бросает `{bad}`, а должно вернуть `{good}`",
        d_expect_raise="`{e}` возвращает `{bad}`, а должно бросать `{good}`",
    ),
    "ja": dict(
        ci=["{blurb}最近の変更以降、{title} のチェックが失敗するようになりました。失敗した実行の報告は次のとおりです(一部抜粋):\n\n"
            "```\n{excerpt}\n```\n\n根本原因を見つけて直してください。{end}"],
        report=["{blurb}ユーザーから {title} の結果がおかしいという報告がありました:\n\n{lines}\n\nコードからバグを突き止めて修正してください。{end}",
                "{title} について報告が来ています:\n\n{lines}\n\nコードを見て直してもらえますか?{end}"],
        visible=["{title} の現在のチェックアウトで `{verify}` が失敗します。コードを正しくしてください。リポジトリにあるもの以外にもチェックがあり、"
                 "`README.md` に意図された挙動が書いてあります。{end}"],
        spec=["{blurb}最近の編集のあと、{title} が少なくとも 1 つのケースで `README.md` の記述どおりに動かなくなりました。変更は `{path}` に及んでいます。"
              "コードと仕様を突き合わせて、食い違いを見つけて直してください。{end}"],
        vague=["{title} のどこかが仕様(`README.md`)からずれています。どの挙動が間違っているかは分かりません。隠しチェックが文書化された挙動を"
               "カバーしています。不具合を見つけて直してください。{end}"],
        terse=["{title} のバグ: {diff1}。修正をお願いします。{end}", "{title}: {diff1}。見てもらえますか?{end}"],
        review=["同僚の最後のコミットが `{path}` に触れて以来、{title} のスイートが赤いままです。失敗のひとつはこう言っています: `{sal}`。直してください。{end}"],
        end=["テストは変更しないでください。", "公開 API はそのままにしてください。", "症状ではなく原因を直してください。", "README が仕様です。",
             "無関係なコードには触れないでください。", ""],
        d_wrong="`{e}` が `{bad}` を返しますが、`{good}` を返すべきです",
        d_raises="`{e}` が `{bad}` を送出しますが、`{good}` を返すべきです",
        d_expect_raise="`{e}` が `{bad}` を返しますが、`{good}` を送出すべきです",
    ),
    "zh": dict(
        ci=["{blurb}最近一次改动之后，{title} 的检查开始失败。失败的运行报告如下（节选）：\n\n```\n{excerpt}\n```\n\n请找出根本原因并修复。{end}"],
        report=["{blurb}有用户反馈 {title} 的结果不对：\n\n{lines}\n\n请在代码里找出这个 bug 并修复。{end}",
                "收到一个关于 {title} 的反馈：\n\n{lines}\n\n能帮忙看看代码并修一下吗？{end}"],
        visible=["`{verify}` 在 {title} 当前的代码上失败。请把代码改正确。检查项比仓库里的更多，`README.md` 描述了预期行为。{end}"],
        spec=["{blurb}最近一次编辑之后，{title} 至少在一种情况下不再符合 `README.md` 的描述。改动涉及 `{path}`。请对照规范检查代码，找到不一致之处并修复。{end}"],
        vague=["{title} 里有什么地方偏离了规范（`README.md`）。我不知道是哪个行为有问题；隐藏的检查覆盖了文档中描述的行为。请找出缺陷并修复。{end}"],
        terse=["{title} 有个 bug：{diff1}。请修复。{end}", "{title}：{diff1}。帮忙看看？{end}"],
        review=["同事的最后一次提交改动了 `{path}`，之后 {title} 的测试一直是红的。其中一个失败写着：`{sal}`。请修好它。{end}"],
        end=["不要修改测试。", "公共 API 保持不变。", "修复原因，而不是症状。", "以 README 为准。", "不要动无关的代码。", ""],
        d_wrong="`{e}` 得到 `{bad}`，但应该得到 `{good}`",
        d_raises="`{e}` 抛出 `{bad}`，但应该返回 `{good}`",
        d_expect_raise="`{e}` 返回 `{bad}`，但应该抛出 `{good}`",
    ),
    "ko": dict(
        ci=["{blurb} 최근 변경 이후 {title}의 검사가 실패하기 시작했습니다. 실패한 실행이 보고하는 내용은 다음과 같습니다(일부 발췌):\n\n"
            "```\n{excerpt}\n```\n\n근본 원인을 찾아서 고쳐 주세요. {end}"],
        report=["{blurb} 사용자가 {title}에서 잘못된 결과가 나온다고 제보했습니다:\n\n{lines}\n\n코드에서 버그를 찾아 수정해 주세요. {end}",
                "{title} 관련 제보가 들어왔어요:\n\n{lines}\n\n코드를 한번 보고 고쳐 주실 수 있나요? {end}"],
        visible=["{title}의 현재 체크아웃에서 `{verify}` 명령이 실패합니다. 코드를 올바르게 만들어 주세요. 저장소에 있는 것보다 검사 항목이 더 많고, "
                 "`README.md`에 의도된 동작이 설명되어 있습니다. {end}"],
        spec=["{blurb} 최근 수정 이후 {title}의 동작이 적어도 한 경우에서 `README.md`에 적힌 것과 달라졌습니다. 변경은 `{path}` 파일에 닿아 있었습니다. "
              "코드를 명세와 비교해서 어긋난 부분을 찾아 고쳐 주세요. {end}"],
        vague=["{title}의 어딘가가 명세(`README.md`)에서 벗어났습니다. 어떤 동작이 틀렸는지는 모르겠고, 숨겨진 검사가 문서에 적힌 동작을 다룹니다. "
               "결함을 찾아서 고쳐 주세요. {end}"],
        terse=["{title} 버그: {diff1}. 수정 부탁드립니다. {end}", "{title}: {diff1}. 한번 봐 주실래요? {end}"],
        review=["동료의 마지막 커밋이 `{path}` 파일을 건드린 뒤로 {title}의 테스트 스위트가 계속 빨간색입니다. 실패 중 하나는 이렇게 말합니다: `{sal}`. "
                "고쳐 주세요. {end}"],
        end=["테스트는 수정하지 마세요.", "공개 API는 그대로 두세요.", "증상이 아니라 원인을 고쳐 주세요.", "README가 명세입니다.",
             "관련 없는 코드는 건드리지 마세요.", ""],
        d_wrong="`{e}` → 현재 `{bad}`, 기대값 `{good}`",
        d_raises="`{e}` → 현재 `{bad}` 예외 발생, 기대값 `{good}`",
        d_expect_raise="`{e}` → 현재 `{bad}` 반환, 기대 동작은 `{good}` 예외",
    ),
    "hi": dict(
        ci=["{blurb} हाल के बदलाव के बाद {title} की जाँचें फेल होने लगीं। फेल हुई रन यह रिपोर्ट करती है (अंश):\n\n```\n{excerpt}\n```\n\n"
            "मूल कारण खोजकर ठीक कीजिए। {end}"],
        report=["{blurb} एक उपयोगकर्ता ने {title} में ग़लत नतीजों की शिकायत की है:\n\n{lines}\n\nकोड में बग ढूँढिए और ठीक कीजिए। {end}",
                "{title} के बारे में रिपोर्ट आई है:\n\n{lines}\n\nज़रा कोड देखकर इसे ठीक कर देंगे? {end}"],
        visible=["{title} के मौजूदा चेकआउट पर `{verify}` फेल हो रहा है। कोड को सही कीजिए। रिपॉज़िटरी में मौजूद जाँचों से ज़्यादा जाँचें हैं; "
                 "`README.md` में अपेक्षित व्यवहार लिखा है। {end}"],
        spec=["{blurb} हाल के संपादन के बाद {title} कम से कम एक मामले में `README.md` के बताए अनुसार व्यवहार नहीं कर रहा। बदलाव ने `{path}` को छुआ था। "
              "कोड की तुलना विनिर्देश से कीजिए, फ़र्क़ ढूँढिए और ठीक कीजिए। {end}"],
        vague=["{title} में कुछ विनिर्देश (`README.md`) से भटक गया है। मुझे नहीं पता कौन-सा व्यवहार ग़लत है; छिपी हुई जाँचें दस्तावेज़ में लिखे व्यवहार को "
               "कवर करती हैं। खोट ढूँढिए और ठीक कीजिए। {end}"],
        terse=["{title} में बग: {diff1}। ठीक कर दीजिए। {end}", "{title}: {diff1}। देख लेंगे? {end}"],
        review=["एक साथी के आख़िरी commit ने `{path}` को छुआ और तब से {title} का सूट लाल है। एक फेलियर कहता है: `{sal}`। कृपया इसे ठीक कीजिए। {end}"],
        end=["टेस्ट मत बदलिए।", "पब्लिक API जैसी है वैसी रखिए।", "लक्षण नहीं, कारण ठीक कीजिए।", "README ही विनिर्देश है।",
             "असंबंधित कोड को मत छुइए।", ""],
        d_wrong="`{e}` का नतीजा `{bad}` आता है, जबकि `{good}` आना चाहिए",
        d_raises="`{e}` से `{bad}` उठता है, जबकि `{good}` लौटना चाहिए",
        d_expect_raise="`{e}` `{bad}` लौटाता है, जबकि `{good}` उठना चाहिए",
    ),
    "ar": dict(
        ci=["{blurb} منذ تعديل حديث بدأت فحوص {title} تفشل. هذا ما يبلغ عنه التشغيل الفاشل (مقتطف):\n\n```\n{excerpt}\n```\n\n"
            "ابحث عن السبب الجذري وأصلحه. {end}"],
        report=["{blurb} أبلغ أحد المستخدمين عن نتائج خاطئة في {title}:\n\n{lines}\n\nتتبّع الخطأ في الكود وأصلحه. {end}",
                "وصلنا بلاغ عن {title}:\n\n{lines}\n\nهل يمكنك إلقاء نظرة على الكود وإصلاحه؟ {end}"],
        visible=["الأمر `{verify}` يفشل على النسخة الحالية من {title}. اجعل الكود صحيحًا. توجد فحوص أكثر من تلك الموجودة في المستودع؛ "
                 "والملف `README.md` يصف السلوك المقصود. {end}"],
        spec=["{blurb} بعد تعديل حديث لم يعد {title} يتصرف كما يقول `README.md` في حالة واحدة على الأقل. التعديل لمس الملف `{path}`. "
              "قارن الكود بالمواصفات، واعثر على الاختلاف وأصلحه. {end}"],
        vague=["هناك شيء في {title} ابتعد عن المواصفات (`README.md`). لا أعرف أي سلوك خاطئ؛ فحوص مخفية تغطي السلوك الموثّق. "
               "اعثر على العيب وأصلحه. {end}"],
        terse=["خلل في {title}: {diff1}. أصلحه من فضلك. {end}", "{title}: {diff1}. هل تلقي نظرة؟ {end}"],
        review=["آخر commit لزميل لمس `{path}` ومنذ ذلك الحين وفحوص {title} حمراء. أحد الإخفاقات يقول: `{sal}`. أصلحه من فضلك. {end}"],
        end=["لا تعدّل الاختبارات.", "أبقِ الواجهة العامة (API) كما هي.", "أصلح السبب لا العَرَض.", "ملف README هو المواصفات.",
             "لا تلمس كودًا لا علاقة له بالموضوع.", ""],
        d_wrong="`{e}` يعطي `{bad}`، لكن المفروض أن يعطي `{good}`",
        d_raises="`{e}` يطلق `{bad}`، لكن المفروض أن يعيد `{good}`",
        d_expect_raise="`{e}` يعيد `{bad}`، لكن المفروض أن يطلق `{good}`",
    ),
    "id": dict(
        ci=["{blurb} Sejak perubahan baru-baru ini, pemeriksaan {title} mulai gagal. Inilah yang dilaporkan oleh proses yang gagal "
            "(cuplikan):\n\n```\n{excerpt}\n```\n\nCari akar masalahnya dan perbaiki. {end}"],
        report=["{blurb} Seorang pengguna melaporkan hasil yang salah dari {title}:\n\n{lines}\n\nTelusuri bug di kodenya dan perbaiki. {end}",
                "Ada laporan soal {title}:\n\n{lines}\n\nTolong lihat kodenya dan benerin ya. {end}"],
        visible=["`{verify}` gagal pada checkout {title} saat ini. Buat kodenya benar. Ada lebih banyak pemeriksaan daripada yang ada di "
                 "repositori; `README.md` menjelaskan perilaku yang dimaksud. {end}"],
        spec=["{blurb} Setelah suntingan baru-baru ini, {title} tidak lagi berperilaku seperti yang tertulis di `README.md` pada setidaknya "
              "satu kasus. Perubahan itu menyentuh `{path}`. Bandingkan kode dengan spesifikasi, temukan ketidaksesuaiannya, lalu perbaiki. {end}"],
        vague=["Ada sesuatu di {title} yang menyimpang dari spesifikasinya (`README.md`). Saya tidak tahu perilaku mana yang salah; "
               "pemeriksaan tersembunyi mencakup perilaku yang terdokumentasi. Temukan dan perbaiki cacatnya. {end}"],
        terse=["Bug di {title}: {diff1}. Tolong diperbaiki. {end}", "{title}: {diff1}. Bisa dicek? {end}"],
        review=["Commit terakhir seorang rekan menyentuh `{path}` dan sejak itu suite {title} merah. Salah satu kegagalannya berbunyi: `{sal}`. "
                "Tolong diperbaiki. {end}"],
        end=["Jangan ubah tes.", "Biarkan API publiknya seperti sekarang.", "Perbaiki penyebabnya, bukan gejalanya.", "README adalah spesifikasinya.",
             "Jangan sentuh kode yang tidak terkait.", ""],
        d_wrong="`{e}` menghasilkan `{bad}`, padahal seharusnya `{good}`",
        d_raises="`{e}` melempar `{bad}`, padahal seharusnya mengembalikan `{good}`",
        d_expect_raise="`{e}` mengembalikan `{bad}`, padahal seharusnya melempar `{good}`",
    ),
}
