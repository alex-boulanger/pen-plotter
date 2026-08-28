"""
Couches de contrôle — voir la donnée d'entrée sous la pièce.

Rien ici n'appartient à l'estampe. Ces couches portent des numéros au-delà des
stylos réels, si bien que le viewer les affiche et les masque séparément, et
que l'export de série les ignore purement et simplement.

Elles répondent à une question que la pièce seule ne permet pas de trancher :
quand une composition déçoit, est-ce le terrain qui est pauvre, la découpe qui
tombe mal, ou le réglage qui écrase tout ? Les trois se corrigent à des
endroits différents.

    4  la découpe          — les facettes, et lesquelles restent vides
    5  un champ du terrain — en demi-teinte, sous la pièce
    6  le gradient         — direction et force de la pente
    7  repères             — cadre, hypsométrie, valeurs clés

Aucune de ces couches ne consomme le tirage aléatoire : les activer ne change
donc jamais un trait de l'estampe.
"""

from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, MultiLineString, Polygon

import marks

LAYER_PARTITION = 4
LAYER_FIELD = 5
LAYER_GRADIENT = 6
LAYER_MARKERS = 7

FIELDS = ["slope", "curvature", "roughness", "elevation"]

# Les champs signés se lisent autour de zéro, pas à partir de zéro.
SIGNED = {"curvature"}


