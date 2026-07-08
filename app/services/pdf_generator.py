import asyncio
import io
from html import escape
from threading import Lock

from app.config import settings

PDF_LOCK = Lock()
import logging
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.utils.charts import (
    chart_ca_charges_bars,
    chart_charges_donut,
    chart_evolution_mm,
    chart_heatmap,
    chart_kpi_dashboard,
    chart_marge_brute,
    chart_waterfall_resultat,
)

logger = logging.getLogger(__name__)

# Palette
NAVY = colors.HexColor("#041627")
NAVY_MED = colors.HexColor("#1A2B3C")
EMERALD = colors.HexColor("#006c49")
ERROR_RED = colors.HexColor("#ba1a1a")
SURFACE = colors.HexColor("#f7fafc")
SURFACE_LOW = colors.HexColor("#f1f4f6")
OUTLINE = colors.HexColor("#74777d")
OUTLINE_VAR = colors.HexColor("#c4c6cd")
ON_SURFACE = colors.HexColor("#181c1e")
ON_SUR_VAR = colors.HexColor("#44474c")
WHITE = colors.white

GREEN_LIGHT = colors.HexColor("#d1fae5")
RED_LIGHT = colors.HexColor("#fee2e2")
GREEN_TEXT = EMERALD
RED_TEXT = ERROR_RED

PAGE_W, PAGE_H = A4
SIDEBAR_W = 1.1 * cm
MARGIN_L = SIDEBAR_W + 1.6 * cm
MARGIN_R = 1.4 * cm
MARGIN_T = 1.8 * cm
MARGIN_B = 1.8 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

MOIS_SHORT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]


def _styles():
    return {
        "label_caps": ParagraphStyle(
            "label_caps",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=WHITE,
            leading=12,
            spaceAfter=2,
        ),
        "label_caps_navy": ParagraphStyle(
            "label_caps_navy", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=12
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=28, textColor=NAVY, leading=32, spaceAfter=4
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=NAVY,
            leading=24,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "section_num": ParagraphStyle(
            "section_num",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=NAVY,
            leading=12,
            spaceBefore=14,
            spaceAfter=4,
        ),
        "mono_lg": ParagraphStyle(
            "mono_lg", fontName="Helvetica-Bold", fontSize=18, textColor=NAVY, leading=22
        ),
        "mono_md": ParagraphStyle(
            "mono_md", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY, leading=17
        ),
        "mono_sm": ParagraphStyle(
            "mono_sm", fontName="Helvetica", fontSize=9, textColor=ON_SURFACE, leading=13
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=ON_SURFACE,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
        "body_sm": ParagraphStyle(
            "body_sm", fontName="Helvetica", fontSize=8, textColor=ON_SUR_VAR, leading=12
        ),
        "body_bold": ParagraphStyle(
            "body_bold", fontName="Helvetica-Bold", fontSize=9, textColor=ON_SURFACE, leading=14
        ),
        "cover_label": ParagraphStyle(
            "cover_label", fontName="Helvetica-Bold", fontSize=8, textColor=ON_SUR_VAR, leading=12
        ),
        "cover_company": ParagraphStyle(
            "cover_company",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=NAVY,
            leading=14,
            spaceAfter=2,
        ),
        "fallback": ParagraphStyle(
            "fallback",
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=colors.HexColor("#b45309"),
            leading=12,
            spaceAfter=4,
        ),
        "indicator_green": ParagraphStyle(
            "indicator_green", fontName="Helvetica-Bold", fontSize=8, textColor=EMERALD, leading=12
        ),
        "indicator_red": ParagraphStyle(
            "indicator_red", fontName="Helvetica-Bold", fontSize=8, textColor=ERROR_RED, leading=12
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=7, textColor=OUTLINE, leading=10
        ),
        "ai_quote": ParagraphStyle(
            "ai_quote",
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=NAVY,
            leading=14,
            leftIndent=8,
            alignment=TA_JUSTIFY,
        ),
        "chart_caption": ParagraphStyle(
            "chart_caption",
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            textColor=ON_SUR_VAR,
            leading=11,
            spaceAfter=8,
            alignment=TA_CENTER,
        ),
    }


def _tnd(v: float, sign=False) -> str:
    s = f"{v:,.0f}".replace(",", " ")
    if sign and v > 0:
        s = f"+{s}"
    return f"{s} TND"


def _pct(v: float, sign=True) -> str:
    return f"{'+' if sign and v > 0 else ''}{v:.1f}%"


def _pct_color(v: float):
    return EMERALD if v >= 0 else ERROR_RED


def _section_rule(color=OUTLINE_VAR, thickness=0.5) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=8, spaceBefore=4)


def _img_from_buf(buf: io.BytesIO, width=None, height=None) -> Image:
    width = width or CONTENT_W
    return Image(buf, width=width, height=height or width * 0.38)


def _caption(s, text: str) -> Paragraph:
    return Paragraph(text, s["chart_caption"])


def _draw_sidebar(canvas, is_cover=False):
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, SIDEBAR_W, PAGE_H, fill=1, stroke=0)
    if is_cover:
        canvas.setFillColor(EMERALD)
        canvas.rect(0, 0, SIDEBAR_W, 2.5 * cm, fill=1, stroke=0)


