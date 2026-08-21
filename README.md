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
