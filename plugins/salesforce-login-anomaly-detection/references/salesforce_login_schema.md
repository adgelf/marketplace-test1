# Salesforce Login Data: Schema Reference

Reference guide for field names and values across Salesforce login data sources. Used by this skill's scripts to auto-detect the source and parse correctly.

## Three sources, three sets of columns

| Source | Naming | Scale | Typical use |
|---|---|---|---|
| Setup → Login History UI export | `Human Readable` (spaces, mixed case) | ≤ 20 000 rows | Ad-hoc admin review |
| SOQL query on `LoginHistory` | `camelCase` as in the API | Up to hundreds of thousands per query | Programmatic audit, scripts |
| Event Monitoring Login event log file | `UPPER_SNAKE_CASE` | Millions of rows / day | Security / Compliance / SIEM |

The scripts auto-detect the source from the column set; the detector lives in `scripts/profile_logins.py`.

---

## Key-field mapping across sources

| Meaning | UI export | SOQL (`LoginHistory`) | Event Monitoring |
|---|---|---|---|
| User ID | *(absent, only Username)* | `UserId` | `USER_ID` |
| Username | `Username` | *(join via User.Username)* | `USER_NAME` |
| Login time | `Login Time` | `LoginTime` | `TIMESTAMP` / `TIMESTAMP_DERIVED` |
| IP address | `Source IP` | `SourceIp` | `SOURCE_IP` / `CLIENT_IP` |
| Login type | `Login Type` | `LoginType` | `LOGIN_TYPE` |
| Login subtype | *(absent in old UI)* | `LoginSubType` | `LOGIN_SUB_TYPE` |
| Status | `Status` | `Status` | `LOGIN_STATUS` |
| Country | `Country` | `CountryIso` (via `LoginGeo`) | `COUNTRY` / `COUNTRY_ISO` |
| Application | `Application` | `Application` | `APPLICATION` |
| Browser | `Browser` | `Browser` | `BROWSER` |
| Platform | `Platform` | `Platform` | `PLATFORM` |
| Client version | `Client Version` | `ClientVersion` | `CLIENT_VERSION` |
| API type | `API Type` | `ApiType` | `API_TYPE` |
| API version | `API Version` | `ApiVersion` | `API_VERSION` |
| TLS protocol | `TLS Protocol` | `TlsProtocol` | `TLS_PROTOCOL` |
| Cipher suite | `Cipher Suite` | `CipherSuite` | `CIPHER_SUITE` |
| Network (Community) | *(absent in UI)* | `NetworkId` | `NETWORK_ID` |
| Auth service | *(absent)* | `AuthenticationServiceId` | `AUTHENTICATION_SERVICE_ID` |
| MFA method | *(absent in UI)* | *(not direct)* | `AUTHENTICATION_METHOD_REFERENCE` |
| Session key | *(absent)* | *(absent)* | `SESSION_KEY` |
| Login key | *(absent)* | *(absent)* | `LOGIN_KEY` |

Key insight: **Event Monitoring is the richest source**. It has `SESSION_KEY` (links a login to a full session), `LOGIN_KEY` (groups attempts within a single user flow), `AUTHENTICATION_METHOD_REFERENCE` (MFA factor). If the user has Event Monitoring, always ask for it instead of a UI export.

---

## `LoginType` values

Top-level login type. Common values (non-exhaustive, depends on enabled features):

| Value | Meaning |
|---|---|
| `Application` | Standard web UI login |
| `Remote Access 2.0` | OAuth 2.0 (Connected App) |
| `SAML Idp Initiated` | SSO via SAML, initiated by the IdP |
| `SAML Sp Initiated` | SSO via SAML, initiated by the SP (Salesforce) |
| `OAuth Enabled User-Agent` | OAuth user-agent flow |
| `OAuth Refresh Token` | OAuth token refresh |
| `OAuth Enabled Client` | OAuth client credentials / web server flow |
| `Salesforce Authenticator` | SFA push login |
| `Remote Access Client Login` | Legacy desktop client (including old Data Loader modes) |
| `Chatter Communities External User` | Community user |
| `Chatter Communities Internal User` | Internal user within a Community |

**Practice:** if SSO is enabled, `SAML *` is the norm for internal users. A plain `Application` login by a regular user in an SSO-enforced org is suspicious (may be an SSO bypass via resettable password).

---

## `LoginSubType` values

The subtype provides finer granularity. It's especially important for separating interactive logins from API ones.

