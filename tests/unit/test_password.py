from app.core.security.password import hash_password, verify_password


def test_hash_and_verify():
    plain = "SecurePass123!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("WrongPass", hashed)
