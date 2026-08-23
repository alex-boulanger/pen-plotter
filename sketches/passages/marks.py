"""
Le système de marques.

C'est la seule partie de la série destinée à être itérée. Elle est isolée
derrière `generate()` : changer d'esthétique ne doit jamais obliger à toucher
au sketch ni à `terrain.py`.

La page est découpée récursivement en **facettes** par des coupes droites,
prises dans le même jeu d'angles quantifiés que les hachures. Coupes et trame
partageant leur vocabulaire de directions, la page se lit comme un minéral
clivé et non comme une image tramée.

Il n'y a plus aucun pas fixe. C'est le point : une grille régulière met toutes
ses frontières sur le même pas, chaque contour devient un escalier de cellules
identiques, et c'est cet escalier qu'on reconnaît comme « pixellisé ». Ici deux
facettes n'ont ni la même taille ni la même forme.

Le partage des rôles entre la graine et le terrain est strict :

* la **graine** place les coupes — direction et position. Elle ne décide de
  rien de ce qu'on lit, seulement du découpage ;
* le **terrain** décide si une facette mérite d'être recoupée (elle l'est tant
  qu'elle reste hétérogène), et donne à chaque facette son angle, sa densité
  et son stylo.

D'où la variété d'échelles : un versant calme reste une seule grande facette,
une arête tourmentée se subdivise profondément. La taille d'une facette *est*
une lecture du massif.

Vocabulaire fermé de six marques, couvertures pour une plume 0,3 mm :

    0  vide
    1  hachures clairsemées      pas 0,40 cm     8 %
    2  hachures denses           pas 0,20 cm    15 %
    3  hachures serrées          pas 0,10 cm    30 %
    4  aplat                     pas 0,05 cm    60 %
    5  noir plein                pas 0,03 cm   100 %

C'est l'écart entre ces six valeurs qui fait le contraste, et le contraste qui
fait lire le blanc comme du vide plutôt que comme une case non remplie. Une
page qui n'utiliserait que le milieu de l'échelle resterait un gris uniforme,
quelle que soit l'encre dépensée.

Les deux extrémités méritent chacune leur justification. Sans le noir plein,
le plus sombre plafonne à 60 % : encore un gris. Sans le clairsemé, il n'y a
plus de passage entre le vide et la matière, et la page redevient un damier.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Polygon, box
from shapely.ops import unary_union

LEVEL_EMPTY = 0
LEVEL_SPARSE = 1
LEVEL_DENSE = 2
LEVEL_TIGHT = 3
LEVEL_FLAT = 4
LEVEL_BLACK = 5

INKED_LEVELS = (LEVEL_SPARSE, LEVEL_DENSE, LEVEL_TIGHT, LEVEL_FLAT, LEVEL_BLACK)

# Part d'aire visée par chaque niveau, cumulée — 72 % de page vide, puis
# 7 / 7 / 7 / 5 / 2 %. C'est la composition moyenne de la série, mesurée sur
# les seuils absolus ; elle sert de cible à l'exposition relative, de sorte
# que les deux extrêmes du réglage décrivent la même pièce moyenne.
AREA_QUANTILES = (0.72, 0.79, 0.86, 0.93, 0.98)

LAYER_CONCAVE = 1
LAYER_CONVEX = 2

# En dessous, un segment n'est plus qu'un point d'encre.
MIN_SEGMENT = 1e-3

# Une facette plus fine que ça ne se lit plus comme une surface.
MIN_SLIVER = 0.02


def pitch_ladder(hatch_min: float, hatch_max: float) -> dict[int, float]:
    """Pas de hachure pour chaque niveau, en divisions entières de `hatch_max`.

    Les divisions entières ne sont pas un détail : c'est ce qui permet aux
    hachures de facettes voisines de même angle de rester colinéaires. La
    trame est globale, pas locale, et deux facettes voisines se fondent en une
    seule masse au lieu d'afficher leur couture.

    Le dernier cran est un vrai aplat. Sous une plume 0,3 mm, un pas de
    0,05 cm couvre 60 % de la surface : l'encre se rejoint et le trait
    disparaît au profit d'une masse. C'est la bavure qui fait le noir.
    """
    return {
        LEVEL_SPARSE: max(hatch_min, hatch_max),
        LEVEL_DENSE: max(hatch_min, hatch_max / 2.0),
        LEVEL_TIGHT: max(hatch_min, hatch_max / 4.0),
        LEVEL_FLAT: max(hatch_min, hatch_max / 8.0),
        # Le noir plein : le pas égale la largeur de plume, les traits se
        # touchent et la surface se remplit. Un défaut de position n'y produit
        # qu'un recouvrement, jamais un blanc — le noir dégrade proprement.
        LEVEL_BLACK: min(hatch_min, hatch_max / 8.0),
    }


def level_for_slope(slope: float, thresholds) -> int:
    """Le niveau d'une facette : le nombre de seuils que sa pente dépasse."""
    return min(LEVEL_BLACK, sum(1 for edge in thresholds if slope >= edge))


