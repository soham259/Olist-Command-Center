const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow,
  TableCell, WidthType, ShadingType, BorderStyle, AlignmentType,
} = require("docx");

const COLORS = { accent: "1F4E5F", muted: "666666", bg: "F2F6F5" };

function h1(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 120 } });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 80 },
    children: [new TextRun({ text, color: COLORS.accent, bold: true })],
  });
}
function body(text, opts = {}) {
  return new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text, ...opts })] });
}
function label(labelText, valueText) {
  return new Paragraph({
    spacing: { after: 60 },
    children: [
      new TextRun({ text: labelText + "  ", bold: true, color: COLORS.accent }),
      new TextRun({ text: valueText }),
    ],
  });
}

function recommendationBlock(num, title, observation, evidence, impact, recommendation, outcome) {
  return [
    new Paragraph({
      spacing: { before: 320, after: 100 },
      border: { bottom: { color: COLORS.accent, space: 4, style: BorderStyle.SINGLE, size: 6 } },
      children: [new TextRun({ text: `${num}. ${title}`, bold: true, size: 26, color: COLORS.accent })],
    }),
    label("Observation:", observation),
    label("Evidence:", evidence),
    label("Business impact:", impact),
    label("Recommendation:", recommendation),
    label("Expected outcome:", outcome),
  ];
}