| Value | Meaning | Red flag for a regular user? |
|---|---|---|
| `Application` | UI login | — |
| `SOAP API` | Legacy SOAP API (Partner / Enterprise WSDL) | 🚩 Yes — often Data Loader / scripts |
| `Partner API` | SOAP Partner API | 🚩 Yes |
| `Enterprise API` | SOAP Enterprise API | 🚩 Yes |
| `Bulk API` | Bulk API v1 (mass exports / imports) | 🚩 Yes — often mass extraction |
| `Bulk API 2.0` | Bulk API v2 | 🚩 Yes |
| `Metadata API` | Metadata deploys (sfdx, ant) | 🚩 Yes if not a DevOps user |
| `REST API` | REST API | Depends — could be legitimate mobile / custom app |
| `Apex API` | Apex REST / SOAP endpoints | Depends on use case |
| `Tooling API` | Tooling API (DevOps) | 🚩 Yes if not a DevOps user |
| `OAuth` | Generic OAuth | — |
| `Refresh Token` | Refresh token use | — |
| `SAML` | SAML assertion consumption | — |
| `Chatter Communities` | Community access | — |

**Note:** the exact `LoginSubType` set varies between Salesforce releases and may include additional values (e.g. `Mobile`, `SFDX`, `Connect`). The `filter_by_subtype.py` script does not hardcode the list — it filters on *any* value passed in.

**Rule of thumb for detecting suspicious API logins:**

```
Suspicious = LoginSubType in {SOAP API, Bulk API, Bulk API 2.0, Metadata API, Partner API, Enterprise API, Tooling API}
           AND Username does NOT match {integration, svc, api, sys, etl, bot, automation, dataloader}
           AND Username matches a human-looking pattern (first.last@)
```

This is a heuristic — the user of this skill should confirm the integration-user list.

---

## `Status` values

A string field, not an enum. Common values (non-exhaustive):

**Success:**
- `Success`

**Failure (many distinct values — each is a different signal):**
- `Invalid Password`
- `Invalid Username or Password`
- `Invalid User`
- `Password Lockout` — user locked out after N failures
- `Restricted IP` — login attempt from an IP outside the Login IP Ranges (🚩 often an attack)
- `Restricted Time` — login attempt outside allowed hours
- `No Data` / `Source IP restricted` — other IP restrictions
- `Failed: Computer activation required` — device activation
- `Failed: Email verification required`
- `Challenge Not Complete` — failed the MFA challenge (🚩)
- `Challenge Issued` — challenge launched (not terminal by itself)
- `Session expired` — technical, not an attack

When analyzing: group failures by `Status`. A cluster of `Restricted IP` for a single user = a targeted attempt. A cluster of `Invalid Password` across many users from one IP = brute force / credential stuffing.

---

## Event Monitoring specifics

In addition to the fields above, EM Login events include:

- `USER_TYPE` — `Standard`, `PowerPartner`, `CustomerSuccess`, `CsnOnly`, etc. Useful for filtering: PowerCustomerSuccess logins often need separate treatment.
- `HTTP_METHOD` — for API logins.
- `URI` — the endpoint invoked.
- `LOGIN_HISTORY_ID` — joinable to the `LoginHistory` object.
- `AUTHENTICATION_METHOD_REFERENCE` — which MFA method was used: `mfa`, `pwd`, `otp`, `u2f`, etc. Absence of `mfa` for an admin = 🚩.
- `USER_ID_DERIVED` — normalized 18-character ID.

---

## Common pitfalls

1. **Timestamps come in different formats.** UI export uses the user's local timezone; SOQL gives UTC ISO8601 (`2026-04-22T09:15:33.000Z`); EM gives epoch-like `TIMESTAMP_DERIVED`. Normalize everything to UTC before joining or comparing.

2. **`SourceIp` may be IPv6.** Account for it when parsing and geolocating. Some mobile carriers default to IPv6.

3. **`CountryIso` is based on IP, not on real location.** VPNs and proxies produce false signals. Don't base hard rules on country alone.

4. **One `LoginHistory` record ≠ one session.** Refresh token events and re-logins create separate records but represent the same "session". For true session analysis you need Event Monitoring with `SESSION_KEY`.

5. **Username changes when the user is renamed.** `UserId` is stable — always prefer it for grouping.

6. **Community users and Guest users.** If `NetworkId IS NOT NULL`, it's an Experience Cloud login, not internal. Often worth analyzing separately.

7. **Logins from deactivated users.** Technically impossible going forward, but historical records remain. Be careful when joining with the current `User` table to filter by active status.
