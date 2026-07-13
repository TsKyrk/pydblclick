# pydblclick — Roadmap durcissement (post-0.5.1, 2026-07)

Issue d'une revue des évolutions v0.2.0 → v0.5.1 (directive `import pydblclick`,
bootstrap `.pyw`, découverte de uv). L'orientation générale — deux canaux
d'adoption : `register` (machine) et la directive (par script, pour la
distribution) — est saine ; les items ci-dessous corrigent les angles morts
identifiés, par priorité décroissante.

Chaque item contient un prompt autonome, prêt à donner à Claude (Sonnet).

---

## P1 — Corrections de comportement

### 1. Faux positif PowerShell : la directive n'est pas inerte dans une console pwsh

**Problème.** La détection double-clic pour `.py` dans
`pydblclick/__init__.py::_maybe_enable_import_fallback()` est « `PROMPT` absent
de l'environnement + stdin est un tty ». Or PowerShell (powershell.exe et pwsh)
ne définit pas la variable `PROMPT`, et son stdin est un tty. Vérifié sur
machine : `python script.py` lancé depuis une session PowerShell interactive
déclenche la relance à travers pydblclick et affiche le menu pause — alors que
la docstring du module promet « run from a console : plain-Python behavior
preserved ». L'heuristique `PROMPT` préexistait dans le moteur, mais la
directive l'étend à *tout* lancement du script, ce qui rend le faux positif
visible pour tous les utilisateurs PowerShell.

**Correction.** Le correctif existe déjà dans le même fichier depuis 0.5.0 :
`_launched_by_explorer()` retourne `False` dès qu'un shell (pwsh inclus) est
rencontré dans l'ascendance. L'utiliser aussi pour le cas `.py` quand `PROMPT`
est absent, au lieu du seul test tty.

**Prompt :**

```text
Dans le projet pydblclick (Windows, wrapper de scripts Python double-cliqués),
corrige un faux positif de détection de double-clic.

Contexte : dans pydblclick/__init__.py, _maybe_enable_import_fallback() décide
si la directive `import pydblclick` doit relancer le script à travers
`python -m pydblclick`. Pour un script .py, le test actuel est : la variable
d'environnement PROMPT est absente ET sys.stdin.isatty(). Problème : PowerShell
(powershell.exe et pwsh.exe) ne définit pas PROMPT et son stdin est un tty,
donc `python script.py` lancé depuis une console PowerShell interactive est
pris pour un double-clic → le script se termine sur le menu pause au lieu du
comportement plain-Python promis par la docstring du module (« run from a
console / a batch file (plain-Python behavior preserved) »).

Le module contient déjà la bonne primitive : _launched_by_explorer() (ajoutée
en 0.5.0 pour les .pyw) remonte l'ascendance des processus et retourne True si
explorer.exe est atteint avant tout shell/console host, False sinon (pwsh, cmd,
Windows Terminal, etc. sont dans la liste SHELLS).

Tâche :
1. Dans _maybe_enable_import_fallback(), pour le cas .py (stdin tty, PROMPT
   absent), exige EN PLUS _launched_by_explorer() == True avant d'activer le
   bootstrap. Le cas simulé (env var pydblclick_simulate_doubleclick ou
   pyexewrap_simulate_doubleclick) doit continuer à court-circuiter tous les
   tests, car les tests automatisés s'appuient dessus.
2. Mets à jour la docstring du module et les commentaires pour décrire la
   nouvelle logique.
3. Ajoute un test dans tests/test_import_fallback.py : un script .py avec la
   directive, lancé en sous-processus SANS variable de simulation et avec un
   environnement sans PROMPT, doit rester inerte (pas de relance, pas de menu
   pause) puisque l'ascendance du runner de test contient un shell. Inspire-toi
   du test existant test_pyw_directive_inert_without_explorer.
4. Vérifie que toute la suite pytest passe (les tests marqués
   PYDBLCLICK_UI_TESTS=1 sont exclus par défaut, c'est normal).

Contrainte : ne change pas le comportement du moteur lui-même
(_script_is_doubleclicked() dans pydblclick/__main__.py) dans ce lot — seulement
la directive d'import. Reste stdlib-only, Python >= 3.8, style du fichier.
```

### 2. `_launched_by_explorer` : passer les « hops » en allowlist

