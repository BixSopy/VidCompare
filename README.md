# VidCompare

Compare la qualité de deux fichiers vidéo locaux et donne une note sur 100 à chacun.
Tout se passe sur votre PC : aucun envoi de fichier.

## Lancer

Double-cliquez sur `lancer.bat` (il crée l'environnement Python au premier lancement).
En ligne de commande :

    lancer.bat                      # fenêtre
    lancer.bat A.mkv B.mkv          # rapport texte
    lancer.bat A.mkv B.mkv --profil "Home cinéma"

## Nouveautés de la V5 (fiabilité et vitesse)

- **Scan deux fois plus rapide** pour les vidéos SDR : un seul appel `ffprobe` au lieu de deux (le second ne sert
  que pour le HDR10+, donc seulement pour une vidéo HDR).
- **Deux files de tâches** : analyser une case A ou B n'attend plus un scan de 3000 fichiers.
- **Pistes d'amélioration paginées** : 50 lignes puis « Afficher plus ». La page n'est plus redessinée quand rien
  n'a changé.
- **Garde « mêmes versions »** : avant les images et le VMAF, VidCompare compare durée, cadence, format d'image
  et chapitres. Si les durées diffèrent (écart d'au moins 1 minute et 1 %), un avertissement s'affiche et la mesure
  VMAF demande une confirmation.
- **VMAF corrigé** : seule la vidéo comparée est ramenée à la cadence de la référence. Une réserve s'affiche pour
  le HDR, où le VMAF est peu fiable.
- **Images côte à côte** : les extraits sont extraits en parallèle et gardés en mémoire.
- **Journal d'erreurs** : `%APPDATA%\VidCompare\vidcompare.log` (Réglages > Diagnostic > Ouvrir le dossier du
  journal). Une erreur du moteur s'affiche avec son vrai message au lieu de « Le moteur ne répond pas ».
- **Dossiers temporaires** nettoyés à la fermeture et au lancement.
- **Accessibilité** : texte gris faible à 4,9 de contraste (norme : 4,5), bordures des champs à 3,5 ou plus,
  fenêtres qui retiennent le focus clavier, le rendent au bouton d'origine et ont un nom pour les lecteurs d'écran.
- **Versions** : numéro affiché en bas du menu, dépôt Git local avec les étiquettes `v4` et `v5`.
- **Tests** : 104 (dont 5 avec un vrai FFmpeg, ignorés s'il est absent).

## Interface (V4)

Interface web moderne dans une vraie fenêtre (`pywebview`, composant WebView2 de Windows 11) :

- **Menu à gauche** : Comparer, Bibliothèque (classement et pistes d'amélioration), Historique, Réglages.
- **Thèmes** : Cinéma (sombre) et OLED (noir pur), au bas du menu ou dans les Réglages.
- **Comparer** : deux cases A et B (glisser-déposer, boutons, magnet, rapport MediaInfo), puis le verdict
  en anneaux, les raisons principales, une barre par critère. Le tableau complet, l'explication, les alertes
  et la comparaison d'image (images côte à côte, VMAF) se déplient à la demande.
- Le code de l'interface est dans `ui/` (HTML, CSS, JavaScript sans dépendance). Le moteur Python est dans
  `vidcompare/` ; `vidcompare/webapp.py` est ce que l'interface appelle.

Tester l'interface dans un navigateur, sans fenêtre : `python -m vidcompare.webapp --dev`, puis ouvrir
http://127.0.0.1:5174/ (les boutons « Choisir » demandent alors un chemin à taper).

Construire le programme : `pyinstaller --windowed --name VidCompare --add-data "ui;ui" --collect-all webview
--collect-all pythonnet --collect-all clr_loader run_app.py`, puis copier `ffprobe.exe` et `ffmpeg.exe` dans `bin/`.

## Prérequis : FFmpeg

L'analyse des fichiers utilise `ffprobe`. Installation : `winget install Gyan.FFmpeg`.
Sinon, indiquez `ffprobe.exe` dans l'application, ou placez-le dans le dossier `bin/`,
ou définissez la variable `VIDCOMPARE_FFPROBE`.

## Pistes d'amélioration (onglet dédié)

Ajoutez plusieurs dossiers (films, séries). Le logiciel lit tous les fichiers, puis liste ce qui gagnerait
le plus à exister en meilleure qualité :

- **Films** et **séries** dans deux tableaux séparés. Une série est regroupée par saison.
- Classement par **gain possible** : le plus gros écart entre la note actuelle et la note visée en premier.
- Pour chaque ligne : les 3 critères à améliorer en priorité (« HDR : SDR → DV P7, +11,9 pts »).
- **Viser** : « Le meilleur possible (4K Remux) », « Très bon (4K ou BluRay) » ou « Correct (1080p BluRay) ».
  La cible tient compte de votre matériel (Réglages) : inutile de viser du Dolby Vision si votre TV ne le lit pas.
- Les analyses sont mémorisées (`%APPDATA%\VidCompare\cache.json`) : un second scan ne relit que les fichiers
  nouveaux ou modifiés.
- Export CSV de la liste. La liste donne des **critères à viser**, jamais des liens de téléchargement.

## Ce que ajoute la V2

- **Torrents et magnets** : fichiers `.torrent` et liens `magnet:` (glisser-déposer ou boutons).
  Le contenu n'est pas lu : source, résolution, codec, HDR et audio viennent du nom, le débit est
  estimé avec la taille et une durée supposée (110 min, réglable). Un « remux » de 12 Go est repéré comme faux.
- **Classement** de plusieurs éléments, ou d'un **dossier entier** (300 vidéos au maximum), avec export CSV.
- **Matériel de lecture** : Dolby Vision, HDR10+, DTS, TrueHD, Atmos, HEVC, AV1, résolution maximale.
  Ce qui n'est pas lu est pénalisé (Dolby Vision lu en HDR10, piste DTS ignorée...).
- **Rapport qualité/taille** : « +10,2 points pour 43 Go de plus, soit 0,24 pt par Go ».
- **Langues** : alerte si la piste française est nettement moins bonne que la meilleure, ou s'il n'y a ni audio ni sous-titres français.
- **Réputation des groupes** (facultatif) : créez `groupes.json` à côté du programme,
  par exemple `{"NOMDUGROUPE": 3, "AUTRE": -5}` (de -10 à +10 points). Aucune valeur par défaut.
- Export du rapport de comparaison en `.txt`.

Console : `VidCompare.exe A.mkv B.torrent C.mkv --profil "Home cinéma" --sortie rapport.txt`
(2 éléments : comparaison détaillée, 3 ou plus : classement).

## Ce que fait la V1

- Lit les vraies caractéristiques : résolution, codec, débit, profondeur de bits,
  HDR10 / HDR10+ / Dolby Vision (profil 5, 7, 8), pistes audio (TrueHD, Atmos, DTS-HD MA, DTS:X...).
- Note chaque critère d'après la « Matrice Qualité Vidéo », puis calcule une note pondérée.
- **Débit par pixel** : un « 4K » ou un « BluRay » très compressé est pénalisé.
- **Détection de faux** : compare le nom du fichier avec le contenu réel (fausse 4K, Dolby Vision
  absent, remux au débit trop bas, Atmos annoncé mais absent...).
- **Verdict expliqué** : points gagnés par critère, pour chaque fichier.
- **Poids réglables** : profils Équilibré, Home cinéma, Écran SDR, ou curseurs libres.
- Un fichier `.iso` est ouvert via FFmpeg (protocole `bluray:`). S'il est illisible, seul son nom est noté.

## Limites connues

- La source (Remux, WEB-DL...) ne figure pas dans le fichier : elle vient du nom, corrigée par le débit.
- Atmos n'est détecté que par les versions récentes de ffprobe.
- HDR10+ est cherché sur la première image seulement.
- Les notes sont des propositions issues du consensus des guides communautaires, pas un standard.

## Ce qu'ajoute la V3

- **Langue souhaitée** (Réglages > Lecture et langue) : « VF ou sous-titres » retire 5 points aux versions sans
  français, « VF obligatoire » en retire 8 et note la piste française au lieu de l'originale. Pour un torrent,
  la langue se lit dans le nom (MULTi, VFF, TRUEFRENCH, VOSTFR...). La ligne « Langue » apparaît dans le tableau.
- **Réputation des groupes** (Réglages > Groupes de release) : un tableau à remplir, de -10 à +10 points par groupe.
  Enregistré dans `%APPDATA%\VidCompare\groupes.json`. Vide au départ.
- **Historique** : chaque comparaison est gardée (`%APPDATA%\VidCompare\historique.json`), on peut la rouvrir,
  supprimer ou exporter en CSV. La même paire comparée de nouveau met à jour sa ligne.
- **Rapport MediaInfo** : le bouton « Coller un rapport MediaInfo… » d'une case lit les vraies pistes
  (HDR, audio, débit) d'un rapport collé en français ou en anglais, sans rien télécharger.
- **Comparaison visuelle** (deux fichiers vidéo locaux) : images côte à côte (3 instants) et score **VMAF**.
  Le meilleur fichier sert de référence ; le score dit à quel point l'autre lui ressemble (95 et plus : quasi
  indiscernable). Mesure sur 3 extraits de 8 s, HDR converti en SDR. Demande FFmpeg avec libvmaf (build « full »).

Choix assumé : le logiciel ne télécharge rien depuis un torrent, pas même un fragment. Pour des vraies pistes
sans fichier, utilisez le rapport MediaInfo.

## Organisation

    vidcompare/parse_name.py   lecture du nom de release (titre, saison, langues)
    vidcompare/probe.py        lecture ffprobe
    vidcompare/mediainfo.py    lecture d'un rapport MediaInfo collé
    vidcompare/metrics.py      résolution, bits par pixel
    vidcompare/scoring.py      tables de notes, poids, langue, comparaison
    vidcompare/checks.py       détection d'incohérences
    vidcompare/report.py       verdict et explications
    vidcompare/torrent.py      .torrent et magnets (estimation)
    vidcompare/device.py       matériel de lecture
    vidcompare/groups.py       réputation des groupes
    vidcompare/history.py      historique
    vidcompare/upgrades.py     pistes d'amélioration
    vidcompare/cache.py        mémoire des analyses
    vidcompare/vmaf.py         images côte à côte et VMAF
    vidcompare/webapp.py       fenêtre pywebview et API appelée par l'interface
    ui/                        interface (index.html, style.css, app.js)
    tests/                     tests (pytest)

## Tests

    .venv\Scripts\python.exe -m pytest

## Suite prévue

La V4 (apparence) est faite. Idées ensuite : filtres dans les pistes d'amélioration, réglage « VF » par titre.
