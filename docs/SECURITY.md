# Bezpečnosť a súkromie

- **NIKDY nepublikuj** `arenti_config.ini`, heslá, API tokeny, celý RTSP URI (môže obsahovať meno/heslo), logy obsahujúce identifikátory ani svoj FTP výpis s citlivými cestami.
- `.gitignore` chráni bežné omyly, ale pred commitom vždy over `git status` a `git diff --cached`.
- Používaj FTPS so zapnutým overovaním certifikátu; `ftp.example.org` nahraď názvom, ktorý certifikát naozaj pokrýva.
- FTP konto obmedz na adresár pre obrázky, ak to hosting umožňuje.
- Na produkčnej kamere nastav silné ONVIF heslo a nevystavuj ONVIF/RTSP priamo do internetu; prístup cez LAN/VPN.
- Prístupové údaje sú v súbore s právami `chmod 600`. V poznámkach, príspevkoch a Screenshotoch ich rozmaž.
- Verejná fotografia môže zobrazovať osoby, EČV alebo súkromný majetok; zverejňuj iba vhodný záber.
- Pred zverejnením na GitHube over licenčné práva k celému kódu (vrátane prípadných prevzatých úryvkov).