**Problème.** La design note (docs/pyw-import-directive-bootstrap.md) annonce
que la remontée d'ascendance « tolère les hops de lanceurs (py.exe, python.exe,
pythonw.exe, MSIX Python Manager) », mais le code enjambe en réalité
*n'importe quel* processus non listé dans `SHELLS` jusqu'à trouver
explorer.exe. Conséquence : un `.pyw` lancé par une application GUI quelconque
(bouton Run de PyCharm, gestionnaire de fichiers alternatif, app orchestrant
des scripts) a Explorer dans son ascendance → relance DETACHED avec
stdout/stderr capturés dans un log → **l'application appelante perd toute la
sortie**. Une blocklist de shells est structurellement incomplète (nushell,
ConEmu, terminaux exotiques, tout futur IDE).

**Correction.** Inverser la logique : n'enjamber que les lanceurs *connus*
(allowlist), et retourner `False` (inerte) devant tout parent inconnu.
Compromis assumé : les gestionnaires de fichiers alternatifs ne seront plus
traités comme un double-clic — l'inertie redonne le comportement Python normal,
c'est le défaut sûr.

**Prompt :**

```text
Dans le projet pydblclick, durcis la détection de double-clic .pyw dans
pydblclick/__init__.py::_launched_by_explorer().

Contexte : cette fonction snapshot la table des processus (ctypes +
CreateToolhelp32Snapshot) et remonte l'ascendance du processus courant. Logique
actuelle : True si explorer.exe est atteint avant tout processus de la
blocklist SHELLS (cmd, powershell, pwsh, conhost, Windows Terminal, ...) ; tout
processus inconnu est enjambé. Problème : la design note
docs/pyw-import-directive-bootstrap.md affirme que seuls les « launcher hops »
(py.exe, python.exe, pythonw.exe, MSIX Python Manager) sont tolérés, mais le
code enjambe n'importe quoi — donc un .pyw lancé par une app GUI (IDE type
PyCharm, gestionnaire de fichiers alternatif) est pris pour un double-clic et
relancé en mode DETACHED avec la sortie capturée dans un log, invisible pour
l'app appelante. Une blocklist de shells est incomplète par construction.

Tâche :
1. Inverse la logique : remplace la blocklist SHELLS par une allowlist de hops
   LAUNCHERS que la remontée est autorisée à enjamber : py.exe, pyw.exe,
   python.exe, pythonw.exe, python3.exe, et les exécutables du MSIX Python
   Manager (py-manager*, pymanager* — vérifie les noms réels dans
   https://github.com/python/pymanager, et regarde aussi
   pydblclick/winpyfiles/_assoc.py qui contient déjà la détection MSIX).
   Règles : parent == explorer.exe → True ; parent dans LAUNCHERS → continuer
   la remontée ; tout autre parent (shell, IDE, app inconnue, svchost) → False.
2. Garde le comportement best-effort : toute erreur → False (inerte).
3. Mets à jour la docstring de la fonction et la design note
   docs/pyw-import-directive-bootstrap.md pour refléter l'allowlist et le
   compromis (les gestionnaires de fichiers alternatifs ne déclenchent plus la
   directive ; l'inertie = comportement Python normal, défaut sûr).
4. Le test tests/test_import_fallback.py::test_pyw_directive_inert_without_explorer
   doit toujours passer. Ajoute un test unitaire de la logique de remontée pure
   si tu peux l'isoler (par exemple en factorisant la boucle de remontée dans
   une fonction pure prenant les dicts parent_of/name_of, testable sans
   snapshot réel).

Contrainte : stdlib-only, Python >= 3.8, Windows-only. Ne change pas la
signature publique. Attention : ce durcissement bénéficiera aussi au cas .py si
l'item « faux positif PowerShell » (utilisation de _launched_by_explorer pour
les .py) a été implémenté — les deux items sont compatibles et complémentaires.
```

### 3. PEP 723 : l'injection PYTHONPATH peut écraser les versions épinglées

**Problème.** Dans `pydblclick/__main__.py::_build_child_command()`, pour
rendre pydblclick importable dans l'environnement éphémère de `uv run`, le
site-packages *hôte* entier est mis en tête de `PYTHONPATH`. Or `PYTHONPATH`
précède le site-packages de l'environnement uv dans `sys.path` : si le script
déclare `requests==2.32` mais que l'hôte a requests 2.28, le script obtient
silencieusement 2.28. Cela vide la promesse PEP 723 dès qu'une dépendance
existe aussi côté hôte. (Préexiste à 0.2.0, mais la publication PyPI a ouvert
la solution propre.)

**Correction.** Utiliser `uv run --with pydblclick=={version}` (la version
installée, via `importlib.metadata`) et supprimer l'injection PYTHONPATH.
Garder l'injection en *fallback* uniquement quand la version locale n'est pas
déterminable (checkout de dev non installé) — mais alors via un répertoire
temporaire ne contenant qu'une junction/copie du package, pas le site-packages
entier.

