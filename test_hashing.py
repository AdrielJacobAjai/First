import copy

import db
import hashing as h


def build_chain(n=3):
    chain, prev = [], h.GENESIS_HASH
    for i in range(n):
        img = f"image-{i}".encode()
        fields = {"test_id": f"t{i}", "outcome": "POSITIVE", "image_hash": h.hash_image(img)}
        rec = {"fields": fields, "image_hash": fields["image_hash"], "prev_hash": prev,
               "record_hash": h.make_record_hash(fields, prev), "img": img}
        chain.append(rec)
        prev = rec["record_hash"]
    return chain


def verify_all(chain):
    out, prev = [], h.GENESIS_HASH
    for rec in chain:
        out.append(h.verify_record(rec, rec["img"], prev))
        prev = h.recompute_hash(rec)
    return out


def test_clean_chain_passes():
    assert all(all(c.values()) for c in verify_all(build_chain()))


def test_tampering_is_localised():
    chain = build_chain()
    chain[0]["fields"]["outcome"] = "NEGATIVE"
    r = verify_all(chain)
    assert r[0]["record_intact"] is False
    assert r[1]["chain_linked"] is False
    assert all(r[2].values())          # record 3 still links to record 2's unchanged hash


def test_deleting_a_record_breaks_next_link():
    chain = build_chain()
    del chain[1]
    r = verify_all(chain)
    assert r[1]["chain_linked"] is False


def test_image_swap_detected():
    chain = build_chain()
    chain[1]["img"] = b"different photo"
    assert verify_all(chain)[1]["image_intact"] is False


def test_db_chain_and_tamper(tmp_path):
    path = str(tmp_path / "t.db")
    db.init_db(path)
    fields = {k: None for k in db.FIELD_COLUMNS}
    fields.update(operator_id="op", timestamp_utc="2026-01-01T00:00:00Z", gps_status="unavailable",
                  kit_profile="p", outcome="POSITIVE", image_path="x", image_hash="a" * 64)
    ids = [db.insert_record({**fields, "test_id": f"t{i}"}, path) for i in range(3)]
    recs = db.all_records_ordered(path)
    assert recs[0]["prev_hash"] == h.GENESIS_HASH
    assert recs[1]["prev_hash"] == recs[0]["record_hash"]
    assert db.tamper_field(ids[0], path)
    r0, _ = db.get_record(ids[0], path)
    r1, p1 = db.get_record(ids[1], path)
    assert h.recompute_hash(r0) != r0["record_hash"]
    assert h.verify_record(r1, None, db.previous_hash_for(p1))["chain_linked"] is False
