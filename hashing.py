"""Tamper-evident hash chain (brief section 7). SHA-256, no signing."""
import hashlib
import json

GENESIS_HASH = "0" * 64


def hash_image(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()


def canonical(record_fields: dict) -> str:
    # Deterministic serialisation so the same fields always hash the same way
    return json.dumps(record_fields, sort_keys=True, separators=(",", ":"))


def make_record_hash(record_fields: dict, prev_hash: str) -> str:
    payload = canonical(record_fields) + prev_hash
    return hashlib.sha256(payload.encode()).hexdigest()


def recompute_hash(record):
    return make_record_hash(record["fields"], record["prev_hash"])


def verify_record(record, image_bytes, previous_record_hash):
    """Three independent checks for one record.

    previous_record_hash must be RECOMPUTED from the previous record's current
    contents (GENESIS_HASH for the first record), not read from its stored
    record_hash column; otherwise editing a record would not show up in the
    link to the next one.
    """
    return {
        "image_intact": image_bytes is not None
        and hash_image(image_bytes) == record["image_hash"],
        "record_intact": recompute_hash(record) == record["record_hash"],
        "chain_linked": record["prev_hash"] == previous_record_hash,
    }
