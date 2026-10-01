from .config import CLEAN_DAILY_PATH, CLEAN_WEEKLY_PATH
from .ingest import ingest_from_local
from .warehouse import load_star_schema


def main() -> None:
    daily = ingest_from_local(CLEAN_DAILY_PATH)
    weekly = ingest_from_local(CLEAN_WEEKLY_PATH)
    counts = load_star_schema(daily, weekly)
    print(counts)


if __name__ == "__main__":
    main()
