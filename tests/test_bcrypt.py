import pytest

from pkg.crypto import PasswordHasher


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def hasher():
    return PasswordHasher(rounds=4)  # 使用较小的 rounds 加快测试速度


@pytest.mark.anyio
class TestPasswordHasher:

    async def test_hash_password_success(self, hasher):
        password = "test_password_123"
        hashed = await hasher.hash(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != password
        assert hashed.startswith("$2b$")

    async def test_hash_password_empty_raises_error(self, hasher):
        with pytest.raises(ValueError, match="Password cannot be empty"):
            await hasher.hash("")

    async def test_verify_correct_password(self, hasher):
        password = "my_secure_password"
        hashed = await hasher.hash(password)

        is_valid = await hasher.verify(password, hashed)
        assert is_valid is True

    async def test_verify_wrong_password(self, hasher):
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = await hasher.hash(password)

        is_valid = await hasher.verify(wrong_password, hashed)
        assert is_valid is False

    async def test_verify_empty_plain_password(self, hasher):
        hashed = await hasher.hash("some_password")
        is_valid = await hasher.verify("", hashed)
        assert is_valid is False

    async def test_verify_empty_hashed_password(self, hasher):
        is_valid = await hasher.verify("some_password", "")
        assert is_valid is False

    async def test_verify_invalid_hash_format(self, hasher):
        is_valid = await hasher.verify("password", "invalid_hash_format")
        assert is_valid is False

    async def test_custom_rounds(self):
        hasher_4 = PasswordHasher(rounds=4)
        hasher_6 = PasswordHasher(rounds=6)

        assert hasher_4.rounds == 4
        assert hasher_6.rounds == 6

        # 两者都能正常工作
        hashed_4 = await hasher_4.hash("test")
        hashed_6 = await hasher_6.hash("test")

        assert "$04$" in hashed_4
        assert "$06$" in hashed_6
