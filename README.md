# ENTITY-2

**BTG-controlled development line for future ENTITY market, integration and protocol work.**

`ENTITY-2` is a public development repository maintained by **Blackmore Technology Group Limited (BTG)**. It is used for post-release engineering work including sovereign data commodities, rights-aware exchange, ADAM/NIKI integration, market evidence and related protocol experiments.

> **This repository is not the current protected ENTITY release, not the authoritative external conformance kit, and not an independent third-party implementation.**

## Public project map

Use the repository that matches the work you are trying to evaluate:

| Purpose | Authoritative location |
| --- | --- |
| Current protected ENTITY release and reference implementation | [blackmore-technology-group/ENTITY](https://github.com/blackmore-technology-group/ENTITY) |
| Current protected release | [ENTITY v3.3.0 — Verifiable Reality, Evidence and Economic Causality](https://github.com/blackmore-technology-group/ENTITY/releases/tag/v3.3.0) |
| Frozen Protocol 1.0 external conformance target | [ENTITY Protocol 1.0 Conformance Kit](https://github.com/blackmore-technology-group/ENTITY-Protocol-1.0-Conformance-Kit) |
| Future/development work | **this repository (`ENTITY-2`)** |

The protected ENTITY v3.3.0 release commit is:

`9c79f987207592cb6791e1a8956f23351cdfb2d3`

The current authoritative Protocol 1.0 conformance-kit release is **v1.0.2**.

## Claim boundary

Work in this repository can be incomplete, experimental, superseded or awaiting qualification. A branch, commit, pull request, passing local test or merged development change does **not** automatically become:

- a new protected ENTITY release;
- a frozen protocol revision;
- external conformance evidence;
- independent interoperability evidence;
- an independent security review;
- a legal, regulatory, accounting or market determination.

Release claims belong with the evidence package and protected release in the main [ENTITY](https://github.com/blackmore-technology-group/ENTITY) repository.

BTG-controlled work—including clean-room work in other BTG repositories—is not described as unrelated third-party validation.

## Development focus

Current engineering themes include:

- sovereign data-commodity objects and rights-bearing instruments;
- listing, disclosure, order/RFQ/auction and price-discovery mechanics;
- clearing, settlement and entitlement state;
- usage evidence, derived outputs and economic consequences;
- rights-aware exchange and market recovery;
- ADAM/NIKI integration boundaries;
- provider-independent evidence and authority semantics;
- failure, rollback, recovery and portability testing.

The intended market lifecycle is:

**DCO → Instrument → Listing → Disclosure → Order/RFQ/Auction → Price Discovery → Trade → Clearing → Settlement → Entitlement → Usage → Derived Output → Economic Consequence**

Data economics in ENTITY concerns governed **rights and authority around data**, not artificial scarcity of byte copies.

## Core invariants

Development work must preserve the project’s authority boundaries:

- identity is not an account;
- registration is not ownership;
- provenance is not truth;
- a valid signature is not objective external truth;
- possession, hosting and storage do not create sovereign authority;
- external evidence sources do not silently become protocol authority;
- generic application events cannot mutate protected authority, rights or economic state;
- historical signed state is superseded rather than silently rewritten;
- internal qualification is not independent external validation.

## Engineering workflow

`main` is protected. Changes should flow through pull requests and required checks.

Current required protection includes:

- public conformance/unit test gate;
- dependency review;
- CodeQL analysis for GitHub Actions;
- CodeQL analysis for Python;
- linear history;
- resolved review conversations;
- no force pushes or branch deletion.

Development work should identify the exact branch/commit tested and should not describe an unqualified development branch as a release.

## Quick start

Python 3.11+ is recommended for the current reference/development runtime.

```powershell
git clone https://github.com/blackmore-technology-group/ENTITY-2.git
cd ENTITY-2
python -m pip install -r requirements.txt
python -m compileall -q src sdk protocol
python -m unittest discover -s tests -v
```

Passing this local smoke path is useful engineering evidence for the checked-out commit. It is not by itself a release or interoperability qualification.

## External conformance and interoperability

Unrelated implementers should work from the sealed public conformance kit rather than using this repository as their implementation source:

- [ENTITY Protocol 1.0 Conformance Kit](https://github.com/blackmore-technology-group/ENTITY-Protocol-1.0-Conformance-Kit)
- [General independent implementation challenge](https://github.com/blackmore-technology-group/ENTITY-Protocol-1.0-Conformance-Kit/issues/2)
- [ENTITY interoperability challenge](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/INTEROPERABILITY_CHALLENGE.md)
- [Interoperability status](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/interoperability/STATUS.md)

Independent external implementation and live interoperability remain evidence-gated milestones. They should be recorded only when an unrelated party actually produces the required evidence.

## Security

Never commit operational sovereignty state or secrets to this repository, including:

- private signing or recovery keys;
- credentials, tokens, cookies or API secrets;
- principal/device/application binding instances;
- `.entitybackup` files;
- production databases or runtime state;
- unredacted user, customer or business data.

Security-sensitive findings should be handled through the private reporting process in the main ENTITY project rather than publishing exploit details in a public issue.

## Governance

The public project governance and release discipline are maintained in the main ENTITY repository:

- [Developer Portal](https://github.com/blackmore-technology-group/ENTITY/blob/main/DEVELOPERS.md)
- [Governance](https://github.com/blackmore-technology-group/ENTITY/blob/main/GOVERNANCE.md)
- [Release Policy](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/governance/RELEASE_POLICY.md)
- [Engineering Evidence](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/ENGINEERING_EVIDENCE.md)
- [Security](https://github.com/blackmore-technology-group/ENTITY/blob/main/SECURITY.md)

## License

ENTITY development material in this repository is published under the **Apache License 2.0** where the repository license applies. See [LICENSE](LICENSE).

---

**Blackmore Technology Group Limited**  
Repository: `blackmore-technology-group/ENTITY-2`  
Role: BTG-controlled future/development engineering line