def absolute_thresholds(params: dict) -> list[float]:
    """Les cinq seuils, en pente, tels que le réglage les fixe.

    Ils sont donnés explicitement plutôt que par une courbe de réponse. Une
    courbe en puissance ne peut pas faire le travail : la pente au-dessus du
    seuil est très dissymétrique, et il faudrait un exposant de 1,8 en bas de
    plage mais de 3,4 en haut pour obtenir une répartition utilisable. Un
    exposant unique nourrit soit les marques claires soit les sombres, jamais
    les deux — à gamma = 0,25, le niveau clairsemé ne recevait plus que 1 %
    des facettes et le vocabulaire en annonçait six pour n'en utiliser que
    quatre.
    """
    empty = params["empty_threshold"]
    span = 1.0 - empty
    return [empty] + [empty + edge * span for edge in params["level_edges"]]


def relative_thresholds(slopes: np.ndarray, areas: np.ndarray) -> list[float]:
    """Les mêmes seuils, mais lus dans la distribution propre à la pièce.

    On travaille en quantiles d'**aire** et non de facettes : ce qui doit être
    régulier d'une pièce à l'autre, c'est la part de page à chaque valeur, pas
    le nombre de facettes — une grande facette pèse dans le rendu ce que trois
    petites ne pèsent pas.
    """
    if len(slopes) == 0 or areas.sum() <= 0.0:
        return [0.0] * len(AREA_QUANTILES)
    order = np.argsort(slopes)
    sorted_slopes, sorted_areas = slopes[order], areas[order]
    # Quantile au milieu de chaque facette, pour ne pas biaiser d'un demi-pas.
    cdf = (np.cumsum(sorted_areas) - 0.5 * sorted_areas) / sorted_areas.sum()
    return [float(np.interp(q, cdf, sorted_slopes)) for q in AREA_QUANTILES]


def level_thresholds(
    slopes: np.ndarray, areas: np.ndarray, params: dict
) -> list[float]:
    """Mélange seuils absolus et seuils propres à la pièce.

    `exposure` = 0 laisse le poids de la pièce dire quelque chose du massif :
    un versant régulier sort clair, un massif tourmenté sort chargé — dans un
    rapport de un à deux sur les cinq premiers lieux. `exposure` = 1 expose
    chaque pièce identiquement, et toute la variété passe alors dans la
    composition. On mélange les *seuils*, pas les valeurs : les deux jeux sont
    dans la même unité, donc l'interpolation garde un sens.
    """
    blend = min(1.0, max(0.0, params.get("exposure", 0.0)))
    fixed = absolute_thresholds(params)
    if blend <= 0.0:
        return fixed
    own = relative_thresholds(slopes, areas)
    return [(1.0 - blend) * a + blend * b for a, b in zip(fixed, own, strict=True)]


def quantize_angle(aspect: float, steps: int) -> float:
    """Rabat une orientation continue sur `steps` directions régulières.

    Les hachures n'ayant pas de sens, deux directions opposées donnent le même
    tracé : `steps` orientations n'en produisent que `steps / 2` visibles.
    C'est voulu — c'est la marge d'abstraction.
    """
    step = 2.0 * math.pi / steps
    return (round(aspect / step) % steps) * step