const doc = new Document({
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
    children: [
      new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { after: 40 },
        children: [new TextRun({ text: "Olist Revenue & Logistics Command Center", bold: true, size: 36, color: COLORS.accent })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { after: 40 },
        children: [new TextRun({ text: "Business Recommendations", size: 26, color: COLORS.muted })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { after: 300 },
        children: [new TextRun({ text: "Based on the Olist Brazilian E-Commerce Public Dataset (Sep 2016 – Aug 2018) · Prepared as a portfolio analytics case study", italics: true, size: 18, color: COLORS.muted })],
      }),

      body(
        "This document presents four evidence-based recommendations arising from an end-to-end analysis covering revenue, logistics, seller performance, and data quality across 96,478 delivered orders. Every figure below traces directly to a validated SQL query or dashboard measure; no financial projections beyond what the data supports are included.",
        { size: 21 }
      ),

      ...recommendationBlock(
        1, "Fix the Northeast (Nordeste) delivery gap — a distance-driven logistics problem, not a seller problem",
        "The Nordeste region has a disproportionately high late-delivery rate compared to the rest of the platform.",
        "Nordeste represents 9.38% of all delivered orders but 16.55% of all late deliveries (a 1.76x concentration), with a 14.31% late rate versus the 8.11% platform average, consistent across all 9 Nordeste states individually. Breaking sellers down by their origin state shows the pattern is distance-driven: sellers shipping from within or near Nordeste (Bahia 8.62%, Pernambuco 4.67%) perform near or better than the platform average, while sellers shipping from the distant São Paulo hub run 15.01% late specifically on this route — no individual seller has enough order volume to explain the pattern alone.",
        "Late deliveries are associated with a 1.738-point average review score gap (4.284 on-time vs. 2.546 late). If Nordeste's late rate matched the platform average, an estimated 561 orders per the analyzed period would shift from late to on-time.",
        "Prioritize a carrier/logistics review specifically for the São Paulo-to-Nordeste long-haul shipping lane, rather than auditing individual sellers. Consider a regional fulfillment partner or adjusted delivery-estimate buffer for this route.",
        "A meaningful reduction in Nordeste's late-delivery rate, with a proportional improvement in the region's average review score — success should be measured by tracking Nordeste's late rate and review average in the quarters following any carrier change."
      ),

      ...recommendationBlock(
        2, "Launch a seller-success program for the platform's largest revenue segment",
        "A large group of high-revenue sellers are performing below the platform's median on delivery timing and reviews.",
        "212 sellers (of 818 with sufficient order volume) fall into the 'high revenue, low performance' quadrant, generating R$5,366,989 in item revenue — more than the 197 sellers in the 'high revenue, high performance' quadrant (R$4,411,381). This group averages 89.1% on-time delivery and a 3.89 review score, versus 95.4% and 4.30 for the high-performing group. This includes the platform's single largest seller by revenue.",
        "This is currently the largest revenue block on the platform, and it is underperforming. The gap is real but moderate, not severe — removing these sellers would risk more revenue than the performance issue itself justifies.",
        "Launch a structured seller-success outreach program targeted at these 212 sellers: fulfillment coaching, a defined improvement checkpoint, and using the high-performing quadrant's practices as a benchmark. This should be a retention-and-improvement program, not a removal policy.",
        "Movement of underperforming high-revenue sellers toward the platform's on-time/review benchmarks, protecting the R$5.37M in revenue currently at elevated risk. Success should be measured by re-running the quadrant segmentation quarterly and tracking how many sellers migrate to the high-performance quadrant."
      ),

      ...recommendationBlock(
        3, "Investigate the office_furniture category — a compounding, multiply-confirmed problem",
        "The office_furniture category consistently underperforms across every independent metric examined in this analysis.",
        "office_furniture has the lowest average review score of any category with meaningful volume (3.50, n=1,254), the highest late-delivery rate in the Nordeste-specific breakdown (17.61%), and the highest freight-cost exposure of any major category (25.01% of item revenue), each identified independently across separate phases of this analysis without being pre-selected as a hypothesis.",
        "This is very likely a single structural issue — bulky, heavy furniture items that are inherently harder and more expensive to ship reliably, and more consequential to receive damaged or late — rather than three unrelated problems.",
        "Commission a focused review of office_furniture's packaging, carrier handling, and freight pricing specifically, rather than treating it as one of many categories needing generic attention.",
        "An improvement in office_furniture's review score and late-delivery rate would be a strong signal the shipping/handling hypothesis is correct; this should be validated with a small pilot (e.g., packaging changes with a subset of sellers) before a platform-wide policy change, since the underlying cause has not been definitively isolated here."
      ),

      ...recommendationBlock(
        4, "Target loyalty investment at high-value customers, not geography",
        "Repeat-purchase behavior on the platform is low overall (3.00%) and does not vary meaningfully by customer location, but it does vary sharply by spend level.",
        "97.0% of customers have exactly one order, and repeat rate sits in a narrow 2.9%-3.4% band across every major state — no geographic pattern. However, the top 5% of customers by total spend (≥R$420) repeat at 8.52%, compared to 4.80% for mid-value customers and just 0.97% for the bottom half of spenders by value.",
        "A geographic loyalty campaign has no evidence behind it. A value-based one does: high-value customers are already ~9x more likely to return than low-value customers, suggesting a receptive audience already primed to repeat, rather than one that needs to be persuaded from a standing start.",
        "Pilot a loyalty or retention program (early access, personalized offers) targeted specifically at the top 5% of customers by historical spend, rather than a broad or geography-based campaign.",
        "This analysis identifies the correlation but does not establish why high-value customers repeat more often — a controlled pilot with a held-out comparison group is recommended before assuming the loyalty program itself will replicate this correlation as causation."
      ),

      new Paragraph({
        spacing: { before: 360, after: 80 },
        border: { top: { color: COLORS.muted, space: 8, style: BorderStyle.SINGLE, size: 4 } },
        children: [new TextRun({ text: "Limitations", bold: true, color: COLORS.accent, size: 22 })],
      }),
      body(
        "This dataset spans September 2016 to August 2018 and contains no cost-of-goods-sold data, so no recommendation above claims a profit or margin impact — only revenue, order-count, and review-score effects that the data can directly support. The office_furniture and Nordeste findings are strong statistical associations, not confirmed causal mechanisms; both recommendations explicitly call for a validation step (pilot or root-cause audit) before a large-scale policy change.",
        { size: 20, italics: true }
      ),
    ],
  }],
});

const path = require("path");
const OUTPUT_PATH = path.join(__dirname, "Business_Recommendations.docx");

Packer.toBuffer(doc).then((buffer) => {
  require("fs").writeFileSync(OUTPUT_PATH, buffer);
  console.log(`Document created: ${OUTPUT_PATH}`);
});
