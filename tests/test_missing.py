import copy
import pickle

from pytypehint import MISSING


def test_missing_repr():
    assert repr(MISSING) == "MISSING"


def test_missing_survives_pickle_as_the_singleton():
    assert pickle.loads(pickle.dumps(MISSING)) is MISSING


def test_missing_survives_copy_and_deepcopy_as_the_singleton():
    assert copy.copy(MISSING) is MISSING
    assert copy.deepcopy(MISSING) is MISSING


def test_missing_stays_the_singleton_across_pickle_protocols():
    for proto in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(MISSING, proto)) is MISSING

