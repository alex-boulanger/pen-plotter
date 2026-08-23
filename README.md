# Pen Plotter

Environnement perso pour faire de pen plotting avec Python, `vsketch` et `vpype`

## Structure

```text
.
├── examples/   # exemples vsketch
└── sketches/   # sketches perso
```

## Installation

Ce repo utilise `uv`.

```bash
uv sync
```

Ajouter une dépendance :

```bash
uv add <package>
```

Supprimer une dépendance :

```bash
uv remove <package>
```

## Créer un sketch

Depuis la racine du repo :

```bash
uv run vsk init sketches/{name}
```

## Lancer un sketch

Depuis la racine du repo :

```bash
uv run vsk run sketches/{name}
```

## Générer le G-code pour le LY DrawBot

Le profil du traceur se trouve dans `calibration/ly_drawbot.toml`. Pour convertir
n'importe quel SVG A4 généré par `vsketch` :

```bash
make gcode SVG=chemin/vers/dessin.svg
```

`pagerotate -o landscape` ne fait rien si le SVG est déjà en paysage et tourne
automatiquement un SVG portrait. Le fichier `.gcode` est créé à côté du SVG avec
le même nom. Le profil `ly_drawbot` est configuré par défaut.

Pour produire un fichier G-code séparé par layer, afin de changer de stylo entre
les fichiers :

```bash
make gcode-layers SVG=chemin/vers/dessin.svg
```

## Trouver le port série du LY DrawBot sur macOS

Brancher le traceur, puis lister les ports série disponibles :

```bash
ls /dev/cu.*
```

Le port du LY DrawBot contient généralement `usbserial`, par exemple :

```text
/dev/cu.usbserial-21220
```

Utiliser le port `/dev/cu.*` dans UGS plutôt que son équivalent `/dev/tty.*`.
Le suffixe (`21220` dans cet exemple) peut changer après une reconnexion ou un
changement de prise USB : rafraîchir alors la liste des ports dans UGS.
