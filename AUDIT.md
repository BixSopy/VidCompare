# Audit de VidCompare (V4) du 6 novembre 2026

Ce rapport couvre l'audit du code, des performances et du design, puis les résultats de recherches sur
les fonctions qui seraient utiles. Chaque chiffre vient d'une mesure faite sur ce poste (Windows 11,
AMD Radeon RX 6700, FFmpeg 9.0.2 « full »). Les affirmations venant d'Internet sont suivies de leur source
et marquées « à vérifier » quand la source est faible (forums, blogs).

## Suivi : V5 faite le 6 novembre 2026

Traités dans la V5 : constats 1 à 8 du résumé, P1, P2, P3, P5, P7 (section 4), Q6, Q8, Q9 (section 3),
D1 à D4 (section 5), F2 (section 6), plus la réserve HDR du VMAF. Les tests d'intégration avec un vrai
FFmpeg sont ajoutés. Restent pour la suite : P4 (VMAF au modèle 4K), P6 (poids de `bin`), P8, Q1 pour `cli.py`,
Q2 et Q3 (simplification du code), Q5, Q7, Q10, D5 à D9, F1, F3 à F13.

## 1. Résumé

VidCompare est sain : 80 tests passent, aucune faille de sécurité moyenne ou haute n'a été trouvée, le
démarrage prend moins d'une seconde et l'application seule pèse 29 Mo. Les points qui méritent du travail,
par ordre d'importance :

1. **Les images et le VMAF peuvent comparer deux montages différents sans le dire** (cinéma, director's cut,
   IMAX). Le résultat serait faux. Il faut une garde avant toute mesure visuelle.
2. **Un scan de dossier fait deux appels `ffprobe` par fichier alors qu'un seul suffit pour les vidéos SDR**
   (129 ms contre environ 55 ms par fichier mesurés). Un scan de 3000 fichiers peut passer de près de 100 s
   à environ 45 s.
3. **Un scan de 3000 fichiers bloque l'analyse des cases A et B**, car les deux partagent les mêmes 4 tâches
   (`vidcompare/webapp.py:105`).
4. **La liste des pistes d'amélioration envoie 719 Ko de données et 3000 cartes à l'écran à chaque
   rafraîchissement.** Il faut paginer.
5. **Le texte gris « faible » ne respecte pas le contraste minimum** (3,2 à 4,0 contre 4,5 demandé) et les
   bordures des champs sont trop discrètes.
6. **Des dossiers temporaires s'accumulent** : 97 dossiers `vidcompare_*` dans `%TEMP%` (`webapp.py:114`).
7. **Aucun journal d'erreurs.** Une erreur du moteur s'affiche comme « Le moteur ne répond pas »
   (`ui/app.js:37`) et n'est écrite nulle part.
8. **Le VMAF applique une cadence de 24 images/s aux deux vidéos**, alors que la pratique recommandée est de
   ne convertir que la vidéo comparée (`vidcompare/vmaf.py:116`).

Les fonctions les plus utiles trouvées par les recherches : distinguer Dolby Vision FEL et MEL, détecter une
fausse 4K, regrouper les doublons d'une bibliothèque avec le gain d'espace, utiliser TMDB pour la durée
exacte des films, et enrichir le VMAF (scènes les plus dégradées, banding). Le détail est en section 6.

## 2. État mesuré

| Mesure | Valeur |
|---|---|
| Code Python (moteur) | environ 2 550 lignes utiles dans 19 modules, plus 4 modules de tests |
| Interface | `ui/` : 58 Ko (HTML, CSS, JavaScript sans dépendance) |
| Tests | 80, tous réussis, 2,7 s |
| Couverture | 78 % (2 188 lignes, 480 non couvertes) |
| Programme du Bureau | exe 5,7 Mo + `_internal` 22,9 Mo = 29 Mo ; FFmpeg et ffprobe dans `bin` : 434 Mo |
| Démarrage | fenêtre visible après 0,9 s |
| Mémoire | 7 processus (dont WebView2) : 245 Mo privés, 445 Mo de travail |
| Évaluation | 0,07 ms par fichier (3000 fichiers : 217 ms) |
| État envoyé à l'écran | 300 éléments classés : 41 ms, 64 Ko. 3000 fichiers scannés : 60 ms, 719 Ko |
| Après un changement de réglage avec 3000 fichiers | 546 ms |

## 3. Audit du code

