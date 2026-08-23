"""
Terrain acquisition, cache and derived fields for the "Passages" series.

This module knows nothing about drawing. It transforms a (lat, lon) pair into
normalized scalar fields consumed by `marks.py`.

Two normalization rules govern the file:

  * normalize **per place**, never across the full series;
  * clip by **percentiles**, never min/max, for `slope`, `curvature` and
    `roughness`.

Orientation convention: row 0 is south and column 0 is west. The physical y
axis points north.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# --- Paths ------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_DIR = DATA_DIR / "cache"
PLACES_FILE = DATA_DIR / "places.json"

# --- Fixed series settings --------------------------------------------------

CODE_VERSION = "1.0.0"

DATASET = "srtm30m"        # ~30 m, couverture -60..60 de latitude
GRID_N = 48                # grille d'acquisition : 48 x 48 = 2304 points
EXTENT_M = 6000.0          # emprise carrée, en mètres
WORK_RES = 256             # résolution de travail après rééchantillonnage
HYPSO_BINS = 32
ROUGHNESS_WINDOW = 5
CLIP_PCT = (2.0, 98.0)     # écrêtage des champs dérivés

METERS_PER_DEG_LAT = 111_320.0

# Missing DEM values. SRTM uses -32768; the API returns `null`.
NODATA_FLOOR = -1000.0


# --- Place seed -------------------------------------------------------------


def place_seed(name: str, lat: float, lon: float) -> int:
    """Deterministic seed, stable across processes and machines."""
    key = f"{name}|{lat:.5f}|{lon:.5f}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big")


# --- Place catalog ----------------------------------------------------------


def load_places() -> list[dict]:
    with open(PLACES_FILE, encoding="utf-8") as fp:
        return json.load(fp)


def find_place(slug: str) -> dict:
    for place in load_places():
        if place["slug"] == slug:
            return place
    known = ", ".join(s["slug"] for s in load_places())
    raise KeyError(f"unknown place: '{slug}' (known: {known})")


def cache_path(slug: str) -> Path:
    return CACHE_DIR / f"{slug}.npz"


# --- Acquisition grid geometry ---------------------------------------------


def extent_degrees(lat: float, extent_m: float = EXTENT_M) -> tuple[float, float]:
    """Extent in degrees for a square metric extent."""
    dlat = extent_m / METERS_PER_DEG_LAT
    dlon = extent_m / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))
    return dlat, dlon


def grid_points(
    lat: float, lon: float, extent_m: float = EXTENT_M, n: int = GRID_N
) -> np.ndarray:
    """Les n*n points de la grille, en (lat, lon), ordre ligne par ligne.

    La ligne 0 est la plus au sud, la colonne 0 la plus à l'ouest.
    """
    dlat, dlon = extent_degrees(lat, extent_m)
    lats = np.linspace(lat - dlat / 2.0, lat + dlat / 2.0, n)
    lons = np.linspace(lon - dlon / 2.0, lon + dlon / 2.0, n)
    grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
    return np.stack([grid_lat.ravel(), grid_lon.ravel()], axis=1)


# --- Cleaning ---------------------------------------------------------------


def fill_missing(z: np.ndarray) -> np.ndarray:
    """Fill NaN values by diffusing valid neighbors."""
    z = np.array(z, dtype=np.float64)
    z[z <= NODATA_FLOOR] = np.nan

    if not np.isnan(z).any():
        return z
    if np.isnan(z).all():
        raise ValueError("tuile entièrement vide : aucune altitude exploitable")

    # Diffusion itérative : chaque passe remplit les NaN qui touchent au moins
    # un voisin valide. Le nombre de passes borne la taille des trous comblés.
    for _ in range(max(z.shape)):
        missing = np.isnan(z)
        if not missing.any():
            return z
        values = np.where(missing, 0.0, z)
        valid = (~missing).astype(np.float64)
        pv, pc = np.pad(values, 1), np.pad(valid, 1)
        neighbour_sum = pv[:-2, 1:-1] + pv[2:, 1:-1] + pv[1:-1, :-2] + pv[1:-1, 2:]
        neighbour_cnt = pc[:-2, 1:-1] + pc[2:, 1:-1] + pc[1:-1, :-2] + pc[1:-1, 2:]
        fillable = missing & (neighbour_cnt > 0)
        z[fillable] = neighbour_sum[fillable] / neighbour_cnt[fillable]

    # Trou plus large que la grille : on rabat sur la moyenne, faute de mieux.
    z[np.isnan(z)] = np.nanmean(z)
    return z


# --- Resampling (pure NumPy, no SciPy) --------------------------------------


def _resample_matrix(n_src: int, n_dst: int) -> np.ndarray:
    """Matrice (n_dst, n_src) d'interpolation bicubique Catmull-Rom 1-D.

    Aux deux extrémités, le noyau réclame un échantillon qui n'existe pas. On
    l'obtient par extrapolation linéaire des deux voisins plutôt qu'en
    dupliquant le bord : dupliquer aplatit la pente sur tout le pourtour de la
    tuile, et cette fausse pente se lirait comme un cadre de marques
    aberrantes autour de chaque pièce.
    """
    u = np.linspace(0.0, n_src - 1, n_dst)
    i0 = np.clip(np.floor(u).astype(int), 0, n_src - 2)
    t = (u - i0)[:, None]
    t2, t3 = t * t, t * t * t

    weights = np.concatenate(
        [
            -0.5 * t3 + t2 - 0.5 * t,
            1.5 * t3 - 2.5 * t2 + 1.0,
            -1.5 * t3 + 2.0 * t2 + 0.5 * t,
            0.5 * t3 - 0.5 * t2,
        ],
        axis=1,
    )
    # On travaille sur une source étendue d'un échantillon fantôme de chaque
    # côté : l'indice source i vit en colonne i + 1.
    taps = i0[:, None] + np.array([-1, 0, 1, 2])[None, :] + 1
    extended = np.zeros((n_dst, n_src + 2), dtype=np.float64)
    rows = np.repeat(np.arange(n_dst), 4)
    # `add.at` et pas une affectation : deux taps peuvent tomber sur la même
    # colonne et leurs poids doivent alors s'additionner.
    np.add.at(extended, (rows, taps.ravel()), weights.ravel())

    # Repli des fantômes : h[-1] = 2h[0] - h[1] et h[n] = 2h[n-1] - h[n-2].
    extended[:, 1] += 2.0 * extended[:, 0]
    extended[:, 2] -= extended[:, 0]
    extended[:, n_src] += 2.0 * extended[:, n_src + 1]
    extended[:, n_src - 1] -= extended[:, n_src + 1]
    return extended[:, 1 : n_src + 1]


def resample(z: np.ndarray, res: int) -> np.ndarray:
    """Rééchantillonne une grille carrée vers res x res."""
    rows = _resample_matrix(z.shape[0], res)
    cols = _resample_matrix(z.shape[1], res)
    return rows @ z @ cols.T


# --- Local statistics -------------------------------------------------------


def detrended_roughness(z: np.ndarray, window: int = ROUGHNESS_WINDOW) -> np.ndarray:
    """Écart-type du résidu à un plan local — la rugosité vraie.

    L'écart-type brut de l'altitude ne mesure pas la rugosité mais la pente :
    sur une fenêtre étroite, il vaut à peu près le gradient multiplié par la
    fenêtre. Mesuré ainsi, il était corrélé à 0,995 avec `slope` — un second
    champ qui n'en était pas un.

    On ajuste donc un plan à chaque fenêtre et on ne garde que ce qui n'y
    rentre pas. Un versant régulier, même très raide, a un résidu nul ; seule
    une surface réellement accidentée en a un.
    """
    radius = window // 2
    padded = np.pad(z, radius, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(padded, (window, window))
    flat = view.reshape(*view.shape[:2], window * window)

    # Le plan z = a + bx + cy, en coordonnées locales à la fenêtre. La matrice
    # de projection ne dépend que de la forme de la fenêtre : on la calcule
    # une fois, et retrancher son image laisse exactement le résidu.
    offsets = np.arange(window) - radius
    grid_x, grid_y = np.meshgrid(offsets, offsets)
    design = np.column_stack(
        [np.ones(window * window), grid_x.ravel(), grid_y.ravel()]
    )
    projector = design @ np.linalg.pinv(design)
    residual = flat - flat @ projector
    return np.sqrt((residual**2).mean(axis=-1))


# --- Normalization ----------------------------------------------------------


def norm_unit(f: np.ndarray) -> np.ndarray:
    """Percentiles 2/98 vers [0, 1], écrêté."""
    lo, hi = np.percentile(f, CLIP_PCT)
    if hi <= lo:
        return np.zeros_like(f)
    return np.clip((f - lo) / (hi - lo), 0.0, 1.0)


def norm_signed(f: np.ndarray) -> np.ndarray:
    """Percentiles 2/98 vers [-1, 1], écrêté, en préservant le zéro.

    Le zéro doit rester le zéro : c'est son signe qui décide de la couche.
    On divise donc par une borne symétrique plutôt que de recentrer.
    """
    lo, hi = np.percentile(f, CLIP_PCT)
    limit = max(abs(lo), abs(hi))
    if limit == 0.0:
        return np.zeros_like(f)
    return np.clip(f / limit, -1.0, 1.0)


def norm_minmax(f: np.ndarray) -> np.ndarray:
    lo, hi = float(f.min()), float(f.max())
    if hi <= lo:
        return np.zeros_like(f)
    return (f - lo) / (hi - lo)


# --- Terrain ----------------------------------------------------------------


@dataclass(frozen=True)
class Terrain:
    """Derived fields for a place, all at working resolution."""

    slug: str
    name: str
    lat: float
    lon: float
    alt_m: float
    extent_m: float
    dataset: str
    fetched_at: str
    res: int

    elevation_m: np.ndarray          # altitudes rééchantillonnées, en mètres
    elevation: np.ndarray            # min-max sur la tuile -> [0, 1]
    slope: np.ndarray                # ‖∇h‖, percentiles -> [0, 1]
    aspect: np.ndarray               # atan2(∂h/∂y, ∂h/∂x) -> [-π, π]
    curvature: np.ndarray            # laplacien, percentiles -> [-1, 1]
    roughness: np.ndarray            # écart-type local, percentiles -> [0, 1]
    hypsometry: np.ndarray           # histogramme d'altitude, somme = 1
    grad_x: np.ndarray               # ∂h/∂x brut, m/m (est)
    grad_y: np.ndarray               # ∂h/∂y brut, m/m (nord)

    @property
    def seed(self) -> int:
        return place_seed(self.name, self.lat, self.lon)

    @property
    def step_m(self) -> float:
        """Physical step of the working grid, in meters."""
        return self.extent_m / (self.res - 1)

    # -- échantillonnage -----------------------------------------------------

    def _pixel(self, u: float, v: float) -> tuple[int, int, float, float]:
        """(ligne, colonne, poids) pour des coordonnées de tuile normalisées.

        `u` va de 0 (ouest) à 1 (est), `v` de 0 (nord, haut de page) à 1 (sud).
        La ligne 0 étant au sud, `v` est inversé ici et nulle part ailleurs.
        """
        x = np.clip(u, 0.0, 1.0) * (self.res - 1)
        y = (1.0 - np.clip(v, 0.0, 1.0)) * (self.res - 1)
        col = min(int(x), self.res - 2)
        row = min(int(y), self.res - 2)
        return row, col, y - row, x - col

    def _bilinear(self, arr: np.ndarray, u: float, v: float) -> float:
        row, col, ty, tx = self._pixel(u, v)
        top = arr[row, col] * (1 - tx) + arr[row, col + 1] * tx
        bot = arr[row + 1, col] * (1 - tx) + arr[row + 1, col + 1] * tx
        return float(top * (1 - ty) + bot * ty)

    def sample(self, field_name: str, u: float, v: float) -> float:
        """Valeur interpolée d'un champ scalaire en coordonnées de tuile."""
        return self._bilinear(getattr(self, field_name), u, v)

    def _span(
        self, u0: float, v0: float, u1: float, v1: float
    ) -> tuple[int, int, int, int]:
        """Fenêtre de pixels couvrant une emprise en coordonnées de tuile."""
        last = self.res - 1
        col0 = math.floor(min(max(u0, 0.0), 1.0) * last)
        col1 = math.ceil(min(max(u1, 0.0), 1.0) * last)
        row0 = math.floor((1.0 - min(max(v1, 0.0), 1.0)) * last)
        row1 = math.ceil((1.0 - min(max(v0, 0.0), 1.0)) * last)
        return row0, max(row1, row0 + 1), col0, max(col1, col0 + 1)

    def average(self, field_name: str, u0: float, v0: float, u1: float, v1: float) -> float:
        """Moyenne d'un champ scalaire sur une emprise de tuile.

        C'est l'accès à privilégier quand la marque couvre une surface. Les
        champs dérivés portent du détail bien plus fin que la grille de
        marques ; les lire en un point unique replierait ce détail en bruit,
        et la structure du massif disparaîtrait au profit d'un grésil.
        """
        row0, row1, col0, col1 = self._span(u0, v0, u1, v1)
        return float(getattr(self, field_name)[row0:row1, col0:col1].mean())

    def average_aspect(self, u0: float, v0: float, u1: float, v1: float) -> float:
        """Orientation moyenne sur une emprise, par moyenne vectorielle.

        On moyenne les composantes du gradient, pas l'angle : moyenner des
        angles autour de la coupure ±π n'a aucun sens.
        """
        row0, row1, col0, col1 = self._span(u0, v0, u1, v1)
        gx = float(self.grad_x[row0:row1, col0:col1].mean())
        gy = float(self.grad_y[row0:row1, col0:col1].mean())
        return math.atan2(gy, gx)

    def sample_many(self, field_name: str, us, vs) -> np.ndarray:
        """Valeurs d'un champ en une série de points de tuile.

        Sert à lire le terrain sous une facette de forme quelconque, là où
        `average()` ne sait traiter qu'un rectangle. On échantillonne au plus
        proche voisin : à cette échelle la facette couvre des dizaines de
        pixels, et c'est leur dispersion qui nous intéresse — pas la valeur
        exacte de chacun.
        """
        last = self.res - 1
        cols = np.clip(np.rint(np.asarray(us) * last), 0, last).astype(int)
        rows = np.clip(np.rint((1.0 - np.asarray(vs)) * last), 0, last).astype(int)
        return getattr(self, field_name)[rows, cols]

    def sample_aspect(self, u: float, v: float) -> float:
        """Orientation en coordonnées de tuile, dans [-π, π].

        On interpole les composantes du gradient plutôt que l'angle : une
        interpolation directe de l'angle traverserait la coupure ±π et
        produirait des orientations fausses le long de cette ligne.
        """
        gx = self._bilinear(self.grad_x, u, v)
        gy = self._bilinear(self.grad_y, u, v)
        return math.atan2(gy, gx)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_elevation(
        cls,
        raw: np.ndarray,
        *,
        slug: str,
        name: str,
        lat: float,
        lon: float,
        alt_m: float,
        extent_m: float,
        dataset: str,
        fetched_at: str,
        res: int = WORK_RES,
    ) -> Terrain:
        clean = fill_missing(raw)
        elevation_m = resample(clean, res)

        step = extent_m / (res - 1)
        # np.gradient renvoie les dérivées dans l'ordre des axes : d'abord
        # selon les lignes (nord), puis selon les colonnes (est).
        grad_y, grad_x = np.gradient(elevation_m, step, step)

        slope_raw = np.hypot(grad_x, grad_y)
        aspect = np.arctan2(grad_y, grad_x)

        d2y, _ = np.gradient(grad_y, step, step)
        _, d2x = np.gradient(grad_x, step, step)
        curvature_raw = d2x + d2y

        # La rugosité se mesure sur la grille **brute**, pas sur la grille de
        # travail. À 256 points pour 48 mesures, une fenêtre de 5 pixels couvre
        # 94 m — moins que le pas de la donnée : on n'y lirait que l'ondulation
        # de l'interpolant. Sur la grille brute, la même fenêtre couvre 640 m
        # de terrain réel.
        roughness_raw = resample(detrended_roughness(clean), res)

        counts, _ = np.histogram(elevation_m, bins=HYPSO_BINS)
        total = counts.sum()
        hypsometry = counts / total if total else np.zeros(HYPSO_BINS)

        return cls(
            slug=slug,
            name=name,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            extent_m=extent_m,
            dataset=dataset,
            fetched_at=fetched_at,
            res=res,
            elevation_m=elevation_m,
            elevation=norm_minmax(elevation_m),
            slope=norm_unit(slope_raw),
            aspect=aspect,
            curvature=norm_signed(curvature_raw),
            roughness=norm_unit(roughness_raw),
            hypsometry=hypsometry,
            grad_x=grad_x,
            grad_y=grad_y,
        )

    @classmethod
    def load(cls, slug: str, res: int = WORK_RES) -> Terrain:
        """Read the cache. Never touches the network."""
        path = cache_path(slug)
        if not path.exists():
            raise FileNotFoundError(
                f"no cache for '{slug}' ({path}). "
                f"Run first: python fetch_all.py --only {slug}"
            )
        with np.load(path, allow_pickle=False) as npz:
            return cls.from_elevation(
                npz["elevation"],
                slug=str(npz["slug"]),
                name=str(npz["name"]),
                lat=float(npz["lat"]),
                lon=float(npz["lon"]),
                alt_m=float(npz["alt_m"]),
                extent_m=float(npz["extent_m"]),
                dataset=str(npz["dataset"]),
                fetched_at=str(npz["fetched_at"]),
                res=res,
            )


def save_tile(
    slug: str,
    elevation: np.ndarray,
    *,
    name: str,
    lat: float,
    lon: float,
    alt_m: float,
    extent_m: float,
    dataset: str,
    fetched_at: str,
    path: Path | None = None,
) -> Path:
    """Write a raw elevation tile and metadata to the cache."""
    path = path or cache_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        elevation=np.asarray(elevation, dtype=np.float64),
        slug=slug,
        name=name,
        lat=lat,
        lon=lon,
        alt_m=alt_m,
        extent_m=extent_m,
        resolution=elevation.shape[0],
        dataset=dataset,
        fetched_at=fetched_at,
    )
    return path