**Prompt :**

```text
Dans le projet pydblclick, corrige un problème de shadowing de dépendances dans
l'exécution PEP 723.

Contexte : pydblclick/__main__.py::_build_child_command() exécute les scripts
qui déclarent un bloc PEP 723 (`# /// script`) via
`uv run --no-project [--python X] --with dep1 --with dep2 python -m
pydblclick._child script args`. Pour que pydblclick soit importable dans
l'environnement éphémère de uv, le code ajoute actuellement le site-packages
hôte (le parent du package pydblclick) en tête de PYTHONPATH. Problème :
PYTHONPATH précède le site-packages de l'environnement uv dans sys.path, donc
toute dépendance présente À LA FOIS dans l'environnement hôte et dans les
déclarations PEP 723 est résolue à la version HÔTE — les versions épinglées du
script sont silencieusement ignorées. Exemple : le script déclare
requests==2.32, l'hôte a requests 2.28 → le script tourne avec 2.28.

Tâche :
1. Remplace l'injection PYTHONPATH par `--with pydblclick=={version}` dans la
   commande uv, où version vient de importlib.metadata.version("pydblclick")
   (attention : Python >= 3.8, donc utilise importlib.metadata avec le fallback
   importlib_metadata inutile — 3.8 a importlib.metadata dans la stdlib).
   pydblclick est publié sur PyPI depuis 0.2.0, uv saura le résoudre.
2. Fallback dev : si importlib.metadata.version("pydblclick") lève
   PackageNotFoundError (checkout de dev lancé via PYTHONPATH sans
   installation), garde une injection PYTHONPATH mais ISOLE-la : crée un
   répertoire temporaire contenant uniquement une copie (shutil.copytree) du
   package pydblclick, et mets CE répertoire sur PYTHONPATH — pas le
   site-packages hôte entier. Nettoie le répertoire temporaire après le
   subprocess.run (le nettoyage best-effort dans un finally suffit).
3. Le child (pydblclick/_child.py) pose déjà builtins.pydblclick_customizations
   avant d'exécuter le script, donc le `import pydblclick` éventuel du script
   reste inerte dans l'environnement uv — ne touche pas à ça, mais vérifie que
   c'est toujours vrai.
4. Tests : dans tests/, ajoute ou adapte un test qui vérifie que PYTHONPATH
   n'est plus pollué par le site-packages hôte dans la commande uv (tu peux
   tester _build_child_command directement : construire la commande pour un
   script PEP 723 factice avec PYDBLCLICK_UV pointant vers un faux exécutable,
   et inspecter la commande et l'env retournés/mutés). Vérifie que la suite
   pytest passe.
5. Mets à jour le commentaire « pydblclick itself must be importable inside
   uv's ephemeral environment » et ARCHITECTURE.md si la section PEP 723 décrit
   l'ancien mécanisme.

Contrainte : hors ligne, --with pydblclick== échouera au premier lancement si
uv n'a pas le paquet en cache ; c'est acceptable (uv affiche une erreur claire
et le script est PEP 723 donc suppose déjà le réseau), mais mentionne-le dans
le CHANGELOG.
```

---

## P2 — Expérience de distribution

### 4. Machine nue : l'`ImportError` de la directive une-ligne flashe et disparaît

**Problème.** Sur une machine sans pydblclick, le double-clic d'un script
portant la directive une-ligne meurt en `ModuleNotFoundError`… dont la fenêtre
flashe et disparaît — précisément le symptôme que le projet combat. Le
destinataire ne lit jamais le commentaire `# optional: pip install pydblclick`.
Le README documente déjà une variante try/except de 3 lignes, mais en
post-scriptum.

**Correction.** Faire de la variante try/except la recommandation *par défaut*
pour la distribution (README + exemples), la une-ligne devenant le raccourci
pour les environnements maîtrisés.

**Prompt :**

