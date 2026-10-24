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
        "This document presents four evidence-based recommendations arising from an end-to-end analysis covering revenue, logistics, seller performance, and data quality across 96,478 delivered orders. Every figure below traces to a SQL view in sql/08_business_findings.sql or a query in sql/04-05, and was reproduced from the source data in the October 2026 audit; no financial projections beyond what the data supports are included.",
        { size: 21 }
      ),

      ...recommendationBlock(
        1, "Fix the Northeast (Nordeste) delivery gap — most likely a regional logistics problem, not a seller problem",
        "The Nordeste region has a disproportionately high late-delivery rate compared to the rest of the platform.",
        "Nordeste represents 9.37% of delivered orders but 16.56% of late deliveries, with a 14.33% late rate versus the 8.11% platform average (1.77x); all 9 Nordeste states are individually above the platform rate, and the worst run at 2-3x (Alagoas 23.93%, Maranhão 19.67%). By seller origin, São Paulo sellers run 15.03% late on deliveries into Nordeste (n=6,374), and Bahia (8.62%) and Pernambuco (4.67%) sellers do better — consistent with a distance effect. The evidence is not uniform: Maranhão-based sellers run 29.33% late (n=75), so distance is the leading hypothesis rather than an established cause. No individual seller has enough volume to explain the pattern alone.",
        "Late deliveries are associated with a 1.73-point average review score gap (4.29 on-time vs. 2.57 late). If Nordeste's late rate matched the platform average, about 563 orders over the analyzed period would have been on time instead of late.",
        "Prioritize a carrier/logistics review specifically for the São Paulo-to-Nordeste long-haul shipping lane, rather than auditing individual sellers. Consider a regional fulfillment partner or adjusted delivery-estimate buffer for this route.",
        "A meaningful reduction in Nordeste's late-delivery rate, with a proportional improvement in the region's average review score — success should be measured by tracking Nordeste's late rate and review average in the quarters following any carrier change."
      ),

      ...recommendationBlock(
        2, "Launch a seller-success program for the platform's largest revenue segment",
        "A large group of high-revenue sellers are performing below the platform's median on delivery timing and reviews.",
        "207 sellers (of 804 with at least 20 delivered orders) fall into the 'high revenue, low performance' quadrant, generating R$5,403,117 in delivered item revenue — more than the 195 sellers in the 'high revenue, high performance' quadrant (R$4,132,924). This group averages 89.1% on-time delivery and a 3.96 review score, versus 95.5% and 4.34 for the high-performing group, and includes the platform's single largest seller by revenue. (An earlier version of this analysis reported 212 sellers / R$5.37M; the headcount varies between 206 and 213 depending on the exact definition, and this quadrant is the largest revenue block under every definition tested.)",
        "This is currently the largest revenue block on the platform, and it is underperforming. The gap is real but moderate, not severe — removing these sellers would risk more revenue than the performance issue itself justifies.",
        "Launch a structured seller-success outreach program targeted at these ~207 sellers: fulfillment coaching, a defined improvement checkpoint, and using the high-performing quadrant's practices as a benchmark. This should be a retention-and-improvement program, not a removal policy.",
        "Movement of underperforming high-revenue sellers toward the platform's on-time/review benchmarks, protecting the ~R$5.4M in revenue currently at elevated risk. Success should be measured by re-running the quadrant segmentation quarterly and tracking how many sellers migrate to the high-performance quadrant."
      ),

      ...recommendationBlock(
        3, "Investigate the office_furniture category — a compounding, multiply-confirmed problem",
        "The office_furniture category consistently underperforms across every independent metric examined in this analysis.",
        "office_furniture has the lowest average review score of any category with meaningful volume (3.62, n=1,244 delivered orders with a review), the highest late-delivery rate in the Nordeste-specific breakdown (17.61%, though on a small sample of 142 orders and only marginally above health_beauty at 17.55%), and the highest freight-cost exposure of any major category (freight equal to 25.01% of item revenue).",
        "This is very likely a single structural issue — bulky, heavy furniture items that are inherently harder and more expensive to ship reliably, and more consequential to receive damaged or late — rather than three unrelated problems.",
        "Commission a focused review of office_furniture's packaging, carrier handling, and freight pricing specifically, rather than treating it as one of many categories needing generic attention.",
        "An improvement in office_furniture's review score and late-delivery rate would be a strong signal the shipping/handling hypothesis is correct; this should be validated with a small pilot (e.g., packaging changes with a subset of sellers) before a platform-wide policy change, since the underlying cause has not been definitively isolated here."
      ),

      ...recommendationBlock(
        4, "Test (don't assume) retention outreach for high-value customers",
        "Repeat-purchase behavior on the platform is low overall (3.00%) and does not vary meaningfully by customer location. It is higher in the top lifetime-spend tier, but that gradient is largely a by-product of how lifetime spend is measured.",
        "97.0% of customers have exactly one order, and repeat rate sits in a narrow 2.9%-3.4% band across every major state. The top 5% of customers by lifetime spend (≥R$420; 29% of revenue) show an 8.52% repeat rate vs. 0.97% for the lowest tier — but repeat buyers accumulate lifetime spend by definition. Grouped by the value of their first order instead, high spenders repeat at 2.19% vs. 3.19% for low spenders.",
        "Neither a geographic nor a value-based loyalty campaign is supported by the observed repeat rates alone. The top lifetime-spend tier is still the group with the most revenue at stake (29% of revenue), which makes it the sensible place to test retention outreach.",
        "Run a controlled pilot of retention outreach (early access, personalized offers) for the top 5% of customers by historical spend, with a randomly held-out comparison group.",
        "The pilot measures whether outreach changes repeat behavior; the historical data cannot answer that question on its own."
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