def _draw_footer(canvas, page_num: int, section: str, annee: int):
    canvas.saveState()
    y = MARGIN_B - 0.5 * cm
    canvas.setStrokeColor(OUTLINE_VAR)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_L, y + 0.3 * cm, PAGE_W - MARGIN_R, y + 0.3 * cm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(OUTLINE)
    canvas.drawString(
        MARGIN_L, y, f"© {annee} Reporting Mensuel  •  Rapport confidentiel  •  {section}"
    )
    canvas.drawRightString(PAGE_W - MARGIN_R, y, f"Page {page_num}")
    canvas.restoreState()


def _kpi_block_3col(
    s, label1, val1, trend1, label2, val2, trend2, label3, val3, trend3, col_w=None
) -> Table:
    if col_w is None:
        col_w = [CONTENT_W / 3] * 3

    def cell(label, val, trend):
        return [
            Paragraph(label, s["label_caps_navy"]),
            Paragraph(val, s["mono_lg"]),
            Paragraph(trend[0], s["indicator_green"] if trend[1] else s["indicator_red"]),
        ]

    data = [[cell(label1, val1, trend1), cell(label2, val2, trend2), cell(label3, val3, trend3)]]
    t = Table(data, colWidths=col_w)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBEFORE", (0, 0), (0, 0), 2, NAVY),
                ("LINEBEFORE", (1, 0), (1, 0), 2, NAVY),
                ("LINEBEFORE", (2, 0), (2, 0), 2, NAVY),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.5, OUTLINE_VAR),
                ("LINEAFTER", (0, 0), (1, 0), 0.5, OUTLINE_VAR),
            ]
        )
    )
    return t


