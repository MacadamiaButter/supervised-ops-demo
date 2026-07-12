"""Knowledge-base BM25-ish search over the seeded markdown snippets in
data/kb/ -- these are the real files shipped with the demo, not fixtures,
since the KB content itself is part of the product story."""

from app.kb import search


def test_pet_query_ranks_pet_policy_first():
    results = search("do you allow cats and dogs, pet deposit")
    assert results
    assert results[0]["slug"] == "pet-policy"


def test_emergency_query_surfaces_emergency_contacts_or_sla():
    results = search("gas leak emergency after hours")
    slugs = {r["slug"] for r in results}
    assert "emergency-contacts" in slugs or "maintenance-sla" in slugs


def test_late_fee_query_ranks_rent_payment_first():
    results = search("late fee grace period rent due date")
    assert results
    assert results[0]["slug"] == "rent-payment"


def test_empty_query_returns_no_results():
    assert search("") == []


def test_nonsense_query_returns_no_results():
    assert search("xyzzyplugh quuxfrobnicate zzqvexnitro") == []


def test_top_k_is_respected():
    results = search("policy fee deposit rent", top_k=2)
    assert len(results) <= 2
