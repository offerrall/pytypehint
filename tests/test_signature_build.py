from dataclasses import dataclass

from pytypehint import signature_of


@dataclass
class Profile:
    name: str = "anon"


def test_signature_build_constructs_kwargs_without_calling_function():
    called = []

    def run(profile: Profile):
        called.append(profile)

    kwargs = signature_of(run).build({"profile": {"name": "neo"}})
    assert kwargs == {"profile": Profile("neo")}
    assert called == []


def test_all_plain_function_kinds_compile_without_execution_policy():
    async def coroutine(n: int = 1):
        return n

    def generator(n: int = 1):
        yield n

    async def async_generator(n: int = 1):
        yield n

    for fn in (coroutine, generator, async_generator):
        assert signature_of(fn).build({}) == {"n": 1}
