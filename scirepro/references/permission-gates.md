# Permission gates

Use this reference only when an action can change local or external state. Score each action independently; the effective level is the highest across access, cost, privacy, security, system mutation, external effect, and scientific impact.

## R0 — automatic read-only

- read supplied artifacts and local source text;
- interpret targets and derive routes or validation criteria;
- search public metadata and source pages;
- query relevant versions, package/toolbox lists, licenses, hardware, free disk, and declared sizes.

## R1 — bounded automatic with provenance

Allowed in a dedicated workspace and inside the approved/default budget:

- download small anonymous public resources from a verified source;
- hash and safely inspect archives;
- create a project-local open-source environment without changing global packages;
- run reviewed, bounded smoke tests with no network after setup;
- create the local report, approval receipt, and create-only outputs.

R1 never authorizes a global install, overwrite, unrestricted network execution, proprietary installation, or unapproved full reproduction. A compact single-route report may summarize R0/R1 effects in one receipt rather than repeat a long decision card.

## R2 — explicit confirmation

- downloads, environments, CPU time, memory, or disk above the R1 budget;
- GPU, shared-license use, network-enabled research execution, or long jobs;
- native/system dependencies, elevated containers, unknown binaries, MEX files, or unclear licenses;
- compatibility or parameter changes that may affect scientific meaning;
- overwrite of an existing output.

State the proposed action, source, size/runtime/cost, risk, rollback, affected targets and generation links, and what claim remains testable. Do not burden the user with irrelevant fields when these facts fit in a concise decision card.

## R3 — user-held authority and itemized approval

- login, MFA, CAPTCHA, account creation, click-through terms, or DUA;
- payment, API/cloud credits, subscription, or institution-only access;
- private repositories, VPN, controlled data, or ethics restrictions;
- uploading paper/data/code, contacting authors, posting issues, cluster submission, publication, or redistribution.

The user performs authentication through the official path. Never request passwords or tokens in a report.

## R4 — block

- bypassing paywalls, DRM, CAPTCHA, access controls, licenses, or DUA;
- unauthorized credentials or disclosure of sensitive, confidential, clinical, personal, or unpublished data;
- privileged execution of untrusted code or destructive/broad deletion;
- fabricated data, concealed assumptions, or claims that visual similarity proves scientific reproduction.

## What requires renewed approval

Renew after a material change to target identity or hash, workflow mode, reproduction level, scientific claim, selected route, accepted assumption, restricted source, effect level, budget, or output/overwrite policy.

Do not renew for harmless formatting, retrying an unchanged command inside the approved envelope, or substituting a byte-identical artifact. Approval permits actions and scope; validation evidence—not approval—determines scientific support.

## Default R1 budget

- anonymous public downloads: 1 GB total;
- project-local environment/cache: 5 GB;
- smoke test: 10 minutes per resource;
- no GPU, payment, cloud quota, global install, overwrite, or unrestricted full run.

Record actual use and stop before crossing a limit. User-supplied stricter limits take precedence.
