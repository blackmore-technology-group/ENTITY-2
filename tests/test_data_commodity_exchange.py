from pathlib import Path
import importlib.util, time
import pytest

ROOT=Path(__file__).resolve().parents[1]/"src"

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

@pytest.fixture
def exchange_env(tmp_path):
    I=load("dce_identity",ROOT/"01_Core_Runtime"/"identity"/"canonical_identity.py")
    E=load("dce_economics",ROOT/"01_Core_Runtime"/"service_runtime"/"canonical_economics.py")
    J=load("dce_market_policy",ROOT/"21_Corporate_Capital"/"digital_commodities"/"market_policy"/"canonical_data_market_policy.py")
    X=load("dce_exchange",ROOT/"21_Corporate_Capital"/"digital_commodities"/"canonical_data_commodity_exchange.py")
    state=tmp_path/"state"; identity=I.EntityIdentityVault(state)
    issuer=identity.create("Commodity Issuer","organization")["entity_id"]
    buyer=identity.create("Buyer One","organization")["entity_id"]
    buyer2=identity.create("Buyer Two","organization")["entity_id"]
    operator=identity.create("Market Operator","organization")["entity_id"]
    classifier=J.DataMarketPolicyRegistry(state); effective=int(time.time()*1000)-1000
    for action in ("ISSUE_DATA_RIGHT","LIST_DATA_RIGHT","TRADE_DATA_RIGHT","CONSUME_DATA_RIGHT","SETTLE_DATA_RIGHT_TRADE"):
        classifier.register_rule(f"bc-data-{action.lower()}",jurisdiction="CA-BC",instrument_class="DATA_COMMODITY_RIGHT",action=action,decision="ALLOW_EVIDENCE_ONLY",version=1,effective_at_ms=effective,authority_ref="test-policy")
    settlement=E.SettlementEngine(state,identity)
    engine=X.DataCommodityExchange(state,identity,classifier=classifier,settlement_engine=settlement)
    market=engine.create_market(operator,"ENTITY Data Rights Market",quote_currency="CAD")
    commodity=engine.register_commodity(issuer,"asset-wildlife-001",commodity_type="WILDLIFE_OBSERVATION_DATASET",unit_code="DCU",unit_description="one standardized data commodity unit",total_units=1000,commercialization_authority=True,jurisdiction="CA-BC",authority_ref="rights-claim:test")
    instrument=engine.create_instrument(issuer,commodity["commodity_id"],symbol="WILD-AITRAIN-27",rights_class="AI_TRAINING_RIGHT",authorized_units=1000,transferable=True,resale_allowed=True,permitted_purposes=["AI_TRAINING"],jurisdictional_classification="DATA_COMMODITY_RIGHT")
    engine.issue(issuer,instrument["instrument_id"],issuer,quantity=500,issuance_nonce="initial-500")
    return {"engine":engine,"settlement":settlement,"issuer":issuer,"buyer":buyer,"buyer2":buyer2,"operator":operator,"market":market["market_id"],"commodity":commodity["commodity_id"],"instrument":instrument["instrument_id"]}

def settle_trade(env,trade,buyer,seller,nonce):
    settlement=env["settlement"]
    amount=int(trade["quantity"])*int(trade["price_minor"])
    created=settlement.create(buyer,seller,amount_units=amount,currency=trade["currency"],obligation_ref=trade["trade_id"],transaction_nonce=nonce,settlement_kind="EXTERNAL_PAYMENT")
    settlement.authorize(buyer,created["settlement_id"])
    settlement.record_external_evidence(buyer,created["settlement_id"],"PROVIDER_CONFIRMED",{"provider":"test-bank","payment_id":nonce})
    settlement.confirm(buyer,created["settlement_id"])
    return env["engine"].finalize_trade(trade["trade_id"],created["settlement_id"])

