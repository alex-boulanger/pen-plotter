"""
Scanlines — blocs de densité en lignes horizontales.

Le principe : une seule grille de rangées horizontales pour toute la page.
Chaque bloc décide, pour la portion de grille qu'il occupe, quelles rangées
tracer — toutes (aplat), une sur deux, une sur quatre, une sur huit (peigne).

Comme les rangées sont globales, deux blocs voisins s'alignent parfaitement.
C'est ce qui fait tenir l'ensemble.

Deux couches, deux stylos :
  1 — rouge
  2 — bleu

Lancer :  vsk run <nom-du-projet>
"""

import numpy as np
import vsketch

PAGE_W, PAGE_H = 21.0, 29.7  # A4 portrait, en cm

DENSITIES = [1, 1, 1, 2, 4, 8, 0]


class ScanlineSketch(vsketch.SketchClass):
    row_pitch = vsketch.Param(0.055, 0.02, step=0.008)  # cm entre deux rangées
    margin = vsketch.Param(3.0, 0.0, step=0.5)

    n_clusters = vsketch.Param(5, 1, 20)
    cluster_w = vsketch.Param(6.0, 1.0, step=0.5)       # largeur max d'un bloc
    cluster_h = vsketch.Param(7.0, 1.0, step=0.5)       # hauteur max d'un bloc

    n_columns = vsketch.Param(4, 1, 12)                 # subdivisions verticales
    n_bands = vsketch.Param(5, 1, 20)                   # subdivisions horizontales

    ragged = vsketch.Param(0.35, 0.0, 1.0, step=0.05)   # proba de bord déchiqueté
    ragged_depth = vsketch.Param(0.8, 0.0, step=0.1)    # amplitude, en cm

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.penWidth("0.4mm", 1)
        vsk.penWidth("0.4mm", 2)

        # --- La grille globale de rangées ----------------------------------
        rows = np.arange(self.margin, PAGE_H - self.margin, self.row_pitch)
        n_rows = len(rows)

        for _ in range(self.n_clusters):
            layer = 1 if vsk.random(1) < 0.5 else 2
            vsk.stroke(layer)

            # Emprise du bloc : en cm horizontalement, en indices de rangée
            # verticalement — pour rester collé à la grille.
            x0 = vsk.random(self.margin, PAGE_W - self.margin - 2)
            w = vsk.random(2.0, min(self.cluster_w, PAGE_W - self.margin - x0))

            h_rows = int(self.cluster_h / self.row_pitch)
            r0 = int(vsk.random(0, max(1, n_rows - h_rows)))
            r1 = min(n_rows, r0 + h_rows)

            self.draw_cluster(vsk, rows, x0, x0 + w, r0, r1)

    # ----------------------------------------------------------------------
    def draw_cluster(self, vsk, rows, x_left, x_right, r0, r1):
        """Découpe le bloc en colonnes, chaque colonne en bandes de densité."""
        cuts = sorted(vsk.random(x_left, x_right) for _ in range(self.n_columns - 1))
        edges = [x_left] + cuts + [x_right]

        for cx0, cx1 in zip(edges, edges[1:]):
            if cx1 - cx0 < 0.15:
                continue  # colonne trop fine pour être lisible

            # Découpe verticale de la colonne, alignée sur les rangées.
            row_cuts = sorted(
                int(vsk.random(r0, r1)) for _ in range(self.n_bands - 1)
            )
            bounds = [r0] + row_cuts + [r1]

            for br0, br1 in zip(bounds, bounds[1:]):
                if br1 <= br0:
                    continue
                density = DENSITIES[int(vsk.random(0, len(DENSITIES)))]
                if density == 0:
                    continue

                # Bord gauche déchiqueté : chaque rangée démarre un peu ailleurs.
                jag = vsk.random(1) < self.ragged

                for r in range(br0, br1):
                    if r % density:
                        continue
                    start = cx0
                    if jag:
                        start += vsk.random(0, self.ragged_depth)
                    if cx1 - start > 0.05:
                        vsk.line(start, rows[r], cx1, rows[r])

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        # Pas de linemerge ici : il fusionnerait des rangées voisines et
        # détruirait la texture. On se contente de trier les déplacements.
        vsk.vpype("linesimplify linesort")


if __name__ == "__main__":
    ScanlineSketch.display()