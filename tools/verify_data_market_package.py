from __future__ import annotations
from pathlib import Path
import base64, hashlib, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIG_SUITE="ENTITY-SIG-ED25519-v1"
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
def unb64(v): return base64.urlsafe_b64decode(str(v)+"="*(-len(str(v))%4))
def method(manifest,key_id):
    for item in manifest.get("verification_methods") or []:
        if item.get("key_id")==key_id: return item
    return None
def verify_manifest(manifest):
    try:
        if manifest.get("schema")!="sovereign-entity-manifest-v2": return False
        data=dict(manifest); sig=dict(data.pop("signature")); m=method(data,str(sig.get("key_id") or ""))
        if not m or m.get("suite")!=SIG_SUITE or m.get("status")!="active": return False
        Ed25519PublicKey.from_public_bytes(unb64(m["public_key"])).verify(unb64(sig["signature"]),canon(data)); return True
    except Exception: return False

def verify_signature(manifest,payload,record):
    try:
        if not verify_manifest(manifest) or record.get("entity_id")!=manifest.get("entity_id"): return False
        digest=hashlib.sha256(canon(payload)).hexdigest()
        if record.get("payload_sha256")!=digest or record.get("signature_schema")!="entity-signature-record-v2": return False
        m=method(manifest,str(record.get("key_id") or ""))
        if not m or m.get("suite")!=record.get("suite"): return False
        signed={"signature_schema":record["signature_schema"],"entity_id":record["entity_id"],"key_id":record["key_id"],
                "suite":record["suite"],"signed_at_ms":record["signed_at_ms"],"payload_sha256":digest}
        Ed25519PublicKey.from_public_bytes(unb64(m["public_key"])).verify(unb64(record["signature"]),canon(signed)); return True
    except Exception: return False

def verify_external(evidence,trust):
    try:
        body=dict(evidence or {}); sig=str(body.pop("signature"))
        if body.get("schema")!="entity-external-authority-evidence-v1": return False
        if str(body.get("authority_id"))!=str(trust.get("authority_id")): return False
        if str(body.get("authority_type")).upper()!=str(trust.get("authority_type")).upper(): return False
        if str(trust.get("status","ACTIVE")).upper()!="ACTIVE": return False
        if str(body.get("jurisdiction")).upper() not in {str(x).upper() for x in trust.get("jurisdictions",[])}: return False
        if str(body.get("evidence_type")).upper() not in {str(x).upper() for x in trust.get("evidence_types",[])}: return False
        Ed25519PublicKey.from_public_bytes(unb64(trust["public_key_b64"])).verify(unb64(sig),canon(body)); return True
    except Exception: return False

def verify_tables(tables,manifests):
    failures=[]; markets={str(x["market_id"]):x for x in tables.get("markets",[])}
    instruments={str(x["instrument_id"]):x for x in tables.get("instruments",[])}; positions=list(tables.get("positions",[]))
    for iid,row in instruments.items():
        issued=int(row["issued_units"]); circulating=int(row["circulating_units"]); consumed=int(row["consumed_units"])
        if issued>int(row["authorized_units"]): failures.append(f"{iid}:issued_exceeds_authorized")
        if issued!=circulating+consumed: failures.append(f"{iid}:issued_supply_reconciliation")
        pos=[p for p in positions if str(p["instrument_id"])==iid]
        if sum(int(p["available_units"])+int(p["reserved_units"]) for p in pos)!=circulating: failures.append(f"{iid}:position_reconciliation")
        if sum(int(p["consumed_units"]) for p in pos)!=consumed: failures.append(f"{iid}:consumed_reconciliation")
    events=sorted(tables.get("market_events",[]),key=lambda x:(str(x["market_id"]),int(x["sequence"])))
    by_market={}
    for event in events: by_market.setdefault(str(event["market_id"]),[]).append(event)
    for market_id,rows in by_market.items():
        prior="0"*64; expected=1
        for row in rows:
            payload=json.loads(row.get("payload_json") or "{}")
            if int(row["sequence"])!=expected or str(row["prior_hash"])!=prior: failures.append(f"{market_id}:{expected}:chain")
            if hashlib.sha256(canon(payload)).hexdigest()!=str(row["payload_hash"]): failures.append(f"{market_id}:{expected}:payload_hash")
            body={"schema":"entity-data-market-event-v1","market_id":market_id,"sequence":int(row["sequence"]),
                  "event_type":row["event_type"],"actor_entity_id":row["actor_entity_id"],"object_ref":row["object_ref"],
                  "payload_hash":row["payload_hash"],"prior_hash":row["prior_hash"],"created_at_ms":int(row["created_at_ms"])}
            sig=json.loads(row.get("signature_json") or "{}"); manifest=manifests.get(str(row["actor_entity_id"]))
            if not manifest or not verify_signature(manifest,body,sig): failures.append(f"{market_id}:{expected}:signature")
            if hashlib.sha256(canon({"body":body,"signature":sig})).hexdigest()!=str(row["event_hash"]): failures.append(f"{market_id}:{expected}:event_hash")
            prior=str(row["event_hash"]); expected+=1
        market=markets.get(market_id)
        if not market or prior!=str(market["head_hash"]) or len(rows)!=int(market["sequence"]): failures.append(f"{market_id}:head")
    return failures

def verify_package(package):
    failures=[]; supplied=dict(package or {}); signature=dict(supplied.pop("signature",{}) or {})
    if supplied.get("schema")!="entity-data-market-package-v1": failures.append("invalid_schema")
    claimed=str(supplied.get("package_sha256") or ""); hash_body=dict(supplied); hash_body.pop("package_sha256",None)
    if hashlib.sha256(canon(hash_body)).hexdigest()!=claimed: failures.append("package_sha256_mismatch")
    manifests=dict(supplied.get("manifests") or {}); operator=str(supplied.get("operator_entity_id") or "")
    if not manifests.get(operator) or not verify_signature(manifests[operator],supplied,signature): failures.append("package_signature_invalid")
    tables=dict(supplied.get("tables") or {}); failures.extend(verify_tables(tables,manifests))
    trust=dict(supplied.get("external_trust") or {})
    for row in tables.get("order_authority",[]):
        for field in ("eligibility_json","collateral_json"):
            try: evidence=dict(json.loads(row.get(field) or "{}").get("evidence") or {})
            except Exception: evidence={}
            if evidence:
                record=trust.get(str(evidence.get("authority_id") or ""))
                if not record or not verify_external(evidence,record): failures.append(f"{row.get('order_id')}:{field}:external_authority")
    for row in tables.get("external_settlements",[]):
        try: evidence=json.loads(row.get("evidence_json") or "{}")
        except Exception: evidence={}
        record=trust.get(str(evidence.get("authority_id") or ""))
        if not evidence or not record or not verify_external(evidence,record): failures.append(f"{row.get('trade_id')}:external_settlement")
    return {"valid":not failures,"failures":failures,"market_id":supplied.get("market_id"),
            "provider_independent":bool(supplied.get("provider_independent")),"raw_data_included":bool(supplied.get("raw_data_included"))}

def verify_file(path): return verify_package(json.loads(Path(path).read_text(encoding="utf-8")))
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("package"); a=p.parse_args(); r=verify_file(a.package)
    print(json.dumps(r,indent=2,sort_keys=True)); raise SystemExit(0 if r["valid"] else 2)