def _page_cover(s, kpis) -> list:
    elems = []
    now = datetime.now(UTC)

    header_data = [
        [
            Paragraph("REPORTING MENSUEL", s["cover_company"]),
            Paragraph("CONFIDENTIEL", s["label_caps"]),
        ]
    ]
    ht = Table(header_data, colWidths=[CONTENT_W * 0.7, CONTENT_W * 0.3])
    ht.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elems.append(ht)
    elems.append(Spacer(1, 0.15 * cm))
    elems.append(
        HRFlowable(width=CONTENT_W, thickness=1.5, color=NAVY, spaceAfter=0, spaceBefore=0)
    )
    elems.append(Spacer(1, 3.5 * cm))

    elems.append(Paragraph("RAPPORT FINANCIER ANNUEL", s["label_caps_navy"]))
    elems.append(Spacer(1, 0.3 * cm))
    elems.append(Paragraph(f"Exercice Comptable<br/>{kpis.annee}", s["h1"]))
    elems.append(Spacer(1, 0.8 * cm))

    badge_data = [
        [
            Paragraph(
                f"EXERCICE {kpis.annee}",
                ParagraphStyle(
                    "badge", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=12
                ),
            ),
            Spacer(0.6 * cm, 0.1),
            Paragraph(
                "Analyse comptable · KPIs · Tendances · Recommandations · 7 Visualisations",
                ParagraphStyle(
                    "sub",
                    fontName="Helvetica-Oblique",
                    fontSize=9,
                    textColor=ON_SUR_VAR,
                    leading=13,
                ),
            ),
        ]
    ]
    bt = Table(badge_data, colWidths=[2.6 * cm, 0.6 * cm, CONTENT_W - 3.2 * cm])
    bt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (1, 0), (2, 0), 0),
                ("RIGHTPADDING", (1, 0), (2, 0), 0),
            ]
        )
    )
    elems.append(bt)
    elems.append(Spacer(1, 4.5 * cm))

    re = kpis.resultat_exploitation_annuel
    re_str = _tnd(re, sign=True)
    re_color = EMERALD if re >= 0 else ERROR_RED

    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.4 * cm))

    info_data = [
        [
            [
                Paragraph("INDICATEURS CLÉS", s["label_caps"]),
                Spacer(1, 0.2 * cm),
                Table(
                    [
                        [
                            Paragraph("Chiffre d'affaires", s["body_sm"]),
                            Paragraph(_tnd(kpis.ca_annuel), s["mono_sm"]),
                        ],
                        [
                            Paragraph("Résultat exploitation", s["body_sm"]),
                            Paragraph(
                                re_str,
                                ParagraphStyle(
                                    "re_cover",
                                    fontName="Helvetica-Bold",
                                    fontSize=9,
                                    textColor=re_color,
                                    leading=13,
                                ),
                            ),
                        ],
                        [
                            Paragraph("Marge brute", s["body_sm"]),
                            Paragraph(f"{kpis.marge_brute_annuelle:.1f}%", s["mono_sm"]),
                        ],
                        [
                            Paragraph("Meilleur mois", s["body_sm"]),
                            Paragraph(kpis.mois_plus_fort, s["mono_sm"]),
                        ],
                    ],
                    colWidths=[3.8 * cm, 3.8 * cm],
                    style=TableStyle(
                        [
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ]
                    ),
                ),
            ],
            [
                Paragraph("ÉTABLI PAR", s["label_caps"]),
                Spacer(1, 0.15 * cm),
                Paragraph("Reporting Mensuel", s["body_bold"]),
                Paragraph("Plateforme d'analyse comptable", s["body_sm"]),
                Spacer(1, 0.4 * cm),
                Paragraph("DATE D'ÉMISSION", s["label_caps"]),
                Spacer(1, 0.1 * cm),
                Paragraph(
                    now.strftime("%d %B %Y").upper(),
                    ParagraphStyle(
                        "date_cover",
                        fontName="Helvetica-Bold",
                        fontSize=10,
                        textColor=NAVY,
                        leading=14,
                    ),
                ),
                Spacer(1, 0.3 * cm),
                Table(
                    [
                        [
                            Paragraph(
                                "DOCUMENT GÉNÉRÉ AUTOMATIQUEMENT",
                                ParagraphStyle(
                                    "cert",
                                    fontName="Helvetica-Bold",
                                    fontSize=7,
                                    textColor=NAVY,
                                    leading=10,
                                ),
                            ),
                        ]
                    ],
                    colWidths=[5.5 * cm],
                    style=TableStyle(
                        [
                            ("BOX", (0, 0), (-1, -1), 0.8, OUTLINE_VAR),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ]
                    ),
                ),
            ],
        ]
    ]
    info_t = Table(info_data, colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    info_t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elems.append(info_t)
    elems.append(Spacer(1, 1.5 * cm))

    elems.append(_section_rule(OUTLINE_VAR, 0.4))
    ref_data = [
        [
            Paragraph("ID RAPPORT", s["label_caps"]),
            Paragraph(f"REF-{kpis.annee}-FIN-{now.strftime('%m%d')}", s["mono_sm"]),
            Spacer(0.1, 0.1),
            Paragraph("EXERCICE COMPTABLE", s["label_caps"]),
            Paragraph(
                str(kpis.annee),
                ParagraphStyle(
                    "ref_yr", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, leading=14
                ),
            ),
        ]
    ]
    ref_t = Table(ref_data, colWidths=[2 * cm, 4 * cm, 0.5 * cm, 3.5 * cm, 2 * cm])
    ref_t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(ref_t)
    elems.append(PageBreak())
    return elems


def _page_dashboard(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Tableau de Bord — Vue d'Ensemble", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. SCORECARD FINANCIÈRE", s["section_num"]))
    elems.append(_section_rule())
    buf = chart_kpi_dashboard(kpis)
    elems.append(_img_from_buf(buf, width=CONTENT_W, height=7.5 * cm))
    elems.append(_caption(s, "Synthèse des 6 KPIs annuels avec sparklines mensuelles"))
    elems.append(Spacer(1, 0.4 * cm))

    elems.append(Paragraph("02. HEATMAP FINANCIÈRE MENSUELLE", s["section_num"]))
    elems.append(_section_rule())
    buf2 = chart_heatmap(kpis)
    elems.append(_img_from_buf(buf2, width=CONTENT_W, height=3.5 * cm))
    elems.append(
        _caption(s, "Intensité relative des montants mensuels : CA · Charges · Résultat (kTND)")
    )

    elems.append(PageBreak())
    return elems


def _page_kpis(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Indicateurs Clés de Performance", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. INDICATEURS ANNUELS", s["section_num"]))
    elems.append(_section_rule())
    re = kpis.resultat_exploitation_annuel
    elems.append(
        _kpi_block_3col(
            s,
            "CHIFFRE D'AFFAIRES",
            _tnd(kpis.ca_annuel),
            (f"Moy. mensuelle : {kpis.ca_annuel / 12:,.0f}".replace(",", " ") + " TND", True),
            "TOTAL CHARGES",
            _tnd(kpis.charges_annuelles),
            (f"Personnel : {kpis.charges_personnel_pourcentage:.1f}% des charges", False),
            "RÉSULTAT D'EXPLOITATION",
            _tnd(re, sign=True),
            ("Bénéficiaire" if re >= 0 else "Déficitaire", re >= 0),
        )
    )
    elems.append(Spacer(1, 0.4 * cm))
    elems.append(
        _kpi_block_3col(
            s,
            "MARGE BRUTE",
            f"{kpis.marge_brute_annuelle:.2f}%",
            ("CA - Achats / CA", True),
            "MEILLEUR MOIS",
            kpis.mois_plus_fort,
            (_tnd(kpis.ca_mensuel.get(kpis.mois_plus_fort, 0)), True),
            "MOIS LE PLUS FAIBLE",
            kpis.mois_plus_faible,
            (_tnd(kpis.ca_mensuel.get(kpis.mois_plus_faible, 0)), False),
        )
    )
    elems.append(Spacer(1, 0.5 * cm))

    # Tableau évolution M/M
    elems.append(Paragraph("02. ÉVOLUTION MENSUELLE DU CHIFFRE D'AFFAIRES (M/M)", s["section_num"]))
    elems.append(_section_rule())
    evol_months = list(kpis.evolution_ca_mm.keys())
    evol_values = list(kpis.evolution_ca_mm.values())

    header = [Paragraph("MOIS", s["label_caps"])]
    header += [Paragraph(m[:3].upper(), s["label_caps"]) for m in evol_months]
    row_ca = [Paragraph("CA (K TND)", s["label_caps_navy"])]
    row_ca += [
        Paragraph(f"{kpis.ca_mensuel.get(m, 0) / 1000:,.0f}".replace(",", " "), s["mono_sm"])
        for m in evol_months
    ]
    row_evol = [Paragraph("ÉVOL. M/M", s["label_caps_navy"])]
    row_evol += [
        Paragraph(
            _pct(v),
            ParagraphStyle(
                f"ev_{i}",
                fontName="Helvetica-Bold",
                fontSize=8,
                textColor=_pct_color(v),
                leading=12,
            ),
        )
        for i, v in enumerate(evol_values)
    ]

    col_w = [2.8 * cm] + [(CONTENT_W - 2.8 * cm) / len(evol_months)] * len(evol_months)
    evol_t = Table([header, row_ca, row_evol], colWidths=col_w, repeatRows=1)
    evol_style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, 1), SURFACE_LOW),
        ("BACKGROUND", (0, 2), (-1, 2), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.3, OUTLINE_VAR),
        ("LINEBELOW", (0, 2), (-1, 2), 1.5, NAVY),
    ]
    for i, v in enumerate(evol_values, start=1):
        evol_style.append(("BACKGROUND", (i, 2), (i, 2), GREEN_LIGHT if v >= 0 else RED_LIGHT))
    evol_t.setStyle(TableStyle(evol_style))
    elems.append(evol_t)
    elems.append(Spacer(1, 0.4 * cm))

    # Tableau charges
    elems.append(Paragraph("03. CHARGES PAR CATÉGORIE", s["section_num"]))
    elems.append(_section_rule())
    cat_header = [
        Paragraph("CATÉGORIE", s["label_caps"]),
        Paragraph("MONTANT (TND)", s["label_caps"]),
        Paragraph("% CHARGES", s["label_caps"]),
        Paragraph("% CA", s["label_caps"]),
    ]
    cat_rows = [cat_header]
    total_ch = kpis.charges_annuelles or 1
    for label, val in sorted(kpis.charges_par_categorie.items(), key=lambda x: x[1], reverse=True):
        if val > 0:
            cat_rows.append(
                [
                    Paragraph(label, s["body_sm"]),
                    Paragraph(f"{val:,.0f}".replace(",", " "), s["mono_sm"]),
                    Paragraph(f"{val / total_ch * 100:.1f}%", s["mono_sm"]),
                    Paragraph(f"{val / (kpis.ca_annuel or 1) * 100:.1f}%", s["body_sm"]),
                ]
            )
    cat_rows.append(
        [
            Paragraph("TOTAL CHARGES", s["label_caps_navy"]),
            Paragraph(
                f"{kpis.charges_annuelles:,.0f}".replace(",", " "),
                ParagraphStyle(
                    "tot", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=12
                ),
            ),
            Paragraph("100.0%", s["label_caps_navy"]),
            Paragraph(
                f"{kpis.charges_annuelles / (kpis.ca_annuel or 1) * 100:.1f}%", s["label_caps_navy"]
            ),
        ]
    )
    cat_cw = [6.5 * cm, 3.5 * cm, 2.5 * cm, 2.5 * cm]
    cat_t = Table(cat_rows, colWidths=cat_cw, repeatRows=1)
    n_data = len(cat_rows) - 1
    cat_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, n_data - 1), [WHITE, SURFACE_LOW]),
                ("GRID", (0, 0), (-1, n_data - 1), 0.3, OUTLINE_VAR),
                ("LINEABOVE", (0, -1), (-1, -1), 1.5, NAVY),
                ("LINEBELOW", (0, -1), (-1, -1), 2.5, NAVY),
                ("BACKGROUND", (0, -1), (-1, -1), SURFACE_LOW),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    elems.append(cat_t)
    elems.append(PageBreak())
    return elems


