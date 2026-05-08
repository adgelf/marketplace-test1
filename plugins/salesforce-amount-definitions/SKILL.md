---
name: salesforce-amount-definitions
description: >
  Use this skill whenever a user asks about amount fields, revenue metrics, or financial field definitions
  in Salesforce or Clari. Triggers include: any question about ACV, TCV, ARR, NAO, MKE, MCR, MCC, MSR,
  MCP, MOS, Lens amounts, opportunity fields, renewal fields, forecast fields, or pipeline metrics.
  Also trigger when users ask "what does X field mean?", "how is X calculated?", "where does X come from?",
  "what's the difference between X and Y?" for any amount-related field. Covers both Salesforce opportunity
  fields and Clari forecasting columns. Always use this skill when the user's question involves financial
  field names, revenue definitions, or forecasting metrics — even if phrased casually.
---

# Amount Definitions: Salesforce & Clari (in ACV)

This skill provides authoritative definitions and calculation logic for all amount fields used in
Salesforce opportunities and Clari forecasting. All Clari figures are in ACV unless otherwise noted.

---

## Salesforce — Opportunity-Level Fields

These fields live on the Opportunity object and are primarily roll-up summaries from Opportunity Products.

### TCV (Total Contract Value) Fields

| Field | Definition |
|---|---|
| **Opportunity TCV** | Total contract value across all product types. Roll-up summary of TCV from opportunity product object (all types). |
| **TCV Subscription Total** | Roll-up of TCV from opportunity products where product family = Subscription, Support, US - Subscription, or Managed Services. |
| **TCV Services Total** | Roll-up of TCV from opportunity products where product family does NOT equal the subscription families above, and is not Training or Public Training. |
| **TVC Training Total** | Roll-up of TCV from opportunity products where product family = Training or Public Training. |

### ACV (Annual Contract Value) Fields

| Field | Definition |
|---|---|
| **Opportunity ACV** | Annual contract value across all product types. Roll-up summary of ACV from opportunity product object (all types). |
| **ACV SUBS** | Roll-up of ACV from opportunity products where product family = Subscription, Support, US - Subscription, or Managed Services. |
| **ACV SVCS** | Roll-up of ACV from opportunity products where product family does NOT equal the subscription families above, and is not Training or Public Training. |
| **ACV TNG** | Roll-up of ACV from opportunity products where product family = Training or Public Training. |

### ARR & Revenue Classification Fields

| Field | Definition |
|---|---|
| **New ARR** | Annual recurring revenue for new customers, new divisions, new business lines, or new products at existing customers. Captures ACV subscription revenue. |
| **Add-on ACV SUBS** | ACV subscription revenue for current customers, excluding renewal amounts. |
| **Renewal Amount** | Current renewal ACV subscription amount. Cannot exceed the related renewal amount from the prior opportunity. |
| **NAO Subs** | New ARR + Add-on ACV SUBS. Formula: `New_ARR__c + Add_on_ACV_SUBS__c` |

### Discount & Pricing Fields

| Field | Definition |
|---|---|
| **Discount %** | Formula field showing the percent discount applied on opportunity products (as a TCV percentage). |
| **Total Discounted Amount** | Roll-up summary of the total discount field from the opportunity product object. |
| **Total List Price** | Total price of products before any discount is applied. |
| **Weighted ACV Total** | Opportunity ACV multiplied by Probability. Formula: `Opportunity ACV × Probability` |

---

## Salesforce — Product Amount Fields (Populated from Opportunity Parts)

These fields reflect ACV subscription amounts broken out by product line. All are populated from Opportunity Parts.

| Field | Product |
|---|---|
| **MKE Amount** | Mirantis Kubernetes Engine |
| **MCR Amount** | Mirantis Container Runtime |
| **MCC Amount** | Mirantis Container Cloud |
| **MSR Amount** | Mirantis Secure Registry |
| **MKE_MSR Amount** | Mirantis Kubernetes Engine + Mirantis Secure Registry (combined) |
| **MCP Amount** | Mirantis Cloud Platform |
| **MOS Amount** | Mirantis OpenStack |
| **Lens Amount** | Lens |
| **Other Amount** | Other products not listed above |

