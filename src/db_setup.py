from .warehouse import init_db


def main() -> None:
    init_db()
    print("DuckDB warehouse initialized with star schema.")


if __name__ == "__main__":
    main()
