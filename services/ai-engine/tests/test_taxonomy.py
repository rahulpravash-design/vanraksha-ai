from vanraksha_ai import taxonomy


def test_synonyms_collapse_onto_one_code():
    for phrase in ("not eating", "poor appetite", "reduced food intake", "off feed"):
        assert taxonomy.normalise([phrase]).codes == ["reduced_appetite"]


def test_multiple_signs_in_one_phrase():
    result = taxonomy.normalise(["fever and cough with loose motion"])
    assert set(result.codes) == {"fever", "cough", "diarrhoea"}


def test_negation_is_not_a_positive_finding():
    result = taxonomy.normalise(["no fever", "cough"])
    assert result.codes == ["cough"]
    assert "fever" in result.negated


def test_longer_surface_form_wins():
    # "blood in dung" must not degrade into plain diarrhoea.
    assert taxonomy.normalise(["blood in dung"]).codes == ["bloody_diarrhoea"]


def test_unmatched_text_is_preserved_for_review():
    result = taxonomy.normalise(["fever", "something nobody has a word for"])
    assert result.codes == ["fever"]
    assert result.unmatched == ["something nobody has a word for"]


def test_codes_pass_through_unchanged():
    assert taxonomy.normalise(["oral_lesions"]).codes == ["oral_lesions"]


def test_duplicates_collapse():
    result = taxonomy.normalise(["fever", "high temperature", "bukhar"])
    assert result.codes == ["fever"]


def test_every_term_declares_at_least_one_syndrome():
    for term in taxonomy.TERMS:
        assert term.syndromes, f"{term.code} has no syndromic group"
        assert 0.0 < term.severity_weight <= 1.0


def test_synonyms_are_unique_across_terms():
    seen: dict[str, str] = {}
    for term in taxonomy.TERMS:
        for synonym in term.synonyms:
            assert synonym not in seen, f"'{synonym}' claimed by {seen.get(synonym)} and {term.code}"
            seen[synonym] = term.code


def test_dominant_syndrome_follows_clinical_weight():
    # Vesicular lesions outweigh a mild systemic sign.
    assert taxonomy.dominant_syndrome(["oral_lesions", "lethargy"]) == taxonomy.SYNDROME_VESICULAR


def test_accented_and_punctuated_input():
    assert taxonomy.normalise(["Fever, cough!"]).codes == ["fever", "cough"]


def test_plural_field_text_matches_the_singular_term():
    # Farmers write plurals; the taxonomy lists singulars. A token-boundary
    # match rejected every one of these before the matcher allowed a plural
    # on the final token.
    for phrase, code in [
        ("mouth ulcers", "oral_lesions"),
        ("mouth blisters", "oral_lesions"),
        ("tongue lesions", "oral_lesions"),
        ("vesicles", "oral_lesions"),
        ("foot blisters", "foot_lesions"),
        ("tremors", "convulsions"),
    ]:
        assert taxonomy.normalise([phrase]).codes == [code], phrase


def test_a_plural_inside_a_phrase_also_matches():
    assert taxonomy.normalise(["blisters in mouth"]).codes == ["oral_lesions"]
    assert taxonomy.normalise(["sores between hooves"]).codes == ["foot_lesions"]


def test_plural_matching_does_not_break_the_token_boundary():
    for phrase in ("coughdrop", "feverish", "sorest"):
        result = taxonomy.normalise([phrase])
        assert result.codes == [], phrase
        assert result.unmatched == [phrase], phrase


def test_a_negated_plural_is_still_a_negation():
    result = taxonomy.normalise(["no mouth ulcers"])
    assert result.codes == []
    assert result.negated == ["oral_lesions"]