---

## Salesforce — Renewal Fields

These fields support renewal tracking and are linked to the prior opportunity.

| Field | Definition |
|---|---|
| **Related Renewal Amount** | ACV subscription renewal amount carried over from the previous opportunity. |
| **Renewal Delta** | (No definition provided — confirm with RevOps.) |
| **Renewal Baseline** | Total ACV subscription renewal amount from the previous opportunity, excluding discounts (list price). |
| **Related Opportunity** | The previous opportunity from which the Related Renewal Amount is pulled. |

---

## Clari — Forecast Columns (All in ACV)

Clari columns represent forecasting and pipeline views. All figures are in ACV.

### Actuals & Targets

| Column | Definition |
|---|---|
| **Target** | AOP/quota as set by Finance. |
| **Closed** | Opportunities closed won. |
| **Target to Go** | Delta between Target and Closed. Formula: `Target − Closed` |

### Forecast Columns

| Column | Definition |
|---|---|
| **Rep Commit + CLSD** | Closed won + open opportunities with a Commit forecast stage. |
| **MGR Forecast** ⚠️ | MGR Forecast checkbox is checked — manager confirms the opportunity will close as forecasted for the stated close date. |
| **MGR Bridge** ⚠️ | MGR Bridge checkbox is checked — manager is including the opportunity in stretch/bridge scenarios. |
| **Total Call** | MGR Forecast + MGR Bridge + Debookings (open or closed won). |
| **Total Call Open** | MGR Forecast + MGR Bridge + Debookings (open opportunities only). |
| **Total/Target** | Total Call as a percentage of Target. Formula: `Total Call ÷ Target` |

> ⚠️ **MGR Forecast and MGR Bridge are mutually exclusive** — only one checkbox can be checked per opportunity. An opportunity cannot be in both.

### Pipeline Columns

| Column | Definition |
|---|---|
| **Most Likely** | Open opportunities NOT included in Total Call, with a forecast stage of Commit or Most Likely. |
| **Stretch** | Open opportunities NOT included in Total Call, with a forecast stage of Stretch. |
| **Pipeline** | Open opportunities NOT included in Total Call, with a forecast stage of Pipeline. |
| **Pipeline Coverage** | All open opportunities, whether forecasted or not. |
| **Pipeline Not Forecasted** | All open opportunities not included in Total Call. Equals Most Likely + Stretch + Pipeline. |

---

## Quick Reference: Key Formulas

| Formula | Calculation |
|---|---|
| NAO Subs | New ARR + Add-on ACV SUBS |
| Weighted ACV Total | Opportunity ACV × Probability |
| Target to Go | Target − Closed |
| Total/Target | Total Call ÷ Target |
| Pipeline Not Forecasted | Most Likely + Stretch + Pipeline |

---

## Key Distinctions to Know

- **TCV vs ACV**: TCV is the total contract value over the full contract term. ACV is the annualized value.
- **New ARR vs Add-on ACV SUBS**: New ARR is for genuinely new business (new customers, new divisions, new products). Add-on is for existing customers buying more, excluding renewals.
- **Renewal Amount vs Related Renewal Amount**: Renewal Amount is the current opportunity's renewal capture (capped by related renewal). Related Renewal Amount is the carry-over figure from the prior deal.
- **MGR Forecast vs MGR Bridge**: Forecast = manager expects this to close on stated date. Bridge = manager is counting this as stretch/upside. These are mutually exclusive.
- **Total Call vs Pipeline Coverage**: Total Call is the manager's committed number (forecast + bridge + debookings). Pipeline Coverage is ALL open opps regardless of forecast stage.
