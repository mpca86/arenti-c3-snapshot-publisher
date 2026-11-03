# Make.com – monitor čerstvosti fotografie

Make scenár je **voliteľný**, funguje nezávisle od Linux notebooku. Nie je súčasťou Python runtime a **nie je pribalený export Make blueprintu** (aby sa nezverejňovali interné väzby, kontakty ani prístupové údaje).

Príklad produkčného nasadenia: HTTP `HEAD` s cache-busting `?check={{formatDate(now; "x")}}` a `Cache-Control: no-cache` na `https://hybe.lovcimrazov.sk/camera/latest.jpg`.

Postup:
1. Spúšťaj scenár približne každých **300 s**.
2. Over úspešnú odpoveď `200` a hlavičku `Last-Modified`.
3. Čas `Last-Modified` interpretuj v UTC; porovnaj ho s aktuálnym časom. Starší ako **15 minút** => `DOWN`. Pri HTTP chybe, neplatnom dátume alebo chýbajúcej hlavičke tiež `DOWN`.
4. Uchovávaj posledný stav (`OK` / `DOWN`) v Make **Data Store**.
5. Pošli e-mail len pri zmene `OK → DOWN` a `DOWN → OK`, až potom zapíš nový stav; pri emailovej chybe dávaj pozor na opakovanie.
6. Testuj skutočné výpadky, obnovenie a opakované kontroly; neodosielaj testovacie e-maily náhodne do ostrej prevádzky.

Konkrétny Make scenár je súkromným nasadením vlastníka a nie je automaticky prenosný na iný účet. Pre nový účet je potrebné nanovo zvoliť pripojenie SMTP a Data Store.

**Poznámka k cache:** webserver môže vracať `Cache-Control: public, max-age=31557600`. Unikátny query parameter obchádza bežné cache kľúče, avšak kompatibilita závisí od proxy vrstvy; presný čas kontroluj vo vrátených hlavičkách, nie podľa vizuálneho dátumu na obrázku.
