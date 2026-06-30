import io

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch

NAVY = "#041627"
NAVY_MED = "#1A2B3C"
EMERALD = "#006c49"
ERROR_RED = "#ba1a1a"
SURFACE = "#f7fafc"
SURFACE_LO = "#f1f4f6"
OUTLINE = "#74777d"
ON_SURFACE = "#181c1e"
ON_SUR_VAR = "#44474c"

PALETTE_CHARGES = [
    "#2E86AB",
    "#E74C3C",
    "#F4A261",
    "#27AE60",
    "#8E44AD",
    "#1A3354",
    "#E67E22",
    "#16A085",
]

MOIS_SHORT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]


def _fig_base(w=14, h=5, facecolor=SURFACE):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(facecolor)
    ax.set_facecolor(facecolor)
    return fig, ax


def _spine_clean(ax, keep_bottom=True, keep_left=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if not keep_bottom:
        ax.spines["bottom"].set_visible(False)
    if not keep_left:
        ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(OUTLINE)
    ax.spines["left"].set_color(OUTLINE)


def _save(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# 1. CA vs Charges — Grouped bar + ligne résultat
def chart_ca_charges_bars(kpis) -> io.BytesIO:
    """Barres groupées CA/Charges + courbe résultat avec annotations."""
    months = list(kpis.ca_mensuel.keys())
    ca_vals = list(kpis.ca_mensuel.values())
    ch_vals = [kpis.charges_mensuelles.get(m, 0) for m in months]
    re_vals = [kpis.resultat_exploitation_mensuel.get(m, 0) for m in months]

    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(len(months))
    bw = 0.38

    ax.bar(
        x - bw / 2, ca_vals, bw, color=NAVY_MED, alpha=0.88, label="Chiffre d'affaires", zorder=3
    )
    ax.bar(x + bw / 2, ch_vals, bw, color=ERROR_RED, alpha=0.72, label="Total charges", zorder=3)

    # Axe secondaire pour résultat
    ax2 = ax.twinx()
    ax2.set_facecolor(SURFACE)
    ax2.plot(
        x,
        re_vals,
        "o-",
        color=EMERALD,
        linewidth=2.2,
        markersize=7,
        label="Résultat exploitation",
        zorder=4,
    )
    ax2.fill_between(x, re_vals, alpha=0.12, color=EMERALD)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax2.set_ylabel("Résultat (TND)", fontsize=10, color=EMERALD)
    ax2.tick_params(axis="y", colors=EMERALD)
    ax2.spines["right"].set_color(EMERALD)
    for sp in ["top", "left", "bottom"]:
        ax2.spines[sp].set_visible(False)

    # Annotations meilleur/pire mois
    best_i = months.index(kpis.mois_plus_fort)
    worst_i = months.index(kpis.mois_plus_faible)
    ax.annotate(
        "▲ Pic",
        xy=(best_i - bw / 2, ca_vals[best_i]),
        xytext=(best_i - bw / 2 - 0.5, ca_vals[best_i] * 1.04),
        fontsize=7.5,
        color=EMERALD,
        fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=EMERALD, lw=0.8),
    )
    ax.annotate(
        "▼ Creux",
        xy=(worst_i - bw / 2, ca_vals[worst_i]),
        xytext=(worst_i - bw / 2 + 0.4, ca_vals[worst_i] * 1.08),
        fontsize=7.5,
        color=ERROR_RED,
        fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=ERROR_RED, lw=0.8),
    )

    ax.set_xticks(x)
    ax.set_xticklabels(MOIS_SHORT, fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.set_ylabel("Montant (TND)", fontsize=10, color=ON_SURFACE)
    ax.set_title(
        f"CA · Charges · Résultat d'exploitation — {kpis.annee}",
        fontsize=14,
        fontweight="bold",
        color=NAVY,
        pad=16,
    )
    ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    _spine_clean(ax)

    # Légende combinée
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(
        handles1 + handles2,
        labels1 + labels2,
        loc="upper left",
        fontsize=9,
        framealpha=0.95,
        edgecolor=OUTLINE,
        fancybox=False,
    )

    plt.tight_layout()
    return _save(fig)


# 2. Évolution M/M CA & Charges — Waterfall-like diverging bars
def chart_evolution_mm(kpis) -> io.BytesIO:
    """Barres divergentes pour l'évolution M/M CA et Charges."""
    months_evol = list(kpis.evolution_ca_mm.keys())
    ca_evol = list(kpis.evolution_ca_mm.values())
    ch_evol = [kpis.evolution_charges_mm.get(m, 0) for m in months_evol]

    x = np.arange(len(months_evol))
    bw = 0.38

    fig, ax = plt.subplots(figsize=(15, 5.5))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    colors_ca = [EMERALD if v >= 0 else ERROR_RED for v in ca_evol]
    colors_ch = [NAVY_MED if v >= 0 else "#e07b6a" for v in ch_evol]

    ax.bar(x - bw / 2, ca_evol, bw, color=colors_ca, alpha=0.88, label="Évol. CA", zorder=3)
    ax.bar(x + bw / 2, ch_evol, bw, color=colors_ch, alpha=0.75, label="Évol. Charges", zorder=3)

    # Valeur sur chaque barre
    for i, (c, ch) in enumerate(zip(ca_evol, ch_evol)):
        ax.text(
            i - bw / 2,
            c + (0.4 if c >= 0 else -1.2),
            f"{c:+.1f}%",
            ha="center",
            va="bottom" if c >= 0 else "top",
            fontsize=7.5,
            color=EMERALD if c >= 0 else ERROR_RED,
            fontweight="bold",
        )
        ax.text(
            i + bw / 2,
            ch + (0.4 if ch >= 0 else -1.2),
            f"{ch:+.1f}%",
            ha="center",
            va="bottom" if ch >= 0 else "top",
            fontsize=7.5,
            color=NAVY_MED if ch >= 0 else "#e07b6a",
            fontweight="bold",
        )

    ax.axhline(0, color=OUTLINE, linewidth=1, linestyle="-", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels([m[:3] for m in months_evol], fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.set_title(
        f"Évolution mensuelle M/M — CA vs Charges ({kpis.annee})",
        fontsize=14,
        fontweight="bold",
        color=NAVY,
        pad=16,
    )
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95, edgecolor=OUTLINE, fancybox=False)
    ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    _spine_clean(ax)

    plt.tight_layout()
    return _save(fig)


# 3. Marge brute mensuelle — Line chart avec zone
def chart_marge_brute(kpis) -> io.BytesIO:
    """Évolution de la marge brute mensuelle avec seuil moyen."""
    months = list(kpis.marge_brute_mensuelle.keys())
    mg_vals = list(kpis.marge_brute_mensuelle.values())
    avg = kpis.marge_brute_annuelle

    fig, ax = plt.subplots(figsize=(14, 4.5))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(len(months))

    ax.fill_between(
        x,
        mg_vals,
        avg,
        where=[v >= avg for v in mg_vals],
        alpha=0.18,
        color=EMERALD,
        interpolate=True,
    )
    ax.fill_between(
        x,
        mg_vals,
        avg,
        where=[v < avg for v in mg_vals],
        alpha=0.18,
        color=ERROR_RED,
        interpolate=True,
    )
    ax.plot(
        x,
        mg_vals,
        "o-",
        color=NAVY_MED,
        linewidth=2.5,
        markersize=8,
        zorder=5,
        label="Marge brute mensuelle",
    )
    ax.axhline(
        avg,
        color=EMERALD,
        linewidth=1.5,
        linestyle="--",
        label=f"Moyenne annuelle : {avg:.2f}%",
        zorder=4,
    )

    # Points annotés (min/max)
    mx_i = mg_vals.index(max(mg_vals))
    mn_i = mg_vals.index(min(mg_vals))
    ax.annotate(
        f"{mg_vals[mx_i]:.1f}%",
        xy=(mx_i, mg_vals[mx_i]),
        xytext=(mx_i, mg_vals[mx_i] + 0.5),
        ha="center",
        fontsize=8,
        color=EMERALD,
        fontweight="bold",
    )
    ax.annotate(
        f"{mg_vals[mn_i]:.1f}%",
        xy=(mn_i, mg_vals[mn_i]),
        xytext=(mn_i, mg_vals[mn_i] - 0.7),
        ha="center",
        fontsize=8,
        color=ERROR_RED,
        fontweight="bold",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(MOIS_SHORT, fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.set_ylim(min(mg_vals) - 2, max(mg_vals) + 2)
    ax.set_title(
        f"Marge brute mensuelle — {kpis.annee}", fontsize=14, fontweight="bold", color=NAVY, pad=16
    )
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95, edgecolor=OUTLINE, fancybox=False)
    ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    _spine_clean(ax)

    plt.tight_layout()
    return _save(fig)


# 4. Charges par catégorie — Donut chart avec légende enrichie
def chart_charges_donut(kpis) -> io.BytesIO:
    """Donut chart des charges avec annotations et légende complète."""
    cat = {k: v for k, v in kpis.charges_par_categorie.items() if v > 0}
    labels = list(cat.keys())
    values = list(cat.values())
    total = sum(values)

    fig, (ax, ax_leg) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1, 1]})
    for a in [fig, ax, ax_leg]:
        if hasattr(a, "patch"):
            a.patch.set_facecolor(SURFACE)
        else:
            a.set_facecolor(SURFACE)
    fig.patch.set_facecolor(SURFACE)

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct=lambda p: f"{p:.1f}%" if p > 4 else "",
        startangle=90,
        colors=PALETTE_CHARGES[: len(values)],
        wedgeprops={"edgecolor": "white", "linewidth": 2.5, "width": 0.6},
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("white")
        at.set_fontweight("bold")

    # Centre du donut — total
    ax.text(
        0,
        0.1,
        f"{total / 1000:.0f}k",
        ha="center",
        va="center",
        fontsize=22,
        fontweight="bold",
        color=NAVY,
    )
    ax.text(0, -0.2, "TND charges", ha="center", va="center", fontsize=9, color=ON_SUR_VAR)

    ax.set_title(
        f"Répartition des charges {kpis.annee}", fontsize=13, fontweight="bold", color=NAVY, pad=14
    )

    # Légende côté droit avec barres
    ax_leg.set_facecolor(SURFACE)
    ax_leg.axis("off")
    y_pos = 0.96
    for i, (label, val) in enumerate(zip(labels, values)):
        pct = val / total * 100
        col = PALETTE_CHARGES[i % len(PALETTE_CHARGES)]
        # Barre horizontale
        bar_w = pct / 100 * 0.55
        ax_leg.add_patch(
            FancyBboxPatch(
                (0.0, y_pos - 0.025),
                bar_w,
                0.038,
                boxstyle="round,pad=0.002",
                facecolor=col,
                alpha=0.85,
                transform=ax_leg.transAxes,
            )
        )
        ax_leg.text(
            0.02,
            y_pos - 0.003,
            label.split("(")[0].strip(),
            transform=ax_leg.transAxes,
            fontsize=8.5,
            va="center",
            color="white",
            fontweight="bold",
        )
        ax_leg.text(
            0.58,
            y_pos - 0.003,
            f"{pct:.1f}%  —  {val:,.0f} TND".replace(",", " "),
            transform=ax_leg.transAxes,
            fontsize=8.5,
            va="center",
            color=ON_SURFACE,
        )
        y_pos -= 0.13

    plt.tight_layout()
    return _save(fig)