def cut_directions(steps: int) -> list[float]:
    """Directions de coupe possibles — celles des hachures, sans les opposées.

    Une droite n'ayant pas de sens, `steps` orientations de hachure ne
    fournissent que `steps / 2` directions de coupe distinctes. Les coupes
    puisent dans le même vocabulaire que la trame : c'est ce qui fait tenir la
    page comme un seul objet plutôt que comme un découpage et un remplissage.
    """
    half = max(1, steps // 2)
    return [k * math.pi / half for k in range(half)]


def tile_coords(u, v, aspect_ratio: float):
    """Coordonnées de page normalisées vers coordonnées de tuile.

    La tuile est carrée, la page ne l'est pas. Plutôt que d'étirer le terrain
    pour remplir la page — ce qui rendrait toutes les pièces anisotropes dans
    le même sens — on recadre la tuile au format de la zone utile.

    Accepte indifféremment des scalaires ou des tableaux.
    """
    if aspect_ratio <= 1.0:
        return 0.5 + (u - 0.5) * aspect_ratio, v
    return u, 0.5 + (v - 0.5) / aspect_ratio


# --- Découpe de la page -----------------------------------------------------


def split(region: Polygon, angle: float, position: float) -> list[Polygon]:
    """Coupe une facette par une droite, et renvoie les deux morceaux.

    `position` est une fraction de l'étendue de la facette perpendiculairement
    à la coupe : 0,5 coupe au milieu.
    """
    direction = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-direction[1], direction[0]])

    corners = np.asarray(region.exterior.coords)
    along_n = corners @ normal
    along_d = corners @ direction
    n_lo, n_hi = along_n.min(), along_n.max()
    if n_hi - n_lo < 2 * MIN_SLIVER:
        return [region]
    offset = n_lo + (n_hi - n_lo) * position

    # Les deux demi-plans sont construits dans le repère (direction, normale)
    # à partir des projections réelles de la facette, et non autour de
    # l'origine : une facette loin de l'origine verrait sinon un coin rogné
    # par une coupe oblique, et la page perdrait de la surface en silence.
    pad = 1.0
    d_lo, d_hi = along_d.min() - pad, along_d.max() + pad
    pieces = []
    for lo, hi in ((n_lo - pad, offset), (offset, n_hi + pad)):
        half = Polygon(
            [
                direction * d_lo + normal * lo,
                direction * d_hi + normal * lo,
                direction * d_hi + normal * hi,
                direction * d_lo + normal * hi,
            ]
        )
        piece = region.intersection(half)
        if piece.geom_type == "Polygon" and piece.area > MIN_SLIVER:
            pieces.append(piece)
        elif piece.geom_type == "MultiPolygon":
            pieces.extend(p for p in piece.geoms if p.area > MIN_SLIVER)
    return pieces if len(pieces) > 1 else [region]


def _facet_samples(region: Polygon, samples: int) -> np.ndarray:
    """Points de lecture du terrain répartis dans une facette."""
    minx, miny, maxx, maxy = region.bounds
    xs = np.linspace(minx, maxx, samples)
    ys = np.linspace(miny, maxy, samples)
    grid = np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)
    inside = shapely.contains_xy(region, grid[:, 0], grid[:, 1])
    if not inside.any():
        point = region.representative_point()
        return np.array([[point.x, point.y]])
    return grid[inside]


class Reader:
    """Lit les champs du terrain sous une facette de la page."""

    def __init__(self, terrain, origin, size, samples: int):
        self.terrain = terrain
        self.origin = origin
        self.size = size
        self.ratio = size[0] / size[1]
        self.samples = samples

    def tile(self, points: np.ndarray):
        u = (points[:, 0] - self.origin[0]) / self.size[0]
        v = (points[:, 1] - self.origin[1]) / self.size[1]
        return tile_coords(u, v, self.ratio)

    def field(self, region: Polygon, name: str) -> np.ndarray:
        tu, tv = self.tile(_facet_samples(region, self.samples))
        return self.terrain.sample_many(name, tu, tv)

    def angle(self, region: Polygon, steps: int) -> float:
        """Orientation moyenne, par moyenne vectorielle puis quantification.

        On moyenne les composantes du gradient, jamais l'angle : moyenner des
        angles de part et d'autre de la coupure ±π n'a aucun sens.
        """
        tu, tv = self.tile(_facet_samples(region, self.samples))
        gx = float(self.terrain.sample_many("grad_x", tu, tv).mean())
        gy = float(self.terrain.sample_many("grad_y", tu, tv).mean())
        return quantize_angle(math.atan2(gy, gx), steps)


