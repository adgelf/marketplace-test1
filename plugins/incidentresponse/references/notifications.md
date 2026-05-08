# Incident Notification Templates

Ready-to-adapt communication templates for each audience during a security incident. Replace bracketed placeholders with incident-specific details. Adjust tone and detail based on severity.

---

## Table of Contents

1. [Internal IR Team Alert](#internal-ir-team-alert)
2. [Engineering / On-Call Escalation](#engineering--on-call-escalation)
3. [CISO / Security Leadership Brief](#ciso--security-leadership-brief)
4. [Executive Leadership Brief](#executive-leadership-brief)
5. [Legal / DPO Notification](#legal--dpo-notification)
6. [GDPR Supervisory Authority Notification](#gdpr-supervisory-authority-notification)
7. [Affected Customer / Data Subject Notification](#affected-customer--data-subject-notification)
8. [All-Staff Advisory](#all-staff-advisory)
9. [Status Update Template](#status-update-template)
10. [Post-Incident Summary](#post-incident-summary)

---

## Internal IR Team Alert

**Channel**: Slack/Teams IR channel or direct page
**Timing**: Immediately upon classification

```
🚨 SECURITY INCIDENT — [SEV-1/2/3/4]

Incident ID: [INC-YYYY-NNNN]
Detected: [YYYY-MM-DD HH:MM UTC]
Reporter: [name/system]

Summary: [One-sentence description of what happened]

Affected systems: [service names, accounts, infrastructure]
Environment: [AWS/GCP/K8s cluster name, region, account]
Current status: [Active/Contained/Under investigation]

Immediate actions taken:
- [Action 1]
- [Action 2]

Incident commander: [Name]
War room: [Link to call/channel]

Next steps: [What we're doing now]
```

---

## Engineering / On-Call Escalation

**Channel**: PagerDuty/Slack/phone
**Timing**: Immediately for SEV-1/2

```
SECURITY INCIDENT ESCALATION — [SEV level]

[Service/system] has been [compromised/is experiencing anomalous behavior].

What we know:
- [Key fact 1]
- [Key fact 2]
- Blast radius: [what's affected]

What we need from you:
- [Specific ask: access to logs, help isolating service, etc.]
- Join war room: [link]

DO NOT:
- Restart or terminate affected resources (evidence preservation)
- Communicate externally about this incident
- Make infrastructure changes outside the war room coordination

Incident commander: [Name] — coordinate all actions through them.
```

---

## CISO / Security Leadership Brief

**Channel**: Direct message/call, followed by email
**Timing**: SEV-1 immediately; SEV-2 within 2 hours

```
Subject: Security Incident Brief — [SEV level] — [Short description]

[Name],

We are responding to a [severity] security incident affecting [systems/services].

SITUATION:
- Detected at [time UTC] via [detection method]
- Nature: [ransomware/data breach/unauthorized access/etc.]
- Affected scope: [systems, data types, users impacted]
- Current status: [Active/Contained/Investigating]

DATA IMPACT:
- Personal data involved: [Yes — categories and approximate volume / No / Under assessment]
- GDPR notification potentially required: [Yes/No/TBD]
- Business-critical data at risk: [description]

ACTIONS TAKEN:
1. [Containment action]
2. [Investigation action]
3. [Communication action]

DECISIONS NEEDED:
- [Decision point 1: e.g., engage external forensics firm?]
- [Decision point 2: e.g., notify customers proactively?]
- [Decision point 3: e.g., involve law enforcement?]

NEXT UPDATE: [time]

Incident Commander: [Name]
War room: [link]
```

---

## Executive Leadership Brief

**Channel**: Email + brief call
**Timing**: SEV-1 within 1 hour; SEV-2 within 4 hours

```
Subject: Security Incident — Executive Brief — [Date]

SUMMARY:
We identified a security incident involving [brief plain-language description]. The security team is actively managing the response.

BUSINESS IMPACT:
- Service availability: [Unaffected / Degraded / Down for X service]
- Customer data: [No customer data involved / Under assessment / Confirmed — details below]
- Financial exposure: [Estimated or "under assessment"]
- Regulatory: [GDPR notification may be required within 72 hours / Not applicable]

CURRENT STATUS: [Contained / Under active response / Monitoring]

KEY ACTIONS:
- [What we've done]
- [What we're doing next]

DECISIONS FOR YOUR AWARENESS:
- [Any executive-level decisions pending: external communications, regulatory filing, etc.]

We will provide the next update by [time]. Please direct any questions to [CISO name].
```

---

## Legal / DPO Notification

**Channel**: Email + call
**Timing**: SEV-1 immediately; SEV-2 within 4 hours; anytime personal data may be affected

```
Subject: URGENT — Security Incident with Potential Data Protection Impact

[Legal counsel / DPO name],

The security team is responding to an incident that may involve personal data. Early assessment below — we need your guidance on regulatory notification obligations.

INCIDENT OVERVIEW:
- Type: [data breach / unauthorized access / etc.]
- Detected: [date/time UTC]
- Current status: [Active / Contained / Investigating]

DATA IMPACT ASSESSMENT (preliminary):
- Personal data potentially involved: [Yes/No/Unknown]
- Categories of data: [names, emails, financial, health, credentials, etc.]
- Categories of data subjects: [employees, customers, partners, EU residents]
- Approximate number of affected individuals: [number or range]
- Data processing role: [Controller / Processor / Joint controller]

GDPR ASSESSMENT:
- Breach likely to result in risk to individuals' rights and freedoms: [Yes/Likely/Under assessment]
- 72-hour notification clock: [Started at YYYY-MM-DD HH:MM UTC / Not yet triggered / Not applicable]
- Supervisory authority: [relevant DPA, e.g., AEPD for Spain, CNIL for France]

QUESTIONS FOR LEGAL/DPO:
1. Based on preliminary data, do we need to notify the supervisory authority?
2. Do we need to notify affected individuals directly?
3. Should we engage external legal counsel or forensics?
4. Are there contractual notification obligations to customers/partners?
5. Should we consider law enforcement engagement?

We will provide updated impact assessment by [time].
```

---

## GDPR Supervisory Authority Notification

**Channel**: DPA's official reporting portal/form
**Timing**: Within 72 hours of becoming aware of the breach
**Important**: This should be reviewed by DPO and Legal before submission

```
PERSONAL DATA BREACH NOTIFICATION — Article 33 GDPR

1. NATURE OF THE BREACH:
   - Type: [Confidentiality / Integrity / Availability breach]
   - Description: [Clear description of what happened]
   - Date/time breach occurred: [if known]
   - Date/time breach discovered: [date/time]
   - Duration of breach: [if known]

2. CATEGORIES AND APPROXIMATE NUMBER OF DATA SUBJECTS:
   - [Category 1: e.g., customers — approximately X individuals]
   - [Category 2: e.g., employees — approximately Y individuals]
   - Total approximate number: [number]

3. CATEGORIES OF PERSONAL DATA RECORDS:
   - [e.g., names, email addresses, IP addresses, financial data, etc.]
   - Special category data involved: [Yes — specify / No]

4. LIKELY CONSEQUENCES:
   - [e.g., potential identity theft, unauthorized access to accounts, financial loss, reputational damage to individuals]

5. MEASURES TAKEN OR PROPOSED:
   - To address the breach: [containment and eradication actions]
   - To mitigate adverse effects: [e.g., credential resets, monitoring services offered, enhanced security controls]

6. DATA PROTECTION OFFICER CONTACT:
   - Name: [DPO name]
   - Email: [DPO email]
   - Phone: [DPO phone]

7. ADDITIONAL INFORMATION:
   - Is this a complete or partial notification? [If partial: additional information will follow by (date)]
   - Cross-border processing: [Yes — list EEA countries where affected subjects reside / No]

Controller organization: [Legal entity name]
Controller address: [Registered address]
```

---

## Affected Customer / Data Subject Notification

**Channel**: Email (or as directed by Legal/DPO)
**Timing**: As directed by DPO/Legal — required under GDPR Article 34 when breach is likely to result in HIGH risk
**Important**: Must be reviewed and approved by Legal and DPO before sending

```
Subject: Important Security Notice — Action May Be Required

Dear [Customer/User],

We are writing to inform you of a security incident that may have affected your personal data.

WHAT HAPPENED:
[Clear, plain-language description of the incident — what occurred, when it was detected. No jargon.]

WHAT INFORMATION WAS INVOLVED:
[Specific data types that may have been affected for this individual/group — e.g., name, email address, account credentials]

WHAT WE ARE DOING:
- [Action 1: e.g., We have contained the incident and secured the affected systems]
- [Action 2: e.g., We have engaged external security experts to investigate]
- [Action 3: e.g., We have notified the relevant data protection authority]

WHAT YOU CAN DO:
- [Recommendation 1: e.g., Change your password for our service and any other service where you use the same password]
- [Recommendation 2: e.g., Enable multi-factor authentication on your account]
- [Recommendation 3: e.g., Monitor your accounts for unusual activity]

If you have questions or concerns, please contact our support team at [email/phone] or our Data Protection Officer at [DPO email].

We sincerely regret this incident and are committed to protecting your information.

[Signature — appropriate executive or DPO]
```

---

## All-Staff Advisory

**Channel**: Company-wide email or Slack
**Timing**: When staff awareness is needed (phishing campaign, credential compromise, etc.)

```
Subject: Security Advisory — [Action Required / For Your Awareness]

Team,

The security team is responding to [brief, appropriate description — no sensitive details].

WHAT YOU NEED TO KNOW:
- [Key fact relevant to all staff]
- [Any changed procedures or restrictions]

ACTION REQUIRED:
- [e.g., Reset your password at (link) by end of day]
- [e.g., Do not click links in emails matching this pattern: (description)]
- [e.g., Report any suspicious activity to security@company.com]

DO NOT:
- Discuss this incident on social media or with external parties
- Speculate about the cause or impact
- Share details outside of official channels

If you have questions, contact the security team at [channel/email].

— Security Team
```

---

## Status Update Template

**Channel**: War room / IR channel / Email (depending on audience)
**Timing**: Regular cadence based on severity (SEV-1: every 1-2 hours; SEV-2: every 4 hours; SEV-3: daily)

```
INCIDENT STATUS UPDATE — [INC-YYYY-NNNN] — Update #[N]
Time: [YYYY-MM-DD HH:MM UTC]
Status: [Active / Contained / Eradication / Recovery / Closed]
Severity: [SEV level — note if changed]

SINCE LAST UPDATE:
- [Action completed or finding discovered]
- [Action completed or finding discovered]

CURRENT FOCUS:
- [What the team is working on right now]

BLOCKERS:
- [Any dependencies or obstacles]

TIMELINE:
- [Estimated time to next milestone]

NEXT UPDATE: [time]
Incident Commander: [Name]
```

---

## Post-Incident Summary

**Channel**: Email + Confluence/wiki page
**Timing**: Within 5 business days of incident closure

```
POST-INCIDENT REPORT — [INC-YYYY-NNNN]

INCIDENT SUMMARY:
- Type: [classification]
- Severity: [SEV level]
- Duration: [detection to closure]
- Systems affected: [list]
- Data impact: [description or "No data impact"]
- Business impact: [downtime, customer impact, financial]

TIMELINE:
[Chronological list of key events with UTC timestamps]
- YYYY-MM-DD HH:MM — [Event]
- YYYY-MM-DD HH:MM — [Event]

ROOT CAUSE:
[Clear description of the underlying cause]

WHAT WENT WELL:
- [Effective detection, fast response, good communication, etc.]

WHAT COULD BE IMPROVED:
- [Gaps identified, slow steps, tooling issues, etc.]

ACTION ITEMS:
| # | Action | Owner | Priority | Due Date | Jira Ticket |
|---|--------|-------|----------|----------|-------------|
| 1 | [action] | [name] | [P1/P2/P3] | [date] | [ticket ID] |
| 2 | [action] | [name] | [P1/P2/P3] | [date] | [ticket ID] |

REGULATORY ACTIONS:
- DPA notified: [Yes — date / No — not required]
- Individuals notified: [Yes — date — number / No — not required]
- Other regulatory actions: [description or N/A]
```
