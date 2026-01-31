import secrets


def main():
    print("PHONE_ENCRYPTION_KEY=", secrets.token_hex(32))
    print("PHONE_HASH_PEPPER=", secrets.token_hex(32))
    print("SESSION_SECRET=", secrets.token_hex(16))


if __name__ == "__main__":
    main()
