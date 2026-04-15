from scripts.database.sqlite_db import init_db


def main():
    init_db()
    print("sqlite ready")


if __name__ == "__main__":
    main()