def test_primary_market_reservation_match_settlement_and_cancel(exchange_env):
    e=exchange_env; engine=e["engine"]
    sell=engine.place_order(e["issuer"],e["market"],e["instrument"],side="SELL",quantity=100,limit_price_minor=200,currency="CAD",order_nonce="sell-100",purpose="AI_TRAINING")
    assert engine.position(e["issuer"],e["instrument"])["available_units"]==400
    assert engine.position(e["issuer"],e["instrument"])["reserved_units"]==100
    with pytest.raises(ValueError,match="insufficient available"):
        engine.place_order(e["issuer"],e["market"],e["instrument"],side="SELL",quantity=450,limit_price_minor=190,currency="CAD",order_nonce="double-sell",purpose="AI_TRAINING")
    buy=engine.place_order(e["buyer"],e["market"],e["instrument"],side="BUY",quantity=60,limit_price_minor=250,currency="CAD",order_nonce="buy-60",purpose="AI_TRAINING")
    assert len(buy["trades"])==1; trade=buy["trades"][0]
    assert trade["price_minor"]==200 and trade["status"]=="PENDING_SETTLEMENT"
    assert engine.position(e["buyer"],e["instrument"])["available_units"]==0
    settled=settle_trade(e,trade,e["buyer"],e["issuer"],"payment-primary")
    assert settled["status"]=="SETTLED" and settled["rights_transferred"] is True
    assert engine.position(e["buyer"],e["instrument"])["available_units"]==60
    assert engine.position(e["issuer"],e["instrument"])["reserved_units"]==40
    snapshot=engine.market_snapshot(e["market"],e["instrument"])
    assert snapshot["last_execution"]["price_minor"]==200 and snapshot["settled_volume"]==60
    engine.cancel_order(e["issuer"],sell["order"]["order_id"])
    assert engine.position(e["issuer"],e["instrument"])["available_units"]==440
    assert engine.position(e["issuer"],e["instrument"])["reserved_units"]==0
    assert engine.verify_invariants()["pass"] is True

def test_secondary_resale_preserves_rights_chain(exchange_env):
    e=exchange_env; engine=e["engine"]
    engine.place_order(e["issuer"],e["market"],e["instrument"],side="SELL",quantity=40,limit_price_minor=100,currency="CAD",order_nonce="primary-sell",purpose="AI_TRAINING")
    primary=engine.place_order(e["buyer"],e["market"],e["instrument"],side="BUY",quantity=40,limit_price_minor=110,currency="CAD",order_nonce="primary-buy",purpose="AI_TRAINING")["trades"][0]
    settle_trade(e,primary,e["buyer"],e["issuer"],"payment-primary-resale")
    engine.place_order(e["buyer"],e["market"],e["instrument"],side="SELL",quantity=20,limit_price_minor=125,currency="CAD",order_nonce="secondary-sell",purpose="AI_TRAINING")
    secondary=engine.place_order(e["buyer2"],e["market"],e["instrument"],side="BUY",quantity=20,limit_price_minor=130,currency="CAD",order_nonce="secondary-buy",purpose="AI_TRAINING")["trades"][0]
    assert secondary["seller_entity_id"]==e["buyer"] and secondary["buyer_entity_id"]==e["buyer2"]
    settle_trade(e,secondary,e["buyer2"],e["buyer"],"payment-secondary")
    assert engine.position(e["buyer"],e["instrument"])["available_units"]==20
    assert engine.position(e["buyer2"],e["instrument"])["available_units"]==20
    assert engine.market_snapshot(e["market"],e["instrument"])["settled_volume"]==60
    assert engine.verify_invariants()["pass"] is True

def test_consumption_retires_circulating_right_units(exchange_env):
    e=exchange_env; engine=e["engine"]
    consumed=engine.consume_right(e["issuer"],e["instrument"],quantity=25,usage_ref="training-run-25")
    assert consumed["status"]=="CONSUMED"
    position=engine.position(e["issuer"],e["instrument"])
    assert position["available_units"]==475 and position["consumed_units"]==25
    with pytest.raises(ValueError,match="duplicate/replayed"):
        engine.consume_right(e["issuer"],e["instrument"],quantity=1,usage_ref="training-run-25")
    assert engine.verify_invariants()["pass"] is True

def test_supply_ceiling_and_missing_policy_fail_closed(exchange_env,tmp_path):
    e=exchange_env; engine=e["engine"]
    with pytest.raises(ValueError,match="authorized instrument supply"):
        engine.issue(e["issuer"],e["instrument"],e["issuer"],quantity=501,issuance_nonce="over-issue")
    no_policy=type(engine)(engine.root.parent,engine.identity,settlement_engine=e["settlement"])
    with pytest.raises(PermissionError,match="classification registry"):
        no_policy.create_instrument(e["issuer"],e["commodity"],symbol="NO-POLICY",rights_class="ACCESS_RIGHT",authorized_units=10,jurisdictional_classification="DATA_COMMODITY_RIGHT")
