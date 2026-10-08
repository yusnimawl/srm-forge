import pytest

from srmapp.references import REFERENCES, make_8_6, make_12_8, make_24_16  # noqa: F401  (tests import the factories from here)
from srmcore.model.design import RadialSRMParams


@pytest.fixture
def srm_8_6() -> RadialSRMParams:
    return make_8_6()


@pytest.fixture
def srm_12_8() -> RadialSRMParams:
    return make_12_8()


@pytest.fixture
def srm_24_16() -> RadialSRMParams:
    return make_24_16()


@pytest.fixture(params=["8/6", "12/8", "24/16"])
def reference_design(request) -> RadialSRMParams:
    return REFERENCES[request.param]()