```text
Dans le projet pydblclick, améliore la recommandation de distribution de la
directive `import pydblclick`.

Contexte : le README recommande d'ajouter en première ligne des scripts
distribués : `import pydblclick  # optional: pip install pydblclick -- or
delete this line`. Sur une machine où pydblclick n'est PAS installé, le
double-clic meurt en ModuleNotFoundError dont la console flashe et disparaît —
exactement le problème que pydblclick est censé résoudre — et le destinataire
ne lit jamais le commentaire. Le README contient déjà (section « Advanced
usage » ou fin de la section directive) une variante robuste de 3 lignes avec
try/except ImportError qui affiche un message et un input() de pause quand
PROMPT est absent de l'environnement.

Tâche :
1. Dans README.md, inverse la présentation : la variante try/except (3 lignes)
   devient la recommandation PAR DÉFAUT pour un script distribué à des
   destinataires inconnus ; la une-ligne reste présentée comme le raccourci
   quand on sait pydblclick déjà installé chez les destinataires. Garde le ton
   et la langue (anglais) du README.
2. Vérifie que la variante 3 lignes du README gère bien le cas .pyw : sous
   pythonw il n'y a pas de stdin, input() lèverait — le fallback doit rester
   silencieux dans ce cas (par exemple en enveloppant l'input dans un
   try/except, ou en le conditionnant à sys.stdin). Corrige la variante si
   nécessaire, en la gardant la plus courte possible.
3. Dans examples/, ajoute un exemple utilisant la variante try/except (nommage
   cohérent avec les paires existantes 01a/01b, par exemple
   01c_HelloWorld_WITH_pydblclick_import_tryexcept.py) avec les commentaires
   pédagogiques du même style que 01b.
4. Mets à jour examples/README.md et la docstring de pydblclick/__init__.py si
   elle mentionne la recommandation.

Ne change aucun comportement du code du package — c'est un lot documentation +
exemples uniquement.
```

### 5. Menu pause : durcissement contre les entrées bruitées (BOM, choix inconnus)

**Problème.** Documenté dans docs/pause-menu-double-print.md : un stdin
préfixé d'un BOM (pipe PowerShell) fait imprimer le menu deux fois, et tout
choix non reconnu re-boucle silencieusement sans feedback. Pas un bug
utilisateur réel (le double-clic donne une console interactive), mais un
durcissement à faible coût, déjà spécifié dans la note.

**Prompt :**

```text
Dans le projet pydblclick, applique le durcissement optionnel décrit dans
docs/pause-menu-double-print.md.

Contexte : pydblclick/_child.py::display_pause_prompt_and_menu() lit le choix
utilisateur avec input() et dispatche sur "c"/"i"/"r"/"" (Enter = quitter). Un
choix non reconnu re-boucle silencieusement en réimprimant le prompt. Cas
observé : PowerShell préfixe un BOM UTF-8 aux bytes qu'il pipe vers un process
natif, le BOM décodé devient un choix non vide non reconnu → le menu s'imprime
deux fois. La note docs/pause-menu-double-print.md documente le mécanisme
exact et propose le durcissement.

Tâche :
1. Normalise l'entrée avant dispatch : strip() + retrait du BOM (﻿).
2. Ajoute un feedback explicite sur choix non reconnu (else: un message bref
   du style "Unknown option." avant de re-boucler) au lieu du silence.
3. IMPORTANT (piège documenté dans la note) : le comportement single-print sur
   un vrai double-clic et sur les pipes OS normaux est CORRECT aujourd'hui —
   le test tests/test_import_fallback.py::test_import_inert_under_pydblclick
   asserte stdout.count("Press <Enter> to Quit.") == 1 et doit toujours passer.
4. Ajoute un test subprocess qui pipe un stdin préfixé de b"\xef\xbb\xbf\n" et
   vérifie que le menu ne s'imprime qu'une fois.
5. Mets à jour docs/pause-menu-double-print.md : la section « Optional
   hardening » devient « Fixed in <version> » avec une ligne de résumé.

Style : suis le code existant de _child.py, stdlib-only, Python >= 3.8.
```

---

## P3 — Dette de la roadmap 2026 (pivot)

### 6. Handler autonome : la registration dépend du Python qui a installé pydblclick

**Problème.** Dernière case non cochée de ROADMAP.md (Phase 2) : la commande
enregistrée dans le registre pointe vers le Python qui a pip-installé
pydblclick ; un upgrade ou une désinstallation de ce Python casse le
double-clic silencieusement. La directive d'import mitige (elle relance via
l'interpréteur courant, quel qu'il soit) mais ne couvre pas le canal
`register`. Avant de construire un exe (gros chantier), une étape intermédiaire
peu coûteuse : détecter et diagnostiquer la registration cassée.

**Prompt :**

