from sqlmodel import SQLModel
from src.db.session import engine
import src.db.models  # noqa: F401


def main():
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    main()
