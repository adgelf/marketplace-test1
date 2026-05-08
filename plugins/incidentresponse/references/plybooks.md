# Incident Response Playbooks

Per-incident-type response procedures. Each playbook follows the NIST phases and includes environment-specific actions for AWS, GCP, and Kubernetes.

---

## Table of Contents

1. [Ransomware](#ransomware)
2. [Data Breach / Exfiltration](#data-breach--exfiltration)
3. [Unauthorized Access / Account Compromise](#unauthorized-access--account-compromise)
4. [DDoS](#ddos)
5. [Insider Threat](#insider-threat)
6. [Supply Chain Compromise](#supply-chain-compromise)
7. [Phishing / Business Email Compromise](#phishing--business-email-compromise)
8. [Cloud Misconfiguration Exposure](#cloud-misconfiguration-exposure)
9. [Container Escape / Kubernetes Compromise](#container-escape--kubernetes-compromise)
10. [API / Credential Compromise](#api--credential-compromise)

---

## Ransomware

**Severity**: SEV-1 by default (active encryption = immediate response)

### Detection Indicators
- Mass file encryption / extension changes
- Ransom notes appearing on systems
- Sudden spike in file I/O
- AV/EDR alerts for known ransomware families
- In cloud: unusual EBS/PD snapshot deletions, S3 object overwrites

### Immediate Containment (first 30 minutes)
1. **DO NOT shut down affected systems** — you lose volatile memory evidence
2. Isolate affected systems from network (swap SGs in AWS, update firewall rules in GCP, apply deny-all NetworkPolicy in K8s)
3. Identify patient zero and lateral movement path
4. Disable compromised accounts immediately
5. Block known C2 IPs/domains at perimeter
6. Preserve evidence: snapshot all affected volumes before any remediation
7. Check backup integrity — verify backups are not encrypted/compromised

### AWS-Specific Actions
- Check CloudTrail for `DeleteSnapshot`, `PutObject` (overwrite), `CreateAccessKey` by unfamiliar principals
- Apply emergency SCP: deny `ec2:TerminateInstances`, `s3:DeleteObject`, `rds:DeleteDBInstance` org-wide
- Isolate affected instances: replace security groups with one allowing only forensic access
- Check for IAM role abuse — ransomware operators often escalate to delete backups
- Enable S3 Object Lock if not already active on backup buckets

### GCP-Specific Actions
- Check Admin Activity logs for `compute.instances.delete`, `storage.objects.delete`
- Apply Organization Policy constraints to prevent resource deletion
- Isolate instances via VPC firewall rules (priority 0 deny-all, allow only forensic IPs)
- Verify Cloud Storage retention policies on backup buckets
- Check for service account key misuse

### Kubernetes-Specific Actions
- Apply deny-all NetworkPolicy to affected namespaces immediately
- Check if encryption is happening inside containers or on node filesystems
- If node-level: cordon and drain, isolate at cloud network layer
- If pod-level: capture pod state, then delete and investigate the image
- Review PersistentVolume claims — check for data at rest
- In k0rdent: check if Flux HelmReleases were modified to deploy ransomware payloads

### Eradication
- Identify initial access vector (phishing, RDP, vulnerable service, supply chain)
- Remove all persistence mechanisms (scheduled tasks, cron jobs, modified AMIs, backdoor containers)
- Rotate ALL credentials in affected scope — assume total compromise
- Patch the vulnerability that enabled access

### Recovery
- Restore from clean, verified backups — never trust "decrypted" systems
- Rebuild affected infrastructure from IaC (Terraform, Helm charts, Flux manifests)
- Staged restoration: critical services first, with enhanced monitoring
- Validate data integrity post-restore

### Do NOT
- Pay the ransom without legal counsel and executive authorization
- Negotiate with attackers without involving legal
- Wipe systems before forensic evidence is preserved
- Assume the attack is limited to what you can see — look for additional persistence

---

## Data Breach / Exfiltration

**Severity**: SEV-1 if PII/sensitive data confirmed; SEV-2 if suspected

### Detection Indicators
- Unusual outbound data transfers (volume, destination, timing)
- DNS exfiltration patterns (high volume of TXT queries, long subdomain strings)
- Cloud: unusual S3/GCS reads, cross-account data copies, large API data responses
- Database query anomalies (bulk SELECT, schema enumeration)
- DLP alerts, CloudTrail/Audit Log anomalies

### Immediate Containment
1. Identify what data is at risk — this drives all downstream decisions (especially GDPR)
2. Block the exfiltration channel (revoke access, update network policies, block destination IPs)
3. Preserve all logs related to the exfiltration path
4. Assess: is it still ongoing? If yes, containment is priority one
5. Document the timeline immediately — regulatory clocks start ticking

### AWS-Specific Actions
- Check CloudTrail for `GetObject`, `CopyObject`, `AssumeRole` to external accounts
- Review VPC Flow Logs for unusual outbound traffic volumes
- Check S3 access logs and bucket policies for unauthorized access grants
- Use Macie findings if available to identify what data types were in affected buckets
- Check for `PutBucketPolicy` changes that enabled external access

### GCP-Specific Actions
- Review Data Access audit logs for bulk read operations
- Check VPC Flow Logs and Cloud NAT logs for unusual egress
- Review IAM bindings for grants to external identities (`allUsers`, `allAuthenticatedUsers`)
- Check BigQuery audit logs for large query jobs or exports
- Review DLP findings in Security Command Center

### Kubernetes-Specific Actions
- Check if exfiltration happened through application-level access or from within pods
- Review ingress/egress network policies — was outbound traffic unrestricted?
- Check for exec sessions into pods (`kubectl exec` in audit logs)
- Examine mounted secrets and configmaps — were credentials exposed?
- Check for sidecar containers that may have been injected for data collection

### GDPR Trigger Assessment
If personal data of EU residents is involved, immediately assess:
- **What data**: categories of personal data (names, emails, health, financial, etc.)
- **How many data subjects**: approximate number
- **Likely consequences**: identity theft risk, financial loss, discrimination
- **Is notification required?**: if risk to rights and freedoms is not unlikely → YES → 72-hour clock starts from awareness
- Read `references/regulatory.md` for notification procedures and templates

### Recovery
- Close the access path permanently
- Rotate all credentials in scope
- Implement monitoring for re-exfiltration attempts
- If cloud misconfig was root cause, implement preventive controls (SCPs, VPC Service Controls)

---

## Unauthorized Access / Account Compromise

**Severity**: SEV-1 if privileged account; SEV-2 for standard accounts

### Detection Indicators
- Login from unusual location/IP/device
- Impossible travel (logins from geographically distant locations in short timeframe)
- New API keys or access tokens created
- MFA changes or bypasses
- Privilege escalation events

### Immediate Containment
1. Disable the compromised account(s) immediately
2. Revoke all active sessions and tokens
3. Rotate credentials (passwords, API keys, service account keys)
4. Check for persistence: new accounts created, roles modified, keys added
5. Review what the attacker accessed during the compromise window

### AWS-Specific Actions
- Deactivate IAM user access keys, revoke IAM role sessions using role policy with `aws:TokenIssueTime` condition
- Check CloudTrail for the full scope of API calls during compromise window
- Look for `CreateUser`, `CreateAccessKey`, `AttachUserPolicy`, `PutRolePolicy`
- Check for new Lambda functions, EC2 instances, or other resource creation
- Review AssumeRole chains — attacker may have pivoted across accounts

### GCP-Specific Actions
- Disable the service account or user account
- Revoke OAuth tokens and service account keys
- Check Admin Activity logs for `SetIamPolicy`, `CreateServiceAccountKey`
- Review Workspace login activity if Google Workspace account
- Check for new Compute instances, Cloud Functions, or IAM bindings

### Kubernetes-Specific Actions
- Check RBAC: who has `cluster-admin`? Any new ClusterRoleBindings?
- Review Kubernetes API audit logs for the compromised identity
- Check for new ServiceAccounts, Secrets, or modified RBAC
- Rotate the compromised ServiceAccount token (delete and recreate the Secret)
- If a kubeconfig was leaked: rotate cluster certificates or the specific user cert

---

## DDoS

**Severity**: SEV-2 typically; SEV-1 if business-critical services are down

### Detection Indicators
- Sudden traffic spike (requests, bandwidth, connections)
- Service degradation or unavailability
- Cloud: load balancer errors, auto-scaling hitting limits, increased egress costs
- Application-layer patterns: specific endpoint flooding, slowloris, cache bypass

### Immediate Actions
1. Confirm it's a DDoS and not a legitimate traffic spike or misconfigured client
2. Enable/engage cloud DDoS protection (AWS Shield Advanced, GCP Cloud Armor)
3. Apply rate limiting at edge (WAF rules, Cloud Armor policies)
4. Scale up if possible to absorb while filtering is tuned
5. Identify attack vector: volumetric, protocol, or application-layer

### AWS-Specific Actions
- Engage AWS Shield Advanced (if subscribed) — contact AWS DDoS Response Team (DRT)
- Apply AWS WAF rate-limiting rules
- Move behind CloudFront if not already
- Use Route 53 health checks to failover if needed
- Check for application-layer attacks hitting specific endpoints

### GCP-Specific Actions
- Apply Cloud Armor security policies with rate limiting and adaptive protection
- Use Cloud CDN for caching and absorption
- Apply Google Cloud Load Balancing for global traffic distribution
- Engage Google Cloud support if under Advanced tier

### Kubernetes-Specific Actions
- Check Ingress controller logs for attack patterns
- Apply rate limiting at Ingress level (nginx rate-limit annotations, Istio rate limits)
- Scale HPA max replicas to absorb legitimate traffic
- If pod-level DoS, apply ResourceQuotas and LimitRanges to prevent node exhaustion
- Consider pod disruption budgets to prevent cascading failures

---

## Insider Threat

**Severity**: Context-dependent — SEV-1 if active data theft; SEV-2 if policy violation under investigation

### Detection Indicators
- Bulk downloads or data access outside normal patterns
- Access to systems/data outside job scope
- Activity during unusual hours or after termination notification
- Attempts to bypass DLP or monitoring controls
- USB device usage, personal cloud storage uploads

### Immediate Actions
1. **Do not alert the subject** until you have legal and HR alignment
2. Preserve evidence covertly — increase logging, enable detailed audit trails
3. Coordinate with HR and Legal before any technical containment
4. Document everything with timestamps — chain of custody matters
5. Assess: is this malicious or negligent? Response differs significantly

### Cloud-Specific Actions (AWS/GCP)
- Enable detailed CloudTrail data events / GCP Data Access logs if not already on
- Review the subject's IAM permissions — what can they access?
- Check for data downloads: S3 GetObject patterns, BigQuery exports, console downloads
- Look for shadow IT: personal AWS accounts, IAM users for non-work purposes
- Check for access key usage from non-corporate IPs

### Kubernetes-Specific Actions
- Review RBAC: what cluster access does the individual have?
- Check for `kubectl exec`, `kubectl cp`, port-forward activity
- Review if they have access to Secrets containing sensitive data
- Check for namespace access patterns outside their scope

### Key Principle
Insider threat response requires close coordination with Legal and HR. Technical actions (revoking access, imaging devices) should be timed to coincide with HR actions (interview, suspension, termination). Premature technical containment can tip off the subject and compromise an investigation.

---

## Supply Chain Compromise

**Severity**: SEV-1 (until scope is understood)

### Detection Indicators
- Vendor/partner notification of breach
- Malicious code in dependencies (npm, PyPI, container images)
- Unexpected behavior in recently updated libraries or tools
- Compromised CI/CD pipeline components
- Backdoored container images or Helm charts

### Immediate Actions
1. Identify all systems using the compromised component
2. Pin or rollback to last known-good version
3. Isolate systems that may have executed compromised code
4. Audit what the compromised component had access to
5. Check for signs of exploitation (data access, credential theft, persistence)

### Cloud-Specific Actions
- Check if compromised dependencies are in Lambda/Cloud Functions
- Review ECR/GCR/Artifact Registry for compromised image tags
- Audit CI/CD pipeline: GitHub Actions, Cloud Build — check for modified workflows
- If a Terraform provider or module is compromised, audit all infra it touched

### Kubernetes-Specific Actions
- Identify all deployments using the compromised image (across all namespaces)
- Check image digests vs tags — tags can be reassigned, digests can't
- Review Helm chart values and OCI artifacts in the supply chain
- In k0rdent: audit the catalog templates — compromised charts in the catalog affect all managed clusters
- Check for admission webhook integrity — a compromised webhook is a root-level persistence mechanism
- Review Flux sources: GitRepository and HelmRepository URLs, verify they point to expected origins

---

## Phishing / Business Email Compromise

**Severity**: SEV-2 if credentials compromised; SEV-3 if reported but no click

### Detection Indicators
- User reports suspicious email
- Email gateway/filter alerts
- Credential use from unusual location after phishing campaign
- Unauthorized email rules or forwarding (BEC indicator)
- Wire transfer or invoice fraud attempt

### Immediate Actions
1. If credentials were entered: treat as Account Compromise (see that playbook)
2. If link clicked but no credentials entered: scan endpoint, check for drive-by download
3. If reported but no interaction: block sender/domain, alert org
4. Check: did the phishing email go to multiple recipients?
5. Search email logs for the same sender/subject/URL across the organization

### Cloud Impact Assessment
- If cloud console credentials were phished, follow Unauthorized Access playbook
- If SSO credentials were compromised, assess all federated services
- Check for OAuth consent phishing — attacker may have authorized a malicious app
- Review cloud audit logs for activity from the compromised identity

---

## Cloud Misconfiguration Exposure

**Severity**: SEV-2 if data exposed; SEV-3 if no evidence of access

### Detection Indicators
- External scan/report of exposed resource (S3 bucket, GCS bucket, database)
- Security tool finding (GuardDuty, SCC, third-party scanner)
- Unusual access patterns on a previously private resource
- Public exposure of API keys, credentials, or internal services

### Immediate Actions
1. Close the exposure immediately (restrict bucket policy, firewall rule, security group)
2. Determine what was exposed and for how long (access logs)
3. Check access logs: was the exposed resource accessed by unauthorized parties?
4. If data was accessed and includes personal data → GDPR assessment required
5. Rotate any credentials that were exposed

### AWS-Specific Actions
- S3: check bucket ACLs and bucket policy, enable S3 Block Public Access at account level
- EC2: review security groups for 0.0.0.0/0 rules on sensitive ports
- RDS: check public accessibility setting, VPC configuration
- Use IAM Access Analyzer to find resources shared externally
- Enable AWS Config rules to prevent recurrence

### GCP-Specific Actions
- Check IAM bindings for `allUsers` or `allAuthenticatedUsers`
- Review Compute Engine firewall rules for 0.0.0.0/0
- Use Security Command Center findings
- Apply VPC Service Controls to sensitive projects
- Check Cloud Storage bucket IAM and ACLs

---

## Container Escape / Kubernetes Compromise

**Severity**: SEV-1 (container escape = node/cluster-level compromise)

### Detection Indicators
- Process execution on node outside of container context
- Unexpected privileged containers or hostPath mounts
- API server access from unexpected sources
- Modified system pods (kube-system namespace)
- New ClusterRoleBindings granting cluster-admin
- etcd access from non-API-server processes

### Immediate Containment
1. Cordon the compromised node (prevents new pod scheduling)
2. Apply deny-all NetworkPolicy to the affected namespace
3. Do NOT delete the pod yet — capture its state first
4. Snapshot the node's disk for forensic analysis
5. Check: has the attacker moved laterally to other nodes or the control plane?

### Investigation Steps
- Capture pod spec: `kubectl get pod <name> -n <ns> -o yaml`
- Check for privilege escalation vectors: `privileged: true`, `hostPID`, `hostNetwork`, `hostPath`, mounted service account tokens with excessive RBAC
- Review K8s audit logs for the pod's service account activity
- Check for modified images: compare running image digest to expected digest
- Look for persistence: CronJobs, DaemonSets, mutating admission webhooks, modified kube-system pods
- Check if `kube-apiserver`, `etcd`, or `kubelet` configuration was modified

### AWS EKS-Specific
- Check CloudTrail for EKS API calls (`CreateNodegroup`, `UpdateClusterConfig`)
- Review aws-auth ConfigMap for unauthorized IAM mappings
- Check for IRSA (IAM Roles for Service Accounts) abuse — pods assuming IAM roles they shouldn't
- Node instance metadata (IMDS) access from pods — check IMDSv2 enforcement

### GCP GKE-Specific
- Check GKE audit logs and Cloud Audit Logs together
- Review Workload Identity bindings — GCP service account to K8s service account mapping
- Check for metadata server access from pods
- Verify GKE node auto-upgrade and auto-repair status

### k0rdent/KCM-Specific
- Check if the compromise affects a managed cluster or the management cluster
- Management cluster compromise = SEV-1 critical — it controls all child clusters
- Review Flux reconciliation: were HelmReleases or Kustomizations modified?
- Check k0rdent templates and ClusterDeployment resources for tampering
- Verify OCI registry integrity for Helm charts used by Flux

### Eradication & Recovery
- Replace the compromised node entirely (don't try to "clean" it)
- Rotate all service account tokens in the affected namespace
- Rotate cluster CA if control plane compromise is suspected
- Rebuild affected workloads from trusted image sources with verified digests
- Review and tighten PodSecurityStandards / PodSecurityPolicies
- Audit and minimize RBAC grants cluster-wide

---

## API / Credential Compromise

**Severity**: SEV-2 typically; SEV-1 if admin/root credentials or broad-scope API keys

### Detection Indicators
- API usage from unexpected IPs or at unusual times
- Spike in API calls (especially administrative endpoints)
- GitHub/GitLab secret scanning alerts
- Credential found in public repository, paste site, or dark web
- Unauthorized resource creation using the compromised credential

### Immediate Actions
1. Revoke/rotate the compromised credential immediately
2. Audit all actions performed with that credential since exposure
3. Check for persistence: did the attacker create new credentials, accounts, or roles?
4. Identify the exposure vector: code commit, log file, misconfigured app, phishing
5. Scan for other exposed credentials using the same vector

### AWS-Specific Actions
- Deactivate exposed access keys via IAM
- Review CloudTrail for all API calls made with those keys
- Use `aws:TokenIssueTime` condition to invalidate any assumed role sessions
- Check for new resources: EC2, Lambda, IAM users created with compromised keys
- Enable and review AWS Secrets Manager / Parameter Store access logs

### GCP-Specific Actions
- Delete exposed service account keys
- Review Admin Activity logs filtered by that service account
- Check for new resources or IAM changes made with the compromised key
- If OAuth token: revoke via Workspace Admin or API
- Check Secret Manager access logs

### Kubernetes-Specific Actions
- If kubeconfig leaked: the urgency depends on the RBAC scope of that identity
- Delete and recreate compromised ServiceAccount Secrets
- Review API audit logs for activity from that identity
- If cluster CA or admin cert leaked: rotate cluster PKI (major operation — coordinate carefully)
- Check for tokens mounted in pods that may still be valid
