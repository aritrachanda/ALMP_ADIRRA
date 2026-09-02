from pathlib import Path

import pytest
import yaml

from core.semantic_types import load_semantic_vocabulary
from core.type_validators import date_range, iso3166, iso4217, lei_checksum, mod97


def test_validators_pass_on_valid_samples():
    assert mod97(["GB82WEST12345698765432", "DE89370400440532013000"]) == 1.0
    assert iso4217(["EUR", "USD", "CHF"]) == 1.0
    assert iso3166(["FI", "GB", "US"]) == 1.0
    assert lei_checksum(["529900T8BM49AURSDO55", "5493001KJTIIGC8Y1R12"]) == 1.0
    assert date_range(["2021-11-05", "05112021", "20211105"]) == 1.0


def test_validators_fail_on_invalid_samples():
    assert mod97(["GB82WEST12345698765432", "GB82WEST12345698765433"]) == 0.5
    assert iso4217(["EUR", "ZZZ"]) == 0.5
    assert iso3166(["FI", "ZZ"]) == 0.5
    assert lei_checksum(["529900T8BM49AURSDO55", "529900T8BM49AURSDO56"]) == 0.5
    assert date_range(["2021-11-05", "not-a-date"]) == 0.5


def test_vocabulary_loads_and_constrains_assignable_types():
    vocabulary = load_semantic_vocabulary()

    assert "natural_iban" in vocabulary.ids
    assert "currency_code" in vocabulary.ids
    assert vocabulary.is_assignable("natural_iban")
    assert vocabulary.is_assignable("unresolved")
    assert not vocabulary.is_assignable("invented_label")
    assert vocabulary.assignable_or_unresolved("invented_label") == "unresolved"


def test_vocabulary_rejects_unknown_validator(tmp_path: Path):
    path = tmp_path / "semantic_types.yaml"
    path.write_text(
        yaml.safe_dump([
            {
                "id": "custom",
                "label": "Custom",
                "category": "identifier",
                "primitive": ["string"],
                "detectors": {"validator": "does_not_exist", "name_tokens": ["custom"]},
                "expectations": [],
            }
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown validator"):
        load_semantic_vocabulary(path)


def test_vocabulary_rejects_reserved_unresolved(tmp_path: Path):
    path = tmp_path / "semantic_types.yaml"
    path.write_text(
        yaml.safe_dump([
            {
                "id": "unresolved",
                "label": "Unresolved",
                "category": "identifier",
                "primitive": ["string"],
                "detectors": {},
                "expectations": [],
            }
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="reserved"):
        load_semantic_vocabulary(path)
