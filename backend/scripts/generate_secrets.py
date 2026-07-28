import hashlib
import secrets


def main() -> None:
    print("Production secrets helper")
    print("-" * 32)
    jwt_secret = secrets.token_urlsafe(48)
    print(f"AUTH_JWT_SECRET={jwt_secret}")
    print()

    password = input("Enter admin password to hash (leave blank to skip): ").strip()
    if password:
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        print(f"ADMIN_PASSWORD_HASH={digest}")
        print("Use ADMIN_PASSWORD_HASH in production and leave ADMIN_PASSWORD empty.")
    else:
        print("Skipped password hashing.")


if __name__ == "__main__":
    main()