```text
Dans le projet pydblclick (wrapper Windows de scripts Python double-cliqués),
améliore la résilience de la registration quand le Python enregistré a disparu.

Contexte : `pydblclick register` écrit dans le registre un ProgID
(pydblclick.PyFile / pydblclick.PywFile) dont la commande pointe vers
l'interpréteur qui a pip-installé pydblclick (chemin absolu vers python.exe /
pythonw.exe). Si ce Python est désinstallé ou déplacé (upgrade), le double-clic
casse silencieusement (Windows affiche une erreur générique ou rien). La
construction d'un exe autonome est prévue à terme (ROADMAP.md Phase 2) mais
pas pour ce lot.

Tâche, en deux volets :
1. Diagnostic : dans la commande `pydblclick diagnose` (voir pydblclick/_cli.py
   et pydblclick/winpyfiles/), ajoute une vérification : pour chaque ProgID
   pydblclick trouvé, extraire le chemin de l'exécutable de la commande shell
   open et vérifier os.path.isfile. Si l'exécutable n'existe plus, afficher un
   avertissement clair du style de l'avertissement MSIX existant ([!!]), avec
   la remédiation : relancer `pydblclick register` depuis un Python valide.
2. Auto-réparation à la registration : `pydblclick register` détecte s'il
   remplace une commande dont l'exécutable n'existe plus et le mentionne dans
   sa sortie (« previous registration pointed to a missing interpreter,
   repaired »).
3. Tests : ajoute des tests unitaires pour la fonction d'extraction du chemin
   d'exécutable depuis une commande de registre (guillemets, arguments) et
   pour la détection d'exécutable manquant. Ne touche pas au registre réel
   dans les tests automatisés — isole la logique pure et mocke les lectures
   registre comme le font les tests existants du sous-package winpyfiles.

Explore d'abord pydblclick/_cli.py et pydblclick/winpyfiles/ pour repérer où le
diagnostic et la registration sont implémentés, et suis leurs conventions
d'affichage ([OK] / [!!]).
```

### 7. Mineur — découverte de uv : fallback `python -m uv`

**Problème.** `_find_uv()` (0.5.1) sonde `PYDBLCLICK_UV`, le PATH, puis les
répertoires Scripts de l'interpréteur. Un dernier filet quasi gratuit : le
paquet PyPI `uv` est exécutable via `python -m uv`, ce qui couvre tout uv
pip-visible sans sonder de chemins.

**Prompt :**

```text
Dans le projet pydblclick, ajoute un dernier fallback à la découverte de uv.

Contexte : pydblclick/__main__.py::_find_uv() localise uv dans cet ordre :
env var PYDBLCLICK_UV, shutil.which("uv"), puis les répertoires Scripts de
l'interpréteur courant (schéma par défaut et --user) — ce dernier cas couvre
`pip install uv` sous le MSIX Python Manager qui ne met pas les Scripts sur le
PATH. Le paquet PyPI uv est aussi exécutable via `python -m uv` (son
__main__.py exécute le binaire embarqué).

Tâche :
1. Si tout échoue, teste si le module uv est importable dans l'interpréteur
   courant (importlib.util.find_spec("uv")) ; si oui, retourne une forme de
   commande représentant [sys.executable, "-m", "uv"]. Attention : _find_uv()
   retourne aujourd'hui un chemin (str) inséré tel quel en tête de la commande
   dans _build_child_command() — adapte le contrat (par exemple retourner une
   LISTE d'arguments dans tous les cas) proprement, en mettant à jour l'appel
   dans _build_child_command() et le message d'erreur uv-absent.
2. Mets à jour les tests existants de _find_uv / du chemin PEP 723 s'il y en a
   (cherche PYDBLCLICK_UV dans tests/) et ajoute un cas pour le nouveau
   fallback (monkeypatch de find_spec).
3. Une ligne dans CHANGELOG.md sous « Unreleased ».

Petit lot : ne refactore rien d'autre.
```

---

## Ordre suggéré

1 et 2 se renforcent (2 durcit la primitive que 1 généralise) : faire **2 puis
1**, ou ensemble. 3 est indépendant et corrige une violation silencieuse de
PEP 723 : à faire tôt. 4 et 5 sont des petits lots sans risque. 6 et 7 au fil
de l'eau.

| # | Item | Risque si ignoré | Taille |
|---|------|------------------|--------|
| 1 | Faux positif PowerShell (.py) | Menu pause intempestif pour tout utilisateur pwsh | S |
| 2 | Allowlist des hops (.pyw) | Sortie perdue quand un .pyw est lancé par une app GUI | S |
| 3 | Shadowing PYTHONPATH → uv | Versions PEP 723 épinglées silencieusement ignorées | M |
| 4 | Recommandation try/except | ImportError qui flashe chez le destinataire nu | S (docs) |
| 5 | Durcissement menu pause | Cosmétique (double print, silence) | S |
| 6 | Diagnostic Python disparu | Double-clic cassé silencieusement après upgrade Python | M |
| 7 | Fallback `python -m uv` | Cas rares de uv invisible | S |