def _grid(page: Polygon, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Centres d'une grille de lecture couvrant la zone utile."""
    minx, miny, maxx, maxy = page.bounds
    cols = max(1, int((maxx - minx) / step))
    rows = max(1, int((maxy - miny) / step))
    xs = minx + (np.arange(cols) + 0.5) * (maxx - minx) / cols
    ys = miny + (np.arange(rows) + 0.5) * (maxy - miny) / rows
    return np.meshgrid(xs, ys)


def partition(facets: list[marks.Facet]) -> list[tuple[int, object]]:
    """Le contour de chaque facette, plus une croix sur les facettes vides.

    Voir la découpe seule répond à la question la plus fréquente : une zone
    est-elle nue parce que le terrain y est calme, ou parce qu'aucune coupe
    n'y est tombée ?
    """
    lines: list[LineString] = []
    for facet in facets:
        lines.append(LineString(facet.polygon.exterior.coords))
        if facet.inked:
            continue
        # Une diagonale suffit à distinguer « vide » de « non découpé ».
        minx, miny, maxx, maxy = facet.polygon.bounds
        diagonal = LineString([(minx, miny), (maxx, maxy)]).intersection(facet.polygon)
        if diagonal.geom_type == "LineString" and diagonal.length > 1e-3:
            lines.append(diagonal)
    return [(LAYER_PARTITION, MultiLineString(lines))] if lines else []


def field(terrain, params: dict, name: str, step: float) -> list[tuple[int, object]]:
    """Un champ scalaire en demi-teinte : un carré d'autant plus grand qu'il vaut.

    Les champs signés sont tournés de 45° quand ils sont négatifs — c'est le
    signe de la courbure qui décide du stylo, et il faut pouvoir le lire.
    """
    page = marks.page_box(params)
    if page is None:
        return []
    reader = marks.reader_for(terrain, params)
    gx, gy = _grid(page, step)
    points = np.column_stack([gx.ravel(), gy.ravel()])
    tu, tv = reader.tile(points)
    values = terrain.sample_many(name, tu, tv)

    signed = name in SIGNED
    amplitude = np.abs(values) if signed else np.clip(values, 0.0, 1.0)
    half = 0.5 * step * 0.86 * amplitude

    lines: list[LineString] = []
    for (x, y), size, value in zip(points, half, values, strict=True):
        if size < 0.01:
            continue
        if signed and value < 0.0:
            corners = [(x, y - size), (x + size, y), (x, y + size), (x - size, y)]
        else:
            corners = [
                (x - size, y - size),
                (x + size, y - size),
                (x + size, y + size),
                (x - size, y + size),
            ]
        lines.append(LineString([*corners, corners[0]]))
    return [(LAYER_FIELD, MultiLineString(lines))] if lines else []


def gradient(terrain, params: dict, step: float) -> list[tuple[int, object]]:
    """Le gradient : un trait orienté selon la pente, long comme elle est forte.

    C'est le champ dont l'estampe ne montre qu'une version quantifiée. Les
    comparer dit tout de la marge d'abstraction : si le trait suit visiblement
    le relief ici alors que la pièce reste illisible, la quantification fait
    son travail.
    """
    page = marks.page_box(params)
    if page is None:
        return []
    reader = marks.reader_for(terrain, params)
    gx, gy = _grid(page, step)
    points = np.column_stack([gx.ravel(), gy.ravel()])
    tu, tv = reader.tile(points)
    dx = terrain.sample_many("grad_x", tu, tv)
    dy = terrain.sample_many("grad_y", tu, tv)
    strength = terrain.sample_many("slope", tu, tv)

    lines: list[LineString] = []
    for (x, y), ex, ey, force in zip(points, dx, dy, strength, strict=True):
        norm = math.hypot(ex, ey)
        if norm <= 0.0 or force < 0.02:
            continue
        # L'axe y de la page descend, celui du terrain monte vers le nord.
        ux, uy = ex / norm, -ey / norm
        reach = 0.45 * step * float(np.clip(force, 0.0, 1.0))
        lines.append(
            LineString([(x - ux * reach, y - uy * reach), (x + ux * reach, y + uy * reach)])
        )
    return [(LAYER_GRADIENT, MultiLineString(lines))] if lines else []


def markers(terrain, facets: list[marks.Facet], params: dict) -> list[tuple[int, object]]:
    """Cadre de la zone utile et courbe hypsométrique dans la marge basse.

    `hypsometry` ne sert à rien dans le tracé ; c'est pourtant la façon la plus
    directe de voir si une tuile est dominée par un plateau ou étalée sur toute
    sa hauteur, donc de comprendre d'où vient une pièce vide.
    """
    page = marks.page_box(params)
    if page is None:
        return []
    lines = [LineString(page.exterior.coords)]

    minx, _, maxx, _ = page.bounds
    counts = np.asarray(terrain.hypsometry, dtype=float)
    peak = counts.max()
    if peak > 0.0:
        # La marge basse loge l'histogramme *et* la légende. On réserve le bas
        # au texte, sinon les barres passent au travers.
        margin = params["margin"]
        base = params["height"] - margin * 0.55
        tall = margin * 0.5
        width = (maxx - minx) / len(counts)
        lines.append(LineString([(minx, base), (maxx, base)]))
        for i, value in enumerate(counts):
            x = minx + (i + 0.5) * width
            top = base - tall * (value / peak)
            if base - top > 1e-3:
                lines.append(LineString([(x, base), (x, top)]))

    return [(LAYER_MARKERS, MultiLineString(lines))] if lines else []


def caption(terrain, facets: list[marks.Facet]) -> str:
    """One numeric line written in the margin by the sketch."""
    inked = [f for f in facets if f.inked]
    areas = np.array([f.polygon.area for f in facets]) if facets else np.zeros(1)
    levels = np.bincount(
        [f.level for f in facets], minlength=marks.LEVEL_BLACK + 1
    ).tolist()
    return (
        f"{terrain.name} {terrain.lat:.4f},{terrain.lon:.4f} "
        f"seed {terrain.seed} | {len(facets)} facets "
        f"({areas.min():.1f}-{areas.max():.1f} cm2) | "
        f"inked {len(inked)} | levels {levels}"
    )


def overlay(terrain, facets: list[marks.Facet], params: dict) -> list[tuple[int, object]]:
    """All control layers requested by the grammar."""
    out: list[tuple[int, object]] = []
    if params.get("debug_partition", True):
        out += partition(facets)
    name = params.get("debug_field", "slope")
    if name in FIELDS:
        out += field(terrain, params, name, params.get("debug_step", 0.6))
    if params.get("debug_gradient", True):
        out += gradient(terrain, params, params.get("debug_step", 0.6) * 1.5)
    if params.get("debug_markers", True):
        out += markers(terrain, facets, params)
    return out