# 5. Résultat cumulé annuel — Waterfall chart
def chart_waterfall_resultat(kpis) -> io.BytesIO:
    """Waterfall du résultat exploitation mensuel cumulé."""
    months = list(kpis.resultat_exploitation_mensuel.keys())
    re_vals = list(kpis.resultat_exploitation_mensuel.values())
    cumul = np.cumsum(re_vals)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 8), gridspec_kw={"height_ratios": [1, 1]})
    for ax in [ax1, ax2]:
        ax.set_facecolor(SURFACE)
    fig.patch.set_facecolor(SURFACE)

    # --- Top: barres mensuelles résultat ---
    colors_re = [EMERALD if v >= 0 else ERROR_RED for v in re_vals]
    x = np.arange(len(months))
    bars = ax1.bar(x, re_vals, color=colors_re, alpha=0.88, zorder=3, width=0.65)

    for i, (bar, val) in enumerate(zip(bars, re_vals)):
        ax1.text(
            i,
            val + (1000 if val >= 0 else -2500),
            f"{val:,.0f}".replace(",", " "),
            ha="center",
            fontsize=7.5,
            color=EMERALD if val >= 0 else ERROR_RED,
            fontweight="bold",
        )

    ax1.axhline(0, color=OUTLINE, linewidth=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(MOIS_SHORT, fontsize=10)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax1.set_title(
        f"Résultat d'exploitation mensuel — {kpis.annee}",
        fontsize=13,
        fontweight="bold",
        color=NAVY,
        pad=12,
    )
    ax1.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    _spine_clean(ax1)

    # --- Bottom: courbe cumulative ---
    ax2.fill_between(x, cumul, alpha=0.15, color=EMERALD)
    ax2.plot(x, cumul, "o-", color=EMERALD, linewidth=2.5, markersize=8, zorder=5)
    ax2.axhline(0, color=OUTLINE, linewidth=0.8)

    # Annotation résultat final
    ax2.annotate(
        f"Total : {cumul[-1]:,.0f} TND".replace(",", " "),
        xy=(x[-1], cumul[-1]),
        xytext=(x[-1] - 2, cumul[-1] * 0.85),
        fontsize=10,
        color=EMERALD,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=EMERALD, lw=1.2),
    )

    ax2.set_xticks(x)
    ax2.set_xticklabels(MOIS_SHORT, fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k TND"))
    ax2.set_title(
        "Résultat cumulé (progression annuelle)", fontsize=13, fontweight="bold", color=NAVY, pad=12
    )
    ax2.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    _spine_clean(ax2)

    fig.suptitle("", y=0)
    plt.tight_layout(pad=2.0)
    return _save(fig)


# 6. Heatmap mensuelle — CA, Charges, Résultat
def chart_heatmap(kpis) -> io.BytesIO:
    """Heatmap 3×12 : CA, Charges, Résultat — intensité relative."""
    months = list(kpis.ca_mensuel.keys())
    ca_vals = np.array(list(kpis.ca_mensuel.values()))
    ch_vals = np.array([kpis.charges_mensuelles.get(m, 0) for m in months])
    re_vals = np.array([kpis.resultat_exploitation_mensuel.get(m, 0) for m in months])

    # Normaliser chaque ligne sur [0,1]
    def norm(arr):
        mn, mx = arr.min(), arr.max()
        return (arr - mn) / (mx - mn + 1e-9)

    data = np.vstack([norm(ca_vals), norm(ch_vals), norm(re_vals)])

    fig, ax = plt.subplots(figsize=(15, 3.2))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # Cmap personnalisée Navy→White→Emerald pour résultat
    cmap_green = LinearSegmentedColormap.from_list("ng", [SURFACE_LO, "#b7e4c7", EMERALD], N=256)
    cmap_red = LinearSegmentedColormap.from_list("nr", [SURFACE_LO, "#fca5a5", ERROR_RED], N=256)
    cmap_navy = LinearSegmentedColormap.from_list("nn", [SURFACE_LO, "#93b4d4", NAVY_MED], N=256)

    cmaps = [cmap_navy, cmap_red, cmap_green]
    row_labels = ["CA", "Charges", "Résultat"]
    raw_rows = [ca_vals, ch_vals, re_vals]

    for row_i, (row_data, cmap, raw) in enumerate(zip(data, cmaps, raw_rows)):
        for col_i, (val, raw_val) in enumerate(zip(row_data, raw)):
            rect = plt.Rectangle([col_i - 0.5, row_i - 0.5], 1, 1, color=cmap(val), zorder=2)
            ax.add_patch(rect)
            # Valeur textuelle
            text_color = "white" if val > 0.55 else ON_SURFACE
            ax.text(
                col_i,
                row_i,
                f"{raw_val / 1000:.0f}k",
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color=text_color,
                zorder=3,
            )

    ax.set_xlim(-0.5, 11.5)
    ax.set_ylim(-0.5, 2.5)
    ax.set_xticks(range(12))
    ax.set_xticklabels(MOIS_SHORT, fontsize=10)
    ax.set_yticks(range(3))
    ax.set_yticklabels(row_labels, fontsize=11, fontweight="bold")
    ax.set_title(
        f"Heatmap financière mensuelle — {kpis.annee} (en kTND)",
        fontsize=13,
        fontweight="bold",
        color=NAVY,
        pad=14,
    )
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0)

    plt.tight_layout()
    return _save(fig)


