# Regulatory Requirements for Incident Notification

This reference covers regulatory obligations triggered by security incidents, with primary focus on GDPR and supplementary coverage of NIS2 and other relevant frameworks.

---

## Table of Contents

1. [GDPR — General Data Protection Regulation](#gdpr)
2. [NIS2 Directive](#nis2-directive)
3. [Cross-Framework Decision Flowchart](#cross-framework-decision-flowchart)
4. [Key EU Supervisory Authorities (DPAs)](#key-eu-supervisory-authorities)
5. [AWS and GCP Shared Responsibility for Breach Notification](#cloud-provider-shared-responsibility)
6. [Practical Guidance for the IR Team](#practical-guidance)

---

## GDPR

**Applies to**: Any organization processing personal data of individuals in the EEA, regardless of where the organization is based.

### Article 33 — Notification to the Supervisory Authority

**Trigger**: A personal data breach that is "likely to result in a risk to the rights and freedoms of natural persons."

**Timeline**: Without undue delay, and no later than **72 hours** after becoming aware of the breach.

**"Becoming aware"**: The moment the organization has a reasonable degree of certainty that a security incident has led to personal data being compromised. Not when you started investigating — when you confirmed (or should reasonably have confirmed) data was affected.

**What to report** (Article 33(3)):
1. Nature of the breach: categories and approximate number of data subjects, categories and approximate number of records
2. DPO contact details
3. Likely consequences of the breach
4. Measures taken or proposed to address the breach and mitigate effects

**Partial notification**: If you cannot provide all information within 72 hours, you may provide it in phases. Submit what you have and supplement later. Document why the delay occurred.

**When NOT to notify**: If the breach is "unlikely to result in a risk" to individuals. Example: encrypted data was stolen and the encryption keys were not compromised. Document this decision and the rationale.

**Fines for non-compliance**: Up to €10 million or 2% of global annual turnover (whichever is higher) under Article 83(4)(a).

### Article 34 — Communication to the Data Subject

**Trigger**: When the breach is "likely to result in a **high** risk to the rights and freedoms of natural persons." Note the higher threshold compared to Article 33.

**Timeline**: Without undue delay (no fixed clock, but promptly).

**What to communicate**:
- Clear, plain language
- Nature of the breach
- DPO contact
- Likely consequences
- Measures taken and recommended protective actions the individual can take

**Exceptions** (when direct notification is NOT required):
1. Data was encrypted/pseudonymized and keys are uncompromised
2. Subsequent measures ensure the high risk is no longer likely to materialize
3. It would involve disproportionate effort — in this case, make a public communication instead

### GDPR Breach Risk Assessment Matrix

Use this to determine whether notification is required:

| Factor | Lower Risk | Higher Risk |
|--------|-----------|-------------|
| Data type | Publicly available info, business email | Credentials, financial, health, government IDs, location, children's data |
| Volume | Single individual | Thousands or millions |
| Identifiability | Pseudonymized, encrypted | Directly identifiable |
| Breach type | Availability (temporary loss) | Confidentiality (data exposed to unauthorized party) |
| Special categories | No Art. 9 data | Health, biometric, political, religious, sexual orientation |
| Vulnerable subjects | General adult population | Children, patients, employees |
| Consequences | Inconvenience, spam | Identity theft, financial loss, discrimination, physical safety |

**Rule of thumb**: When in doubt, notify. The penalty for not notifying when you should have is worse than notifying when you didn't strictly need to. The DPA will view a proactive notification favorably.

### GDPR Roles and Notification Responsibilities

**Controller**: Primary obligation to notify DPA and data subjects. This is you if you determine the purposes and means of processing.

**Processor**: Must notify the **controller** without undue delay after becoming aware of a breach. Does NOT notify the DPA directly (unless contractually agreed or also acting as controller for some processing). The 72-hour clock for the controller starts when the processor notifies them, not when the processor discovered the breach.

**Joint Controllers**: Determine in your joint controller arrangement who handles breach notification. If unclear, both should notify.

---

## NIS2 Directive

**Applies to**: Essential and important entities across the EU in sectors including digital infrastructure, cloud computing, managed services, ICT service management, and others.

**Relevant to Mirantis**: As a provider of cloud/Kubernetes platform services, likely falls under "digital infrastructure" or "ICT service management" categories.

### Notification Requirements

NIS2 introduces a **multi-stage notification process**:

| Stage | Timing | Content |
|-------|--------|---------|
| **Early warning** | Within **24 hours** of becoming aware | Whether the incident is suspected to be caused by unlawful/malicious acts, and whether it could have cross-border impact |
| **Incident notification** | Within **72 hours** | Initial assessment: severity, impact, indicators of compromise (if available) |
| **Intermediate report** | Upon request by CSIRT/authority | Status update with relevant details |
| **Final report** | Within **1 month** of incident notification | Detailed description, root cause, mitigation measures, cross-border impact |

### What Constitutes a "Significant Incident" Under NIS2

- Caused or is capable of causing severe operational disruption or financial loss
- Has affected or is capable of affecting other natural or legal persons by causing considerable material or non-material damage

### Key Differences from GDPR
- NIS2 focuses on **service disruption and operational impact**, not personal data
- Both may apply simultaneously: a ransomware attack that disrupts services AND compromises personal data triggers both NIS2 and GDPR obligations
- NIS2 has a **24-hour early warning** requirement — faster than GDPR's 72 hours
- NIS2 requires a **final report within 1 month**

### NIS2 Implementation Status
NIS2 must be transposed into national law by EU member states. Implementation timelines and specific authority designations vary by country. Check the national implementation for each relevant jurisdiction. Spain: CCN-CERT and INCIBE handle different sectors.

---

## Cross-Framework Decision Flowchart

When an incident occurs, walk through this decision tree:

```
INCIDENT DETECTED
    │
    ├── Does it involve personal data of individuals?
    │   ├── YES → GDPR Assessment
    │   │   ├── Risk to rights and freedoms? → Notify DPA within 72h (Art. 33)
    │   │   └── HIGH risk? → Also notify individuals (Art. 34)
    │   └── NO → Skip GDPR
    │
    ├── Does it cause significant operational disruption?
    │   ├── YES → NIS2 Assessment
    │   │   └── Essential/Important entity? → Early warning within 24h
    │   └── NO → Skip NIS2
    │
    ├── Are you a processor for other organizations?
    │   └── YES → Notify each affected controller without undue delay
    │        (Check DPA contracts for specific notification timelines — often 24-48h)
    │
    ├── Contractual obligations?
    │   └── Check customer contracts for breach notification clauses
    │       (Enterprise SLAs often require notification within 24-72h)
    │
    └── Document ALL decisions to notify or not notify, with reasoning
```

---

## Key EU Supervisory Authorities

When notifying under GDPR, you notify the DPA of the EU member state where you have your main establishment, or where the affected data subjects reside if no EU establishment.

| Country | Authority | Portal/Contact |
|---------|-----------|---------------|
| **Spain** | AEPD (Agencia Española de Protección de Datos) | https://sedeagpd.gob.es — online breach notification form |
| **France** | CNIL | https://www.cnil.fr/en/notifying-cnil-personal-data-breach |
| **Germany** | State-level DPAs (varies by Bundesland) | Check the relevant Landesbeauftragte |
| **Netherlands** | Autoriteit Persoonsgegevens | https://autoriteitpersoonsgegevens.nl/en |
| **Ireland** | DPC (Data Protection Commission) | https://www.dataprotection.ie — relevant for many US tech companies with EU HQ in Ireland |
| **Belgium** | APD/GBA | https://www.autoriteprotectiondonnees.be |
| **Italy** | Garante per la protezione dei dati personali | https://www.garanteprivacy.it |

**Cross-border breaches**: If the breach affects individuals across multiple EEA countries, you notify your **lead supervisory authority** (where your main establishment is). The lead DPA coordinates with other concerned DPAs under the one-stop-shop mechanism.

---

## Cloud Provider Shared Responsibility

### AWS
- AWS is responsible for security **of** the cloud (physical infra, hypervisor, managed service internals)
- Customer is responsible for security **in** the cloud (data, access management, network config, application security)
- **Breach notification**: If AWS detects a breach affecting your data, they will notify you per the AWS DPA. YOU are still the controller responsible for notifying the DPA and individuals
- AWS provides tools for your investigation: CloudTrail, GuardDuty, Security Hub, Macie
- AWS Artifact provides compliance reports and DPA documentation

### GCP
- Similar shared responsibility model
- Google Cloud DPA covers processor obligations
- Google notifies the customer of incidents affecting their data per the DPA terms
- **You** remain responsible for GDPR notification to DPAs and data subjects
- GCP provides: Cloud Audit Logs, Security Command Center, Chronicle for investigation
- Review the Google Cloud Data Processing Terms for specific timelines

### Key Principle
Cloud providers (AWS, GCP) act as **processors** for your data. Under GDPR, the processor must notify the controller (you) of a breach. But the **controller** (you) bears the obligation to assess, decide, and execute notification to the DPA and data subjects. Don't wait for the cloud provider to tell you what to do — assess independently using their logs and tools.

---

## Practical Guidance

### The 72-Hour Clock — How to Manage It

**Hour 0-4: Confirm and assess**
- Confirm the breach involves personal data
- Begin preliminary impact assessment (data types, volume, subjects)
- Alert DPO and Legal
- Start the incident timeline document

**Hour 4-24: Deepen assessment**
- Narrow down affected data categories and approximate subject count
- Assess risk to individuals
- DPO makes preliminary notification decision
- Begin drafting DPA notification (use template from `references/notifications.md`)
- If processor breach: verify you've been properly notified by the processor

**Hour 24-48: Prepare notification**
- Finalize DPA notification content (can be partial — you have the option to supplement)
- DPO and Legal review the notification
- Identify if individual notification (Art. 34) is also required
- Prepare individual notification if needed

**Hour 48-72: Submit**
- Submit notification via DPA portal
- Document submission (screenshot, confirmation number, timestamp)
- If you cannot fully assess by 72h: submit partial notification with explanation for phased approach

**Post-72h:**
- Supplement initial notification as investigation progresses
- Execute individual notification if required
- Maintain communication with DPA if they request additional information
- Document everything for accountability (Art. 5(2))

### Common Mistakes to Avoid

1. **Starting the clock too late**: "We didn't know it was a breach yet" is not a valid defense if you had enough indicators to trigger an investigation. Awareness ≠ certainty.

2. **Waiting for forensic completion before notifying**: You don't need full root cause analysis to notify. Partial notification is explicitly allowed and expected.

3. **Processor not notifying controller promptly**: If you're a processor, notify the controller immediately — not after your internal investigation concludes. Their 72-hour clock depends on your notification.

4. **Not documenting the decision NOT to notify**: If you assess a breach as low-risk and decide not to notify the DPA, you MUST document this decision, the assessment, and the reasoning. The DPA can request this documentation.

5. **Confusing Art. 33 and Art. 34 thresholds**: Art. 33 (DPA notification) = "risk" to individuals. Art. 34 (individual notification) = "high risk" to individuals. The thresholds are different.

6. **Ignoring contractual obligations**: Your enterprise customer contracts may have notification timelines shorter than 72 hours. Check DPA (Data Processing Agreement) clauses for each affected customer.
