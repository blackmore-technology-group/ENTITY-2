from pathlib import Path
import base64, importlib.util, json, time, uuid
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/"src"
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def b64(raw): return base64.urlsafe_b64encode(raw).decode().rstrip("=")
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def pub(priv): return b64(priv.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
def ext(priv,aid,atype,etype,subject,ref,payload):
    now=int(time.time()*1000); body={"schema":"entity-external-authority-evidence-v1","authority_id":aid,
      "authority_type":atype,"jurisdiction":"CA-BC","evidence_type":etype,"external_authority_ref":ref,
      "subject_entity_id":subject,"payload":dict(payload),"issued_at_ms":now,"effective_at_ms":now,"nonce":uuid.uuid4().hex}
    body["signature"]=b64(priv.sign(canon(body))); return body

@pytest.fixture
def env(tmp_path):
    I=load("fq_i",ROOT/"01_Core_Runtime"/"identity"/"canonical_identity.py")
    E=load("fq_e",ROOT/"01_Core_Runtime"/"service_runtime"/"canonical_economics.py")
    P=load("fq_p",ROOT/"21_Corporate_Capital"/"digital_commodities"/"market_policy"/"canonical_data_market_policy.py")
    X=load("fq_x",ROOT/"21_Corporate_Capital"/"digital_commodities"/"canonical_data_commodity_exchange_v2.py")
    C=load("fq_c",ROOT/"21_Corporate_Capital"/"digital_commodities"/"market_policy"/"canonical_data_market_compliance.py")
    A=load("fq_a",ROOT/"21_Corporate_Capital"/"external_authorities"/"canonical_external_authority.py")
    B=load("fq_b",ROOT/"15_Operations"/"backups"/"canonical_portable_state.py")
    V=load("fq_v",REPO/"tools"/"verify_data_market_package.py")
    state=tmp_path/"market_state"; remote_state=tmp_path/"remote_state"
    identity=I.EntityIdentityVault(state); remote_identity=I.EntityIdentityVault(remote_state)
    issuer=identity.create("Data Issuer","organization")["entity_id"]
    contributor=identity.create("Contributor","person")["entity_id"]
    operator=identity.create("Market Operator","organization")["entity_id"]
    buyer=remote_identity.create("Federated Buyer","organization")["entity_id"]
    policy=P.DataMarketPolicyRegistry(state); effective=int(time.time()*1000)-1000
    for action in ("ISSUE_DATA_RIGHT","LIST_DATA_RIGHT","TRADE_DATA_RIGHT","CONSUME_DATA_RIGHT","SETTLE_DATA_RIGHT_TRADE"):
        policy.register_rule("fq-"+action.lower(),jurisdiction="CA-BC",instrument_class="DATA_COMMODITY_RIGHT",
          action=action,decision="ALLOW_EVIDENCE_ONLY",version=1,effective_at_ms=effective,authority_ref="fq-policy")
    authorities=A.ExternalAuthorityRegistry(state); legal_key=Ed25519PrivateKey.generate(); pay_key=Ed25519PrivateKey.generate()
    authorities.trust_authority("eligibility-fq","LEGAL_ATTESTOR",pub(legal_key),jurisdictions=["CA-BC"],
      evidence_types=["BUYER_ELIGIBILITY"])
    authorities.trust_authority("payment-fq","PAYMENT_PROVIDER",pub(pay_key),jurisdictions=["CA-BC"],
      evidence_types=["ORDER_COLLATERAL_RESERVATION","PAYMENT_SETTLEMENT_CONFIRMATION"])
    gate=C.DataMarketComplianceGate(authorities); settlement=E.SettlementEngine(state,identity)
    royalty=settlement.create_royalty_plan(issuer,{issuer:7000,contributor:3000},version=1)
    exchange=X.DataCommodityExchangeV2(state,identity,classifier=policy,settlement_engine=settlement,compliance_gate=gate)
    remote=X.DataCommodityExchangeV2(remote_state,remote_identity)
    market=exchange.create_market(operator,"Federated Data Rights Market",quote_currency="CAD")
    commodity=exchange.register_commodity(issuer,"asset-observation-corpus-001",commodity_type="OBSERVATION_DATASET",
      unit_code="DCU",unit_description="standardized data-right unit",total_units=1000,commercialization_authority=True,
      jurisdiction="CA-BC",authority_ref="rights:test:commodity")
    instrument=exchange.create_instrument(issuer,commodity["commodity_id"],symbol="OBS-AI-01",rights_class="AI_TRAINING_RIGHT",
      authorized_units=1000,transferable=True,resale_allowed=True,permitted_purposes=["AI_TRAINING"],
      buyer_requirements={"jurisdiction":"CA-BC","collateral_required":True},royalty_plan_id=royalty["plan_id"],
      jurisdictional_classification="DATA_COMMODITY_RIGHT")
    exchange.issue(issuer,instrument["instrument_id"],issuer,quantity=600,issuance_nonce="fq-issue-600")
    return locals()

def evidences(e,trade=None,price=25,qty=40):
    now=int(time.time()*1000)+600000
    eligibility=ext(e["legal_key"],"eligibility-fq","LEGAL_ATTESTOR","BUYER_ELIGIBILITY",e["buyer"],"elig:fq:1",
      {"eligible":True,"jurisdiction":"CA-BC","purposes":["AI_TRAINING"],"expires_at_ms":now})
    collateral=ext(e["pay_key"],"payment-fq","PAYMENT_PROVIDER","ORDER_COLLATERAL_RESERVATION",e["buyer"],"collateral:fq:1",
      {"reserved_amount_minor":qty*price,"currency":"CAD","expires_at_ms":now})
    if trade is None: return eligibility,collateral,None
    settlement=ext(e["pay_key"],"payment-fq","PAYMENT_PROVIDER","PAYMENT_SETTLEMENT_CONFIRMATION",e["issuer"],"settlement:fq:"+trade["trade_id"],
      {"trade_id":trade["trade_id"],"buyer_entity_id":trade["buyer_entity_id"],"seller_entity_id":trade["seller_entity_id"],
       "amount_minor":int(trade["quantity"])*int(trade["price_minor"]),"currency":trade["currency"],"final":True,
       "settlement_ref":"provider-settle:"+trade["trade_id"]})
    return eligibility,collateral,settlement

def execute_remote_trade(e,*,qty=40,price=25,nonce="fq-buy-1"):
    x=e["exchange"]; iid=e["instrument"]["instrument_id"]; mid=e["market"]["market_id"]
    x.place_order(e["issuer"],mid,iid,side="SELL",quantity=qty,limit_price_minor=price,currency="CAD",
      order_nonce="sell-"+nonce,purpose="AI_TRAINING")
    envelope=e["remote"].create_signed_order(e["buyer"],mid,iid,side="BUY",quantity=qty,limit_price_minor=price,
      currency="CAD",order_nonce=nonce,time_in_force="GTC",purpose="AI_TRAINING",expires_at_ms=int(time.time()*1000)+300000)
    eligibility,collateral,_=evidences(e,price=price,qty=qty)
    result=x.ingest_signed_order(e["operator"],envelope,e["remote_identity"].load_manifest(e["buyer"]),
      eligibility_evidence=eligibility,collateral_evidence=collateral)
    assert len(result["trades"])==1
    trade=result["trades"][0]; _,_,payment=evidences(e,trade=trade,price=price,qty=qty)
    settled=x.finalize_trade_external(e["operator"],trade["trade_id"],payment)
    return envelope,trade,settled

def test_federated_order_collateral_external_settlement_and_royalty(env):
    envelope,trade,settled=execute_remote_trade(env)
    x=env["exchange"]; iid=env["instrument"]["instrument_id"]
    assert settled["external_settlement_verified"] is True and settled["rights_transferred"] is True
    assert x.position(env["buyer"],iid)["available_units"]==40
    allocation=settled["royalty_allocation"]; assert allocation and allocation["allocated_total"]==1000
    assert allocation["distribution"][env["issuer"]]==700 and allocation["distribution"][env["contributor"]]==300
    assert x.verify_invariants()["pass"] is True

def test_provider_independent_market_package_and_tamper_detection(env,tmp_path):
    execute_remote_trade(env,qty=30,price=20,nonce="fq-package-buy")
    path=tmp_path/"market_package.json"; package=env["exchange"].export_market_package(env["market"]["market_id"],path)
    checked=env["V"].verify_file(path)
    assert checked["valid"] is True and checked["provider_independent"] is True and checked["raw_data_included"] is False
    tampered=json.loads(json.dumps(package)); tampered["tables"]["trades"][0]["price_minor"]+=1
    assert env["V"].verify_package(tampered)["valid"] is False

def test_replay_bad_collateral_and_bad_settlement_fail_closed(env):
    x=env["exchange"]; iid=env["instrument"]["instrument_id"]; mid=env["market"]["market_id"]
    x.place_order(env["issuer"],mid,iid,side="SELL",quantity=10,limit_price_minor=50,currency="CAD",order_nonce="fq-bad-sell",purpose="AI_TRAINING")
    envelope=env["remote"].create_signed_order(env["buyer"],mid,iid,side="BUY",quantity=10,limit_price_minor=50,currency="CAD",
      order_nonce="fq-bad-buy",purpose="AI_TRAINING",expires_at_ms=int(time.time()*1000)+300000)
    eligibility,collateral,_=evidences(env,price=50,qty=10); bad_collateral=json.loads(json.dumps(collateral)); bad_collateral["payload"]["reserved_amount_minor"]=499
    with pytest.raises(PermissionError): x.ingest_signed_order(env["operator"],envelope,env["remote_identity"].load_manifest(env["buyer"]),eligibility_evidence=eligibility,collateral_evidence=bad_collateral)
    accepted=x.ingest_signed_order(env["operator"],envelope,env["remote_identity"].load_manifest(env["buyer"]),eligibility_evidence=eligibility,collateral_evidence=collateral)
    with pytest.raises(ValueError,match="duplicate/replayed"): x.ingest_signed_order(env["operator"],envelope,env["remote_identity"].load_manifest(env["buyer"]),eligibility_evidence=eligibility,collateral_evidence=collateral)
    trade=accepted["trades"][0]; _,_,payment=evidences(env,trade=trade,price=50,qty=10); bad_payment=json.loads(json.dumps(payment)); bad_payment["payload"]["amount_minor"]+=1
    with pytest.raises(PermissionError): x.finalize_trade_external(env["operator"],trade["trade_id"],bad_payment)
    assert x.position(env["buyer"],iid)["available_units"]==0

def test_destructive_recovery_and_entity_export_include_exchange_state(env,tmp_path):
    execute_remote_trade(env,qty=15,price=40,nonce="fq-recovery-buy")
    state=env["state"]; manager=env["B"].PortableStateManager(state,env["identity"])
    backup=manager.create_encrypted_backup(tmp_path/"exchange-state.enc")
    key=base64.urlsafe_b64decode(backup["key_b64"]); unavailable=tmp_path/"state_unavailable"
    state.rename(unavailable); assert not state.exists()
    env["B"].PortableStateManager(unavailable,env["identity"]).restore_encrypted_backup(backup["path"],key,state)
    I=env["I"]; restored_identity=I.EntityIdentityVault(state)
    policy=env["P"].DataMarketPolicyRegistry(state); authorities=env["A"].ExternalAuthorityRegistry(state)
    gate=env["C"].DataMarketComplianceGate(authorities); settlement=env["E"].SettlementEngine(state,restored_identity)
    restored=env["X"].DataCommodityExchangeV2(state,restored_identity,classifier=policy,settlement_engine=settlement,compliance_gate=gate)
    assert restored.verify_invariants()["pass"] is True
    package_path=tmp_path/"restored_market.json"; restored.export_market_package(env["market"]["market_id"],package_path)
    assert env["V"].verify_file(package_path)["valid"] is True
    export_dir=tmp_path/"issuer_export"; env["B"].PortableStateManager(state,restored_identity).export_entity(env["issuer"],export_dir)
    files=list(export_dir.glob("*exchange.sqlite.json")); assert files
    tables=json.loads(files[0].read_text(encoding="utf-8"))["tables"]
    assert "instruments" in tables and "trades" in tables and "market_events" in tables

def test_market_chaos_replay_forgery_double_sale_and_chain_tamper(env):
    import sqlite3
    x=env["exchange"]; iid=env["instrument"]["instrument_id"]; mid=env["market"]["market_id"]
    envelope=env["remote"].create_signed_order(env["buyer"],mid,iid,side="BUY",quantity=5,limit_price_minor=10,currency="CAD",
      order_nonce="chaos-forge",purpose="AI_TRAINING",expires_at_ms=int(time.time()*1000)+300000)
    forged=json.loads(json.dumps(envelope)); forged["quantity"]=6
    eligibility,collateral,_=evidences(env,price=10,qty=5)
    with pytest.raises(PermissionError,match="signature"): x.ingest_signed_order(env["operator"],forged,env["remote_identity"].load_manifest(env["buyer"]),eligibility_evidence=eligibility,collateral_evidence=collateral)
    expired=env["remote"].create_signed_order(env["buyer"],mid,iid,side="BUY",quantity=5,limit_price_minor=10,currency="CAD",
      order_nonce="chaos-expired",purpose="AI_TRAINING",expires_at_ms=int(time.time()*1000)+500)
    time.sleep(.6)
    with pytest.raises(PermissionError,match="expired"): x.ingest_signed_order(env["operator"],expired,env["remote_identity"].load_manifest(env["buyer"]),eligibility_evidence=eligibility,collateral_evidence=collateral)
    with pytest.raises(ValueError,match="insufficient"): x.place_order(env["issuer"],mid,iid,side="SELL",quantity=601,limit_price_minor=1,currency="CAD",order_nonce="chaos-oversell",purpose="AI_TRAINING")
    execute_remote_trade(env,qty=5,price=10,nonce="chaos-good")
    assert x.verify_invariants()["pass"] is True
    db=sqlite3.connect(x.path); row=db.execute("SELECT event_id,payload_json FROM market_events WHERE market_id=? ORDER BY sequence LIMIT 1",(mid,)).fetchone()
    db.execute("UPDATE market_events SET payload_json=? WHERE event_id=?",(json.dumps({"tampered":True}),row[0])); db.commit(); db.close()
    assert x.verify_market(mid)["pass"] is False