### Ce qui va bien
- Séparation nette : moteur (`vidcompare/`), interface (`ui/`), pont (`webapp.py`).
- Toutes les chaînes affichées passent par `esc()` côté interface : aucune injection de page trouvée.
- Les appels à FFmpeg utilisent des listes d'arguments, sans passer par un shell.
- Les réglages, l'historique et le cache résistent à un fichier corrompu (ils repartent vides).

### Constats

| # | Gravité | Constat | Où |
|---|---|---|---|
| Q1 | Moyenne | Couverture faible sur `cli.py` (0 %), `__main__.py` (0 %), `vmaf.py` (48 %), `report.py` (68 %), `webapp.py` (71 %), `probe.py` (75 %). Le vrai appel à `ffprobe` n'est testé par aucun test automatique. Aucun test de l'interface JavaScript. | `tests/` |
| Q2 | Moyenne | Fonctions trop complexes : `parse_name` (39), `run_checks` (25), `evaluate` (19). | `parse_name.py:65`, `checks.py:27`, `scoring.py:178` |
| Q3 | Faible | Logique dupliquée : deux fonctions de reconnaissance audio (`probe.audio_label` et `mediainfo._audio_label`) et deux de classement HDR (`probe.classify_hdr` et `mediainfo._hdr`). Un oubli dans l'une crée un écart de notes selon la source. | `probe.py:131`, `mediainfo.py:127` |
| Q4 | Faible | Petites dettes : import inutile (`checks.py:4`), variable `l` ambiguë (5 endroits), fonction qui capture une variable de boucle sans bug réel (`scoring.py:323`), `try/except/pass`. | voir `ruff` |
| Q5 | Faible | Le serveur de test `--dev` accepte des requêtes de n'importe quelle page web ouverte sur le PC tant qu'il tourne (pas de contrôle d'origine). Sans effet sur l'application normale. | `webapp.py` (`run_dev`) |
| Q6 | Moyenne | Pas de journal. Les erreurs du moteur arrivent à l'écran sous la forme « Le moteur ne répond pas ». C'est ce qui a rendu l'erreur d'images sur vos remuxes difficile à analyser. | `ui/app.js:37` |
| Q7 | Moyenne | Pas de contrôle de la présence de WebView2. Sur un Windows 10 ancien, `pywebview` peut retomber sur un moteur d'affichage ancien et l'interface casse. Sans effet sur votre Windows 11. | `webapp.py:816` |
| Q8 | Moyenne | Fichiers temporaires jamais nettoyés : 97 dossiers `vidcompare_*` laissés dans `%TEMP%`. | `webapp.py:114` |
| Q9 | Faible | Hygiène du projet : pas de dépôt Git (aucun historique des versions V1 à V4), versions des dépendances non figées, pas de numéro de version visible dans l'application. | racine |
| Q10 | Moyenne | Le modèle de notes (poids, seuils de débit par pixel) n'est validé par aucune mesure. Exemple : un 4K x265 à 18 Mb/s, que des encodeurs jugent quasi transparent, obtient environ 87/100 selon la formule. Plausible, mais jamais comparé à un VMAF. | `metrics.py` |

### Limites connues du moteur (déjà documentées, à garder en tête)
- Le HDR10+ n'est cherché que sur la première image (`probe.py:51`).
- Dolby Vision profil 7 : le moteur ne distingue pas FEL et MEL (voir F1).
- Une fausse 4K n'est repérée que par un débit bas, jamais par l'analyse de l'image.
- Atmos n'est reconnu que si `ffprobe` est assez récent : le correctif qui l'ajoute date de février 2023
  ([patch FFmpeg](https://ffmpeg.org/pipermail/ffmpeg-devel/2023-February/306724.html)).

### Sécurité
`bandit` : 0 problème moyen ou haut, 5 faibles (appels de sous-processus à liste d'arguments, un
`try/except/pass`). Aucun secret n'est stocké. L'application ne contacte aucun serveur.

## 4. Audit de performance et propositions

| # | Proposition | Gain mesuré ou attendu | Effort |
|---|---|---|---|
| P1 | **Ne lancer le deuxième `ffprobe` (HDR10+) que si la vidéo est en PQ (HDR).** Le Dolby Vision se lit déjà dans le premier appel. | 129 ms → environ 55 ms par fichier SDR (−50 à −63 % mesurés) | Petit |
| P2 | **Deux files de tâches** : une pour les cases A et B, une pour les scans. | L'analyse d'une case ne attend plus un scan de 3000 fichiers | Petit |
| P3 | **Paginer les pistes d'amélioration** (50 lignes puis « afficher plus »), envoyer ce tableau à la demande et ne pas redessiner si les données n'ont pas changé. | 719 Ko et 3000 cartes → quelques dizaines de Ko ; fin des à-coups à chaque action | Moyen |
| P4 | **VMAF plus rapide** : `n_subsample=4`, modèle 4K au-dessus de 1440p, une seule conversion de cadence. | Mesuré : 5,6 s → 4,2 s sur un clip 4K de 6 s. Le gain est limité car le décodage domine. | Petit |
| P5 | Images côte à côte : lancer les 3 instants en parallèle, garder les images déjà extraites, ajouter un bouton Annuler. | Délai divisé par environ 2 à 3 sur des fichiers lents | Petit |
| P6 | **Alléger `bin` (434 Mo)** : FFmpeg et ffprobe sont deux copies de 217 Mo. Tester la version « shared » (un seul jeu de bibliothèques) ou « essentials ». Vérifier que `libvmaf` est inclus avant de changer. | Possiblement −250 à −300 Mo (à mesurer) | Moyen |
| P7 | Nettoyer les dossiers temporaires à la fermeture et balayer les anciens au lancement. | Fin de l'accumulation (97 dossiers, 2,1 Mo aujourd'hui) | Petit |
| P8 | Mémoriser l'évaluation de chaque fichier par révision de réglages. | 546 ms → quelques ms après un changement de réglage avec 3000 fichiers. Peu urgent. | Petit |

**À ne pas faire sans mesure réelle :**
- *Décodage matériel* (`-hwaccel auto`) : mesuré plus lent sur le clip de test (2,0 s contre 1,0 s). À essayer
  seulement sur un vrai remux.
- *VMAF sur carte graphique* (`libvmaf_cuda`) : absent de votre FFmpeg, et votre carte est une AMD alors que
  cette voie est réservée aux cartes NVIDIA ([NVIDIA](https://developer.nvidia.com/blog/calculating-video-quality-using-nvidia-gpus-and-vmaf-cuda)).
- *Réduire `-probesize` / `-analyzeduration`* pour aller plus vite : un blog annonce 20 % de gain, mais la
  documentation de FFmpeg et un ancien rapport de bug indiquent un risque de flux non reconnus
  ([ticket 4249](https://trac.ffmpeg.org/ticket/4249)). Non vérifié, donc à éviter.

## 5. Audit du design et de l'accessibilité

Mesures de contraste (norme WCAG : 4,5 pour le texte, 3 pour les éléments d'interface,
[critères](https://getwcag.com/blog/wcag-2-2-checklist)) :

| Couleur | Thème Cinéma | Thème OLED | Verdict |
|---|---|---|---|
| Texte principal | 15,7 | 18,4 | Très bon |
| Texte atténué (`--muted`) | 6,8 | 7,8 | Bon |
| **Texte faible (`--faint`)** | **3,2** | **3,8** | **Insuffisant pour du texte** |
| Notes (vert, jaune, orange, rouge) | 5,4 à 10,1 | 6,0 à 11,3 | Bon |
| Bordure des cartes | 1,3 | 1,5 | Décoratif, acceptable |
| Bordure des champs et menus | environ 1,8 | environ 2,2 | **Sous 3 : à renforcer** |

| # | Constat ou proposition | Où |
|---|---|---|
| D1 | `--faint` sert à du vrai texte : lettres A/B des barres, mention « égal », numéros de rang, croix de retrait. Passer à un gris d'au moins 4,5, ou réserver cette couleur à ce qui est décoratif. | `style.css:149, 156, 182, 190` |
| D2 | Renforcer la bordure des champs de saisie et des menus déroulants jusqu'à 3. | `style.css:193, 272` |
| D3 | Les fenêtres (modales) ne retiennent pas le focus clavier, ne le rendent pas au bouton d'origine et n'ont pas de nom accessible. Échap les ferme, c'est déjà bien. | `app.js` (`modal`) |
| D4 | Vocabulaire à expliquer par une info-bulle : « VMAF », « bit/px », « Remux ». | `app.js` |
| D5 | **Visionneuse d'images** : ajouter un curseur de balayage, un mode clignotant (alterner A et B), un zoom 1:1 synchronisé et une carte des différences. Les outils de comparaison d'images connus proposent le balayage et le clignotement. Les images actuelles sont limitées à 960×540 par fichier. | `vmaf.py`, `app.js` |
| D6 | Bibliothèque : filtres (gain minimum, dossier, type), actions groupées, affiches de films (voir F5). | `app.js` |
| D7 | Premier lancement : vérification guidée de FFmpeg et exemple de comparaison. | `app.js` |
| D8 | « Vider » et « Retirer » sans retour arrière : proposer « Annuler » dans le message en bas d'écran. | `app.js` |
| D9 | Mémoriser la taille et la position de la fenêtre, ajouter des raccourcis clavier (Ctrl+O, Ctrl+Entrée), afficher le numéro de version. | `webapp.py` |
| D10 | Résultat long : une barre fixe en haut rappelant les deux notes quand on descend. | `app.js` |

## 6. Recherches : fonctions utiles à ajouter

Chaque fonction est classée par valeur pour vous, effort et risque. Elles respectent le choix déjà fait :
VidCompare analyse vos fichiers, il ne cherche ni ne télécharge rien (voir section 7).

### Fiabilité de la note

**F1. Dolby Vision FEL ou MEL (valeur haute, effort moyen).** Un disque UHD en profil 7 a une couche
d'amélioration qui peut être complète (FEL) ou minimale (MEL). Pour les collectionneurs de remux, ce n'est pas
pareil. La méthode citée est d'extraire les métadonnées RPU puis de lancer `dovi_tool info`. Une règle
approximative circule (couche d'amélioration sous 3 Mb/s = MEL) mais elle est présentée comme un pari, pas un
test. L'outil `dovi_convert` compare la luminosité de crête sur 10 instants pour repérer un FEL qui dépasse la
couche de base. Sources (forums, donc à vérifier) :
[CoreELEC](https://discourse.coreelec.org/t/ce-ng-dolby-vision-fel-for-dv-licensed-socs-s905x2-s922x-z-s905x4/50953?page=49),
[Firecore](https://community.firecore.com/t/dolby-vision-profile-7-8-support-ts-mkv-files/19713?page=72).
Il faudrait livrer `dovi_tool` avec le programme.

**F2. Garde « mêmes versions » avant images et VMAF (valeur haute, effort moyen).** Le VMAF compare image par
image : les deux vidéos doivent partager la même ligne de temps, la même cadence et la même durée. Un décalage
au départ produit une dérive et des scores faux
([guide](https://gdavila.github.io/video/Vmaf/2020-03-05-Vmaf)). Des outils font la recherche du décalage
([easyVmaf](https://pypi.org/project/easyvmaf/5.0.0/),
[video-offset-finder](https://pypi.org/project/video-offset-finder/0.3.0/)). VidCompare devrait comparer durée,
chapitres (`ffprobe -show_chapters`), cadence et format d'image, puis avertir : « durées différentes de 7 min :
montages probablement différents ».

**F3. VMAF enrichi (valeur haute, effort moyen).**
- Utiliser le modèle 4K au-delà de 1440p : appliquer le modèle 1080p à du 4K donne des scores trop hauts
  ([source](https://streaminglearningcenter.com/encoding/best-practices-for-netflixs-vmaf-metric.html)).
- Afficher les scènes les plus dégradées (le VMAF donne un score par image) avec des vignettes, plutôt qu'une
  seule moyenne.
- Ajouter le **banding** avec CAMBI. Vérifié sur votre FFmpeg : `libvmaf=feature=name=cambi` fonctionne et
  renvoie un score (0 = aucun banding ; autour de 5, il devient gênant,
  [documentation](https://github.com/1480c1/vmaf/blob/master/resource/doc/cambi.md)).
- **Avertir pour le HDR** : une synthèse de recherche donne une corrélation d'environ 0,56 pour le VMAF en
  HDR, contre une bonne corrélation en SDR ([synthèse](https://www.emergentmind.com/topics/sfv-hdr-quality)).
  Le résultat actuel sur deux remuxes HDR doit donc afficher une réserve.

**F4. Fausse 4K (valeur moyenne à haute, effort moyen à grand).** Deux voies complémentaires :
- Analyse de l'image : la méthode la plus citée passe par le spectre de fréquences, où une vidéo agrandie perd
  les hautes fréquences ([fil FFmpeg](https://ffmpeg.org/pipermail/ffmpeg-user/2019-July/044877.html),
  [video-fft](https://github.com/slhck/video-fft)). Le filtre `resdet` n'existe pas dans votre FFmpeg : il faudrait
  le calculer en Python. Des filtres comme le flou ou le blocage existent (`blurdetect`, `blockdetect`).
  Une vidéo simplement floutée peut tromper la méthode.
- Origine de la copie : de nombreux disques UHD viennent d'un master 2K agrandi. Des listes communautaires le
  recensent ([HomeTheaterForum](https://www.hometheaterforum.com/community/threads/i-compiled-a-simple-list-separating-2k-uhd-blurays-and-actual-4k-blurays.346557/),
  [Sound & Vision](https://soundandvision.com/node/117310)). Cela décrit le master, pas la qualité vue à l'écran.
  À proposer comme indication, pas comme pénalité.

**F5. Audio « sans perte » truqué (valeur moyenne, effort moyen).** Un son compressé puis remis dans un conteneur
sans perte garde sa coupure de fréquence : vers 16 kHz pour du MP3 128 kb/s, 19 à 20 kHz pour 320 kb/s. Votre
FFmpeg a `aspectralstats` et `showspectrumpic`. Un outil mesure 0,3 à 1 % de faux positifs
([lossprint](https://app.alphaneural.io/assets/maxdj/lossprint)) : à présenter comme « à vérifier ».
Voir aussi [Spek](https://github.com/Spek-audio-spectrogram) et
[une étude](https://arxiv.org/html/2407.21545v1).

**F6. Contrôles techniques (valeur moyenne, effort petit à moyen).** Votre FFmpeg a `idet`, `cropdetect`,
`blackdetect`, `freezedetect`, `ebur128` et `signalstats`. Possibilités : entrelacement, bandes noires inutiles
(échantillonner plusieurs endroits, car une seule image noire fausse le résultat,
[explication](https://fileflows.com/docs/plugins/video-nodes/ffmpeg-builder/crop-black-bars-clustered)),
cadence 25 contre 23,976 (film accéléré de 4 %), métadonnées HDR présentes, contrôle d'intégrité par décodage
complet en option. `idet` est jugé peu fiable sur des sources télécinémées
([Doom9](https://forum.doom9.org/archive/index.php/t-182159.html)). La plage dynamique audio (DR) demande un
outil dédié : `ebur128` ne donne que l'étendue de sonie (LRA).

### Bibliothèque et confort

**F7. Doublons et gain d'espace (valeur haute, effort moyen).** Regrouper les versions d'un même film (titre
plus année, durées à 5 % près) puis proposer « garder la meilleure, voici ce que vous libérez : 63 Go ». Des
outils reconnaissent des doublons malgré une résolution ou une cadence différentes, avec un défaut : deux
épisodes de même durée et même générique peuvent être confondus
([vid_dup_finder](https://docs.rs/crate/vid_dup_finder_lib/latest),
[VidDup](https://pypi.org/project/viddup/), [liste d'outils](https://www.github.com/github-userx/Awesome-Duplication-Finders)).
La simple correspondance titre + durée suffit pour commencer.

**F8. TMDB pour la durée exacte et les affiches (valeur moyenne à haute, effort moyen).** Aujourd'hui le débit
d'un torrent est estimé avec une durée supposée de 110 minutes. TMDB renvoie la durée réelle (recherche par
titre, puis détail par identifiant) et les affiches, ce qui irait bien avec l'ambiance « cinéma ». Une clé
gratuite existe ; l'usage non commercial est gratuit avec mention de TMDB, l'usage commercial demande un accord
([conditions](https://themoviedb.org:443/api-terms-of-use), [guide](https://apidog.com/blog/tmdb-api-key/)).
Les sources se contredisent sur certains détails : lire les conditions officielles avant d'ajouter la fonction.
Elle enverrait des titres à un service externe : à rendre optionnelle, avec la clé fournie par vous.

**F9. Compatibilité fondée sur des tables officielles (valeur moyenne, effort petit à moyen).** Les modèles de
matériel actuels sont des exemples saisis à la main. La documentation de Jellyfin donne des tables de codecs par
client : un codec vidéo non pris en charge force un transcodage lourd, un codec audio non pris en charge
seulement un transcodage léger ; le HDR dépend du client
([tables](https://jellyfin.org/docs/general/clients/codec-support/)). Les sources divergent sur le profil 7 :
proposer des modèles modifiables (Apple TV, Shield, Fire TV, LG, Samsung, PC) marqués « à vérifier ».
Ajouter l'indication « lecture directe probable ».

**F10. Reconnaissance des noms de release plus solide (valeur moyenne, effort petit).** Aucune comparaison neutre
entre `guessit` et `parse-torrent-title` n'existe : les scores publiés viennent des projets eux-mêmes
([PTT](https://github.com/platelminto/parse-torrent-title)). Constituer 300 à 500 noms réels annotés, mesurer
votre analyseur et ces deux bibliothèques, puis décider.

**F11. Sous-titres et sonie (valeur faible à moyenne, effort petit).** Noter le type de sous-titres (PGS image
ou SRT texte, forcés, pour sourds et malentendants) et les chapitres.

**F12. Automatisation (valeur faible à moyenne).** Sortie `--json` de la console, surveillance de dossiers avec
rescan automatique, notification Windows en fin de scan ou de mesure VMAF, rapport HTML partageable avec images.

**F13. Distribution (valeur faible pour un usage perso).** Les exe PyInstaller sont souvent signalés à tort par
les antivirus et par SmartScreen, surtout sans signature
([PyInstaller #5579](https://github.com/pyinstaller/pyinstaller/issues/5579),
[vba-edit](https://github.com/markuskiller/vba-edit/issues/24)). Pistes : signature de code (un projet cite 300
à 500 dollars par an ; SignPath pour l'open source et Azure Artifact Signing sont mentionnés, détails non
vérifiés), informations de version dans l'exe, déclaration des faux positifs aux éditeurs
([discussion](https://github.com/microsoft/apm/issues/487)). Une signature ne garantit pas l'absence de
signalement. Autre technologie d'interface : Tauri donnerait des programmes bien plus petits que Electron
([comparatif](https://www.pkgpulse.com/guides/electron-vs-tauri-2026)), mais VidCompare est déjà léger
(29 Mo) et un changement n'apporterait rien d'évident.

### Idées examinées et mises de côté
- **Mesures sans référence** (DOVER, BRISQUE) : conçues pour des vidéos d'utilisateurs, peu adaptées à des films
  ([panorama](https://www.forasoft.com/learn/video-quality/articles-vqm/open-source-no-reference-tools)).
  Sans intérêt ici puisque vous comparez deux copies.
- **Décodage matériel** et **VMAF sur carte graphique** : voir section 4.
- **Barème des « Custom Formats »** des guides TRaSH : utile seulement comme inspiration. Les notions de score
  minimum et de score d'arrêt des améliorations existent déjà sous la forme du « niveau visé »
  ([guide](https://git.sudo.is/mirrors/TRaSH-Guides/src/branch/master/docs/Radarr/radarr-setup-quality-profiles.md)).

## 7. Volontairement exclu

Ces fonctions ressortent des recherches mais ne seront pas proposées, car elles servent à trouver ou
télécharger des copies de films : recherche de torrents sur des sites, envoi des « pistes d'amélioration »
vers un outil qui télécharge automatiquement, téléchargement partiel des en-têtes d'un torrent. Les guides
TRaSH et Recyclarr n'ont été lus que pour leur logique de notation.

## 8. Feuille de route proposée

| Version | Thème | Contenu |
|---|---|---|
| V5 | Fiabilité et vitesse | P1, P2, P3, P5, P7 ; journal d'erreurs ; garde « mêmes versions » (F2) ; contrastes et fenêtres accessibles (D1 à D3) ; Git ; tests d'intégration avec un vrai clip ; réserve HDR sur le VMAF |
| V6 | Analyse avancée | VMAF enrichi (F3) ; Dolby Vision FEL/MEL (F1) ; fausse 4K (F4) ; audio truqué (F5) ; contrôles techniques (F6) ; visionneuse d'images (D5) |
| V7 | Bibliothèque | Doublons et gain d'espace (F7) ; TMDB et affiches (F8) ; filtres (D6) ; compatibilité fondée sur les tables officielles (F9) |
| V8 | Finition | Reconnaissance des noms (F10) ; automatisation (F12) ; distribution (F13) ; allègement de `bin` (P6) |

## 9. Limites de cet audit

- Aucun test sur vos vrais films : les mesures de vitesse viennent de petits clips générés. Les fichiers de
  plusieurs dizaines de Go peuvent se comporter autrement.
- Le glisser-déposer depuis l'Explorateur n'a pas été testé avec la souris.
- Windows 10 et d'autres tailles ou densités d'écran n'ont pas été testés.
- La plupart des sources web sont des forums, des blogs ou des pages d'outils ; les points marqués « à vérifier »
  sont à confirmer avant de s'y fier. Aucune source officielle de Netflix, de Dolby ou de Microsoft n'a été
  trouvée pour les points techniques de la section 6.