def _page_charts_ca(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Évolution CA · Charges · Résultat", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. CA VS CHARGES — BARRES GROUPÉES + RÉSULTAT", s["section_num"]))
    elems.append(_section_rule())
    buf = chart_ca_charges_bars(kpis)
    elems.append(_img_from_buf(buf, width=CONTENT_W, height=6.2 * cm))
    elems.append(
        _caption(
            s,
            "Barres groupées CA / Charges (axe gauche) · Courbe résultat exploitation (axe droit) · "
            "Annotations pic et creux",
        )
    )
    elems.append(Spacer(1, 0.5 * cm))

    elems.append(Paragraph("02. ÉVOLUTION M/M DIVERGENTE — CA ET CHARGES", s["section_num"]))
    elems.append(_section_rule())
    buf2 = chart_evolution_mm(kpis)
    elems.append(_img_from_buf(buf2, width=CONTENT_W, height=5.5 * cm))
    elems.append(
        _caption(
            s,
            "Barres divergentes : vert = croissance, rouge = décroissance · "
            "CA (gauche) et Charges (droite) côte à côte",
        )
    )

    elems.append(PageBreak())
    return elems


def _page_charts_marge(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Marge Brute & Résultat d'Exploitation", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. MARGE BRUTE MENSUELLE — ZONE CHART", s["section_num"]))
    elems.append(_section_rule())
    buf = chart_marge_brute(kpis)
    elems.append(_img_from_buf(buf, width=CONTENT_W, height=4.8 * cm))
    elems.append(
        _caption(
            s,
            "Zone verte = au-dessus de la moyenne annuelle · Zone rouge = en-dessous · "
            f"Moyenne annuelle : {kpis.marge_brute_annuelle:.2f}%",
        )
    )
    elems.append(Spacer(1, 0.5 * cm))

    elems.append(Paragraph("02. RÉSULTAT MENSUEL ET PROGRESSION CUMULÉE", s["section_num"]))
    elems.append(_section_rule())
    buf2 = chart_waterfall_resultat(kpis)
    elems.append(_img_from_buf(buf2, width=CONTENT_W, height=8.5 * cm))
    elems.append(
        _caption(
            s,
            "Haut : résultat mensuel (vert = bénéfice, rouge = déficit) · "
            "Bas : courbe cumulative avec résultat final annoté",
        )
    )

    elems.append(PageBreak())
    return elems


def _page_charges(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Répartition des Charges d'Exploitation", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. DONUT — RÉPARTITION PAR CATÉGORIE", s["section_num"]))
    elems.append(_section_rule())
    buf = chart_charges_donut(kpis)
    elems.append(_img_from_buf(buf, width=CONTENT_W, height=6.5 * cm))
    elems.append(
        _caption(s, "Donut avec total au centre · Légende avec barres proportionnelles et montants")
    )
    elems.append(Spacer(1, 0.4 * cm))

    elems.append(Paragraph("02. KEY METRICS — CHARGES", s["section_num"]))
    elems.append(_section_rule())
    total_ch = kpis.charges_annuelles or 1
    personnel = kpis.charges_par_categorie.get("Personnel (63xxx)", 0)
    achats = kpis.charges_par_categorie.get("Achats (60xxx)", 0)
    elems.append(
        _kpi_block_3col(
            s,
            "CHARGES TOTALES",
            _tnd(kpis.charges_annuelles),
            (f"{kpis.charges_annuelles / (kpis.ca_annuel or 1) * 100:.1f}% du CA", False),
            "CHARGES PERSONNEL",
            f"{kpis.charges_personnel_pourcentage:.1f}%",
            (_tnd(personnel), False),
            "ACHATS (60xxx)",
            f"{achats / total_ch * 100:.1f}%",
            (_tnd(achats), False),
        )
    )
    elems.append(PageBreak())
    return elems


def _page_monthly(s, kpis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Détail Mensuel — CA · Charges · Résultat", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.3 * cm))

    elems.append(Paragraph("01. TABLEAU MENSUEL COMPLET (TND)", s["section_num"]))
    elems.append(_section_rule())

    months = list(kpis.ca_mensuel.keys())
    th = [
        Paragraph(h, s["label_caps"])
        for h in ["MOIS", "CA", "CHARGES", "RÉSULTAT", "MARGE %", "ÉVOL.CA"]
    ]
    rows = [th]
    for m in months:
        ca = kpis.ca_mensuel[m]
        ch = kpis.charges_mensuelles.get(m, 0)
        re = kpis.resultat_exploitation_mensuel.get(m, 0)
        mg = kpis.marge_brute_mensuelle.get(m, 0)
        ev = kpis.evolution_ca_mm.get(m, None)
        ev_str = _pct(ev) if ev is not None else "—"
        ev_pos = ev >= 0 if ev is not None else True
        rows.append(
            [
                Paragraph(m, s["body_sm"]),
                Paragraph(f"{ca:,.0f}".replace(",", " "), s["mono_sm"]),
                Paragraph(f"{ch:,.0f}".replace(",", " "), s["mono_sm"]),
                Paragraph(
                    f"{re:+,.0f}".replace(",", " "),
                    ParagraphStyle(
                        f"re_{m}",
                        fontName="Helvetica-Bold",
                        fontSize=8,
                        textColor=EMERALD if re >= 0 else ERROR_RED,
                        leading=12,
                    ),
                ),
                Paragraph(f"{mg:.1f}%", s["mono_sm"]),
                Paragraph(
                    ev_str,
                    ParagraphStyle(
                        f"ev_{m}",
                        fontName="Helvetica-Bold",
                        fontSize=8,
                        textColor=EMERALD if ev_pos else ERROR_RED,
                        leading=12,
                    ),
                ),
            ]
        )
    rows.append(
        [
            Paragraph("TOTAL", s["label_caps_navy"]),
            Paragraph(
                f"{kpis.ca_annuel:,.0f}".replace(",", " "),
                ParagraphStyle(
                    "tot_ca", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=12
                ),
            ),
            Paragraph(
                f"{kpis.charges_annuelles:,.0f}".replace(",", " "),
                ParagraphStyle(
                    "tot_ch", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=12
                ),
            ),
            Paragraph(
                f"{kpis.resultat_exploitation_annuel:+,.0f}".replace(",", " "),
                ParagraphStyle(
                    "tot_re",
                    fontName="Helvetica-Bold",
                    fontSize=8,
                    textColor=EMERALD if kpis.resultat_exploitation_annuel >= 0 else ERROR_RED,
                    leading=12,
                ),
            ),
            Paragraph(
                f"{kpis.marge_brute_annuelle:.1f}%",
                ParagraphStyle(
                    "tot_mg", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=12
                ),
            ),
            Paragraph("—", s["body_sm"]),
        ]
    )

    cw = [2 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2 * cm, 2 * cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, SURFACE_LOW]),
        ("GRID", (0, 0), (-1, -2), 0.3, OUTLINE_VAR),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, NAVY),
        ("LINEBELOW", (0, -1), (-1, -1), 2.5, NAVY),
        ("BACKGROUND", (0, -1), (-1, -1), SURFACE_LOW),
    ]
    for i, m in enumerate(months, start=1):
        if m == kpis.mois_plus_fort:
            ts.append(("BACKGROUND", (0, i), (0, i), GREEN_LIGHT))
        elif m == kpis.mois_plus_faible:
            ts.append(("BACKGROUND", (0, i), (0, i), RED_LIGHT))
    t.setStyle(TableStyle(ts))
    elems.append(t)
    elems.append(PageBreak())
    return elems


