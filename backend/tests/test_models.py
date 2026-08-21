import pytest
from pydantic import ValidationError

from models import BreachReasonArgs, QueryArgs


def test_invalid_region_is_rejected():
    with pytest.raises(ValidationError):
        QueryArgs.model_validate({"region": "LATAM", "max_rows": 10})


def test_max_rows_over_200_is_rejected():
    with pytest.raises(ValidationError):
        QueryArgs.model_validate({"region": "APAC", "max_rows": 201})


def test_empty_breach_reason_ids_are_rejected():
    with pytest.raises(ValidationError):
        BreachReasonArgs.model_validate({"ids": []})