def subdivide(region: Polygon, reader: Reader, params: dict, rng) -> list[Polygon]:
    """Découpe la page en facettes, tant que le terrain reste hétérogène.

    Le critère d'arrêt est la dispersion de la pente sous la facette. Une
    facette homogène — un versant régulier, un plateau — n'a rien de plus à
    dire et reste entière, même très grande. C'est de là que viennent à la
    fois les grands vides et les zones très détaillées : la taille d'une
    facette est une mesure de l'agitation du terrain qu'elle recouvre.
    """
    detail = params["detail"]
    min_area = params["min_facet"]
    spread = params["cut_spread"]
    min_depth = int(params["min_cuts"])
    max_depth = int(params["max_cuts"])
    directions = cut_directions(int(params["angle_steps"]))

    facets: list[Polygon] = []
    stack: list[tuple[Polygon, int]] = [(region, 0)]
    while stack:
        current, depth = stack.pop()

        forced = depth < min_depth
        splittable = depth < max_depth and current.area > 2.0 * min_area
        if not forced and (
            not splittable or float(reader.field(current, "slope").std()) <= detail
        ):
            facets.append(current)
            continue

        angle = directions[int(rng.integers(len(directions)))]
        position = 0.5 + (rng.random() - 0.5) * spread
        pieces = split(current, angle, position)
        # Une coupe qui produirait une écharde est refusée plutôt que rabotée :
        # le plancher de taille doit valoir pour toutes les facettes, pas
        # seulement pour celles qu'on a choisi de recouper.
        if len(pieces) < 2 or min(piece.area for piece in pieces) < min_area:
            facets.append(current)
            continue
        stack.extend((piece, depth + 1) for piece in pieces)

    return facets


# --- Hachure ----------------------------------------------------------------


def hatch(region: Polygon, angle: float, pitch: float) -> list[LineString]:
    """Hachure une facette selon une trame globale.

    Les distances sont mesurées depuis l'origine de la page, jamais depuis la
    facette : deux facettes voisines partageant angle et pas produisent des
    hachures qui se prolongent exactement, et leur couture disparaît.

    L'intervalle des lignes est semi-ouvert. Une ligne tombant pile sur une
    arête partagée n'appartient qu'à une des deux facettes, sinon le plotter la
    repasserait deux fois et l'encre baverait le long de la couture.
    """
    direction = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-direction[1], direction[0]])

    corners = np.asarray(region.exterior.coords)
    along_normal = corners @ normal
    along_dir = corners @ direction

    first = math.floor(along_normal.min() / pitch) + 1
    last = math.floor(along_normal.max() / pitch)

    centre = (along_dir.max() + along_dir.min()) / 2.0
    reach = (along_dir.max() - along_dir.min()) / 2.0 + pitch

    segments: list[LineString] = []
    for k in range(first, last + 1):
        offset = normal * (k * pitch)
        ray = LineString(
            [offset + direction * (centre - reach), offset + direction * (centre + reach)]
        )
        clipped = ray.intersection(region)
        if clipped.is_empty:
            continue
        parts = clipped.geoms if clipped.geom_type.startswith("Multi") else [clipped]
        segments.extend(
            p for p in parts if p.geom_type == "LineString" and p.length > MIN_SEGMENT
        )
    return segments


def erode(segments: list[LineString], contour, depth: float, rng) -> list[LineString]:
    """Ronge les hachures qui butent sur le contour extérieur de la masse.

    Seul le pourtour est attaqué : les coutures intérieures, entre deux
    facettes encrées, restent nettes. Éroder partout dissoudrait les masses en
    confettis ; n'éroder que la silhouette la déchire sans la dissoudre.

    On ne déplace jamais une hachure, on la raccourcit — la trame reste donc
    intacte pendant que le bord devient irrégulier.
    """
    if depth <= 0.0 or not segments:
        return segments

    ends = np.array([[s.coords[0], s.coords[-1]] for s in segments], dtype=float)
    flat = ends.reshape(-1, 2)
    touching = (
        shapely.distance(shapely.points(flat), contour).reshape(len(segments), 2) < 1e-9
    )

    out: list[LineString] = []
    for (x0, y0), (x1, y1), (open0, open1) in zip(
        ends[:, 0], ends[:, 1], touching, strict=True
    ):
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0.0:
            continue
        start = rng.random() * depth if open0 else 0.0
        end = rng.random() * depth if open1 else 0.0
        if start + end >= length - MIN_SEGMENT:
            continue
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        out.append(
            LineString([(x0 + ux * start, y0 + uy * start), (x1 - ux * end, y1 - uy * end)])
        )
    return out


