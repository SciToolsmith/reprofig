# Permission gates

Score each action independently. The effective level is the highest level across access, cost, privacy, security, external effects, system mutation, and scientific-claim impact.

## R0 — automatic read-only

- read supplied paper and images;
- interpret figure semantics, panels, visual encodings, and the figure's role in the paper's evidence chain;
- reconstruct an explicit input-to-figure generation chain, derive candidate routes, and define scientific validation targets;
- inspect local source text;
- search public metadata and source pages;
- query versions, package lists, licenses, hardware, and free disk;
- estimate download and compute size.

## R1 — bounded automatic with provenance

Allowed only inside a dedicated investigation workspace and within the declared budget:

- download small publicly accessible resources with clear provenance;
- compute hashes and inspect archives;
- create an isolated open-source environment;
- run reviewed smoke tests with time, memory, disk, and network bounds;
- create a static local report and approval draft.

Do not modify a global environment, overwrite user files, or run a full reproduction under R1.

## R2 — explicit confirmation before action

- downloads or environments above the R1 budget;
- long CPU jobs, GPU use, large memory/disk use, or shared license consumption;
- network-enabled execution of research code;
- native/system dependencies, containers requiring elevated access, unknown binaries or MEX files;
- unclear license;
- compatibility patch that may change scientific semantics;
- overwriting existing outputs.

Present a decision card with action, reason, source, license, download size, disk use, estimated runtime, cost, risks, rollback, recommended alternative, affected generation-chain links, and the scientific claim that would remain testable.

## R3 — user-held authority and itemized approval

- login, MFA, CAPTCHA, account creation, or accepting click-through terms/DUA;
- payment, cloud/API credits, subscriptions, or institution-only access;
- private repository, VPN, controlled data, IRB/ethics conditions;
- uploading the paper, data, or code to a third party;
- contacting authors, posting an issue, submitting a cluster job, publishing a website, or redistributing code/data/images.

Never ask the user to paste passwords or tokens into the report. Direct them to the official authentication path.

## R4 — block

Block:

- bypassing paywalls, DRM, CAPTCHA, or access controls;
- unauthorized credentials or license/DUA violations;
- disclosure of sensitive, confidential, clinical, personal, or unpublished data;
- root or privileged execution of untrusted code;
- destructive deletion or broad overwrite;
- fabricated data, omitted assumptions, or claiming visual similarity as scientific reproduction.

## Scientific route gate

Treat a change among `direct-recompute`, `mechanism-reproduction`, `alternative-validation`, `editable-reconstruction`, and `original-case-blocked` as a material plan change. Never downgrade silently. State what the new route can and cannot support, then request a new approval.

Approval authorizes actions and scope; it does not establish scientific validity. Scientific support is determined only by execution evidence evaluated against the predefined validation criteria.

## Default budget

Unless the user supplied another budget:

- public downloads: 1 GB total;
- isolated environment/cache: 5 GB;
- smoke test: 10 minutes per resource;
- full reproduction during investigation: prohibited;
- GPU, paid services, cloud quota, and global install: prohibited.

Record actual usage and stop before crossing a limit.