def _page_analysis(s, kpis, analysis) -> list:
    elems = []
    elems.append(Paragraph(f"RAPPORT FINANCIER {kpis.annee}", s["label_caps"]))
    elems.append(Paragraph("Analyse par Intelligence Artificielle", s["h2"]))
    elems.append(_section_rule(NAVY, 1.5))
    elems.append(Spacer(1, 0.2 * cm))

    if getattr(analysis, "is_fallback", False):
        elems.append(
            Paragraph(
                (
                    "Synthèse automatique locale, sans IA."
                    if analysis.used_model == "local"
                    else "Analyse de secours : service IA indisponible. Synthèse calculée localement."
                ),
                s["fallback"],
            )
        )

    elems.append(Paragraph("01. RÉSUMÉ DE L'EXERCICE", s["section_num"]))
    elems.append(_section_rule())
    resume_block = Table(
        [[Paragraph(escape(analysis.resume), s["ai_quote"])]],
        splitInRow=1,
        colWidths=[CONTENT_W],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE_LOW),
                ("LINEBEFORE", (0, 0), (0, 0), 3, NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("BOX", (0, 0), (-1, -1), 0.4, OUTLINE_VAR),
            ]
        ),
    )
    elems.append(resume_block)
    elems.append(Spacer(1, 0.4 * cm))

    elems.append(Paragraph("02. TENDANCES ET POINTS D'ATTENTION", s["section_num"]))
    elems.append(_section_rule())
    for line in analysis.tendances.split("\n"):
        if line.strip():
            elems.append(Paragraph(escape(line.strip()), s["body"]))
    elems.append(Spacer(1, 0.4 * cm))

    elems.append(Paragraph("03. RECOMMANDATIONS", s["section_num"]))
    elems.append(_section_rule())
    lines = [line.strip() for line in analysis.recommandations.split("\n") if line.strip()]
    reco_rows = []
    for line in lines:
        reco_rows.append(
            [
                Table(
                    [
                        [
                            Paragraph(
                                "●",
                                ParagraphStyle(
                                    "bull",
                                    fontName="Helvetica-Bold",
                                    fontSize=10,
                                    textColor=EMERALD,
                                    leading=14,
                                ),
                            ),
                            Paragraph(escape(line), s["body"]),
                        ]
                    ],
                    colWidths=[0.5 * cm, CONTENT_W - 1 * cm],
                    style=TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]
                    ),
                )
            ]
        )
    if reco_rows:
        reco_t = Table(reco_rows, colWidths=[CONTENT_W], splitInRow=1)
        reco_t.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.3, OUTLINE_VAR),
                ]
            )
        )
        elems.append(reco_t)

    elems.append(Spacer(1, 0.5 * cm))
    elems.append(_section_rule(OUTLINE_VAR))
    model_str = getattr(analysis, "used_model", "N/A")
    elems.append(
        Paragraph(
            f"Analyse générée le {analysis.generated_at.strftime('%d/%m/%Y à %H:%M')} UTC  ·  "
            f"Modèle : {model_str}",
            s["body_sm"],
        )
    )

    elems.append(Spacer(1, 0.5 * cm))
    elems.append(Paragraph("04. CONFIDENTIALITÉ & CONTRÔLES", s["section_num"]))
    elems.append(_section_rule())
    conf_data = [
        [
            Paragraph(
                "AVIS DE CONFIDENTIALITÉ\nCe document contient des données financières "
                "propriétaires et confidentielles destinées exclusivement au personnel "
                "autorisé. Toute reproduction ou diffusion sans consentement écrit est "
                "strictement interdite.",
                s["body_sm"],
            ),
            Paragraph(
                f"CONTRÔLES AUTOMATIQUES\nRapport généré par Reporting Mensuel "
                f"le {datetime.now(UTC).strftime('%d/%m/%Y')}. "
                "Toutes les données ont été calculées à partir du fichier CSV comptable "
                "fourni. Document non certifié, à valider par un comptable.",
                s["body_sm"],
            ),
        ]
    ]
    conf_t = Table(conf_data, colWidths=[CONTENT_W / 2 - 0.3 * cm, CONTENT_W / 2 - 0.3 * cm])
    conf_t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elems.append(conf_t)
    return elems