# --- Assemblage -------------------------------------------------------------


@dataclass(frozen=True)
class Facet:
    """Une facette et tout ce que le terrain en dit.

    Le plan de découpe est séparé de son tracé pour qu'on puisse le relire
    autrement — c'est ce qui permet aux couches de contrôle de montrer la
    partition et les champs qui l'ont produite, sans rejouer le hasard.
    """

    polygon: Polygon
    level: int
    slope: float
    angle: float = 0.0
    pen: int = LAYER_CONVEX
    curvature: float = 0.0
    roughness: float = 0.0

    @property
    def inked(self) -> bool:
        return self.level != LEVEL_EMPTY


def page_box(params: dict) -> Polygon | None:
    """Zone utile de la page, ou None si les marges ne laissent rien."""
    margin = params["margin"]
    zone_w = params["width"] - 2.0 * margin
    zone_h = params["height"] - 2.0 * margin
    if zone_w <= 0.0 or zone_h <= 0.0:
        return None
    return box(margin, margin, margin + zone_w, margin + zone_h)


def reader_for(terrain, params: dict) -> Reader:
    margin = params["margin"]
    return Reader(
        terrain,
        (margin, margin),
        (params["width"] - 2.0 * margin, params["height"] - 2.0 * margin),
        int(params["samples"]),
    )


def plan(terrain, params: dict, rng) -> list[Facet]:
    """Découpe la page et décide du sort de chaque facette.

    Renvoie **toutes** les facettes, y compris celles qui resteront vides :
    une facette vide fait partie de la composition au même titre qu'une autre,
    et les couches de contrôle doivent pouvoir la montrer.
    """
    page = page_box(params)
    if page is None:
        return []
    reader = reader_for(terrain, params)
    steps = int(params["angle_steps"])

    # La pente de toutes les facettes est lue d'abord : les seuils peuvent
    # dépendre de la distribution de la pièce entière, on ne peut donc rien
    # trancher avant de l'avoir vue en entier.
    polygons = subdivide(page, reader, params, rng)
    slopes = np.array([float(reader.field(poly, "slope").mean()) for poly in polygons])
    areas = np.array([poly.area for poly in polygons])
    thresholds = level_thresholds(slopes, areas, params)

    facets = []
    for polygon, slope in zip(polygons, slopes, strict=True):
        level = level_for_slope(float(slope), thresholds)
        if level == LEVEL_EMPTY:
            # Rien d'autre à lire : une facette vide n'a ni angle ni stylo, et
            # les champs qu'on ne trace pas ne valent pas d'être échantillonnés.
            facets.append(Facet(polygon=polygon, level=level, slope=float(slope)))
            continue
        curvature = float(reader.field(polygon, "curvature").mean())
        facets.append(
            Facet(
                polygon=polygon,
                level=level,
                slope=float(slope),
                angle=reader.angle(polygon, steps),
                pen=LAYER_CONCAVE if curvature < 0.0 else LAYER_CONVEX,
                curvature=curvature,
                roughness=float(reader.field(polygon, "roughness").mean()),
            )
        )
    return facets


def render(facets: list[Facet], params: dict, rng) -> list[tuple[int, object]]:
    """Trace un plan de découpe."""
    inked = [f for f in facets if f.inked]
    if not inked:
        return []

    # La silhouette doit être connue avant de tracer quoi que ce soit :
    # l'érosion ne mord que le pourtour de la masse, pas ses coutures.
    contour = unary_union([f.polygon for f in inked]).boundary
    pitches = pitch_ladder(params["hatch_min"], params["hatch_max"])

    layers: dict[int, list[LineString]] = {LAYER_CONCAVE: [], LAYER_CONVEX: []}
    for facet in inked:
        segments = hatch(facet.polygon, facet.angle, pitches[facet.level])
        depth = params["erosion"] * facet.roughness * math.sqrt(facet.polygon.area)
        layers[facet.pen].extend(erode(segments, contour, depth, rng))

    return [
        (layer, MultiLineString(segments))
        for layer, segments in sorted(layers.items())
        if segments
    ]


def generate(terrain, params: dict, rng) -> list[tuple[int, object]]:
    """Retourne une liste de (numéro_de_couche, géométrie Shapely)."""
    return render(plan(terrain, params, rng), params, rng)
