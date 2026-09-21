from pathlib import Path
import base64, importlib.util, json, time, uuid
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/"src"
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def b64(raw): return base64.urlsafe_b64encode(raw).decode().rstrip("=")
def pub(k): return b64(k.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def evidence(key,operator):
    now=int(time.time()*1000); body={"schema":"entity-external-authority-evidence-v1","authority_id":"venue-regulator-test",
      "authority_type":"REGULATOR","jurisdiction":"CA-BC","evidence_type":"VENUE_OPERATION_AUTHORIZATION",
      "external_authority_ref":"regulator:test:venue","subject_entity_id":operator,
      "payload":{"venue_id":"venue-test-1","jurisdiction":"CA-BC","active":True,"expires_at_ms":now+600000},
      "issued_at_ms":now,"effective_at_ms":now,"nonce":uuid.uuid4().hex}
    body["signature"]=b64(key.sign(canon(body))); return body

def test_authorized_venue_adapter_is_fail_closed_and_provider_bounded(tmp_path):
    I=load("va_i",ROOT/"01_Core_Runtime"/"identity"/"canonical_identity.py")
    A=load("va_a",ROOT/"21_Corporate_Capital"/"external_authorities"/"canonical_external_authority.py")
    V=load("va_v",ROOT/"21_Corporate_Capital"/"digital_commodities"/"canonical_regulated_venue_adapter.py")
    state=tmp_path/"state"; identity=I.EntityIdentityVault(state); operator=identity.create("Venue Operator","organization")["entity_id"]
    registry=A.ExternalAuthorityRegistry(state); key=Ed25519PrivateKey.generate()
    registry.trust_authority("venue-regulator-test","REGULATOR",pub(key),jurisdictions=["CA-BC"],evidence_types=["VENUE_OPERATION_AUTHORIZATION"])
    auth=evidence(key,operator); order={"schema":"entity-data-market-order-v1","entity_id":operator,"market_id":"m1","instrument_id":"i1"}
    disabled=V.AuthorizedVenueAdapter(identity,registry)
    with pytest.raises(RuntimeError,match="provider is not configured"):
        disabled.submit_order(operator,"venue-test-1","CA-BC",order,auth)
    calls=[]
    def submit(payload): calls.append(payload); return {"provider_order_ref":"external-order-1","status":"ACCEPTED"}
    def cancel(ref): return {"status":"CANCELLED","ref":ref}
    adapter=V.AuthorizedVenueAdapter(identity,registry,submit_callback=submit,cancel_callback=cancel)
    receipt=adapter.submit_order(operator,"venue-test-1","CA-BC",order,auth)
    assert receipt["provider_order_ref"]=="external-order-1" and receipt["provider_submission_is_not_settlement"] is True
    assert calls==[order]
    cancelled=adapter.cancel_order(operator,"venue-test-1","CA-BC","external-order-1",auth)
    assert cancelled["provider_status"]=="CANCELLED"
    bad=json.loads(json.dumps(auth)); bad["payload"]["active"]=False
    with pytest.raises(PermissionError): adapter.submit_order(operator,"venue-test-1","CA-BC",order,bad)