class _ReportCanvas:
    SECTIONS = [
        "PAGE DE GARDE",
        "TABLEAU DE BORD",
        "KPIs & INDICATEURS",
        "ÉVOLUTION CA & CHARGES",
        "MARGE & RÉSULTAT",
        "RÉPARTITION CHARGES",
        "DÉTAIL MENSUEL",
        "ANALYSE IA",
    ]

    def __init__(self, annee: int):
        self.annee = annee

    def __call__(self, canvas, doc):
        canvas.saveState()
        page = canvas.getPageNumber()
        _draw_sidebar(canvas, is_cover=(page == 1))
        section = "RAPPORT FINANCIER"
        _draw_footer(canvas, page, section, self.annee)
        canvas.restoreState()


async def generate_pdf(
    kpis, analysis, task_id: str, reports_dir=None, comparison=None, warnings=None
) -> Path:
    return await asyncio.to_thread(
        _generate_locked, kpis, analysis, task_id, reports_dir, comparison, warnings
    )


def _generate_locked(kpis, analysis, task_id, reports_dir, comparison, warnings):
    # Matplotlib uses process-global state; serialize rendering across callers.
    with PDF_LOCK:
        return _generate_pdf(kpis, analysis, task_id, reports_dir, comparison, warnings)


def _generate_pdf(kpis, analysis, task_id, reports_dir, comparison, warnings) -> Path:
    """Génère le rapport PDF enrichi (8 pages, 7 graphiques)."""
    reports_dir = Path(reports_dir or settings.reports_dir).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"rapport_{kpis.annee}_{task_id}.pdf"
    report_path = reports_dir / filename

    logger.info(f"Génération PDF, path:  {report_path}")

    doc = SimpleDocTemplate(
        str(report_path.with_suffix(".tmp")),
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title=f"Rapport Financier {kpis.annee}",
        author="Reporting Mensuel",
        subject=f"Analyse comptable exercice {kpis.annee}",
        creator="Reporting Mensuel 1.0",
    )

    s = _styles()
    story = []
    story += _page_cover(s, kpis)
    story += _page_dashboard(s, kpis)
    story += _page_kpis(s, kpis)
    story += _page_charts_ca(s, kpis)
    story += _page_charts_marge(s, kpis)
    story += _page_charges(s, kpis)
    story += _page_monthly(s, kpis)
    story += _page_analysis(s, kpis, analysis)
    story.append(PageBreak())
    story.append(Paragraph("Contrôles et points à vérifier", s["h2"]))
    story.append(
        Paragraph(
            "Les alertes signalent des variations, pas des erreurs comptables établies. "
            "Le résultat présenté est le solde des produits et charges importés. "
            "Les ratios dont la base est nulle sont conventionnellement affichés à zéro.",
            s["body"],
        )
    )
    for warning in warnings or []:
        story.append(Paragraph(escape(warning), s["body_sm"]))
    anomalies = kpis.anomalies_detectees
    if not anomalies:
        story.append(Paragraph("Aucune variation dépassant le seuil configuré.", s["body"]))
    for item in anomalies[:100]:
        story.append(
            Paragraph(
                escape(
                    f"{item.compte} - {item.libelle} : {item.previous_month} / {item.month}, "
                    f"{item.variation_pct:+.1f} %"
                ),
                s["body"],
            )
        )
    if len(anomalies) > 100:
        story.append(
            Paragraph(
                "Affichage limité aux 100 premières alertes. Liste complète dans l'application.",
                s["body"],
            )
        )
    if comparison:
        story.append(
            Paragraph(
                f"Comparaison {comparison['previous_year']} / {comparison['current_year']}", s["h2"]
            )
        )
        labels = {
            "ca_annuel": "Chiffre d'affaires",
            "charges_annuelles": "Charges",
            "resultat_exploitation_annuel": "Solde produits - charges",
            "marge_brute_annuelle": "Marge brute (%)",
        }
        for key, values in comparison["indicators"].items():
            story.append(
                Paragraph(
                    escape(
                        f"{labels[key]} : {values['previous']:,.2f} / {values['current']:,.2f} "
                        f"(écart : {values['difference']:+,.2f})"
                    ),
                    s["body"],
                )
            )

    cb = _ReportCanvas(kpis.annee)
    try:
        doc.build(story, onFirstPage=cb, onLaterPages=cb)
        report_path.with_suffix(".tmp").replace(report_path)
    finally:
        report_path.with_suffix(".tmp").unlink(missing_ok=True)

    size_kb = report_path.stat().st_size / 1024
    logger.info(f"PDF généré : {report_path} ({size_kb:.0f} Ko)")
    return report_path