# 7. Dashboard KPI — Scorecard visuelle 2×3
def chart_kpi_dashboard(kpis) -> io.BytesIO:
    """Scorecard visuelle : 6 KPIs en grille avec sparklines."""
    months = list(kpis.ca_mensuel.keys())
    ca_vals = list(kpis.ca_mensuel.values())
    ch_vals = [kpis.charges_mensuelles.get(m, 0) for m in months]
    re_vals = list(kpis.resultat_exploitation_mensuel.values())
    mg_vals = list(kpis.marge_brute_mensuelle.values())

    fig = plt.figure(figsize=(16, 7))
    fig.patch.set_facecolor(SURFACE)

    cards = [
        {
            "title": "Chiffre d'affaires",
            "value": f"{kpis.ca_annuel / 1e6:.2f}M TND",
            "sub": f"Moy. {kpis.ca_annuel / 12 / 1000:.0f}k TND/mois",
            "data": ca_vals,
            "color": NAVY_MED,
            "positive": True,
        },
        {
            "title": "Total Charges",
            "value": f"{kpis.charges_annuelles / 1e6:.2f}M TND",
            "sub": f"{kpis.charges_annuelles / kpis.ca_annuel * 100:.1f}% du CA"
            if kpis.ca_annuel
            else "CA nul : ratio non défini",
            "data": ch_vals,
            "color": ERROR_RED,
            "positive": False,
        },
        {
            "title": "Résultat exploitation",
            "value": f"{kpis.resultat_exploitation_annuel / 1000:.0f}k TND",
            "sub": "Bénéficiaire ✓" if kpis.resultat_exploitation_annuel > 0 else "Déficitaire ✗",
            "data": re_vals,
            "color": EMERALD if kpis.resultat_exploitation_annuel >= 0 else ERROR_RED,
            "positive": kpis.resultat_exploitation_annuel >= 0,
        },
        {
            "title": "Marge brute moy.",
            "value": f"{kpis.marge_brute_annuelle:.2f}%",
            "sub": f"Min {min(mg_vals):.1f}% — Max {max(mg_vals):.1f}%",
            "data": mg_vals,
            "color": "#2E86AB",
            "positive": True,
        },
        {
            "title": "Meilleur mois",
            "value": kpis.mois_plus_fort,
            "sub": f"{ca_vals[months.index(kpis.mois_plus_fort)] / 1000:.0f}k TND CA",
            "data": ca_vals,
            "color": EMERALD,
            "positive": True,
        },
        {
            "title": "Mois le plus faible",
            "value": kpis.mois_plus_faible,
            "sub": f"{ca_vals[months.index(kpis.mois_plus_faible)] / 1000:.0f}k TND CA",
            "data": ca_vals,
            "color": ERROR_RED,
            "positive": False,
        },
    ]

    gs = gridspec.GridSpec(
        2, 3, figure=fig, hspace=0.42, wspace=0.3, left=0.04, right=0.97, top=0.9, bottom=0.07
    )

    for i, card in enumerate(cards):
        ax = fig.add_subplot(gs[i // 3, i % 3])
        ax.set_facecolor("white")

        # Fond card
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        # Border-left couleur
        ax.axvline(0, color=card["color"], linewidth=6, ymin=0, ymax=1, zorder=5)

        # Sparkline mini dans le fond
        sp_x = np.linspace(0.05, 0.95, len(card["data"]))
        d = np.array(card["data"], dtype=float)
        d_n = (d - d.min()) / (d.max() - d.min() + 1e-9) * 0.35 + 0.04
        ax.fill_between(sp_x, d_n, 0.04, alpha=0.12, color=card["color"])
        ax.plot(sp_x, d_n, color=card["color"], linewidth=1.2, alpha=0.5)

        # Textes
        ax.text(
            0.08,
            0.86,
            card["title"].upper(),
            transform=ax.transAxes,
            fontsize=8,
            color=ON_SUR_VAR,
            fontweight="bold",
            va="top",
        )
        ax.text(
            0.08,
            0.62,
            card["value"],
            transform=ax.transAxes,
            fontsize=17,
            color=NAVY,
            fontweight="bold",
            va="top",
        )
        ax.text(
            0.08,
            0.30,
            card["sub"],
            transform=ax.transAxes,
            fontsize=9,
            color=card["color"],
            va="top",
        )

        ax.axis("off")
        for spine in ax.spines.values():
            spine.set_edgecolor("#d0d5dd")
            spine.set_linewidth(0.8)
            spine.set_visible(True)

    fig.suptitle(
        f"Tableau de bord financier — Exercice {kpis.annee}",
        fontsize=15,
        fontweight="bold",
        color=NAVY,
        y=0.97,
    )
    return _save(fig)
